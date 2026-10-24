# Market data

Quotes, OHLC, depth, historical and intraday candles, and market status.

| Task | Call | HTTP |
|---|---|---|
| Quotes | `high.scrips.quotes(body)` | `POST /scrips/quotes` |
| OHLC | `high.scrips.ohlc(body)` | `POST /scrips/ohlc` |
| Market depth | `high.scrips.depth(symbol)` | `GET /scrips/{symbol}/depth` |
| Historical candles | `high.scrips.historical(body)` | `POST /scrips/historical` |
| Intraday candles | `high.scrips.intraday(body)` | `POST /scrips/intraday` |
| Futures on a symbol | `high.scrips.future_data(symbol)` | `GET /scrips/{symbol}/future-data` |
| Market status | `high.market.status()` | `GET /market/status` |

## Market status

Check it before any live order. Safety rule 7 depends on it.

```python
from scripts.high_helpers import get_client, market_is_open

with get_client() as high:
    if not market_is_open(high):
        print("Market closed — an order now needs isAMO=True.")
```

Placing outside hours without `isAMO` is rejected. Placing outside hours
*with* `isAMO` queues the order for the next session, which is a materially
different thing from what the user usually meant — confirm it explicitly.

## Quotes

```python
quotes = high.scrips.quotes({"symbols": ["RELIANCE-EQ", "TCS-EQ"]})
reliance = quotes["RELIANCE-EQ"]
print(reliance.LTP)
```

The response is a **dict keyed by the symbol you asked for**, not a list — so
a missing key means that symbol returned nothing, and `.get()` is safer than
indexing.

The body accepts either form:

```python
{"symbols": ["RELIANCE-EQ"]}     # trading symbols
{"scripKeys": ["NSE@2885"]}      # exchange@scripCode
```

Batch aggressively: one call with fifty symbols beats fifty calls, and
`scripts.high_helpers.chunked` splits an oversized list.

```python
from scripts.high_helpers import chunked

prices = {}
for batch in chunked(symbols, 50):
    prices.update(high.scrips.quotes({"symbols": batch}))
```

## OHLC

Same request shape, same dict-keyed response. Returns the session's open,
high, low and close rather than the full touchline.

```python
bars = high.scrips.ohlc({"symbols": ["RELIANCE-EQ"]})
```

Use OHLC when you want today's range; use quotes when you want the live last
traded price and the bid/ask.

## Market depth

```python
depth = high.scrips.depth("RELIANCE-EQ")
best_bid = depth.bids[0] if depth.bids else None
```

Five levels each side. One symbol per call — there is no batch form. For
continuous depth on several instruments, use the datafeed instead:
[live-feed.md](live-feed.md).

## Historical candles

```python
import time

now = int(time.time())
candles = high.scrips.historical({
    "tradingSymbol": "RELIANCE-EQ",
    "interval": "1D",
    "fromTime": now - 180 * 24 * 3600,   # Unix epoch SECONDS
    "toTime": now,
})
```

### Required fields

| Field | Notes |
|---|---|
| `tradingSymbol` | From the instrument list. Or send `exchangeSegment` + `scripCode` instead |
| `interval` | See the table below |
| `fromTime` | Unix epoch **seconds**, not milliseconds |
| `toTime` | Unix epoch seconds. Candles opening after it are excluded |
| `fields` | Accepted but ignored — every series is always returned |

### Intervals

```
1m  2m  3m  4m  5m  10m  15m  30m  45m
1h  2h  3h  4h
1D  1W  1M
3M  6M  1Y
```

`m` is minutes, `h` hours, `D`/`W`/`M` day, week, month.

**`3M`, `6M` and `1Y` are passed straight to the broker without the
translation the other intervals get, and may come back empty.** Build them
from `1M` candles instead — aggregate three, six or twelve monthly bars
yourself. This is a known sharp edge, not a transient failure; do not retry
into it.

### Intraday candles

The most recent trading session only, so it works over a weekend or holiday
without computing a range. No `fromTime`/`toTime`.

```python
today = high.scrips.intraday({
    "tradingSymbol": "RELIANCE-EQ",   # or exchangeSegment + scripCode
    "interval": "5m",
})
```

`interval` is one of `1m 2m 3m 4m 5m 10m 15m 30m 45m 1h 2h 3h 4h`. Daily and
longer intervals belong to `historical`. The response has the same columnar
shape as `historical`.

### Epoch seconds

The most common mistake. `int(time.time())` is right;
`int(time.time() * 1000)` silently asks for a range 50,000 years out and
returns nothing.

```python
from datetime import datetime, timezone

def epoch(year, month, day):
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())
```

### Intraday ranges

Minute intervals over long ranges return large payloads and may be truncated
by the broker. For a year of 1-minute data, page the request month by month
rather than asking for the whole span at once.

## Futures on a symbol

```python
futures = high.scrips.future_data("RELIANCE-EQ")
```

The live futures contracts on an underlying — near, next and far month —
without filtering the whole derivatives instrument list.

## Choosing a source

| Need | Use |
|---|---|
| A price right now, a handful of symbols | `quotes` |
| Today's range | `ohlc` |
| The book, one symbol | `depth` |
| A series over time | `historical` |
| Continuous updates | the datafeed |

Do not poll `quotes` in a tight loop to simulate a feed. That is what the
datafeed is for, and polling will hit rate limits — see
[error-codes.md](error-codes.md).
