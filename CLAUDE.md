# CLAUDE.md

Operational notes for working in this repo. See `README.md` for the full design.

## Running the Python tools — use the venv

Dependencies (`pandas`, `yfinance`) are installed **only** in `.venv`, not the system
Python. Always invoke the CLI through the venv interpreter:

```bash
.venv/bin/python -m ic.cli <command> ...
```

Do **not** run `python -m ic.cli ...` (the bare `python` lacks `pandas` and will fail
with `ModuleNotFoundError: No module named 'pandas'`). No `source activate` /
`pip install` step is needed — the venv already exists and is populated.

## CLI commands (`ic.cli`)

| Command | What it does |
|---|---|
| `regime`    | Recent price history + implied/realized vol read (use `--json`) |
| `recommend` | Generate condor candidates (use `--json`, `--top N`) |
| `fetch`     | Fetch and persist an option chain |
| `add`       | Record a manually-filled position into `data/positions.csv` |
| `list`      | List recorded positions |
| `analyze`   | Recompute live P&L and flag management triggers |
| `close`     | Close a position and record realized P&L |

Common flags: `--ticker` (default **SPX**), `--lookback` (default `6mo`), `--json`.
`regime` persists the fetched chain so a follow-up `recommend --no-fetch` reuses it
(one network pull instead of two).

## Conventions

- **Default underlying is SPX** (cash-settled, §1256). Index aliases resolve to yfinance
  `^`-symbols automatically; pass `--ticker SPY` etc. for ETFs/single names.
- `--wing-width` is in index points — scale to the underlying (SPX ~50, SPY/XSP ~5–10,
  single names ~10–25).
- For **index** options, yfinance under-reports open interest — judge liquidity by
  `avg_spread_pct`, not `min_open_interest`.
- Only use numbers returned by the CLI; never invent prices, IV, or deltas.
