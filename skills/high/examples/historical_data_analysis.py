# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Historical candles, moving averages and basic statistics.

    python examples/historical_data_analysis.py
    python examples/historical_data_analysis.py TCS-EQ 1D 365

Reads only. Two traps this example exists to demonstrate:

  * fromTime/toTime are Unix epoch SECONDS. Milliseconds silently return
    nothing — int(time.time()), never int(time.time() * 1000).
  * The 3M, 6M and 1Y intervals are passed to the broker untranslated and may
    come back empty. Build them from 1M candles instead.
"""

from __future__ import annotations

import statistics
import sys
import time

from high_openapi import HighApiError

from scripts.high_helpers import describe_error, get_client

SYMBOL = "RELIANCE-EQ"
INTERVAL = "1D"
DAYS = 180

# Passed to the broker without translation; may return empty.
UNRELIABLE_INTERVALS = {"3M", "6M", "1Y"}


def closes_of(candles):
    """Candle shapes vary — pull closes without assuming one layout."""
    rows = list(getattr(candles, "root", None) or getattr(candles, "candles", None) or candles)
    values = []
    for row in rows:
        close = None
        for name in ("close", "c", "Close"):
            if hasattr(row, name):
                close = getattr(row, name)
                break
            if isinstance(row, dict) and name in row:
                close = row[name]
                break
        if close is None and isinstance(row, (list, tuple)) and len(row) >= 5:
            close = row[4]        # [time, open, high, low, close, volume]
        if close is not None:
            values.append(float(close))
    return values


def sma(values, window):
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def main(argv) -> None:
    symbol = argv[0] if argv else SYMBOL
    interval = argv[1] if len(argv) > 1 else INTERVAL
    days = int(argv[2]) if len(argv) > 2 else DAYS

    if interval in UNRELIABLE_INTERVALS:
        print(
            f"{interval} is passed to the broker untranslated and often returns empty.\n"
            f"Fetch 1M candles and aggregate them instead."
        )
        return

    now = int(time.time())                      # SECONDS
    body = {
        "tradingSymbol": symbol,
        "interval": interval,
        "fromTime": now - days * 24 * 3600,
        "toTime": now,
    }

    with get_client() as high:
        try:
            candles = high.scrips.historical(body)
        except HighApiError as error:
            print(describe_error(error))
            raise

    closes = closes_of(candles)
    if not closes:
        print(
            "No candles returned. Check that fromTime/toTime are epoch SECONDS,\n"
            "that the symbol exists, and that the range covers trading days."
        )
        return

    last = closes[-1]
    first = closes[0]

    print(f"\n  {symbol} — {interval}, {len(closes)} candle(s) over ~{days} days")
    print(f"  {'-' * 46}")
    print(f"  first      {first:,.2f}")
    print(f"  last       {last:,.2f}")
    print(f"  change     {(last - first) / first * 100:+.2f}%")
    print(f"  high       {max(closes):,.2f}")
    print(f"  low        {min(closes):,.2f}")
    print(f"  mean       {statistics.fmean(closes):,.2f}")
    if len(closes) > 1:
        print(f"  stdev      {statistics.stdev(closes):,.2f}")

    print(f"  {'-' * 46}")
    for window in (20, 50, 200):
        average = sma(closes, window)
        if average is None:
            print(f"  SMA {window:<4}   not enough data ({len(closes)} candles)")
        else:
            side = "above" if last > average else "below"
            print(f"  SMA {window:<4}   {average:,.2f}   (price is {side})")

    fast, slow = sma(closes, 20), sma(closes, 50)
    if fast and slow:
        print(f"  {'-' * 46}")
        print(f"  20 is {'above' if fast > slow else 'below'} 50 — "
              f"{'uptrend' if fast > slow else 'downtrend'} by this crossover.")

    print("\n  Descriptive only. This is not a signal, and a moving average is not advice.")


if __name__ == "__main__":
    main(sys.argv[1:])
