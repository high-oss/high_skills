# Option chain and expiries

| Task | Call | HTTP |
|---|---|---|
| Option chain | `high.scrips.option_chain(body)` | `POST /scrips/option-chain` |
| Expiry list | `high.scrips.expiries(symbol, type)` | `GET /scrips/{symbol}/{type}/expiries` |

## Expiries

```python
expiries = high.scrips.expiries("NIFTY", "options")
nearest = expiries[0]
```

`type` is `futures` or `options`, case-insensitive. The symbol is the
underlying — a stock's trading symbol (`RELIANCE-EQ`), an index (`NIFTY`), or
any F&O contract on it.

Always read the expiry list rather than computing "last Thursday of the
month". Expiry conventions change, and holidays shift them.

## The chain

```python
chain = high.scrips.option_chain({
    "tradingSymbol": "NIFTY",
    "expiry": "2026-09-29",      # omit for the nearest expiry
    "strikeCount": 10,           # omit for the full chain
})
```

| Field | Notes |
|---|---|
| `tradingSymbol` | Required. The underlying, an index, or a contract on it |
| `expiry` | `YYYY-MM-DD`. Omit for the nearest |
| `strikeCount` | Strikes **each side** of at-the-money, so up to `2 × strikeCount + 1` rows |

`strikeCount` is per side. `strikeCount=10` returns about 21 rows, not 10.
Near the edges of a chain you get fewer, because the strikes do not exist.

Omitting `strikeCount` returns the full chain — for a liquid index that is
hundreds of rows. Ask for what you need.

For MCX commodities the chain is built on the **nearest future**, not spot.

## Reading the chain

Each row carries the call and put side for one strike: last price, bid and
ask, open interest, volume, implied volatility, and the Greeks.

```python
for row in chain.rows if hasattr(chain, "rows") else chain:
    print(row)
```

Inspect one row before writing code against it — field names come from the
response, and guessing them is how a script silently computes zeros.

## Finding at-the-money

The chain is already centred on ATM when you pass `strikeCount`, so the
middle row is your reference. To be explicit:

```python
spot = high.scrips.quotes({"symbols": ["NIFTY"]})["NIFTY"].LTP
atm = min(strikes, key=lambda strike: abs(strike - spot))
```

Round to the strike interval — 50 for Nifty, 100 for Bank Nifty — rather than
assuming the nearest listed strike is the conventional ATM.

## Ordering an option

The chain gives you strikes and prices, not order identifiers. To place, get
the contract's trading symbol from the instrument list:

```python
from scripts.resolve_symbol import resolve_all

matches = resolve_all("NIFTY", category="derivatives", limit=200)
contract = next(
    m for m in matches
    if m.expiry == target_expiry and m.option_type == "CE" and m.strike_price == atm
)

body = {
    "tradingSymbol": contract.tradingSymbol,
    "tradeSide": "B",
    "productType": "INTRADAY",
    "flavor": "REGULAR",
    "orderType": "LIMIT",
    "validity": "DAY",
    "quantity": contract.lot_size,      # one lot, not 1
    "price": premium,
    "isAMO": False,
}
```

**Quantity is in units, and must be a multiple of `lot_size`.** "Buy one lot"
means `quantity = lot_size`. `validate_order.py` catches the error and names
the nearest valid quantity.

## Multi-leg

Price the whole structure as one basket, or the margin will be badly
overstated:

```python
margin = high.orders.margin([leg_one, leg_two, leg_three, leg_four])
```

Place legs in an order that never leaves the account more exposed than the
finished structure: **buy the protective legs first, sell the short legs
after**. If a later leg fails, you are long protection you did not want,
rather than short naked options.

Confirm the whole structure once, then place. Do not ask for confirmation
four times — the user cannot meaningfully approve leg three in isolation.

See [options-analysis-patterns.md](options-analysis-patterns.md) and
[examples/iron_condor.py](../examples/iron_condor.py).
