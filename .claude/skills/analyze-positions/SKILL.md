---
name: analyze-positions
description: Analyze currently-open iron condor positions and recommend defensive actions (roll, close, or hold). Use when the user asks to review/check their open trades, asks "what should I do with my positions", or asks about rolling/defending a condor.
---

# Analyze open iron condors

You turn the deterministic position metrics + triggers from `ic/analyze.py` into concrete
management recommendations. The Python recomputes live greeks and P&L; you decide the action.

## Steps

1. Pull live metrics for every open position (fetches fresh chains automatically):

   ```
   python -m ic.cli analyze --json
   ```

   Each result object includes: `id`, `ticker`, `expiration`, `underlying`,
   `dte_remaining`, `short_put_strike`/`short_call_strike` and their live deltas,
   `dist_to_short_put`/`dist_to_short_call` (points of cushion), `cost_to_close`,
   `unrealized_pnl`, and a `triggers` list.

2. Interpret the triggers (management style is **delta / strike-breach based**):
   - `DELTA_BREACH_PUT` / `DELTA_BREACH_CALL` — that short strike's |delta| ≥ the defense
     threshold (default 0.30). The tested side is under pressure.
   - `STRIKE_TOUCHED_PUT` / `STRIKE_TOUCHED_CALL` — underlying has reached/passed a short
     strike. Most urgent.
   - `GAMMA_RISK` — DTE ≤ 21; gamma/assignment risk rising, prefer to act rather than hold.
   - `PROFIT_TARGET` — captured ≥ 50% of credit; consider taking profit (secondary signal).

3. Recommend an action per position, tied to the fired triggers and P&L:
   - **Roll the untested side** toward the money to collect more credit and re-center,
     when one side is tested (`DELTA_BREACH`/`STRIKE_TOUCHED`) but the position is defensible.
   - **Roll out / roll out-and-down(up) the tested side** when the breach is deeper or DTE
     is short — buy more time/distance for a net credit if possible.
   - **Close** when the loss is approaching your risk limit, both sides are pressured, or
     defense can no longer be done for a credit.
   - **Take profit / close** on `PROFIT_TARGET`.
   - **Hold** when no triggers fired and there is comfortable cushion.

4. Present, per position: current state (underlying, DTE, P&L, deltas, cushion), the fired
   triggers in plain English, your recommended action, and the rationale. When you suggest
   closing, give the command:

   ```
   python -m ic.cli close --id <ID> --debit <net_debit_to_close>
   ```

## Notes
- Only use numbers returned by the CLI; never estimate live prices yourself.
- If a position shows `EXPIRED_OR_MISSING`, tell the user it expired or is no longer listed
  and should be reconciled/closed in the tracker.
- Mention `cost_to_close` so the user knows the current debit to exit.
