# Auth and credentials

Two credentials, two audiences, and one network requirement that catches
everyone. Get this wrong and every other call fails in ways that look like
other problems.

## The two credentials

| Credential | Header | Used by |
|---|---|---|
| **API key** | `x-api-key` | The `/auth/*` operations only |
| **Access token** | `Authorization: Bearer ...` | Every other operation |

The split is deliberate: the API key mints access tokens, so it must keep
working after the access token expires. The SDK attaches the right one per
operation — supply both and stop thinking about it.

```python
import os
from high_openapi import HighClient

high = HighClient(
    environment="sandbox",
    api_key=os.environ["HIGH_API_KEY"],
    access_token=os.environ["HIGH_ACCESS_TOKEN"],
)
```

Environment variables the SDK reads unaided:

```
HIGH_API_KEY
HIGH_ACCESS_TOKEN
HIGH_ENVIRONMENT      sandbox | production
HIGH_BASE_URL         overrides the host outright
```

**Never** hardcode either credential in generated code, a notebook cell, a
config committed to a repo, or a log line.

## Environments

| Environment | REST host | Datafeed |
|---|---|---|
| `production` | `https://openapi.high.live` | `wss://openapi-feed.high.live` |
| `sandbox` | `https://sandbox.high.live` | **none** |

This skill defaults to `sandbox`. Production is opt-in.

Pass `environment=` explicitly whenever it matters. An explicit value
suppresses `HIGH_BASE_URL` entirely, so a client written as
`environment="sandbox"` can never be silently rerouted to production by a
stray variable left in a shell profile. That is the whole reason to pass it.

There is no sandbox datafeed. `HighFeed` and `AsyncHighFeed` refuse to
construct when the resolved environment is `sandbox`, rather than connecting
to a host nothing serves.

## Getting an access token

### TOTP — the automation path

```python
token = high.auth.generate_access_token(client_id, t_otp)
```

`HTTP GET /auth/generate-access-token?clientId=...&tOtp=...`, authenticated
with the API key. `tOtp` is the six-digit code from the authenticator app
bound to the account.

The helper wraps it:

```python
from scripts.high_helpers import refresh_access_token

token = refresh_access_token(client_id="...", t_otp="123456")
# export it as HIGH_ACCESS_TOKEN for later calls
```

A TOTP code is valid for one short window. Never cache one, never ask the
user for "your TOTP" in advance of needing it, and never write one to a log
or a journal — `trade_logger.py` redacts it if it ever reaches an entry.

### Consent — the redirect path

For applications logging a user in rather than running as the account holder:

1. `GET /auth/generate-consent?clientId=...` — returns a consent URL.
2. Send the user to it. They authenticate with HIGH.
3. HIGH redirects back with a `tokenId`.
4. `GET /auth/consume-consent?tokenId=...` — exchanges it for an access token.

All three are API-key authenticated. The `tokenId` is single-use and
short-lived.

An agent running scripts for its own user wants the TOTP path, not this one.

### Checking a token

```
GET /auth/validate-token       (bearer)
```

Cheap, and worth doing before a long run rather than discovering expiry
halfway through a multi-leg execution.

## Static IP pinning

**The failure everyone hits.** Order writes require the API key's source IP
to be pinned in the HIGH developer portal:

- `POST /orders` — place
- `PATCH /orders` — modify
- `DELETE /orders/{orderId}` — cancel
- `PATCH /portfolio/positions/convert`
- `DELETE /portfolio/positions/exit`
- `DELETE /portfolio/positions/exit/all`

Reads are unaffected. So a session where quotes, holdings and the order book
all work but every placement fails is an IP pin problem, not a credential
problem.

Symptoms:

- `403`, not `401`. A `401` is an expired or wrong token; a `403` on an
  otherwise valid order body is the pin.
- It appears the moment the machine's public IP changes — a new network, a
  VPN toggling, a laptop moving, a cloud instance being recreated.

Fix: find the current public IP, pin it against the key in the developer
portal, retry. A dynamic residential IP will need re-pinning whenever it
rotates; for anything long-running, use a host with a fixed address.

## Rotation and revocation

- Access tokens expire. Re-mint with TOTP; the API key keeps working.
- API keys are revoked in the developer portal. A revoked key fails the
  `/auth/*` operations first, which is the signal.
- Rotating a key does not invalidate access tokens already minted from it —
  do not assume rotation is an emergency stop. Revoke the token path too.

## What not to do

- Do not put credentials in the command the agent prints. They end up in
  shell history.
- Do not read a token from one environment and use it against the other.
  Sandbox and production tokens are not interchangeable.
- Do not retry a `401` in a loop. Re-mint once, then stop.
- Do not ask the user to paste an API key into a chat. Point them at the
  environment variable.

See [error-codes.md](error-codes.md) for the full status-code table.
