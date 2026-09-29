# Backtesting with HIGH data

`scrips.historical` gives candles. Everything else is yours. This is a guide
to doing it honestly — a backtest that flatters a strategy is worse than none.

## Getting the data

```python
import time
from scripts.high_helpers import get_client

now = int(time.time())
with get_client() as high:
    candles = high.scrips.historical({
        "tradingSymbol": "RELIANCE-EQ",
        "interval": "1D",
        "fromTime": now - 3 * 365 * 24 * 3600,
        "toTime": now,
    })
```

Traps, all covered in [market-data.md](market-data.md):

- `fromTime` / `toTime` are epoch **seconds**. Milliseconds silently return
  nothing.
- `3M`, `6M` and `1Y` intervals may come back empty. Build them from `1M`.
- Long minute-interval ranges may be truncated. Page month by month.

Cache to disk. Re-downloading three years of candles on every run is slow and
burns rate limit.

```python
import json
from pathlib import Path

cache = Path(f"data/{symbol}-{interval}.json")
if cache.is_file():
    candles = json.loads(cache.read_text())
else:
    candles = high.scrips.historical(body)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(candles, default=str))
```

## The cost model

A backtest without costs is fiction. Indian equity costs are material and
asymmetric.

Get them from the API rather than inventing them:

```python
charges = high.orders.charges({
    "tradingSymbol": "RELIANCE-EQ",
    "quantity": 100,
    "tradeSide": "B",
    "productType": "DELIVERY",
    "price": 2450,
})
```

Sample a few representative sizes, derive a per-trade model, and apply it to
both sides of every round trip. Components: brokerage, STT (much higher on
delivery sells), exchange transaction charges, SEBI turnover fee, stamp duty
(buy side), GST on brokerage and charges.

Then add what `charges` cannot tell you:

- **Slippage.** A limit at the close is not a fill. Assume at least one tick
  against you; more for illiquid names and for market orders.
- **Impact.** Size beyond a fraction of the bar's volume moves the price. If
  a backtest's position size exceeds ~1% of typical daily volume, the result
  is not reachable.
- **Spread.** Crossing the spread costs half of it per side.

## Honest mechanics

**Decide on bar close, execute on the next bar.** Using a bar's close as both
signal and fill price is lookahead — you cannot know the close until the bar
is over.

```python
for i in range(1, len(candles) - 1):
    signal = compute_signal(candles[: i + 1])     # only data up to bar i
    if signal:
        fill = candles[i + 1].open                # execute on the NEXT bar
```

**Survivorship bias.** The instrument list is today's list. Companies that
delisted are absent, so a universe built from it is a universe of survivors.
Backtests across a broad universe overstate returns for this reason alone.
Say so in the results.

**Corporate actions.** Verify whether candles are adjusted for splits and
bonuses before building a strategy on a price series that may contain a
50% single-day "drop" that never happened. Check a known split date.

**Parameter fitting.** A strategy tuned on the same data it is tested on will
look excellent and fail live. Hold out a period, or walk forward.

**Regime.** Three years of a bull market tells you about bull markets. State
the period tested and what it contained.

## Metrics worth reporting

| Metric | Why |
|---|---|
| Total and annualised return | The headline |
| Maximum drawdown | What the user must have sat through |
| Sharpe / Sortino | Return per unit of risk |
| Win rate **and** average win / average loss | Either alone misleads |
| Number of trades | Twelve trades prove nothing |
| Turnover and total costs | What the strategy paid to exist |
| Longest losing streak | What it takes to keep running it |

Report drawdown and cost alongside return, always. A strategy returning 40%
with a 60% drawdown is not a good strategy.

## F&O specifics

- **Contracts expire.** A continuous futures series must be stitched with a
  roll, and the roll has a cost. Naive stitching creates phantom gaps.
- **Lot sizes change** over time. A backtest using today's lot size across
  three years sizes historical trades wrongly.
- **Options need the chain**, which is a live endpoint. There is no
  historical option-chain API, so options backtesting needs data you have
  been recording yourself.
- **Margin varies** with volatility. A strategy that was affordable on
  average may have been unaffordable exactly when it mattered.

## Before showing results

State plainly: the period, the universe, the costs assumed, the slippage
assumed, the number of trades, and which biases were not corrected. A
backtest presented without those is a marketing artefact.

And say the obvious thing: past performance does not predict future returns.
Do not let a backtest become a recommendation.

## Paper trading

Better than a backtest for anything path-dependent. Run the strategy against
`sandbox` with live data and real order plumbing — it catches identifier
errors, lot-size errors, margin shortfalls and rate limits that a backtest
never will.

There is no sandbox datafeed, so a paper run that needs live ticks polls
`quotes` on a sane interval, or runs against production data with orders
still pointed at sandbox.
