# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""A bracket order — entry, target and stop-loss in one instruction.

    python examples/bracket_order.py

BO is INTRADAY only. It needs targetPrice, stoplossPrice and legIndicator,
and the direction of the two prices relative to entry matters: for a buy the
stop sits below and the target above. validate_order.py checks both.
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
TARGET_PCT = 0.02      # 2% above entry
STOP_PCT = 0.01        # 1% below entry
TRAIL_TICKS = 5


def main() -> None:
    log = TradeLogger()

    with get_client() as high:
        if not market_is_open(high):
            print("Market is closed. A bracket order is intraday — it cannot be an AMO.")
            return

        scrip = resolve(SYMBOL)

        body = {
            **scrip.order_identity(),
            "tradeSide": "B",
            "productType": "INTRADAY",              # BO is intraday only
            "flavor": "BO",
            "orderType": "LIMIT",
            "validity": "DAY",
            "quantity": QUANTITY,
            "price": ENTRY,
            "targetPrice": round(ENTRY * (1 + TARGET_PCT), 1),
            "stoplossPrice": round(ENTRY * (1 - STOP_PCT), 1),
            "trailSL": TRAIL_TICKS,
            "legIndicator": "ENTRY_LEG",            # BO/CO only
            "isAMO": False,
        }

        risk = (ENTRY - body["stoplossPrice"]) * QUANTITY
        reward = (body["targetPrice"] - ENTRY) * QUANTITY

        verdict = validate(body, lot_size=scrip.lot_size)
        if not verdict.ok:
            print("\nThe order is not valid:")
            for error in verdict.errors:
                print(f"  - {error}")
            return

        preview = (
            f"{verdict.preview}\n"
            f"  risk if stopped   Rs. {risk:,.2f}\n"
            f"  gain if target    Rs. {reward:,.2f}\n"
            f"  reward : risk     {reward / risk:.2f} : 1\n"
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
        print(
            "\nThe bracket is now three orders at the exchange. To move the target,\n"
            "modify with legIndicator='TARGET_LEG'; to move the stop, 'STOP_LOSS_LEG'.\n"
            "Exiting the position must use flavor='BO' so the remaining legs go with it."
        )


if __name__ == "__main__":
    main()
