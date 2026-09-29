# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""An append-only local journal of what the agent did.

The order book records what the exchange accepted. It does not record what
was proposed and declined, what the agent believed the notional was, or which
session placed it. A multi-step run that half-succeeds is much easier to
unpick with a local trail.

Entries are JSON Lines, one object per line, so the file is appendable,
greppable and never rewritten. Default location is ./high-trades.jsonl,
overridable with HIGH_TRADE_LOG.

    from scripts.trade_logger import TradeLogger

    log = TradeLogger()
    log.proposed(body, notional=24_500)
    log.placed(body, result)
    ...
    for entry in log.read():
        print(entry["event"], entry["tradingSymbol"])
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

DEFAULT_LOG = "high-trades.jsonl"

# Never journal anything that could carry a credential.
_REDACT = {"api_key", "apiKey", "access_token", "accessToken", "authorization", "t_otp", "tOtp"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***" if k in _REDACT else _clean(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class TradeLogger:
    """A journal file. Construction never fails on a missing directory."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = Path(path or os.environ.get("HIGH_TRADE_LOG") or DEFAULT_LOG)
        if self.path.parent and not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- writing ----------------------------------------------------------

    def _write(self, event: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        entry: Dict[str, Any] = {"at": _now(), "event": event}
        entry.update(_clean(payload))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def _order_fields(self, body: Dict[str, Any]) -> Dict[str, Any]:
        keys = (
            "tradeSide", "tradingSymbol", "exchangeSegment", "scripCode",
            "productType", "flavor", "orderType", "validity", "quantity",
            "price", "triggerPrice", "targetPrice", "stoplossPrice",
        )
        return {key: body[key] for key in keys if key in body}

    def proposed(self, body: Dict[str, Any], *, notional: Optional[float] = None) -> Dict[str, Any]:
        """An order the agent built and showed, before any confirmation."""
        return self._write("proposed", {**self._order_fields(body), "notional": notional})

    def declined(self, body: Dict[str, Any], *, reason: str = "user declined") -> Dict[str, Any]:
        """A proposal the user or a validator stopped."""
        return self._write("declined", {**self._order_fields(body), "reason": reason})

    def placed(self, body: Dict[str, Any], result: Any = None) -> Dict[str, Any]:
        """An order the API accepted."""
        return self._write("placed", {**self._order_fields(body), "result": _clean(result)})

    def modified(self, body: Dict[str, Any], result: Any = None) -> Dict[str, Any]:
        return self._write("modified", {**self._order_fields(body), "result": _clean(result)})

    def cancelled(self, order_id: str, result: Any = None) -> Dict[str, Any]:
        return self._write("cancelled", {"orderId": order_id, "result": _clean(result)})

    def failed(self, body: Dict[str, Any], error: Any) -> Dict[str, Any]:
        """A call the API rejected. request_id is what support will ask for."""
        detail: Dict[str, Any] = {"error": str(error)}
        for attribute in ("status", "code", "request_id"):
            if hasattr(error, attribute):
                detail[attribute] = getattr(error, attribute)
        if getattr(error, "messages", None):
            detail["messages"] = list(error.messages)
        return self._write("failed", {**self._order_fields(body), **detail})

    def note(self, message: str, **extra: Any) -> Dict[str, Any]:
        """Anything else worth recording in sequence."""
        return self._write("note", {"message": message, **extra})

    # -- reading ----------------------------------------------------------

    def read(self, *, event: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        """Replay the journal. A malformed line is skipped, not fatal."""
        if not self.path.is_file():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event is None or entry.get("event") == event:
                    yield entry

    def summary(self) -> Dict[str, int]:
        """Counts per event — the quick end-of-session read."""
        counts: Dict[str, int] = {}
        for entry in self.read():
            key = str(entry.get("event", "unknown"))
            counts[key] = counts.get(key, 0) + 1
        return counts


def _main(argv: List[str]) -> int:
    log = TradeLogger()
    if not log.path.is_file():
        print(f"No journal at {log.path}.")
        return 0

    if argv and argv[0] == "--summary":
        for event, count in sorted(log.summary().items()):
            print(f"{event:<12} {count}")
        return 0

    for entry in log.read():
        symbol = entry.get("tradingSymbol") or entry.get("orderId") or ""
        print(f"{entry.get('at'):<26} {entry.get('event'):<10} {symbol}")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
