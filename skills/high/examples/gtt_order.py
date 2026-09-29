# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""A GTT — an order that rests until the market reaches a trigger.

    python examples/gtt_order.py

GTT is DELIVERY or MTF only, needs triggerPrice, and rests with
validity="YEAR". Because it rests rather than executing now, it is the one
order flavor that does not need the market to be open.
"""

from __future__ import annotations

from high_openapi import HighApiError

from scripts.high_helpers import confirm, describe_error, get_client
from scripts.resolve_symbol import resolve
from scripts.trade_logger import TradeLogger
from scripts.validate_order import validate

SYMBOL = "tcs"
QUANTITY = 5
TRIGGER = 3000.0
LIMIT = 3000.0          # the limit placed once the trigger fires


def main() -> None:
    log = TradeLogger()

    with get_client() as high:
        scrip = resolve(SYMBOL)

        quotes = high.scrips.quotes({"symbols": [scrip.tradingSymbol]})
        quote = quotes.get(scrip.tradingSymbol)
        last = getattr(quote, "LTP", None) if quote else None
        if last:
            direction = "falls to" if TRIGGER < last else "rises to"
            print(f"{scrip.tradingSymbol} is at {last}. This GTT fires if it {direction} {TRIGGER}.")

        body = {
            **scrip.order_identity(),
            "tradeSide": "B",
            "productType": "DELIVERY",              # GTT is DELIVERY/MTF only
            "flavor": "GTT",
            "orderType": "LIMIT",
            "validity": "YEAR",                     # how a GTT rests
            "quantity": QUANTITY,
            "price": LIMIT,                         # the limit once triggered
            "triggerPrice": TRIGGER,                # what wakes the order
            "isAMO": False,
        }

        verdict = validate(body, lot_size=scrip.lot_size)
        if not verdict.ok:
            print("\nThe order is not valid:")
            for error in verdict.errors:
                print(f"  - {error}")
            return

        preview = (
            f"{verdict.preview}\n"
            f"  This order rests until {scrip.tradingSymbol} reaches {TRIGGER}.\n"
            f"  It will still be live tomorrow. Cancel it with orders.cancel(orderId).\n"
        )

        log.proposed(body, notional=QUANTITY * LIMIT)
        if not confirm(preview):
            log.declined(body)
            return

        try:
            result = high.orders.place(body)
        except HighApiError as error:
            log.failed(body, error)
            print(describe_error(error))
            raise

        log.placed(body, result)
        print(f"\nPlaced: {result}")
        print(
            "\nA resting GTT is an order, not a position — cancel it through\n"
            "orders.cancel(), not through portfolio.exit_position()."
        )


if __name__ == "__main__":
    main()
