# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""A cover order — entry plus a compulsory stop-loss, no target.

    python examples/cover_order.py

CO is INTRADAY only. It needs stoplossPrice and legIndicator, and must NOT
carry targetPrice — sending one is what makes an order a bracket instead.
"""

from __future__ import annotations

from high_openapi import HighApiError

from scripts.high_helpers import confirm, describe_error, get_client, market_is_open
from scripts.resolve_symbol import resolve
from scripts.trade_logger import TradeLogger
from scripts.validate_order import validate

SYMBOL = "reliance"
QUANTITY = 10
ENTRY = 2450.0
STOP_PCT = 0.01        # 1% below entry


def main() -> None:
    log = TradeLogger()

    with get_client() as high:
        if not market_is_open(high):
            print("Market is closed. A cover order is intraday — it cannot be an AMO.")
            return

        scrip = resolve(SYMBOL)

        body = {
            **scrip.order_identity(),
            "tradeSide": "B",
            "productType": "INTRADAY",              # CO is intraday only
            "flavor": "CO",
            "orderType": "LIMIT",
            "validity": "DAY",
            "quantity": QUANTITY,
            "price": ENTRY,
            "stoplossPrice": round(ENTRY * (1 - STOP_PCT), 1),
            "legIndicator": "ENTRY_LEG",
            "isAMO": False,
            # No targetPrice — that would make this a bracket order.
        }

        max_loss = (ENTRY - body["stoplossPrice"]) * QUANTITY

        verdict = validate(body, lot_size=scrip.lot_size)
        if not verdict.ok:
            print("\nThe order is not valid:")
            for error in verdict.errors:
                print(f"  - {error}")
            return

        preview = (
            f"{verdict.preview}\n"
            f"  max loss if stopped   Rs. {max_loss:,.2f}\n"
            f"  upside                open — a cover order has no target\n"
        )

        log.proposed(body, notional=QUANTITY * ENTRY)
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
        print("\nExit this position with flavor='CO' so the stop-loss leg is cancelled with it.")


if __name__ == "__main__":
    main()
