# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Composable helpers every example in this skill imports.

Credentials are read from the environment, never from arguments and never
from a file in the working tree:

    HIGH_API_KEY        the developer-portal API key
    HIGH_ACCESS_TOKEN   the bearer token derived from it
    HIGH_ENVIRONMENT    "sandbox" (default here) or "production"
    HIGH_CLIENT_ID      only needed to mint a fresh access token

The skill defaults to sandbox. Production is opt-in, either by setting
HIGH_ENVIRONMENT or by passing environment="production" explicitly. An
explicit value also suppresses a stray HIGH_BASE_URL left in a shell profile,
which is why get_client() always passes one.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from high_openapi import AsyncHighClient, HighApiError, HighClient

# Sandbox unless told otherwise — see the skill's safety rules.
DEFAULT_ENVIRONMENT = "sandbox"

_CONFIG_CACHE: Optional[Dict[str, Any]] = None


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    """Read config.json if the user created one from config.json.example.

    Absent, this returns the built-in defaults, so nothing here requires the
    file to exist. The caps it carries (max_order_value, max_order_quantity)
    are what validate_order.py enforces.
    """
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and path is None:
        return _CONFIG_CACHE

    defaults: Dict[str, Any] = {
        "environment": DEFAULT_ENVIRONMENT,
        "default_exchange_segment": "NSE",
        "default_product_type": "DELIVERY",
        "default_flavor": "REGULAR",
        "default_order_type": "LIMIT",
        "risk_warnings": True,
        "max_order_value": 50_000,
        "max_order_quantity": 1_000,
        "allow_market_orders": False,
        "allow_amo": False,
    }

    candidate = Path(path) if path else Path.cwd() / "config.json"
    if candidate.is_file():
        try:
            defaults.update(json.loads(candidate.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            # A malformed config must not silently disable the caps.
            pass

    if path is None:
        _CONFIG_CACHE = defaults
    return defaults


def _environment() -> str:
    return os.environ.get("HIGH_ENVIRONMENT") or str(load_config().get("environment", DEFAULT_ENVIRONMENT))


def _credentials() -> Dict[str, str]:
    credentials: Dict[str, str] = {}
    api_key = os.environ.get("HIGH_API_KEY")
    access_token = os.environ.get("HIGH_ACCESS_TOKEN")
    if api_key:
        credentials["api_key"] = api_key
    if access_token:
        credentials["access_token"] = access_token
    return credentials


def get_client(**overrides: Any) -> HighClient:
    """A sync client built from the environment.

    Close it, or use it as a context manager. Overrides are passed straight
    through, so get_client(environment="production") is the explicit
    production opt-in.
    """
    options: Dict[str, Any] = {"environment": _environment()}
    options.update(_credentials())
    options.update(overrides)
    return HighClient(options)


def get_async_client(**overrides: Any) -> AsyncHighClient:
    """The async equivalent of get_client()."""
    options: Dict[str, Any] = {"environment": _environment()}
    options.update(_credentials())
    options.update(overrides)
    return AsyncHighClient(options)


def refresh_access_token(client_id: Optional[str] = None, t_otp: Optional[str] = None) -> str:
    """Mint a fresh access token from the API key and a TOTP code.

    The /auth/* operations authenticate with the API key, not the bearer
    token, so this works even once the current access token has expired.
    Export the result as HIGH_ACCESS_TOKEN for subsequent calls.
    """
    client_id = client_id or os.environ.get("HIGH_CLIENT_ID")
    if not client_id:
        raise RuntimeError("Set HIGH_CLIENT_ID, or pass client_id, to mint an access token.")
    if not t_otp:
        raise RuntimeError("A TOTP code is required. Read it from your authenticator app.")

    with get_client() as high:
        token = high.auth.generate_access_token(client_id, t_otp)

    value = getattr(token, "accessToken", None) or getattr(token, "access_token", None)
    if not value:
        raise RuntimeError(f"No access token in the response: {token!r}")
    return str(value)


def describe_error(error: HighApiError) -> str:
    """Render a HighApiError the way a human can act on.

    request_id is the field HIGH support asks for. messages is plural because
    the validation pipeline returns every failure at once — printing only the
    first hides the rest.
    """
    parts = [f"HIGH API error: status={error.status}"]
    if error.code:
        parts.append(f"code={error.code}")
    if error.request_id:
        parts.append(f"request_id={error.request_id}")
    line = " ".join(parts)

    for message in error.messages or []:
        line += f"\n  - {message}"
    if not error.messages and str(error):
        line += f"\n  - {error}"
    if error.status == 0:
        line += "\n  (status=0 means a transport failure or timeout, not an API rejection.)"
    return line


def confirm(preview: str, *, assume_yes: bool = False) -> bool:
    """The confirmation gate every write path in this skill goes through.

    assume_yes exists for non-interactive runs and is never the default. An
    agent must show the preview and wait for the user, not pass assume_yes on
    the user's behalf.
    """
    print(preview)
    if assume_yes:
        print("\n[auto-confirmed]")
        return True
    try:
        answer = input("\nPlace this order? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return False
    return answer in {"y", "yes"}


def market_is_open(high: HighClient) -> bool:
    """True when the exchange is open. Safety rule 7 depends on this."""
    status = high.market.status()
    raw = getattr(status, "exchangeStatus", None) or getattr(status, "status", None)
    return str(raw).upper() in {"OPEN", "NORMAL", "TRUE"}


def chunked(items: Iterable[Any], size: int) -> Iterator[List[Any]]:
    """Batch an iterable — quotes and OHLC take many symbols per call, but
    not unlimited ones."""
    batch: List[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


__all__ = [
    "DEFAULT_ENVIRONMENT",
    "chunked",
    "confirm",
    "describe_error",
    "get_async_client",
    "get_client",
    "load_config",
    "market_is_open",
    "refresh_access_token",
]
