# iron-condor-workflow

## TL;DR

A small toolkit for selling iron condors on **SPX** or any optionable ticker, built as a **hybrid** of
deterministic Python and Claude judgment layers:

- **`/iron-condor`** — reads the recent price history and vol regime for an underlying
  (SPX by default) and recommends a condor — strikes, wings, and skew tuned to the data,
  with the reasoning. Use it to open a new trade.
  ```
  /iron-condor                 # regime-aware SPX pick
  /iron-condor SPY             # any ticker
  ```
- **`/analyze-positions`** — reviews your open condors (from `data/positions.csv`),
  recomputes live P&L and management triggers, and tells you whether to **roll, close, or
  hold** each one. Use it to maintain trades you already have on.
  ```
  /analyze-positions
  ```

Typical loop: run `/iron-condor` to get a recommendation → record the fill with
`python -m ic.cli add ...` → run `/analyze-positions` whenever you want to check on open
trades. Everything below is the underlying CLI the skills drive.

- **Python** (`ic/` package) does everything mechanical: pull the option chain, compute
  Black-Scholes greeks, generate condor candidates, keep a CSV database of open positions,
  and recompute live P&L / management triggers.
- **Claude skills** (`.claude/skills/`) apply judgment on top: pick the best candidate
  considering liquidity, and recommend defensive actions on open trades.

No broker API — fills are entered manually. Schema and code are multi-ticker.

**Underlying:** the default is **SPX**. Index aliases (`SPX`, `XSP`, `NDX`, ...) resolve
to their yfinance `^`-symbols automatically; pass `--ticker SPY` for the ETF. `--wing-width`
is in index points, so scale it to the underlying's price (SPX ~50, SPY/XSP ~5–10, single
names ~10–25). Note: yfinance under-reports **open interest for index options** (often 0) —
judge index liquidity by bid/ask spread, not reported OI.

## Install

```bash
pip install -r requirements.txt   # yfinance, pandas (numpy already present)
```

## The three features

### 1. Recommend a condor
```bash
python -m ic.cli recommend            # SPX by default, human-readable, top 5
python -m ic.cli recommend --json     # for the skill to consume
```
Targets ~0.10-delta short strikes, 30–45 DTE, $50 wings by default (SPX scale). Or invoke
the **`iron-condor`** Claude skill for a single, liquidity-aware pick with rationale.

### 2. Track open condors (CSV database — `data/positions.csv`)
```bash
python -m ic.cli add --ticker SPX --expiration 2026-07-31 --contracts 1 \
  --put-long 6835 --put-short 6885 --call-short 7950 --call-long 8000 --credit 6.15
python -m ic.cli list
python -m ic.cli close --id 1 --debit 3.00         # records realized P&L
```

### 3. Analyze open condors
```bash
python -m ic.cli analyze            # live metrics + fired triggers per position
python -m ic.cli analyze --json     # for the skill to consume
```
Fires **delta / strike-breach** triggers (`DELTA_BREACH_*`, `STRIKE_TOUCHED_*`,
`GAMMA_RISK`, `PROFIT_TARGET`). Invoke the **`analyze-positions`** Claude skill to turn
those into roll / close / hold recommendations.

### Regime-aware recommendation
```bash
python -m ic.cli regime --lookback 6mo                     # SPX trend + realized/implied vol read
python -m ic.cli recommend --no-fetch \
  --put-delta 0.16 --call-delta 0.10 --wing-width 50        # skewed condor (leans with the trend)
```
The **`iron-condor`** Claude skill chains these: it reads the regime (trend, vol
level, IV-vs-RV premium), chooses delta/wings/skew from it, then recommends a condor and
explains the reasoning. Use it when you want the parameters picked from the data rather
than supplied. `--put-delta`/`--call-delta` build a **skewed** condor; pass them equal (or
use `--target-delta`) for a symmetric one.

## Other commands
```bash
python -m ic.cli fetch                  # SPX by default -> data/SPX_chain.csv
python -m ic.cli fetch --ticker SPY     # write data/SPY_chain.csv
```

## Strategy parameters
Defaults live in `ic/config.py` and can be overridden on any command:

| Flag | Default | Meaning |
|------|---------|---------|
| `--target-delta` | 0.10 | short-strike target delta |
| `--dte-min` / `--dte-max` | 30 / 45 | entry DTE window |
| `--wing-width` | 50.0 | strike points from short to long leg (SPX scale; lower for cheaper underlyings) |
| `--defense-delta` | 0.30 | short-strike \|delta\| that fires `DELTA_BREACH` |
| `--min-dte-hold` | 21 | DTE that fires `GAMMA_RISK` |
| `--profit-take-pct` | 0.50 | credit fraction that fires `PROFIT_TARGET` |
| `--r` | 0.045 | risk-free rate for greeks |

## Layout
```
ic/         config, greeks, chain, candidates, positions, analyze, cli
data/       chain snapshots + positions.csv (gitignored)
.claude/skills/  iron-condor, analyze-positions
```

## Out of scope (for now)
Broker/order execution, backtesting, non-condor strategies, intraday streaming. The
multi-ticker schema leaves room to add these later.
