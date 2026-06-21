"""Generate iron condor candidates from an annotated option chain.

Pure and deterministic: given a chain DataFrame (from :mod:`ic.chain`) and a
:class:`~ic.config.Config`, build one candidate condor per eligible expiration by placing
short strikes near the target delta and long wings ``wing_width`` away. The Claude
``recommend-condor`` skill applies judgment on top of this ranked list.
"""

from __future__ import annotations

import math
from typing import Optional

import pandas as pd

from .config import Config, DEFAULT


def _mid(row: pd.Series) -> Optional[float]:
    """Best available per-share price: bid/ask mid, falling back to lastPrice."""
    bid, ask = row.get("bid"), row.get("ask")
    if bid and ask and bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    last = row.get("lastPrice")
    if last and last > 0:
        return float(last)
    return None


def _spread_pct(row: pd.Series) -> Optional[float]:
    bid, ask = row.get("bid"), row.get("ask")
    if bid and ask and bid > 0 and ask > 0:
        return (ask - bid) / ((ask + bid) / 2.0)
    return None


def _nearest_by_delta(legs: pd.DataFrame, target_signed: float) -> Optional[pd.Series]:
    """Row whose delta is closest to ``target_signed`` (e.g. -0.10 for puts, +0.10 calls)."""
    valid = legs.dropna(subset=["delta"])
    if valid.empty:
        return None
    return valid.iloc[(valid["delta"] - target_signed).abs().argmin()]


def _nearest_by_strike(legs: pd.DataFrame, strike: float) -> Optional[pd.Series]:
    if legs.empty:
        return None
    return legs.iloc[(legs["strike"] - strike).abs().argmin()]


def _candidate_for_expiration(exp_df: pd.DataFrame, cfg: Config, ticker: str) -> Optional[dict]:
    puts = exp_df[exp_df["type"] == "P"]
    calls = exp_df[exp_df["type"] == "C"]
    if puts.empty or calls.empty:
        return None

    short_put = _nearest_by_delta(puts, -cfg.target_delta)
    short_call = _nearest_by_delta(calls, cfg.target_delta)
    if short_put is None or short_call is None:
        return None

    long_put = _nearest_by_strike(puts, short_put["strike"] - cfg.wing_width)
    long_call = _nearest_by_strike(calls, short_call["strike"] + cfg.wing_width)
    if long_put is None or long_call is None:
        return None

    legs = {
        "short_put": short_put, "long_put": long_put,
        "short_call": short_call, "long_call": long_call,
    }
    mids = {name: _mid(row) for name, row in legs.items()}
    if any(m is None for m in mids.values()):
        return None

    # Credit = collected on shorts minus paid on longs (per share).
    credit = mids["short_put"] + mids["short_call"] - mids["long_put"] - mids["long_call"]
    put_width = short_put["strike"] - long_put["strike"]
    call_width = long_call["strike"] - short_call["strike"]
    max_width = max(put_width, call_width)
    max_loss = max_width - credit  # per share; x100 per contract
    lower_be = short_put["strike"] - credit
    upper_be = short_call["strike"] + credit

    # Rough probability of profit: both shorts expire OTM (disjoint tails).
    pop = 1.0 - (abs(short_put["delta"]) + abs(short_call["delta"]))

    spreads = [s for s in (_spread_pct(r) for r in legs.values()) if s is not None]
    avg_spread = sum(spreads) / len(spreads) if spreads else math.nan
    min_oi = min(float(r.get("openInterest") or 0) for r in legs.values())
    total_vol = sum(float(r.get("volume") or 0) for r in legs.values())

    credit_to_width = credit / max_width if max_width else 0.0
    # Higher is better: reward credit relative to risk, penalize wide bid/ask spreads.
    score = credit_to_width - (avg_spread if not math.isnan(avg_spread) else 0.5)

    return {
        "ticker": ticker,
        "expiration": short_put["expiration"],
        "dte": int(short_put["dte"]),
        "underlying": float(short_put["underlying"]),
        "put_long_strike": float(long_put["strike"]),
        "put_short_strike": float(short_put["strike"]),
        "call_short_strike": float(short_call["strike"]),
        "call_long_strike": float(long_call["strike"]),
        "short_put_delta": round(float(short_put["delta"]), 4),
        "short_call_delta": round(float(short_call["delta"]), 4),
        "credit": round(credit, 2),
        "max_loss": round(max_loss, 2),
        "max_gain": round(credit, 2),
        "wing_width": round(max_width, 2),
        "credit_to_width": round(credit_to_width, 3),
        "lower_breakeven": round(lower_be, 2),
        "upper_breakeven": round(upper_be, 2),
        "est_pop": round(pop, 3),
        "avg_spread_pct": None if math.isnan(avg_spread) else round(avg_spread, 3),
        "min_open_interest": min_oi,
        "total_volume": total_vol,
        "score": round(score, 4),
    }


def build_condor_candidates(chain_df: pd.DataFrame, cfg: Config = DEFAULT, ticker: str = "") -> list[dict]:
    """Return one candidate condor per eligible expiration, ranked best-first by score."""
    eligible = chain_df[(chain_df["dte"] >= cfg.dte_min) & (chain_df["dte"] <= cfg.dte_max)]
    candidates = []
    for exp in sorted(eligible["expiration"].unique()):
        cand = _candidate_for_expiration(eligible[eligible["expiration"] == exp], cfg, ticker)
        if cand is not None:
            candidates.append(cand)
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates
