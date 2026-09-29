# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""The full order lifecycle: place, read the book, modify, cancel.

    python examples/order_management.py

Also shows the recovery path for an uncertain write — a HighApiError with
status=0 on a placement means the outcome is unknown, and the order book must
be checked before anything is retried.
"""

from __future__ import annotations

from high_openapi import HighApiError

from scripts.high_helpers import confirm, describe_error, get_client, market_is_open
from scripts.resolve_symbol import resolve
from scripts.trade_logger import TradeLogger
from scripts.validate_order import validate

SYMBOL = "reliance"
QUANTITY = 10
ENTRY = 2400.0          # deliberately away from the market, so it rests
REPRICE = 2410.0


def show_book(high) -> None:
    book = high.orders.list()
    rows = list(book.root if hasattr(book, "root") else book)
    print(f"\nOrder book — {len(rows)} order(s)")
    for row in rows:
        print(f"  {row}")


def main() -> None:
    log = TradeLogger()

    with get_client() as high:
        if not market_is_open(high):
            print("Market is closed.")
            return

        scrip = resolve(SYMBOL)

        # --- 1. place ----------------------------------------------------
        body = {
            **scrip.order_identity(),
            "tradeSide": "B",
            "productType": "DELIVERY",
            "flavor": "REGULAR",
            "orderType": "LIMIT",
            "validity": "DAY",
            "quantity": QUANTITY,
            "price": ENTRY,
            "isAMO": False,
        }

        verdict = validate(body, lot_size=scrip.lot_size)
        if not verdict.ok:
            for error in verdict.errors:
                print(f"  - {error}")
            return

        log.proposed(body, notional=QUANTITY * ENTRY)
        if not confirm(verdict.preview):
            log.declined(body)
            return

        try:
            placed = high.orders.place(body)
        except HighApiError as error:
            log.failed(body, error)
            print(describe_error(error))
            if error.status == 0:
                # Uncertain: the request may or may not have reached HIGH.
                # Never blind-retry a write — look first.
                print("\nOutcome uncertain. Checking the order book before anything else.")
                show_book(high)
            raise

        log.placed(body, placed)
        print(f"\nPlaced: {placed}")

        order_id = getattr(placed, "orderId", None) or getattr(placed, "order_id", None)
        if not order_id:
            print("No orderId in the response — inspect it before going further.")
            return

        # --- 2. read -----------------------------------------------------
        show_book(high)
        print(f"\nThis order: {high.orders.get(str(order_id))}")

        # --- 3. modify ---------------------------------------------------
        modification = {**body, "orderId": str(order_id), "price": REPRICE}
        modify_verdict = validate(modification, lot_size=scrip.lot_size)

        if modify_verdict.ok and confirm(f"Reprice to {REPRICE}?\n{modify_verdict.preview}"):
            try:
                modified = high.orders.modify(modification)
                log.modified(modification, modified)
                print(f"Modified: {modified}")
            except HighApiError as error:
                log.failed(modification, error)
                print(describe_error(error))

        # --- 4. cancel ---------------------------------------------------
        if confirm(f"\nCancel order {order_id}?"):
            try:
                cancelled = high.orders.cancel(str(order_id))
                log.cancelled(str(order_id), cancelled)
                print(f"Cancelled: {cancelled}")
            except HighApiError as error:
                print(describe_error(error))

        # --- 5. what actually filled -------------------------------------
        print(f"\nFills for this order: {high.orders.trades_for(str(order_id))}")
        print(f"\nJournal: {log.summary()}")


if __name__ == "__main__":
    main()
