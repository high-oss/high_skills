# Live datafeed

A WebSocket stream of quotes, depth and index ticks. **Production only.**

```python
from high_openapi import AsyncHighFeed, Quote, Depth, IndexTick
```

## Before anything else

- **There is no sandbox feed.** `sandbox` resolves the socket host to
  nothing, and `HighFeed` / `AsyncHighFeed` refuse to construct rather than
  connect to a host nothing serves. A feed script cannot be dry-run.
- **Subscriptions key on `scrip_key`** — `EXCHANGE@scripCode`, e.g.
  `"NSE@2885"`. A trading symbol does not error; it simply never delivers a
  tick. Resolve it: `resolve("reliance").scrip_key`.
- **There is no order-update stream.** The feed carries market data only.
  Poll `orders.list()` for order state.
- Authentication is the access token. `HIGH_ACCESS_TOKEN` is enough.

## The async form — preferred

```python
import asyncio
from high_openapi import AsyncHighFeed, Quote, Depth, IndexTick

async def main():
    feed = AsyncHighFeed()                  # picks up HIGH_ACCESS_TOKEN
    await feed.connect()

    await feed.subscribe_quotes(["NSE@2885"])
    await feed.subscribe_depth(["NSE@2885"])
    await feed.subscribe_indices(["NSE@26000"])     # Nifty 50

    async for event in feed:
        if isinstance(event, Quote):
            print(f"quote {event.scrip_key} LTP={event.last_traded_price}")
        elif isinstance(event, Depth):
            print(f"depth {event.scrip_key} levels={event.level_count}")
        elif isinstance(event, IndexTick):
            print(f"index {event.scrip_key} value={event.index_value}")

    await feed.close()

asyncio.run(main())
```

`async for event in feed` is the primary consumption path. One event at a
time, typed, with `isinstance` dispatch.

## The sync form

For callers not already in an asyncio application:

```python
from high_openapi import HighFeed

feed = HighFeed()
feed.connect()
feed.add_listener(lambda event: print(event))
feed.subscribe_quotes(["NSE@2885"])
...
feed.close()
```

`add_listener` returns a handle; `remove_listener` detaches it.

## Subscription methods

| Stream | Subscribe | Unsubscribe | One-shot |
|---|---|---|---|
| Quotes | `subscribe_quotes` | `unsubscribe_quotes` | `snapshot_quotes` |
| Depth | `subscribe_depth` | `unsubscribe_depth` | `snapshot_depth` |
| Indices | `subscribe_indices` | `unsubscribe_indices` | `snapshot_indices` |

Each takes a single key or an iterable of them:

```python
await feed.subscribe_quotes("NSE@2885")
await feed.subscribe_quotes(["NSE@2885", "NSE@11536"])
```

### snapshot vs subscribe

`snapshot_*` asks for the current value once. `subscribe_*` asks for every
update until unsubscribed. Use a snapshot for "what is it now" on a socket
you already hold; use the REST `quotes` call if you do not hold one.

## Event types

| Type | Carries |
|---|---|
| `Quote` | `scrip_key`, `last_traded_price`, `changed_fields`, touchline fields |
| `Depth` | `scrip_key`, `bids`, `asks`, `level_count` |
| `IndexTick` | `scrip_key`, `index_value` |

`Quote.changed_fields` names which fields moved on this tick. Use it rather
than diffing whole objects — most ticks change one or two fields.

## Indices

Index keys come from the committed index table, not the instrument CSV —
`NSE@26000` is Nifty 50. Subscribe to indices with `subscribe_indices`, not
`subscribe_quotes`; the payloads differ.

## Lifecycle

```python
feed = AsyncHighFeed()
await feed.connect()
try:
    ...
finally:
    await feed.close()
```

Always close. An abandoned socket holds a connection slot.

Reconnects are handled internally, but a reconnect does **not** replay ticks
missed while disconnected. A strategy that must not miss a print should
reconcile against REST after any gap.

## Running a feed responsibly

- Subscribe to what you need. Hundreds of symbols is a lot of traffic and a
  lot of CPU in the callback.
- Never do blocking work in a listener — queue it. A slow callback backs up
  the socket.
- A feed script is long-running. Say so to the user before starting one, and
  give it an exit condition (a tick count, a duration, a Ctrl-C handler)
  rather than an unbounded loop.
- Do not place orders directly from inside a tick handler without a rate
  limit and a confirmation path. That is how a bug becomes a hundred orders.

See [examples/live_feed_setup.py](../examples/live_feed_setup.py).
