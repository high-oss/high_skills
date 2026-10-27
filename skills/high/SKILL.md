---
name: high
description: >
  Use when the user mentions HIGH, the HIGH Open API, high.live, or wants to
  trade on Indian exchanges (NSE, BSE) through HIGH. Triggers for: place,
  modify, or cancel equity or F&O orders on HIGH, including bracket, cover
  and GTT orders; fetch holdings, positions, or funds; read account profile (demat/DP
  details, linked bank accounts, enabled segments); exit positions; get
  live or historical market data; access option chains and expiries; check
  margin or order charges; resolve NSE/BSE trading symbols or scrip codes;
  stream the live HIGH datafeed; build any trading automation on HIGH. Also
  trigger for general questions about programmatic trading on Indian
  exchanges if HIGH is the user's broker.
compatibility: >
  Requires Python 3.9+ and the high-openapi package (pip install high-openapi).
  Order placement, modification, cancellation, and position exits require the
  API key's static IP to be pinned in the HIGH developer portal. The live
  datafeed is production-only — there is no sandbox feed.
---

# HIGH — Indian Market Trading Skill

## Setup

```bash
pip install high-openapi
```

Minimal initialization:

```python
import os
from high_openapi import HighClient

high = HighClient(
    environment="sandbox",                        # or "production"
    api_key=os.environ["HIGH_API_KEY"],
    access_token=os.environ["HIGH_ACCESS_TOKEN"],
)
```

The bare form reads `HIGH_API_KEY`, `HIGH_ACCESS_TOKEN` and
`HIGH_ENVIRONMENT` / `HIGH_BASE_URL` from the environment on its own:

```python
with HighClient() as high:
    print(high.portfolio.funds().availableBalance)
```

If generating scripts for this repo, prefer:

```python
from scripts.high_helpers import get_client

high = get_client()
```

Async work uses `AsyncHighClient`, with the same resources and `await` on
every call.

## Safety Rules — Always Enforce

1. Confirm before placing a live order. Show a readable preview first —
   flavor, side, quantity and every conditional price that flavor carries.
2. Default to `LIMIT`. Use `MARKET` only when the user explicitly asks.
3. Warn when notional exceeds `Rs. 50,000`.
4. Apply the configured per-order quantity cap. Never exceed it silently.
5. For F&O, validate quantity against the instrument row's `lot_size`.
6. Check `flavor` against `productType` before placing — `BO`/`CO` are
   `INTRADAY` only, `GTT` is `DELIVERY`/`MTF` only.
7. Never place a live order outside market hours unless the user explicitly
   asked for an after-market order (`isAMO=True`). Check `market.status()`.
8. Never hardcode credentials. Environment variables only.
9. Confirm before `orders.modify`, `orders.cancel`, `portfolio.exit_position`, `portfolio.set_stoploss`, `portfolio.set_target`,
   and especially `portfolio.exit_all_positions` or any multi-leg execution.
10. Default to `sandbox`. Switch to `production` only when the user says so,
    and pass `environment=` explicitly — an explicit value suppresses a stray
    `HIGH_BASE_URL` in the shell profile.

## Access Checks Before Live Use

1. Access token is valid — an expired token returns `401` with a readable
   `code`.
2. `HIGH_API_KEY` is set; the `/auth/*` operations authenticate with the key,
   every other operation with the bearer token.
3. The API key's **static IP is pinned** in the developer portal. Required for
   order place, modify, cancel, and position exits. A pin mismatch is a `403`,
   not a `401` — see [references/error-codes.md](references/error-codes.md).
4. For datafeed work, the environment resolves to `production`. There is no
   sandbox feed, and `HighFeed` refuses to construct without one.
5. `market.status()` before any live order.

## Identifiers — Three Forms, Never Hand-Built

HIGH takes different identifiers on different surfaces. Getting this wrong is
the most common failure, and the feed fails silently rather than erroring.

| Surface | Identifier | Example |
|---|---|---|
| Orders | `tradingSymbol` **or** `exchangeSegment` + `scripCode` | `"RELIANCE-EQ"` or `"NSE"` + `"2885"` |
| Historical, intraday candles | `tradingSymbol` **or** `exchangeSegment` + `scripCode` | `"RELIANCE-EQ"` or `"NSE"` + `"2885"` |
| Position stop-loss, target | `tradingSymbol` **or** `exchangeSegment` + `scripCode` | `"RELIANCE-EQ"` or `"NSE"` + `"2885"` |
| Quotes, OHLC, depth | `tradingSymbol` | `"RELIANCE-EQ"` |
| Datafeed | `scrip_key`, i.e. `EXCHANGE@scripCode` | `"NSE@2885"` |

An order, historical, intraday, stop-loss or target request must supply **exactly one** of the two accepted paths: the
trading symbol, or the segment-and-code pair. The API rejects a request that
supplies neither.

Always resolve, never construct:

```python
from scripts.resolve_symbol import resolve

scrip = resolve("reliance")
# scrip.tradingSymbol  "RELIANCE-EQ"
# scrip.exchange       "NSE"
# scrip.scripCode      "2885"
# scrip.scrip_key      "NSE@2885"   — for the datafeed
# scrip.lot_size       1
# scrip.price_tick     5
```

## Constants

| Category | Values |
|---|---|
| Exchange segment | `NSE`, `BSE`, `NSEFO`, `BSEFO`, `NSECDSFO`, `BSECDSFO`, `MCXFO` |
| Trade side | `B` (buy), `S` (sell) — **not** `BUY`/`SELL` |
| Product type | `INTRADAY`, `DELIVERY`, `MTF` — there is no `CNC` |
| Order flavor | `REGULAR`, `BO`, `CO`, `GTT` |
| Order type | `LIMIT`, `MARKET`, `STOP_LOSS`, `STOP_LOSS_MARKET` |
| Validity | `DAY`, `IOC`, `YEAR` (`YEAR` is how a GTT rests) |
| Leg indicator | `ENTRY_LEG`, `STOP_LOSS_LEG`, `TARGET_LEG` — `BO`/`CO` only |
| Square-off flavor | `REGULAR`, `BO`, `CO` |

## Order Flavors — The Central Model

HIGH has **one** `orders.place` call. The flavor is a field on the request,
not a separate endpoint. Which flavors a product type permits is enforced
server-side:

| `productType` | Permitted `flavor` |
|---|---|
| `INTRADAY` | `REGULAR`, `BO`, `CO` |
| `DELIVERY`, `MTF` | `REGULAR`, `GTT` |

Anything else is rejected with `flavor must be one of ... for ... orders`.

### Conditional fields by flavor

| Field | Required / allowed when |
|---|---|
| `price` | `orderType` is `LIMIT` or `STOP_LOSS` |
| `triggerPrice` | `flavor` is `GTT`, or `orderType` is a stop-loss type |
| `targetPrice` | `flavor` is `BO` |
| `stoplossPrice` | `flavor` is `BO` or `CO` |
| `trailSL` | optional trailing stop-loss, in ticks |
| `legIndicator` | `BO`/`CO` **only** — must be absent for `REGULAR` and `GTT` |
| `disclosedQuantity` | `flavor` is `REGULAR` **and** `validity` is `DAY` |
| `isAMO` | after-market flag |
| `isSlice` | slice a large order into children |

Validate locally before sending — it turns a `400` into a readable message:

```python
from scripts.validate_order import validate

verdict = validate(body, lot_size=scrip.lot_size)
if not verdict.ok:
    print(verdict.errors)          # fix before sending
print(verdict.preview)             # show this, then ask for confirmation
```

## Methods

| Task | Call |
|---|---|
| Place order | `high.orders.place(body)` |
| Modify order | `high.orders.modify(body)` |
| Cancel order | `high.orders.cancel(order_id)` |
| Order book | `high.orders.list()` |
| Order by id | `high.orders.get(order_id)` |
| Trade book | `high.orders.trades()` |
| Trades for an order | `high.orders.trades_for(order_id)` |
| Order charges | `high.orders.charges(body)` |
| Order margin | `high.orders.margin([body, ...])` |
| Positions | `high.portfolio.positions()` |
| Holdings | `high.portfolio.holdings()` |
| Funds | `high.portfolio.funds()` |
| Account profile (masked PAN/Aadhaar/bank a/c) | `high.profile.get()` |
| Convert position | `high.portfolio.convert_position(body)` |
| Set a position stop-loss | `high.portfolio.set_stoploss(body)` |
| Set a position target | `high.portfolio.set_target(body)` |
| Exit one position | `high.portfolio.exit_position(body)` |
| Exit every position | `high.portfolio.exit_all_positions()` |
| Quotes | `high.scrips.quotes({"symbols": [...]})` |
| OHLC | `high.scrips.ohlc({"symbols": [...]})` |
| Market depth | `high.scrips.depth(symbol)` |
| Historical candles | `high.scrips.historical(body)` |
| Intraday candles (last session) | `high.scrips.intraday(body)` |
| Option chain | `high.scrips.option_chain(body)` |
| Expiries | `high.scrips.expiries(symbol, type)` |
| Futures for a symbol | `high.scrips.future_data(symbol)` |
| Instrument list | `high.instruments.stream(category)` / `.list(category)` |
| Market status | `high.market.status()` |
| Access token | `high.auth.generate_access_token(client_id, t_otp)` |
| Live feed | `HighFeed` / `AsyncHighFeed` |
| Errors | `HighApiError`, `OperationCancelled` |

## Core Patterns

### 1. Regular order

```python
from scripts.high_helpers import get_client
from scripts.resolve_symbol import resolve

high = get_client()
scrip = resolve("reliance")

body = {
    "tradeSide": "B",
    "tradingSymbol": scrip.tradingSymbol,
    "productType": "DELIVERY",
    "flavor": "REGULAR",
    "orderType": "LIMIT",
    "validity": "DAY",
    "quantity": 10,
    "price": 2450,
    "isAMO": False,
}
result = high.orders.place(body)
print(result)
```

### 2. Bracket order — entry, target and stop-loss in one

`INTRADAY` only. Needs `targetPrice`, `stoplossPrice` and `legIndicator`.

```python
body = {
    "tradeSide": "B",
    "tradingSymbol": scrip.tradingSymbol,
    "productType": "INTRADAY",
    "flavor": "BO",
    "orderType": "LIMIT",
    "validity": "DAY",
    "quantity": 10,
    "price": 2450,
    "targetPrice": 2500,
    "stoplossPrice": 2400,
    "trailSL": 5,
    "legIndicator": "ENTRY_LEG",
    "isAMO": False,
}
```

### 3. Cover order — entry plus a compulsory stop-loss

`INTRADAY` only. Stop-loss but **no** target.

```python
body = {
    "tradeSide": "B",
    "tradingSymbol": scrip.tradingSymbol,
    "productType": "INTRADAY",
    "flavor": "CO",
    "orderType": "LIMIT",
    "validity": "DAY",
    "quantity": 10,
    "price": 2450,
    "stoplossPrice": 2400,
    "legIndicator": "ENTRY_LEG",
    "isAMO": False,
}
```

### 4. GTT — a resting trigger

`DELIVERY` or `MTF`. Needs `triggerPrice`, and rests with `validity="YEAR"`.

```python
body = {
    "tradeSide": "B",
    "tradingSymbol": scrip.tradingSymbol,
    "productType": "DELIVERY",
    "flavor": "GTT",
    "orderType": "LIMIT",
    "validity": "YEAR",
    "quantity": 10,
    "price": 2400,
    "triggerPrice": 2400,
    "isAMO": False,
}
```

### 5. Portfolio

```python
funds = high.portfolio.funds()
positions = high.portfolio.positions()
holdings = high.portfolio.holdings()

print(f"Available: {funds.availableBalance}")
for position in positions.root if hasattr(positions, "root") else positions:
    print(position)
```

### 6. Live datafeed — production only

```python
import asyncio
from high_openapi import AsyncHighFeed, Quote, Depth, IndexTick

async def main():
    feed = AsyncHighFeed()                 # picks up HIGH_ACCESS_TOKEN
    await feed.connect()
    await feed.subscribe_quotes(["NSE@2885"])

    async for event in feed:
        if isinstance(event, Quote):
            print(event.scrip_key, event.last_traded_price)

asyncio.run(main())
```

## Error Handling

Every failure surfaces as `HighApiError`. Transport failures and timeouts
carry `status=0`. Always print `request_id` — it is what support needs.

```python
from high_openapi import HighApiError

try:
    high.orders.place(body)
except HighApiError as error:
    print(f"status={error.status} code={error.code} request_id={error.request_id}")
    for message in error.messages or []:
        print(f"  - {message}")
```

`OperationCancelled` is the caller's own cancellation. Never retry it.

## Reference Index

| Topic | File |
|---|---|
| Order lifecycle, all four flavors, modify and cancel | [references/orders.md](references/orders.md) |
| Positions, holdings, conversion and exits | [references/portfolio.md](references/portfolio.md) |
| Quotes, OHLC, depth, historical candles | [references/market-data.md](references/market-data.md) |
| Option chain and expiries | [references/option-chain.md](references/option-chain.md) |
| Instrument master and symbol resolution | [references/instruments.md](references/instruments.md) |
| Funds, charges and margin | [references/funds.md](references/funds.md) |
| Account profile, demat/DP, bank accounts, segments (MCP: `high_get_profile`) | [references/profile.md](references/profile.md) |
| Live datafeed — quotes, depth, indices | [references/live-feed.md](references/live-feed.md) |
| Errors, validator messages, rate limits, retries | [references/error-codes.md](references/error-codes.md) |
| API keys, tokens, TOTP, consent, static IP | [references/auth-and-credentials.md](references/auth-and-credentials.md) |
| Multi-step workflows | [references/common-workflows.md](references/common-workflows.md) |
| Options analysis patterns | [references/options-analysis-patterns.md](references/options-analysis-patterns.md) |
| Backtesting on HIGH data | [references/backtesting-with-high.md](references/backtesting-with-high.md) |

## What HIGH Does Not Have

Do not generate code for these — they belong to other brokers' APIs:

- No `CNC` product type. Delivery is `DELIVERY`.
- No `BUY`/`SELL` strings. Sides are `B` and `S`.
- No numeric-only `security_id`. See the identifier table above.
- No separate super-order or forever-order API. Flavors cover both.
- No scanner / screener endpoint.
- No endpoint that returns a full PAN, Aadhaar or bank account number — the profile is masked; never ask for or print the full values.
- No ledger, eDIS or TPIN endpoints.
- No order-update stream on the datafeed — quotes, depth and indices only.
