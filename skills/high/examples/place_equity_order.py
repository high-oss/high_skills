# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""A plain delivery equity order, end to end.

    HIGH_ENVIRONMENT=sandbox HIGH_API_KEY=... HIGH_ACCESS_TOKEN=... \
        python examples/place_equity_order.py

Resolve, build, validate, journal, preview, confirm, place. Every write path
in this skill follows this shape — start here.
"""

from __future__ import annotations

from high_openapi import HighApiError

from scripts.high_helpers import confirm, describe_error, get_client, market_is_open
from scripts.resolve_symbol import resolve
from scripts.trade_logger import TradeLogger
from scripts.validate_order import validate

SYMBOL = "reliance"
QUANTITY = 10
LIMIT_PRICE = 2450


def main() -> None:
    log = TradeLogger()

    with get_client() as high:
        if not market_is_open(high):
            print("Market is closed. Placing now would need isAMO=True — confirm that intent first.")
            return

        scrip = resolve(SYMBOL)
        print(f"Resolved {SYMBOL!r} -> {scrip.tradingSymbol} ({scrip.exchange}@{scrip.scripCode})")

        body = {
            **scrip.order_identity(),
            "tradeSide": "B",
            "productType": "DELIVERY",
            "flavor": "REGULAR",
            "orderType": "LIMIT",
            "validity": "DAY",
            "quantity": QUANTITY,
            "price": LIMIT_PRICE,
            "isAMO": False,
        }

        verdict = validate(body, lot_size=scrip.lot_size)
        if not verdict.ok:
            print("\nThe order is not valid:")
            for error in verdict.errors:
                print(f"  - {error}")
            return

        log.proposed(body, notional=QUANTITY * LIMIT_PRICE)
        if not confirm(verdict.preview):
            log.declined(body)
            print("Not placed.")
            return

        try:
            result = high.orders.place(body)
        except HighApiError as error:
            log.failed(body, error)
            print(describe_error(error))
            raise

        log.placed(body, result)
        print(f"\nPlaced: {result}")


if __name__ == "__main__":
    main()
