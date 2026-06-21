---
name: condor-from-history
description: Analyze the last few months of an underlying's price history and implied/realized volatility, then recommend a (possibly skewed) iron condor tuned to that regime. Use when the user asks for a recommendation "based on recent history/volatility", a market-aware or regime-based condor, or wants the strategy parameters chosen from the data rather than supplied.
---

# Regime-aware iron condor

You read the market regime (trend + volatility), choose the strategy parameters from it
(delta, wing width, and any skew), then generate and present a condor. The Python
(`ic/market.py`) supplies the deterministic facts; you supply the judgment that maps
those facts to parameters. This is the automated version of the manual analysis a user
might otherwise ask for.

## Steps

1. **Pull the regime** (fetches history + a fresh chain, and persists the chain so the
   later `recommend` can reuse it):

   ```
   python -m ic.cli regime --ticker <TICKER> --lookback 6mo --json
   ```

   Key fields: `spot`, `sma20`/`sma50`, `trend` (strong_up | up | neutral | down |
   strong_down), `realized_vol.d21/d63/d126`, `vol_regime` (low | moderate | elevated |
   high), `atm_iv`, `iv_rv_premium` + `premium_label` (rich | cheap), `expected_move_1sd`,
   the `windows` ranges, and `max_drawdown_63d_pct`.

2. **Map the regime to parameters** using this judgment (adapt, don't apply blindly):

   - **Premium (IV vs RV) sets how greedy to be on delta:**
     - `rich` and meaningful (IV − RV ≳ 3 pts) → standard ~0.16-delta shorts are justified.
     - thin (`iv_rv_premium` ~0–3 pts) → favor probability: ~0.10–0.12-delta shorts.
     - `cheap` (IV < RV) → condor edge is weak; either pass, go very wide (~0.08 delta),
       or tell the user the premium isn't there.
   - **Vol regime sets wing width / DTE:**
     - `low`/`moderate` → wings $10 (room for credit without huge max loss); 30–45 DTE.
     - `elevated` → wider wings ($15–20) and/or push toward 45 DTE; shorts stay far out.
     - `high` → smaller size, wider wings, lower delta; note the elevated tail risk.
   - **Trend sets the skew** (use the `--put-delta`/`--call-delta` overrides):
     - `up`/`strong_up` → skew the tent up: put short closer (higher delta, e.g. 0.16),
       call short farther (lower delta, e.g. 0.10). More upside room where price is drifting.
     - `down`/`strong_down` → mirror it: call short closer, put short farther.
     - `neutral` → symmetric (equal put/call delta).
   - **Sanity-check against `expected_move_1sd`:** the short strikes should sit beyond the
     1-SD expected move; if a chosen delta puts a short inside it, widen.

3. **Generate the condor** with the chosen parameters (reuse the persisted chain):

   ```
   python -m ic.cli recommend --ticker <TICKER> --no-fetch --json --top 3 \
     --put-delta <p> --call-delta <c> --wing-width <w>
   ```

   For a symmetric condor pass equal `--put-delta`/`--call-delta` (or `--target-delta`).
   Pick ONE candidate using the usual liquidity/credit checks (tight `avg_spread_pct`,
   healthy `min_open_interest`, prefer the middle of the DTE window).

4. **Present the recommendation**, explicitly tying choices back to the regime:
   - One short paragraph on the regime read (trend, vol level, IV-vs-RV premium).
   - Why these parameters (delta/wings/skew) follow from that read.
   - The exact four legs + expiration, credit, max gain/loss, breakevens, est. PoP, and
     the put/call cushion in points and in SD (vs `expected_move_1sd`).
   - A caveat line: check for FOMC/CPI inside the window; note the credit/width honestly.
   - The ready-to-run `add` command if the user fills it:

     ```
     python -m ic.cli add --ticker <T> --expiration <YYYY-MM-DD> --contracts <N> \
       --put-long <K> --put-short <K> --call-short <K> --call-long <K> \
       --credit <net> --spd <short_put_delta> --scd <short_call_delta>
     ```

## Notes
- Only use numbers returned by the CLI — never invent prices, IV, or deltas.
- Default `--lookback` is 6mo; honor a different window if the user names one.
- If `iv_rv_premium` is clearly negative, say so plainly and let the user decide rather
  than forcing a marginal trade.
- State the regime→parameter reasoning so the user can override your judgment.
