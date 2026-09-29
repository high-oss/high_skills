# HIGH Agent Skills

Use the HIGH Open API inside AI agents like Claude Code, Codex or any other agent of your choice.

**HIGH-native agent skill for NSE/BSE equity and F&O trading.**

Give your AI agent the ability to place live orders across all four order flavors, read real portfolio data, stream the live datafeed, and resolve the full instrument universe of Indian exchanges — all through the [HIGH Open API](https://openapi.high.live).

Built for the [Agent Skills open standard](https://agentskills.io) and compatible with Claude Code, Codex, and any agent that supports SKILL.md.

---

## Installation

**You don't need to clone the repository. Install the skill directly with `npx`.**

### Global install

```bash
npm install -g skills
skills add high-oss/high_skills --skill high
```

### Claude Code or Codex

```bash
npx skills add high-oss/high_skills --skill high
```

OR

```bash
npx @high-oss/high-skill
```

---

## After Installation

Once installed, your AI agent can automatically use the `high` skill when your prompt involves the HIGH Open API, Indian market data, portfolio, orders, funds, or trading workflows.

Example prompts:

- Show my holdings
- Get daily OHLC for RELIANCE for the last 6 months
- Show the Nifty option chain for the nearest expiry
- Check the margin required to sell 1 lot of Nifty
- Put a bracket order on Reliance with a 2% target and a 1% stop
- Set a GTT to buy TCS if it drops to 3000

## Requirements

- Python 3.9+ and `pip install high-openapi`
- **Order APIs**: the API key's static IP pinned in the [HIGH developer portal](https://openapi.high.live)
- **Live datafeed**: production only — there is no sandbox feed
- Credentials via environment variables: `HIGH_API_KEY` and `HIGH_ACCESS_TOKEN`

---

## What's Included

```
skills/
└── high/
    ├── SKILL.md                          # Entry point — setup, safety rules, order flavors
    │
    ├── references/                       # Deep-dive docs loaded on demand
    │   ├── orders.md                     # All four flavors: REGULAR, BO, CO, GTT
    │   ├── portfolio.md                  # Positions, holdings, conversion, exits
    │   ├── market-data.md                # Quotes, OHLC, depth, historical candles
    │   ├── option-chain.md               # Option chain and expiries
    │   ├── instruments.md                # Instrument master, the three identifier forms
    │   ├── funds.md                      # Funds, charges, basket margin
    │   ├── live-feed.md                  # WebSocket: quotes, depth, indices
    │   ├── error-codes.md                # Status codes, validator messages, retries
    │   ├── auth-and-credentials.md       # API key, access token, TOTP, consent, static IP
    │   ├── common-workflows.md           # Multi-step patterns (roll-up, rebalance, recovery)
    │   ├── options-analysis-patterns.md  # PCR, max pain, payoff, IV skew
    │   └── backtesting-with-high.md      # Backtest patterns with an honest cost model
    │
    ├── scripts/
    │   ├── high_helpers.py               # Client construction, config, errors, confirmation
    │   ├── resolve_symbol.py             # Name → tradingSymbol + exchange + scripCode
    │   ├── validate_order.py             # Pre-flight validation mirroring the server's rules
    │   └── trade_logger.py               # Append-only trade journal
    │
    └── examples/
        ├── place_equity_order.py         # Plain delivery equity order, end to end
        ├── place_fno_order.py            # F&O order with lot-size validation
        ├── bracket_order.py              # BO: entry + target + trailing stop
        ├── cover_order.py                # CO: entry + compulsory stop, no target
        ├── gtt_order.py                  # GTT: a resting trigger
        ├── order_management.py           # Place, read, modify, cancel; uncertain-write recovery
        ├── fetch_option_chain.py         # Chain with ATM region and PCR
        ├── iron_condor.py                # Four legs: build, margin as a basket, place
        ├── portfolio_summary.py          # Holdings + positions + funds; guarded exit-all
        ├── margin_check.py               # Affordability before placing
        ├── historical_data_analysis.py   # Candles, moving averages, statistics
        └── live_feed_setup.py            # Live quotes, depth and index ticks
```

---

## How It Works

The skill follows **progressive disclosure** to minimize context usage:

1. **SKILL.md** gives the agent setup, safety rules, the order-flavor model, constants and core code patterns — enough for 80% of tasks.
2. **references/*.md** are loaded only when a task needs deeper detail (full parameter tables, WebSocket setup, error taxonomy).
3. **scripts/** provide reusable utilities the agent can call directly.
4. **examples/** are complete, runnable scripts the agent can reference or adapt.

---

## Safety

The skill keeps an agent a knowledgeable assistant, not an autonomous trader.

- **Orders wait for you.** Nothing is placed without a readable preview and an explicit confirmation.
- **LIMIT by default.** `MARKET` only when you ask for it.
- **A quantity cap and a value cap per order**, set in `config.json`, so a misunderstanding cannot become an oversized order.
- **Lot-size validation** for F&O, with the nearest valid quantity named.
- **Product × flavor checked locally** — `BO`/`CO` are intraday-only, `GTT` is delivery/MTF-only — so a mistake is a readable message, not a `400`.
- **No trading outside market hours** unless you explicitly asked for an after-market order.
- **Sandbox by default.** Production is opt-in.
- **Credentials never leave the environment.** Nothing is hardcoded, and the trade journal redacts anything key-shaped.

Copy `config.json.example` to `config.json` to change the caps and defaults.

---

## When Agents Use This Skill

The skill activates when the user:

- Wants to **place, modify, or cancel** equity or F&O orders, including **bracket, cover and GTT** orders
- Asks about **portfolio holdings, positions or funds**, or wants to **exit** a position
- Needs **live or historical market data** (quotes, OHLC, depth, candles)
- Wants to work with **option chains** or expiries
- Asks about **margin or charges**
- Needs to **resolve a symbol** to its trading symbol or scrip code
- Wants to **stream the live datafeed**
- Mentions **HIGH**, the **HIGH Open API**, or **high.live**

---

## Related

- [HIGH Open API documentation](https://openapi.high.live)
- [high-openapi Python SDK](https://github.com/high-oss/high-sdk-python)

## License

MIT — see [LICENSE](LICENSE).
