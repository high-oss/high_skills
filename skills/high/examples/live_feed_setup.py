# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Stream live quotes, depth and index ticks.

    HIGH_ENVIRONMENT=production HIGH_ACCESS_TOKEN=... \
        python examples/live_feed_setup.py

PRODUCTION ONLY. There is no sandbox datafeed — AsyncHighFeed refuses to
construct when the environment resolves to sandbox, so this example cannot be
dry-run.

Two things to get right:

  * Subscriptions key on scrip_key — EXCHANGE@scripCode, e.g. "NSE@2885".
    A trading symbol does not error; it simply never delivers a tick.
  * The feed carries market data only. There is NO order-update stream —
    poll orders.list() for order state.

This script stops after MAX_EVENTS so it terminates on its own. A real feed
consumer still needs an explicit exit condition — never an unbounded loop
with no way out.
"""

from __future__ import annotations

import asyncio
import os

from high_openapi import AsyncHighFeed, Depth, HighApiError, IndexTick, Quote

from scripts.high_helpers import get_client
from scripts.resolve_symbol import resolve

SYMBOLS = ["reliance", "tcs"]
NIFTY_50 = "NSE@26000"          # from the committed index table, not the CSV
MAX_EVENTS = 20


def resolve_keys() -> list:
    """Trading symbol -> scrip_key. Never build a feed key by hand."""
    keys = []
    with get_client() as high:
        for name in SYMBOLS:
            scrip = resolve(name, high=high)
            print(f"  {name:<12} -> {scrip.tradingSymbol:<16} {scrip.scrip_key}")
            keys.append(scrip.scrip_key)
    return keys


async def main() -> None:
    environment = os.environ.get("HIGH_ENVIRONMENT", "sandbox")
    if environment != "production":
        print(
            "The datafeed is production-only. Set HIGH_ENVIRONMENT=production.\n"
            "There is no sandbox feed, so this cannot be dry-run."
        )
        return

    print("Resolving scrip keys...")
    keys = resolve_keys()

    feed = AsyncHighFeed()              # picks up HIGH_ACCESS_TOKEN
    await feed.connect()
    print("\nConnected.")

    try:
        await feed.subscribe_quotes(keys)
        await feed.subscribe_depth(keys[:1])
        await feed.subscribe_indices([NIFTY_50])
        print(f"Subscribed. Stopping after {MAX_EVENTS} events (Ctrl-C to stop sooner).\n")

        count = 0
        async for event in feed:
            if isinstance(event, Quote):
                changed = ",".join(sorted(event.changed_fields or []))
                print(f"quote  {event.scrip_key:<12} LTP={event.last_traded_price:<12} [{changed}]")
            elif isinstance(event, Depth):
                best_bid = event.bids[0] if event.bids else None
                print(f"depth  {event.scrip_key:<12} levels={event.level_count} best_bid={best_bid}")
            elif isinstance(event, IndexTick):
                print(f"index  {event.scrip_key:<12} value={event.index_value}")

            count += 1
            if count >= MAX_EVENTS:
                break

    except HighApiError as error:
        print(f"Feed error: status={error.status} request_id={error.request_id}")
        raise
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        # Always close — an abandoned socket holds a connection slot.
        await feed.close()
        print("Closed.")


if __name__ == "__main__":
    asyncio.run(main())
