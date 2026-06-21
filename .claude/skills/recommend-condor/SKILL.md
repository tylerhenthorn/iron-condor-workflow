---
name: recommend-condor
description: Recommend a single iron condor to open on a given underlying (default SPY). Use when the user asks for a trade idea, an iron condor to sell/open, or "what should I trade". Runs the deterministic candidate generator, then applies liquidity/credit judgment to pick one.
---

# Recommend an iron condor

You turn the deterministic candidate list from `ic/candidates.py` into a single,
well-reasoned recommendation. The Python does the math; you do the judgment.

## Steps

1. Generate candidates (fetches a fresh chain automatically):

   ```
   python -m ic.cli recommend --ticker <TICKER> --json --top 8
   ```

   Default ticker is SPY. Honor any strategy overrides the user mentions, e.g.
   `--target-delta 0.16`, `--dte-min 30 --dte-max 45`, `--wing-width 10`.

2. Each candidate JSON object includes: `expiration`, `dte`, the four strikes, short-leg
   deltas, `credit`, `max_loss`, `wing_width`, `credit_to_width`, breakevens, `est_pop`,
   and liquidity fields (`avg_spread_pct`, `min_open_interest`, `total_volume`, `score`).

3. Pick ONE candidate using this judgment (the list is pre-ranked by `score`, but verify):
   - **Liquidity first** — prefer tight `avg_spread_pct` (≲ 0.10) and healthy
     `min_open_interest`/`total_volume`. A great-looking credit on illiquid strikes is a trap.
   - **Credit vs risk** — favor `credit_to_width` ≳ 0.33 (collect ~1/3 of the width).
   - **Balance** — short put and short call deltas should be roughly symmetric.
   - **DTE** — stay inside the requested window; prefer the middle of it.
   - Note (don't silently ignore) anything near a known earnings/macro event.

4. Present the recommendation:
   - The exact four legs (long put / short put / short call / long call) and expiration.
   - Credit, max gain, max loss, both breakevens, estimated PoP.
   - A 2-3 sentence rationale referencing liquidity and credit/width.
   - The ready-to-run command to record it **if the user fills it**:

     ```
     python -m ic.cli add --ticker <T> --expiration <YYYY-MM-DD> --contracts <N> \
       --put-long <K> --put-short <K> --call-short <K> --call-long <K> \
       --credit <net> --spd <short_put_delta> --scd <short_call_delta>
     ```

## Notes
- Do not invent prices — only use values returned by the CLI.
- If `recommend` returns an empty list, widen the DTE window or report that no liquid
  condor fits the criteria today.
