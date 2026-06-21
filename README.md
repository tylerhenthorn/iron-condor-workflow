# iron-condor-claude-workflow

A small toolkit for selling iron condors on SPY (or any optionable ticker), built as a
**hybrid** of deterministic Python and Claude judgment layers:

- **Python** (`ic/` package) does everything mechanical: pull the option chain, compute
  Black-Scholes greeks, generate condor candidates, keep a CSV database of open positions,
  and recompute live P&L / management triggers.
- **Claude skills** (`.claude/skills/`) apply judgment on top: pick the best candidate
  considering liquidity, and recommend defensive actions on open trades.

No broker API — fills are entered manually. Schema and code are multi-ticker.

## Install

```bash
pip install -r requirements.txt   # yfinance, pandas (numpy already present)
```

## The three features

### 1. Recommend a condor
```bash
python -m ic.cli recommend --ticker SPY            # human-readable, top 5
python -m ic.cli recommend --ticker SPY --json     # for the skill to consume
```
Targets ~0.10-delta short strikes, 30–45 DTE, $5 wings by default. Or invoke the
**`recommend-condor`** Claude skill for a single, liquidity-aware pick with rationale.

### 2. Track open condors (CSV database — `data/positions.csv`)
```bash
python -m ic.cli add --ticker SPY --expiration 2026-07-31 --contracts 1 \
  --put-long 590 --put-short 595 --call-short 640 --call-long 645 --credit 1.20
python -m ic.cli list
python -m ic.cli close --id 1 --debit 0.55         # records realized P&L
```

### 3. Analyze open condors
```bash
python -m ic.cli analyze            # live metrics + fired triggers per position
python -m ic.cli analyze --json     # for the skill to consume
```
Fires **delta / strike-breach** triggers (`DELTA_BREACH_*`, `STRIKE_TOUCHED_*`,
`GAMMA_RISK`, `PROFIT_TARGET`). Invoke the **`analyze-positions`** Claude skill to turn
those into roll / close / hold recommendations.

## Other commands
```bash
python -m ic.cli fetch --ticker SPY     # write data/SPY_chain.csv
```

## Strategy parameters
Defaults live in `ic/config.py` and can be overridden on any command:

| Flag | Default | Meaning |
|------|---------|---------|
| `--target-delta` | 0.10 | short-strike target delta |
| `--dte-min` / `--dte-max` | 30 / 45 | entry DTE window |
| `--wing-width` | 5.0 | strike points from short to long leg |
| `--defense-delta` | 0.30 | short-strike \|delta\| that fires `DELTA_BREACH` |
| `--min-dte-hold` | 21 | DTE that fires `GAMMA_RISK` |
| `--profit-take-pct` | 0.50 | credit fraction that fires `PROFIT_TARGET` |
| `--r` | 0.045 | risk-free rate for greeks |

## Layout
```
ic/         config, greeks, chain, candidates, positions, analyze, cli
data/       chain snapshots + positions.csv (gitignored)
.claude/skills/  recommend-condor, analyze-positions
```

## Out of scope (for now)
Broker/order execution, backtesting, non-condor strategies, intraday streaming. The
multi-ticker schema leaves room to add these later.
