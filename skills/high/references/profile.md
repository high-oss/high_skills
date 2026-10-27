# Profile

Read-only account details for the authenticated client: identity, demat, enabled segments, address and linked bank accounts.

| Task | Call | HTTP |
|---|---|---|
| Account profile | `high.profile.get()` | `GET /profile` |

MCP equivalent: `high_get_profile`. Same auth as the portfolio reads (bearer access token). Read-only, so no static IP pin is needed.

```python
from scripts.high_helpers import get_client

with get_client() as high:
    profile = high.profile.get()
    print(profile.name, profile.depository, profile.segmentsAllowed)
    for bank in profile.bankAccounts:
        print(bank.bankName, bank.accountNumber, bank.isPrimary)
```

## Response

| Field | Notes |
|---|---|
| `clientId`, `name`, `email`, `mobile` | Identity |
| `pan`, `aadhaar` | **Masked** to the last 4 characters |
| `depository`, `boCode`, `dpCode` | Demat / DP details |
| `isPOAApproved`, `isNRI`, `isMTFEnabled` | Account flags |
| `segmentsAllowed` | `string[]` of enabled segments |
| `address` | `{address, city, state, pinCode}` |
| `bankAccounts` | `[{bankName, accountNumber, ifscCode, branch, isPrimary}]`; `accountNumber` **masked** to the last 4 characters |

No feed URLs or tokens are returned.

## Masking — never work around it

- `pan`, `aadhaar` and each `accountNumber` arrive masked. Show them as returned.
- Never ask the user for a full PAN, Aadhaar or bank account number, and never print or log one if the user volunteers it.
- Treat the rest as personal data: show only the fields the question needs, and do not write the profile to files, the trade journal or logs.

## Using it

- `segmentsAllowed` answers "can I trade F&O / currency / commodity" before building an order. A segment missing here is why an order for it is rejected.
- `isMTFEnabled` gates `productType="MTF"` orders.
- `bankAccounts` entry with `isPrimary` is the account funds settle to.
- Funds balance is a different call: see [funds.md](funds.md).
