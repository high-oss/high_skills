# Funds, charges and margin

Three related questions: what is available, what will this cost, and what
will it block.

| Task | Call |
|---|---|
| Available cash and margin | `high.portfolio.funds()` |
| Charges for an order | `high.orders.charges(body)` |
| Margin for a basket | `high.orders.margin([body, ...])` |

## Funds

```python
from scripts.high_helpers import get_client

with get_client() as high:
    funds = high.portfolio.funds()
    print(f"Available: {funds.availableBalance}")
```

`availableBalance` already nets out margin blocked by open positions, so it
is the number to compare an intended order's margin against — not the
account's total value.

## Charges

Brokerage, exchange fees, STT, stamp duty and GST for a **hypothetical**
order. Places nothing.

```python
charges = high.orders.charges({
    "tradingSymbol": "RELIANCE-EQ",
    # or: "exchangeSegment": "NSE", "scripCode": "2885",
    "quantity": 100,
    "tradeSide": "B",
    "productType": "DELIVERY",
    "price": 2450,
})
```

Note the reduced field set — charges takes no `flavor`, `orderType` or
`validity`, because none of them changes the cost.

Charges differ sharply by product type and segment. Delivery equity pays a
higher STT than intraday; F&O is charged on premium or turnover depending on
the instrument. Never estimate charges arithmetically — ask.

## Margin

```python
margin = high.orders.margin([
    {"tradingSymbol": "RELIANCE-EQ", "quantity": 50, "tradeSide": "B", "productType": "INTRADAY"},
])
```

The request is a **list**, and that matters: the API prices the basket as a
whole and nets offsetting legs. A hedged options position margined leg by leg
can report several times the true requirement.

```python
# Right — one basket, hedges recognised
margin = high.orders.margin([
    {"tradingSymbol": "NIFTY-26SEP-24000-CE", "quantity": 75, "tradeSide": "S", "productType": "INTRADAY"},
    {"tradingSymbol": "NIFTY-26SEP-24200-CE", "quantity": 75, "tradeSide": "B", "productType": "INTRADAY"},
])

# Wrong — two naked legs, margin wildly overstated
for leg in legs:
    high.orders.margin([leg])
```

Required fields per leg: `quantity`, `tradeSide`, `productType`, plus the
instrument by either identifier path. `price` is optional and improves the
estimate for limit orders.

## The affordability check

The pattern worth running before any sizeable order:

```python
from scripts.high_helpers import get_client

with get_client() as high:
    funds = high.portfolio.funds()
    required = high.orders.margin([leg])
    charges = high.orders.charges(charge_body)

    print(f"Available  {funds.availableBalance}")
    print(f"Margin     {required}")
    print(f"Charges    {charges}")
```

Show all three in the confirmation preview for anything above the configured
`max_order_value`. A rejection for insufficient funds is avoidable and looks
like a bug to the user.

See [examples/margin_check.py](../examples/margin_check.py).
