# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""A four-leg iron condor: build, analyse, margin, confirm once, place.

    python examples/iron_condor.py

Demonstrates the multi-leg discipline:

  * quantity is a multiple of lot_size, per leg
  * the whole basket is margined in ONE orders.margin() call, so the hedges
    are netted — leg-by-leg margining overstates the requirement badly
  * maximum loss is computed and shown BEFORE anything is placed
  * ONE confirmation for the whole structure, not four
  * long (protective) legs go first, short legs after — a partial failure
    then leaves the account over-hedged rather than short naked options
"""

from __future__ import annotations

from high_openapi import HighApiError

from scripts.high_helpers import confirm, describe_error, get_client, market_is_open
from scripts.resolve_symbol import resolve_all
from scripts.trade_logger import TradeLogger
from scripts.validate_order import validate

UNDERLYING = "NIFTY"
LOTS = 1
SHORT_WIDTH = 200       # points from spot to the short strikes
WING_WIDTH = 200        # points from short strike to its protective long


def nearest_expiry_contracts(high):
    contracts = [
        scrip
        for scrip in resolve_all(UNDERLYING, category="derivatives", limit=2000, high=high)
        if scrip.expiry is not None and scrip.option_type in ("CE", "PE")
    ]
    if not contracts:
        raise LookupError(f"No option contracts found for {UNDERLYING!r}.")
    nearest = min(scrip.expiry for scrip in contracts)
    return [scrip for scrip in contracts if scrip.expiry == nearest], nearest


def pick(contracts, option_type, strike):
    candidates = [c for c in contracts if c.option_type == option_type and c.strike_price is not None]
    if not candidates:
        raise LookupError(f"No {option_type} contracts available.")
    return min(candidates, key=lambda c: abs(c.strike_price - strike))


def main() -> None:
    log = TradeLogger()

    with get_client() as high:
        if not market_is_open(high):
            print("Market is closed.")
            return

        contracts, expiry = nearest_expiry_contracts(high)

        quotes = high.scrips.quotes({"symbols": [UNDERLYING]})
        quote = quotes.get(UNDERLYING)
        spot = getattr(quote, "LTP", None) if quote else None
        if not spot:
            print(f"No live price for {UNDERLYING}; cannot centre the condor.")
            return

        short_call = pick(contracts, "CE", spot + SHORT_WIDTH)
        long_call = pick(contracts, "CE", spot + SHORT_WIDTH + WING_WIDTH)
        short_put = pick(contracts, "PE", spot - SHORT_WIDTH)
        long_put = pick(contracts, "PE", spot - SHORT_WIDTH - WING_WIDTH)

        lot_size = short_call.lot_size
        quantity = LOTS * lot_size

        # Longs first, shorts after.
        legs = [
            ("B", long_put, "long put (wing)"),
            ("B", long_call, "long call (wing)"),
            ("S", short_put, "short put"),
            ("S", short_call, "short call"),
        ]

        print(f"\n  IRON CONDOR on {UNDERLYING} @ {spot}, expiry {expiry}")
        print(f"  {'-' * 56}")
        for side, contract, label in legs:
            print(f"  {side}  {contract.tradingSymbol:<28} {label}")
        print(f"  {'-' * 56}")
        print(f"  {LOTS} lot(s) = {quantity} units per leg (lot size {lot_size})")

        bodies = []
        for side, contract, _ in legs:
            body = {
                **contract.order_identity(),
                "tradeSide": side,
                "productType": "INTRADAY",
                "flavor": "REGULAR",
                "orderType": "MARKET",
                "validity": "DAY",
                "quantity": quantity,
                "isAMO": False,
            }
            verdict = validate(body, lot_size=lot_size)
            if not verdict.ok:
                print(f"\n  Leg {contract.tradingSymbol} is not valid:")
                for error in verdict.errors:
                    print(f"    - {error}")
                return
            bodies.append(body)

        # The whole basket in one call — this is the point.
        try:
            margin = high.orders.margin([
                {
                    **contract.order_identity(),
                    "tradeSide": side,
                    "productType": "INTRADAY",
                    "quantity": quantity,
                }
                for side, contract, _ in legs
            ])
        except HighApiError as error:
            print(describe_error(error))
            raise

        # Wings cap the loss: width between short and long, less net credit.
        max_loss_points = WING_WIDTH
        max_loss = max_loss_points * quantity

        preview = (
            f"\n  PLACE THIS 4-LEG STRUCTURE\n"
            f"  {'-' * 56}\n"
            + "\n".join(
                f"    {side}  {quantity:>5}  {contract.tradingSymbol:<28} {label}"
                for side, contract, label in legs
            )
            + f"\n  {'-' * 56}\n"
            f"    margin (basket, netted)   {margin}\n"
            f"    max loss (before credit)  Rs. {max_loss:,.2f}\n"
            f"    profits if {UNDERLYING} stays between "
            f"{short_put.strike_price} and {short_call.strike_price}\n"
            f"  {'-' * 56}\n"
            f"    Risk is DEFINED by the wings. All four legs must fill for that\n"
            f"    to hold — a partial fill is a different, riskier position.\n"
        )

        if not confirm(preview):
            for body in bodies:
                log.declined(body, reason="structure declined")
            print("Not placed.")
            return

        for body in bodies:
            log.proposed(body)
            try:
                result = high.orders.place(body)
                log.placed(body, result)
                print(f"  placed {body['tradeSide']} {body.get('tradingSymbol')}: {result}")
            except HighApiError as error:
                log.failed(body, error)
                print(describe_error(error))
                print(
                    "\n  STOPPED PART-WAY. The structure is incomplete and its risk is\n"
                    "  NOT what was previewed. Review the order book and positions now."
                )
                raise

        print(f"\n  All four legs placed. Journal: {log.summary()}")


if __name__ == "__main__":
    main()
