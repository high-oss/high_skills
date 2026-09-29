# Orders

Everything HIGH's order surface does. One `orders.place` call covers all four
flavors — `REGULAR`, `BO`, `CO`, `GTT` — because the flavor is a field on the
request, not a separate endpoint.

## The call surface

| Task | Call | HTTP |
|---|---|---|
| Place | `high.orders.place(body)` | `POST /orders` |
| Modify | `high.orders.modify(body)` | `PATCH /orders` |
| Cancel | `high.orders.cancel(order_id)` | `DELETE /orders/{orderId}` |
| Order book | `high.orders.list()` | `GET /orders/list` |
| One order | `high.orders.get(order_id)` | `GET /orders/{orderId}` |
| Trade book | `high.orders.trades()` | `GET /orders/trades` |
| Trades for an order | `high.orders.trades_for(order_id)` | `GET /orders/{orderId}/trades` |
| Charges estimate | `high.orders.charges(body)` | `POST /orders/charges` |
| Margin estimate | `high.orders.margin([body, ...])` | `POST /orders/margin` |

Place, modify, cancel and the position exits require the API key's **static
IP to be pinned**. Reads do not.

## The request body

```python
body = {
    # identity — exactly one of the two paths
    "tradingSymbol": "RELIANCE-EQ",
    # or: "exchangeSegment": "NSE", "scripCode": "2885",

    "tradeSide": "B",             # B | S
    "productType": "DELIVERY",    # INTRADAY | DELIVERY | MTF
    "flavor": "REGULAR",          # REGULAR | BO | CO | GTT
    "orderType": "LIMIT",         # LIMIT | MARKET | STOP_LOSS | STOP_LOSS_MARKET
    "validity": "DAY",            # DAY | IOC | YEAR
    "quantity": 10,
    "price": 2450,
    "isAMO": False,
}
```

### Every field

| Field | Type | Notes |
|---|---|---|
| `tradingSymbol` | string | Required unless `exchangeSegment` + `scripCode` are sent |
| `exchangeSegment` | string | Required unless `tradingSymbol` is sent. `NSE`, `BSE`, `NSEFO`, `BSEFO`, `NSECDSFO`, `BSECDSFO`, `MCXFO` |
| `scripCode` | string | Digits only, as a **string**: `"2885"`, not `2885` |
| `tradeSide` | string | `B` or `S`. Not `BUY`/`SELL` |
| `productType` | string | `INTRADAY`, `DELIVERY`, `MTF`. There is no `CNC` |
| `flavor` | string | `REGULAR`, `BO`, `CO`, `GTT` |
| `orderType` | string | `LIMIT`, `MARKET`, `STOP_LOSS`, `STOP_LOSS_MARKET` |
| `validity` | string | `DAY`, `IOC`, `YEAR` |
| `quantity` | number | Greater than 0. A multiple of `lot_size` for F&O |
| `disclosedQuantity` | number | `REGULAR` + `DAY` only. 0 or ≤ `quantity` |
| `price` | number | Required for `LIMIT` and `STOP_LOSS` |
| `triggerPrice` | number | Required for `GTT` and stop-loss order types |
| `targetPrice` | number | `BO` only |
| `stoplossPrice` | number | `BO` and `CO` only |
| `trailSL` | number | Trailing stop-loss, in ticks |
| `legIndicator` | string | `BO`/`CO` only: `ENTRY_LEG`, `STOP_LOSS_LEG`, `TARGET_LEG`. Must be absent otherwise |
| `isAMO` | boolean | After-market order |
| `isSlice` | boolean | Split a large order into child orders |

## Product × flavor

The server rejects illegal pairs with
`flavor must be one of .../... for ... orders`.

| `productType` | Permitted `flavor` | Why |
|---|---|---|
| `INTRADAY` | `REGULAR`, `BO`, `CO` | Bracket and cover square off the same day |
| `DELIVERY` | `REGULAR`, `GTT` | A resting trigger only makes sense on a held position |
| `MTF` | `REGULAR`, `GTT` | Same |

So: **BO and CO are intraday-only. GTT is delivery/MTF-only.**

## REGULAR

The plain order. Nothing conditional beyond the order type's own price.

```python
from scripts.high_helpers import confirm, get_client
from scripts.resolve_symbol import resolve
from scripts.validate_order import validate

high = get_client()
scrip = resolve("reliance")

body = {
    "tradingSymbol": scrip.tradingSymbol,
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
if verdict.ok and confirm(verdict.preview):
    print(high.orders.place(body))
```

`disclosedQuantity` is the one field unique to this flavor, and only with
`validity="DAY"`. It shows part of the quantity on the book.

## BO — bracket

Entry, target and stop-loss in one instruction. `INTRADAY` only.

```python
body = {
    "tradingSymbol": scrip.tradingSymbol,
    "tradeSide": "B",
    "productType": "INTRADAY",
    "flavor": "BO",
    "orderType": "LIMIT",
    "validity": "DAY",
    "quantity": 10,
    "price": 2450,
    "targetPrice": 2500,        # required
    "stoplossPrice": 2400,      # required
    "trailSL": 5,               # optional, in ticks
    "legIndicator": "ENTRY_LEG",
    "isAMO": False,
}
```

Direction matters and the API will not save you from an inverted bracket:

- Buy: `stoplossPrice` **below** `price`, `targetPrice` **above** it.
- Sell: the reverse.

`validate_order.py` checks both.

### Legs

A bracket becomes three orders at the exchange. `legIndicator` says which one
a request refers to:

| Value | Meaning |
|---|---|
| `ENTRY_LEG` | The entry. What you send to open the bracket |
| `TARGET_LEG` | The profit leg. Used when modifying the target |
| `STOP_LOSS_LEG` | The stop leg. Used when modifying the stop |

To move a target on a live bracket, `modify` the order with
`legIndicator="TARGET_LEG"` and the new `targetPrice`.

## CO — cover

Entry plus a compulsory stop-loss. No target. `INTRADAY` only.

```python
body = {
    "tradingSymbol": scrip.tradingSymbol,
    "tradeSide": "B",
    "productType": "INTRADAY",
    "flavor": "CO",
    "orderType": "LIMIT",
    "validity": "DAY",
    "quantity": 10,
    "price": 2450,
    "stoplossPrice": 2400,      # required
    "legIndicator": "ENTRY_LEG",
    "isAMO": False,
}
```

Sending `targetPrice` on a cover order is an error — that is what makes it a
bracket instead.

## GTT — good till triggered

A resting order that fires when the market reaches `triggerPrice`.
`DELIVERY` or `MTF`, and it rests with `validity="YEAR"`.

```python
body = {
    "tradingSymbol": scrip.tradingSymbol,
    "tradeSide": "B",
    "productType": "DELIVERY",
    "flavor": "GTT",
    "orderType": "LIMIT",
    "validity": "YEAR",
    "quantity": 10,
    "price": 2400,              # the limit once triggered
    "triggerPrice": 2400,       # required — what wakes the order
    "isAMO": False,
}
```

`triggerPrice` is the level being watched; `price` is the limit placed once it
fires. They are commonly equal, but need not be — a trigger slightly above
the limit gives the order room to fill on a fast move.

A GTT is cancelled like any other order, with its `orderId`.

## Modify

`PATCH /orders` takes the same body plus `orderId`. Send the fields being
changed along with the identifying ones.

```python
body = {
    "orderId": "250512000012345",
    "tradingSymbol": scrip.tradingSymbol,
    "tradeSide": "B",
    "productType": "INTRADAY",
    "flavor": "BO",
    "orderType": "LIMIT",
    "validity": "DAY",
    "quantity": 10,
    "price": 2455,
    "legIndicator": "ENTRY_LEG",
    "isAMO": False,
}
result = high.orders.modify(body)
```

Confirm before modifying, exactly as for placing. A modify on a partially
filled order applies to the unfilled remainder.

## Cancel

```python
result = high.orders.cancel("250512000012345")
```

Cancelling a bracket's entry leg cancels the bracket. Cancelling a filled
order fails — check the book first.

## Reading the book

```python
book = high.orders.list()                       # every order today
order = high.orders.get("250512000012345")      # one order
trades = high.orders.trades()                   # every fill today
fills = high.orders.trades_for("250512000012345")
```

An order's status tells you whether it is still live. Poll the book rather
than assuming a placement succeeded — the datafeed carries no order updates.

## Charges and margin

Both take an order-shaped body and place nothing.

```python
charges = high.orders.charges({
    "tradingSymbol": "RELIANCE-EQ",
    "quantity": 100,
    "tradeSide": "B",
    "productType": "DELIVERY",
    "price": 2450,
})

margin = high.orders.margin([
    {"tradingSymbol": "RELIANCE-EQ", "quantity": 50, "tradeSide": "B", "productType": "INTRADAY"},
    {"tradingSymbol": "NIFTY-26SEP-FUT", "quantity": 75, "tradeSide": "S", "productType": "INTRADAY"},
])
```

`margin` takes a **list** — it prices a basket, netting offsetting legs. A
multi-leg strategy should be margined as one basket, not leg by leg, or the
number will be far too high. See
[options-analysis-patterns.md](options-analysis-patterns.md).

## Slicing

`isSlice: True` asks HIGH to break an oversized order into children below the
exchange freeze limit. Prefer it to hand-rolled loops: the children are
tracked together.

## Failure modes

| Message | Cause |
|---|---|
| `flavor must be one of REGULAR/GTT for DELIVERY/MTF orders` | BO or CO on a delivery product |
| `flavor must be one of BO/CO/REGULAR for INTRADAY orders` | GTT on intraday |
| `legIndicator is only applicable for BO/CO orders` | Leg sent on a REGULAR or GTT order |
| `quantity should be greater than 0` | Missing or zero quantity |
| `disclosedQuantity must be 0 or less than or equal to quantity` | Disclosed exceeds total |
| `403` on an otherwise valid order | Static IP not pinned — see [auth-and-credentials.md](auth-and-credentials.md) |

Full list: [error-codes.md](error-codes.md).
