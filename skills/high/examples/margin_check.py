# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Can this order be afforded — margin, charges and available funds.

    python examples/margin_check.py

Places nothing. Run it before any sizeable order: a rejection for
insufficient funds is avoidable and looks like a bug to the user.

The key detail is that orders.margin takes a LIST. It prices the basket as a
whole and nets offsetting legs — margining leg by leg reports several times
the true requirement for anything hedged.
"""

from __future__ import annotations

from high_openapi import HighApiError

from scripts.high_helpers import describe_error, get_client
from scripts.resolve_symbol import resolve

SYMBOL = "reliance"
QUANTITY = 100
PRICE = 2450.0
PRODUCT = "DELIVERY"


def main() -> None:
    with get_client() as high:
        scrip = resolve(SYMBOL)

        try:
            funds = high.portfolio.funds()

            # A list, always — even for one leg.
            margin = high.orders.margin([
                {
                    **scrip.order_identity(),
                    "tradeSide": "B",
                    "productType": PRODUCT,
                    "quantity": QUANTITY,
                    "price": PRICE,
                }
            ])

            charges = high.orders.charges({
                **scrip.order_identity(),
                "tradeSide": "B",
                "productType": PRODUCT,
                "quantity": QUANTITY,
                "price": PRICE,
            })
        except HighApiError as error:
            print(describe_error(error))
            raise

        notional = QUANTITY * PRICE
        available = getattr(funds, "availableBalance", None)

        print(f"\n  {SYMBOL.upper()} — BUY {QUANTITY} @ {PRICE} ({PRODUCT})")
        print(f"  {'-' * 46}")
        print(f"  notional    Rs. {notional:,.2f}")
        print(f"  margin      {margin}")
        print(f"  charges     {charges}")
        print(f"  available   {available}")
        print(f"  {'-' * 46}")

        if isinstance(available, (int, float)) and available < notional:
            print(
                f"\n  Available funds are below the notional. Compare against the\n"
                f"  margin figure rather than the notional for a leveraged product."
            )

        # A hedged basket, margined as one request — the reason margin()
        # takes a list at all.
        print("\n  A hedged basket is margined as ONE call, not leg by leg:")
        print("    high.orders.margin([short_leg, long_leg])")
        print("  Leg-by-leg margining ignores the hedge and overstates the requirement.")


if __name__ == "__main__":
    main()
