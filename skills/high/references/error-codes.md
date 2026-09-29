# Errors, validation messages and retries

Every failure the SDK surfaces is a `HighApiError`.

```python
from high_openapi import HighApiError, OperationCancelled

try:
    high.orders.place(body)
except HighApiError as error:
    print(error.status)       # HTTP status; 0 for transport failures and timeouts
    print(error.code)         # HIGH's error code, when the response carried one
    print(error.request_id)   # quote this in a support ticket
    print(error.messages)     # a LIST — validation returns several at once
    print(error.body)         # the parsed body, when there was one
```

`scripts.high_helpers.describe_error` renders all of it:

```python
from scripts.high_helpers import describe_error

except HighApiError as error:
    print(describe_error(error))
```

## `messages` is plural

HIGH validates an order body with a pipeline that returns **every** failure at
once. Printing `error.messages[0]` hides the rest, so the user fixes one
field, resubmits, and hits the next. Always print the whole list.

## Status codes

| Status | Meaning | Do |
|---|---|---|
| `0` | Transport failure or timeout — the request may or may not have reached HIGH | For a **write**, check the order book before retrying. Never blind-retry a placement |
| `400` | Validation. `messages` names every bad field | Fix and resend. Do not retry unchanged |
| `401` | Token expired or wrong | Re-mint once with TOTP, then stop |
| `403` | Static IP not pinned, or the key lacks the scope | Pin the IP. Retrying will not help |
| `404` | Unknown order id or symbol | Re-resolve the identifier |
| `429` | Rate limited | Back off — see below |
| `5xx` | HIGH or the broker upstream | Retry with backoff, bounded |

### `0` on a write is the dangerous one

A timeout on `orders.place` does not mean the order was not placed. It means
you do not know. Check `orders.list()` for the order before sending it again,
or you will double-fill.

```python
try:
    result = high.orders.place(body)
except HighApiError as error:
    if error.status == 0:
        print("Uncertain outcome. Checking the order book before doing anything else.")
        print(high.orders.list())
        raise
```

## Validation messages you will actually see

| Message | Cause | Fix |
|---|---|---|
| `flavor must be one of REGULAR/GTT for DELIVERY/MTF orders` | BO or CO with a delivery product | BO/CO need `productType: "INTRADAY"` |
| `flavor must be one of BO/CO/REGULAR for INTRADAY orders` | GTT on intraday | GTT needs `DELIVERY` or `MTF` |
| `legIndicator is only applicable for BO/CO orders` | Leg sent on REGULAR or GTT | Drop the field |
| `quantity should be greater than 0` | Missing or zero quantity | Send a positive quantity |
| `disclosedQuantity must be 0 or less than or equal to quantity` | Disclosed exceeds total | Lower it, or drop it |
| `flavor can only be from REGULAR,BO,CO,GTT` | Typo or another broker's vocabulary | Use HIGH's enum |
| `tradeSide can only be from B,S` | `BUY`/`SELL` sent | `B` or `S` |
| `productType can only be from INTRADAY,DELIVERY,MTF` | `CNC` sent | HIGH has no `CNC`; delivery is `DELIVERY` |
| `exchangeSegment can only be from ...` | Unsupported segment | See the segment list in [instruments.md](instruments.md) |

Run `scripts/validate_order.py` first and most of these never reach the wire.

## Rate limits

Per API key. Reads are more generous than writes; the datafeed has its own
budget separate from REST.

On `429`:

1. Stop. Do not retry immediately.
2. Back off exponentially — 1s, 2s, 4s, 8s — with jitter.
3. Give up after a small number of attempts and tell the user.

```python
import random
import time

def with_backoff(call, attempts=4):
    for attempt in range(attempts):
        try:
            return call()
        except HighApiError as error:
            if error.status not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise
            time.sleep((2 ** attempt) + random.random())
```

**Never wrap a write in this.** Retrying a placement that may have succeeded
is how duplicate orders happen. Backoff is for reads.

The commonest cause of `429` is polling `quotes` in a loop to simulate a live
feed. Use the datafeed instead — [live-feed.md](live-feed.md).

## OperationCancelled

```python
from high_openapi import OperationCancelled
```

Raised by the sync client when a caller-supplied `cancel_event` was set
before an attempt was sent, or during a retry delay. It is deliberately
**not** a `HighApiError`: a cancellation is the caller's own decision, not a
failure. Never retry it, never report it as an API error, never count it
towards a failure budget.

The async client instead lets `asyncio.CancelledError` propagate unchanged.

## What to tell the user

When a call fails, report:

1. What was being attempted, in their terms — "placing the Reliance order",
   not "POST /orders".
2. The actual cause from `messages`, all of them.
3. `request_id`, so support can find it.
4. Whether anything was left in an uncertain state.

Do not silently swallow a failure and carry on to the next step of a
multi-step run. Stop, report, and let the user decide.
