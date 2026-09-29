# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Fetch an option chain and read the at-the-money region.

    python examples/fetch_option_chain.py
    python examples/fetch_option_chain.py RELIANCE-EQ

Reads only. strikeCount is per SIDE of at-the-money, so strikeCount=10
returns about 21 rows, not 10.
"""

from __future__ import annotations

import sys

from high_openapi import HighApiError

from scripts.high_helpers import describe_error, get_client

UNDERLYING = "NIFTY"
STRIKE_COUNT = 10


def field(row, *names, default=None):
    """Chain field names come from the response — probe rather than assume."""
    for name in names:
        if hasattr(row, name):
            return getattr(row, name)
        if isinstance(row, dict) and name in row:
            return row[name]
    return default


def main(argv) -> None:
    underlying = argv[0] if argv else UNDERLYING

    with get_client() as high:
        try:
            expiries = high.scrips.expiries(underlying, "options")
        except HighApiError as error:
            print(describe_error(error))
            raise

        if not expiries:
            print(f"No option expiries for {underlying!r}.")
            return

        print(f"Expiries for {underlying}:")
        for expiry in expiries[:6]:
            print(f"  {expiry}")

        nearest = expiries[0]
        print(f"\nFetching the chain for {nearest} (+/- {STRIKE_COUNT} strikes)...")

        try:
            chain = high.scrips.option_chain({
                "tradingSymbol": underlying,
                "expiry": str(nearest),
                "strikeCount": STRIKE_COUNT,
            })
        except HighApiError as error:
            print(describe_error(error))
            raise

        rows = list(field(chain, "rows", "root", default=chain) or [])
        if not rows:
            print("The chain came back empty.")
            return

        print(f"\n{len(rows)} strike(s) — roughly 2 x {STRIKE_COUNT} + 1\n")
        print(f"  {'strike':>10}  {'call LTP':>10} {'call OI':>12}  {'put LTP':>10} {'put OI':>12}")

        total_call_oi = 0
        total_put_oi = 0

        for row in rows:
            strike = field(row, "strikePrice", "strike")
            call = field(row, "call", "CE", default={})
            put = field(row, "put", "PE", default={})

            call_ltp = field(call, "LTP", "lastPrice", default="-")
            put_ltp = field(put, "LTP", "lastPrice", default="-")
            call_oi = field(call, "openInterest", "OI", default=0) or 0
            put_oi = field(put, "openInterest", "OI", default=0) or 0

            total_call_oi += call_oi
            total_put_oi += put_oi

            print(f"  {str(strike):>10}  {str(call_ltp):>10} {call_oi:>12}  {str(put_ltp):>10} {put_oi:>12}")

        if total_call_oi:
            print(f"\n  PCR (open interest, this window): {total_put_oi / total_call_oi:.2f}")
            print("  Computed over a bounded strike window — far OTM strikes distort it.")

        print(
            "\n  The chain gives strikes and prices, not order identifiers. To place,\n"
            "  resolve the contract from the derivatives instrument list and send\n"
            "  quantity as a multiple of its lot size."
        )


if __name__ == "__main__":
    main(sys.argv[1:])
