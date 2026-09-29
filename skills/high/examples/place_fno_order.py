# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""An F&O order, with the lot-size validation that makes it legal.

    python examples/place_fno_order.py

The point of this example is quantity. "One lot of Nifty" means
quantity = lot_size, not quantity = 1, and an F&O quantity that is not a
whole multiple of the lot size is rejected.
"""

from __future__ import annotations

from high_openapi import HighApiError

from scripts.high_helpers import confirm, describe_error, get_client, market_is_open
from scripts.resolve_symbol import resolve_all
from scripts.trade_logger import TradeLogger
from scripts.validate_order import validate

UNDERLYING = "NIFTY"
LOTS = 1
LIMIT_PRICE = 120.0


def pick_contract(high):
    """The nearest-expiry contract on the underlying.

    Derivatives are one row per strike and expiry, so filter the instrument
    list rather than trying to spell the trading symbol.
    """
    matches = [
        scrip
        for scrip in resolve_all(UNDERLYING, category="derivatives", limit=500, high=high)
        if scrip.expiry is not None
    ]
    if not matches:
        raise LookupError(f"No derivative contracts found for {UNDERLYING!r}.")
    return min(matches, key=lambda scrip: scrip.expiry)


def main() -> None:
    log = TradeLogger()

    with get_client() as high:
        if not market_is_open(high):
            print("Market is closed.")
            return

        contract = pick_contract(high)
        quantity = LOTS * contract.lot_size

        print(f"Contract  {contract.tradingSymbol}")
        print(f"Expiry    {contract.expiry}")
        print(f"Lot size  {contract.lot_size}")
        print(f"Quantity  {LOTS} lot(s) = {quantity} units")

        body = {
            **contract.order_identity(),
            "tradeSide": "B",
            "productType": "INTRADAY",     # F&O is never DELIVERY
            "flavor": "REGULAR",
            "orderType": "LIMIT",
            "validity": "DAY",
            "quantity": quantity,
            "price": LIMIT_PRICE,
            "isAMO": False,
        }

        verdict = validate(body, lot_size=contract.lot_size)
        if not verdict.ok:
            print("\nThe order is not valid:")
            for error in verdict.errors:
                print(f"  - {error}")
            return

        margin = high.orders.margin([
            {
                **contract.order_identity(),
                "tradeSide": "B",
                "productType": "INTRADAY",
                "quantity": quantity,
            }
        ])
        print(f"\nMargin required: {margin}")

        log.proposed(body, notional=quantity * LIMIT_PRICE)
        if not confirm(verdict.preview):
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


if __name__ == "__main__":
    main()
