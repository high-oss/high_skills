# Options analysis patterns

Analysis built on `scrips.option_chain` and `scrips.expiries`. Nothing here
places an order on its own — combine with [orders.md](orders.md).

## Getting a chain to work with

```python
from scripts.high_helpers import get_client

with get_client() as high:
    expiries = high.scrips.expiries("NIFTY", "options")
    chain = high.scrips.option_chain({
        "tradingSymbol": "NIFTY",
        "expiry": expiries[0],
        "strikeCount": 15,
    })
```

Inspect one row before computing anything — field names come from the
response, and guessing them produces a script that silently returns zeros.

## Put-call ratio

Open-interest PCR, the standard sentiment read:

```python
put_oi = sum(row.put.openInterest for row in rows)
call_oi = sum(row.call.openInterest for row in rows)
pcr = put_oi / call_oi if call_oi else float("inf")
```

Above 1 means more puts open than calls — conventionally read as bearish
positioning, and often as a contrarian bullish signal. Below 0.7 the reverse.
Compute it over a **bounded strike window** around ATM: including far
out-of-the-money strikes with stale open interest distorts it badly.

Volume PCR is the intraday-sentiment variant, same formula on volume.

## Max pain

The strike at which the total value of expiring options is smallest — where
option writers lose least.

```python
def max_pain(rows):
    strikes = [row.strikePrice for row in rows]
    pain = {}
    for settle in strikes:
        total = 0
        for row in rows:
            total += max(0, settle - row.strikePrice) * row.call.openInterest
            total += max(0, row.strikePrice - settle) * row.put.openInterest
        pain[settle] = total
    return min(pain, key=pain.get)
```

A heuristic about where open interest clusters, not a forecast. It matters
more near expiry and very little a month out. Never present it as a
prediction.

## Support and resistance from open interest

The strike with the largest call open interest often acts as resistance; the
largest put open interest as support — writers defend those levels.

```python
resistance = max(rows, key=lambda row: row.call.openInterest).strikePrice
support = max(rows, key=lambda row: row.put.openInterest).strikePrice
```

Watch the **change** in open interest rather than the level. Fresh writing at
a strike is information; open interest that has sat there a fortnight is not.

## IV skew

```python
skew = [(row.strikePrice, row.call.impliedVolatility, row.put.impliedVolatility) for row in rows]
```

Index options normally show a downside skew: out-of-the-money puts carry
higher IV than equidistant calls, because crash protection is bid. A skew
that flattens or inverts is a genuine change in positioning.

Compare IV against its own recent range, not against an absolute number. "IV
is 14" means nothing without knowing whether 14 is high or low for that
underlying.

## Payoff at expiry

```python
def payoff(legs, spot):
    """legs: (kind, side, strike, premium, quantity)"""
    total = 0.0
    for kind, side, strike, premium, quantity in legs:
        if kind == "CE":
            intrinsic = max(0.0, spot - strike)
        else:
            intrinsic = max(0.0, strike - spot)
        value = intrinsic - premium if side == "B" else premium - intrinsic
        total += value * quantity
    return total
```

Evaluate across a spot range to find breakevens, maximum profit and maximum
loss. **Always show maximum loss before placing a multi-leg structure** — for
an undefined-risk structure, say so in those words rather than printing a
large number.

Expiry payoff ignores time value before expiry. A position can be deep
underwater mid-life and still expire at maximum profit.

## Common structures

| Structure | Legs | Risk |
|---|---|---|
| Covered call | Long stock + short OTM call | Capped upside |
| Protective put | Long stock + long OTM put | Defined downside, costs premium |
| Bull call spread | Long lower CE + short higher CE | Defined both ways |
| Bear put spread | Long higher PE + short lower PE | Defined both ways |
| Iron condor | Short OTM call + long further call + short OTM put + long further put | Defined; profits in a range |
| Straddle | Long CE + long PE, same strike | Defined loss, needs a big move |
| Strangle | Long OTM CE + long OTM PE | Cheaper straddle, needs more move |

Short options without a long leg are **undefined risk**. Never build one
without saying so explicitly and getting an explicit acknowledgement.

## Margining a structure

```python
margin = high.orders.margin([leg_one, leg_two, leg_three, leg_four])
```

One basket. `orders.margin` nets offsetting legs; margining leg by leg
reports several times the true requirement and will make a perfectly
affordable spread look impossible.

## Placing a structure

1. Resolve every contract from the `derivatives` instrument list — strike,
   expiry and option type, not by spelling the symbol.
2. Quantity in units, a multiple of `lot_size`.
3. Validate every leg before placing any.
4. Margin the basket.
5. Show payoff, maximum loss, margin and total premium in **one** preview.
6. Confirm **once**.
7. Place protective (long) legs first, short legs after — a partial failure
   then leaves you over-hedged, not naked.
8. Journal each fill; stop and report on the first failure.

See [examples/iron_condor.py](../examples/iron_condor.py).
