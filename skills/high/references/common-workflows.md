# Common workflows

Multi-step patterns that combine several calls. Each assumes
`from scripts.high_helpers import confirm, describe_error, get_client`.

## 1. Place an order properly, end to end

The canonical shape. Every write path in this skill follows it.

```python
from scripts.high_helpers import confirm, get_client, market_is_open
from scripts.resolve_symbol import resolve
from scripts.trade_logger import TradeLogger
from scripts.validate_order import validate
from high_openapi import HighApiError

log = TradeLogger()

with get_client() as high:
    if not market_is_open(high):
        print("Market is closed. An order now needs isAMO=True — confirm that intent first.")
        raise SystemExit(1)

    scrip = resolve("reliance")
    body = {
        **scrip.order_identity(),
        "tradeSide": "B",
        "productType": "DELIVERY",
        "flavor": "REGULAR",
        "orderType": "LIMIT",
        "validity": "DAY",
        "quantity": 10,
        "price": 2450,
        "isAMO": False,
    }

    verdict = validate(body, lot_size=scrip.lot_size)
    if not verdict.ok:
        for error in verdict.errors:
            print(f"  - {error}")
        raise SystemExit(1)

    log.proposed(body)
    if not confirm(verdict.preview):
        log.declined(body)
        raise SystemExit(0)

    try:
        result = high.orders.place(body)
        log.placed(body, result)
        print(result)
    except HighApiError as error:
        log.failed(body, error)
        raise
```

Resolve, build, validate, journal, preview, confirm, place, journal again.
Skipping the validate step turns a readable message into a 400; skipping the
confirm step breaks safety rule 1.

## 2. Daily roll-up

"How did today go."

```python
with get_client() as high:
    orders = high.orders.list()
    trades = high.orders.trades()
    positions = high.portfolio.positions()
    holdings = high.portfolio.holdings()
    funds = high.portfolio.funds()
```

Report in this order: funds available, open positions with unrealised P&L,
fills today, orders still working, then holdings. Working orders matter most
— an order the user forgot is live is the actionable item.

Do not re-price everything from `quotes` to compute P&L. The broker's figures
account for average cost and corporate actions.

## 3. Affordability check before a large order

```python
with get_client() as high:
    funds = high.portfolio.funds()
    margin = high.orders.margin([leg])
    charges = high.orders.charges(charge_body)
```

Show all three in the preview when notional exceeds the configured
`max_order_value`. A rejection for insufficient funds is avoidable.

## 4. Square off a single position safely

```python
with get_client() as high:
    positions = high.portfolio.positions()
    rows = list(positions.root if hasattr(positions, "root") else positions)

    target = next((row for row in rows if getattr(row, "tradingSymbol", None) == "RELIANCE-EQ"), None)
    if target is None:
        print("No open position in RELIANCE-EQ.")
        raise SystemExit(0)

    body = {
        "tradingSymbol": "RELIANCE-EQ",
        "tradeSide": "B",
        "productType": "INTRADAY",
        "quantity": 10,
        "flavor": "REGULAR",     # the flavor the position was OPENED with
    }
    if confirm(f"Exit this position?\n  {target}"):
        print(high.portfolio.exit_position(body))
```

The `flavor` must match how the position was opened. Exiting a bracket
position as `REGULAR` can leave an orphaned stop-loss working against you.

## 5. Watch a list of symbols

```python
from scripts.high_helpers import chunked

with get_client() as high:
    prices = {}
    for batch in chunked(symbols, 50):
        prices.update(high.scrips.quotes({"symbols": batch}))

    for symbol, quote in prices.items():
        print(f"{symbol:<16} {quote.LTP}")
```

For anything continuous, use the datafeed rather than looping this — polling
is what triggers `429`. See [live-feed.md](live-feed.md).

## 6. Trend over a window

```python
import time

now = int(time.time())
candles = high.scrips.historical({
    "tradingSymbol": "RELIANCE-EQ",
    "interval": "1D",
    "fromTime": now - 180 * 24 * 3600,
    "toTime": now,
})
```

Epoch **seconds**. And avoid `3M` / `6M` / `1Y` — build them from `1M`
candles. See [market-data.md](market-data.md).

## 7. Convert intraday to delivery before the square-off

```python
body = {
    "tradingSymbol": "RELIANCE-EQ",
    "tradeSide": "B",
    "quantity": 10,
    "sourceProductType": "INTRADAY",
    "targetProductType": "DELIVERY",
}
if confirm("Carry this position overnight as delivery?"):
    print(high.portfolio.convert_position(body))
```

Converting to delivery needs the full cash and changes the account's
overnight risk. Always confirm.

## 8. Rebalance toward target weights

1. Read `holdings` and `funds`.
2. Price every holding plus every intended new position with one batched
   `quotes` call.
3. Compute current weights, diff against targets, and turn the diff into a
   list of orders.
4. Validate every order **before** placing any of them.
5. Show the whole basket in one preview, with total buy value, total sell
   value and net cash effect.
6. Confirm once.
7. Place sells before buys, so the cash exists.
8. Journal each result; stop on the first failure and report what did and did
   not execute.

Never place a rebalance order by order with a confirmation each time — the
user cannot meaningfully approve step seven of twelve. One basket, one
decision.

## 9. Recovering from an uncertain write

A `HighApiError` with `status=0` on a placement means the outcome is unknown.

```python
except HighApiError as error:
    if error.status == 0:
        print("Uncertain outcome — checking the order book before anything else.")
        print(high.orders.list())
        raise
```

Never blind-retry a write. Check first.
