# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Set a stop-loss and a target on an open position, and read the last session.

    python examples/position_stoploss_target.py

Places REAL exit orders after an explicit confirmation. Needs a pinned static
IP. The calls are never retried, so a failure is reported, not repeated.

Quantity is read from the live position by the API, so none is sent.
"""

from __future__ import annotations

from high_openapi import HighApiError

from scripts.high_helpers import confirm, describe_error, get_client
from scripts.resolve_symbol import resolve

SYMBOL = "reliance"
PRODUCT = "INTRADAY"
FLAVOR = "REGULAR"        # REGULAR | BO | CO | GTT
TRIGGER_PRICE = 2400.0    # stop-loss: below LTP for a long, above for a short
TARGET_PRICE = 2600.0     # target: above LTP for a long, below for a short


def main() -> None:
    with get_client() as high:
        scrip = resolve(SYMBOL)

        try:
            # Last trading session only; no fromTime/toTime needed.
            candles = high.scrips.intraday({**scrip.order_identity(), "interval": "5m"})
            closes = getattr(candles, "close", None) or []
            print(f"\n  last session: {len(closes)} five-minute candles")
            if closes:
                print(f"  last close:   {closes[-1]}")

            preview = (
                f"\n  {SYMBOL.upper()} ({PRODUCT}, {FLAVOR})"
                f"\n  stop-loss trigger  {TRIGGER_PRICE}"
                f"\n  target limit       {TARGET_PRICE}"
            )
            if not confirm(preview):
                print("Cancelled.")
                return

            base = {**scrip.order_identity(), "flavor": FLAVOR, "productType": PRODUCT}
            stop = high.portfolio.set_stoploss({**base, "triggerPrice": TRIGGER_PRICE})
            target = high.portfolio.set_target({**base, "targetPrice": TARGET_PRICE})
        except HighApiError as error:
            print(describe_error(error))
            raise

        for result in (stop, target):
            print(
                f"  {result.leg}: {result.action} order {result.orderId or '(none)'} "
                f"qty {result.quantity} @ {result.price}"
            )


if __name__ == "__main__":
    main()
