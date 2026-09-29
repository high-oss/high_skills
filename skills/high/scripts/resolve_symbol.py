# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Human name to HIGH's identifiers — all of them, from one lookup.

HIGH takes different identifiers on different surfaces, and the datafeed
fails *silently* when given the wrong one:

    orders          tradingSymbol, or exchangeSegment + scripCode
    quotes / ohlc   tradingSymbol, or scripKeys
    datafeed        scrip_key, i.e. EXCHANGE@scripCode

So a resolved scrip carries every form, plus the lot_size and price_tick a
caller needs to size an order and build a legal limit price. Never construct
an identifier by hand.

Usage:

    from scripts.resolve_symbol import resolve, resolve_all

    scrip = resolve("reliance")
    print(scrip.tradingSymbol, scrip.exchange, scrip.scripCode)

    for match in resolve_all("nifty", category="derivatives", limit=5):
        print(match.tradingSymbol, match.expiry, match.strike_price)

Runs with no credentials at all — the instrument list is public.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Optional

from high_openapi import HighClient

try:  # when imported as part of the skill
    from .high_helpers import get_client
except ImportError:  # when run directly as a script
    from high_helpers import get_client  # type: ignore[no-redef]


@dataclass(frozen=True)
class Scrip:
    """Every identifier HIGH's surfaces ask for, resolved together."""

    tradingSymbol: str
    exchange: str
    scripCode: str
    scrip_key: str
    symbol: str
    name: str
    segment: str
    lot_size: int
    price_tick: int
    has_fno: bool
    isin: Optional[str] = None
    expiry: Optional[date] = None
    option_type: Optional[str] = None
    strike_price: Optional[float] = None
    underlying_symbol: Optional[str] = None

    def order_identity(self, *, by_code: bool = False) -> dict:
        """The identifier fields for an order body.

        An order must supply exactly one of the two accepted paths. Default
        is the trading symbol, which is the readable one; by_code=True gives
        the exchangeSegment + scripCode pair instead.
        """
        if by_code:
            return {"exchangeSegment": self.exchange, "scripCode": self.scripCode}
        return {"tradingSymbol": self.tradingSymbol}


def _score(row, needle: str) -> Optional[int]:
    """Lower is better; None means no match.

    Exact identifiers beat exact names, which beat prefixes, which beat
    substrings — so "reliance" finds RELIANCE-EQ rather than
    RELIANCERETAIL-EQ or a Reliance option 40 strikes out.
    """
    trading_symbol = (row.high_trading_symbol or "").lower()
    symbol = (row.symbol or "").lower()
    name = (row.name or "").lower()

    if needle in {trading_symbol, symbol}:
        return 0
    if needle == name:
        return 1
    if symbol.startswith(needle) or trading_symbol.startswith(needle):
        return 2
    if name.startswith(needle):
        return 3
    if needle in name:
        return 4
    if needle in trading_symbol:
        return 5
    return None


def _to_scrip(row) -> Scrip:
    return Scrip(
        tradingSymbol=row.high_trading_symbol,
        exchange=row.exchange,
        scripCode=str(row.scrip_code),
        scrip_key=row.scrip_key,
        symbol=row.symbol,
        name=row.name,
        segment=row.segment,
        lot_size=row.lot_size,
        price_tick=row.price_tick,
        has_fno=bool(row.has_fno),
        isin=row.isin,
        expiry=row.expiry,
        option_type=row.option_type,
        strike_price=row.strike_price,
        underlying_symbol=row.underlying_symbol,
    )


def resolve_all(
    query: str,
    *,
    category: str = "equity",
    exchange: Optional[str] = None,
    limit: int = 10,
    high: Optional[HighClient] = None,
) -> List[Scrip]:
    """Every instrument matching `query`, best match first.

    category is one of: all, equity, derivatives, commodity, etfs. Prefer the
    narrowest one — "all" is a 14 MB download, "equity" a small fraction of
    that.
    """
    needle = query.strip().lower()
    if not needle:
        return []

    owned = high is None
    client = high or get_client()
    scored: List[tuple] = []
    try:
        for row in client.instruments.stream(category):  # type: ignore[arg-type]
            if exchange and row.exchange != exchange:
                continue
            rank = _score(row, needle)
            if rank is not None:
                scored.append((rank, row.high_trading_symbol, row))
    finally:
        if owned:
            client.close()

    scored.sort(key=lambda item: (item[0], item[1]))
    return [_to_scrip(row) for _, _, row in scored[:limit]]


def resolve(
    query: str,
    *,
    category: str = "equity",
    exchange: Optional[str] = None,
    high: Optional[HighClient] = None,
) -> Scrip:
    """The single best match. Raises when nothing matches."""
    matches = resolve_all(query, category=category, exchange=exchange, limit=1, high=high)
    if not matches:
        raise LookupError(
            f"No instrument matched {query!r} in category {category!r}. "
            f"Try category='all', or check the spelling against the instrument list."
        )
    return matches[0]


def scrip_keys(scrips: Iterable[Scrip]) -> List[str]:
    """Datafeed subscription keys for a set of resolved scrips."""
    return [scrip.scrip_key for scrip in scrips]


def _main(argv: List[str]) -> int:
    if not argv:
        print("usage: python resolve_symbol.py <query> [category]", file=sys.stderr)
        return 2

    query = argv[0]
    category = argv[1] if len(argv) > 1 else "equity"

    matches = resolve_all(query, category=category)
    if not matches:
        print(f"No match for {query!r} in {category!r}.", file=sys.stderr)
        return 1

    print(f"{'tradingSymbol':<24} {'exch':<6} {'scripCode':<10} {'scrip_key':<16} {'lot':<6} name")
    for scrip in matches:
        print(
            f"{scrip.tradingSymbol:<24} {scrip.exchange:<6} {scrip.scripCode:<10} "
            f"{scrip.scrip_key:<16} {scrip.lot_size:<6} {scrip.name}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
