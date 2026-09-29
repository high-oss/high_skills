# Instruments

The instrument master, and how to turn a human name into the identifiers
HIGH's surfaces actually want.

## The three identifier forms

| Surface | Wants | Example |
|---|---|---|
| Orders | `tradingSymbol`, **or** `exchangeSegment` + `scripCode` | `"RELIANCE-EQ"`, or `"NSE"` + `"2885"` |
| Quotes, OHLC | `symbols` (trading symbols) or `scripKeys` | `["RELIANCE-EQ"]` |
| Depth, historical, option chain, expiries | `tradingSymbol` | `"RELIANCE-EQ"` |
| Datafeed | `scrip_key` — `EXCHANGE@scripCode` | `"NSE@2885"` |

The feed is the dangerous one: subscribing with a trading symbol does not
error, it simply never delivers a tick. Resolve, never construct.

## Fetching the list

```python
from scripts.high_helpers import get_client

with get_client() as high:
    for row in high.instruments.stream("equity"):
        print(row.high_trading_symbol, row.scrip_code, row.lot_size)
```

**Needs no credentials.** The instrument list is public, so this is the one
call that works before anything else is set up — useful for proving the
client is wired correctly.

### Categories

| Category | Contents | Size |
|---|---|---|
| `equity` | Cash-segment stocks | small |
| `derivatives` | Futures and options | ~11 MB |
| `commodity` | MCX contracts | small |
| `etfs` | Exchange-traded funds | small |
| `all` | Everything | ~14 MB |

Always pick the narrowest category that can hold the answer. Reaching for
`all` to find a stock downloads 14 MB to answer a question `equity` answers.

### stream vs list

- `high.instruments.stream(category)` — a generator, row by row, nothing
  buffered. **The default choice.**
- `high.instruments.list(category)` — materialises the whole category. Fine
  for `equity`; wasteful for `derivatives` or `all`.

The manifest is cached for the client's lifetime — it is rebuilt once a
trading morning, not per call — so repeated lookups through one client do not
re-download it.

## The row

`InstrumentRow` has 17 columns:

| Field | Notes |
|---|---|
| `exchange` | `NSE`, `BSE`, `NSEFO`, ... |
| `segment` | Segment within the exchange |
| `instrument` | Instrument class, when present |
| `high_trading_symbol` | **The `tradingSymbol` an order wants** |
| `scrip_key` | **`EXCHANGE@scripCode` — what the datafeed wants** |
| `isin` | ISIN, when present |
| `scrip_code` | Integer broker code. Send it to the API as a **string** |
| `symbol` | Bare symbol, without the series suffix |
| `name` | Company or contract name |
| `group_series` | `EQ`, `BE`, ... |
| `has_fno` | Whether derivatives exist on it |
| `underlying_symbol` | For derivatives |
| `expiry` | Contract expiry date |
| `option_type` | `CE` / `PE` |
| `strike_price` | Option strike |
| `price_tick` | **Scale varies by segment** — see below |
| `lot_size` | Contract lot. Quantity must be a multiple for F&O |

### price_tick

Reported exactly as the CSV gives it, and its scale differs between equity,
derivatives and commodity. It is not normalised, deliberately — normalising
it centrally would be a silent pricing bug. Do not divide it by a guessed
factor; compare it against a known live price for that segment before using
it to build a limit price.

### lot_size

For anything in a derivatives segment, `quantity` must be a whole multiple of
`lot_size`. "One lot of Nifty" means `quantity = lot_size`, not `1`.
`validate_order.py` enforces this and names the nearest valid quantity.

## Resolving

```python
from scripts.resolve_symbol import resolve, resolve_all

scrip = resolve("reliance")
scrip.tradingSymbol   # "RELIANCE-EQ"
scrip.exchange        # "NSE"
scrip.scripCode       # "2885"
scrip.scrip_key       # "NSE@2885"
scrip.lot_size        # 1

for match in resolve_all("nifty", category="derivatives", limit=5):
    print(match.tradingSymbol, match.expiry, match.option_type, match.strike_price)
```

Ranking is exact identifier, then exact name, then prefix, then substring —
so `"reliance"` returns `RELIANCE-EQ` rather than `RELIANCERETAIL-EQ` or an
option forty strikes out of the money.

For an order body:

```python
body = {**scrip.order_identity(), "tradeSide": "B", ...}
# or by code:
body = {**scrip.order_identity(by_code=True), ...}
```

An order must carry **exactly one** of the two paths. `order_identity()`
returns one or the other, never both.

Run it directly to check a symbol by hand:

```bash
python scripts/resolve_symbol.py reliance
python scripts/resolve_symbol.py nifty derivatives
```

## Finding a derivative contract

Options and futures are separate rows, one per strike and expiry. To find a
specific contract, filter the `derivatives` category on
`underlying_symbol`, `expiry`, `option_type` and `strike_price` rather than
trying to spell the trading symbol:

```python
contracts = [
    row for row in high.instruments.stream("derivatives")
    if row.underlying_symbol == "NIFTY"
    and row.expiry == target_expiry
    and row.option_type == "CE"
]
```

For the at-the-money region specifically, the option chain is a much cheaper
route than the instrument list — see [option-chain.md](option-chain.md).
