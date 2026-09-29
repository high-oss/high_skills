# Portfolio

Positions, holdings, funds, product conversion, and exits.

| Task | Call | HTTP |
|---|---|---|
| Open positions | `high.portfolio.positions()` | `GET /portfolio/positions` |
| Holdings | `high.portfolio.holdings()` | `GET /portfolio/holdings` |
| Funds | `high.portfolio.funds()` | `GET /portfolio/funds` |
| Convert a position | `high.portfolio.convert_position(body)` | `PATCH /portfolio/positions/convert` |
| Exit one position | `high.portfolio.exit_position(body)` | `DELETE /portfolio/positions/exit` |
| Exit every position | `high.portfolio.exit_all_positions()` | `DELETE /portfolio/positions/exit/all` |

Reads need no static IP. The three write paths do.

## Positions vs holdings

They are not the same thing and conflating them produces wrong P&L.

- **Positions** are today's open exposure — intraday, F&O, and anything not
  yet settled into the demat account. They square off or roll.
- **Holdings** are settled delivery stock sitting in the demat account. They
  persist across days.

A day trader's whole book is positions. A long-term investor's is holdings.
Most accounts have both, and "my portfolio" usually means both.

```python
from scripts.high_helpers import get_client

with get_client() as high:
    positions = high.portfolio.positions()
    holdings = high.portfolio.holdings()
    funds = high.portfolio.funds()
```

## Funds

```python
funds = high.portfolio.funds()
print(funds.availableBalance)
```

Available balance is what can be committed to a new order — it already nets
out margin blocked by open positions. Check it before placing, not after a
rejection.

For "can I afford this order", pair it with `orders.margin`:

```python
required = high.orders.margin([
    {"tradingSymbol": "RELIANCE-EQ", "quantity": 100, "tradeSide": "B", "productType": "DELIVERY"},
])
```

See [funds.md](funds.md).

## Converting a position

Moves an open position between product types — intraday to delivery, most
commonly, to carry a trade overnight rather than let it square off.

```python
body = {
    "tradingSymbol": "RELIANCE-EQ",
    # or: "exchangeSegment": "NSE", "scripCode": "2885",
    "tradeSide": "B",
    "quantity": 10,
    "sourceProductType": "INTRADAY",
    "targetProductType": "DELIVERY",
    "clientOrderNo": "...",        # from the position, when present
}
result = high.portfolio.convert_position(body)
```

Converting to `DELIVERY` requires the full cash. Converting the other way
frees margin but exposes the position to the intraday square-off.

Confirm before converting — it changes the account's overnight risk.

## Exiting one position

```python
body = {
    "tradingSymbol": "RELIANCE-EQ",
    "tradeSide": "B",              # the side of the position being closed
    "productType": "INTRADAY",
    "quantity": 10,
    "flavor": "REGULAR",           # REGULAR | BO | CO
}
result = high.portfolio.exit_position(body)
```

`flavor` here is the flavor the **original** position was opened with — the
square-off flavors are `REGULAR`, `BO`, `CO`. A bracket position must be
exited as `BO` so its remaining legs are cancelled with it; exiting it as
`REGULAR` can leave an orphaned stop-loss working against you.

`GTT` is not a square-off flavor: a GTT that has not triggered is an order,
cancelled through `orders.cancel`, not a position.

## Exiting everything

```python
result = high.portfolio.exit_all_positions()
```

The most destructive call on the surface. It closes every open position at
market. **Always** show the positions first, count them, and require an
explicit confirmation:

```python
from scripts.high_helpers import confirm, get_client

with get_client() as high:
    positions = high.portfolio.positions()
    rows = list(positions.root if hasattr(positions, "root") else positions)

    if not rows:
        print("No open positions.")
    else:
        preview = "\n".join(f"  {row}" for row in rows)
        if confirm(f"\nExit ALL {len(rows)} positions at market?\n{preview}"):
            print(high.portfolio.exit_all_positions())
```

Never call it as a first response to "close my positions" without showing
what that means. Never call it in a loop or a retry.

## Computing P&L

Positions and holdings each carry their own P&L fields. To roll the whole
book up:

1. Sum realised and unrealised P&L across positions.
2. Add holdings' unrealised P&L against average cost.
3. Subtract the day's charges if you want a net figure — `orders.charges`
   estimates them per order, and `orders.trades()` lists the day's fills.

Do not derive P&L by re-pricing everything from `scrips.quotes` unless a
field is genuinely missing; the broker's own figures account for corporate
actions and average cost in ways a quote does not.

See [common-workflows.md](common-workflows.md) for the full daily roll-up.
