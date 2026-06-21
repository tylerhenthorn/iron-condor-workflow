"""Analyze open iron condors and flag management triggers.

Deterministic core for Feature 3: for each open position, pull a fresh chain, recompute
short-strike deltas, cost-to-close, unrealized P&L, DTE remaining, and distance from the
underlying to each short strike, then fire delta/strike-breach triggers. The Claude
``analyze-positions`` skill turns these flags into concrete roll/close/hold recommendations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from . import chain as chain_mod
from . import positions as positions_mod
from .candidates import _mid
from .config import Config, DEFAULT


def _leg(exp_df: pd.DataFrame, strike: float, opt_type: str) -> Optional[pd.Series]:
    legs = exp_df[(exp_df["type"] == opt_type) & (exp_df["strike"] == float(strike))]
    if legs.empty:
        # Fall back to nearest strike if exact not present.
        same_type = exp_df[exp_df["type"] == opt_type]
        if same_type.empty:
            return None
        return same_type.iloc[(same_type["strike"] - float(strike)).abs().argmin()]
    return legs.iloc[0]


def analyze_position(row: pd.Series, chain_df: pd.DataFrame, cfg: Config = DEFAULT) -> dict:
    """Compute live metrics + fired triggers for a single open position row."""
    exp = str(row["expiration"])
    exp_df = chain_df[chain_df["expiration"] == exp]
    contracts = float(row.get("contracts") or 1)
    credit = float(row.get("credit_received") or 0)

    result = {
        "id": int(row["id"]),
        "ticker": row["ticker"],
        "expiration": exp,
        "contracts": contracts,
        "credit_received": credit,
        "triggers": [],
    }

    if exp_df.empty:
        result["error"] = "expiration not found in chain (expired or unlisted)"
        result["triggers"].append("EXPIRED_OR_MISSING")
        return result

    underlying = float(exp_df["underlying"].iloc[0])
    dte = int(exp_df["dte"].iloc[0])

    sp = _leg(exp_df, row["put_short_strike"], "P")
    sc = _leg(exp_df, row["call_short_strike"], "C")
    lp = _leg(exp_df, row["put_long_strike"], "P")
    lc = _leg(exp_df, row["call_long_strike"], "C")

    short_put_delta = float(sp["delta"]) if sp is not None and pd.notna(sp["delta"]) else None
    short_call_delta = float(sc["delta"]) if sc is not None and pd.notna(sc["delta"]) else None

    # Debit to close = buy back shorts, sell longs (same per-share formula as the credit).
    mids = {"sp": _mid(sp) if sp is not None else None,
            "sc": _mid(sc) if sc is not None else None,
            "lp": _mid(lp) if lp is not None else None,
            "lc": _mid(lc) if lc is not None else None}
    cost_to_close = None
    unrealized = None
    if all(m is not None for m in mids.values()):
        cost_to_close = mids["sp"] + mids["sc"] - mids["lp"] - mids["lc"]
        unrealized = (credit - cost_to_close) * 100 * contracts

    dist_to_put = underlying - float(row["put_short_strike"])    # >0 = above short put (safe)
    dist_to_call = float(row["call_short_strike"]) - underlying  # >0 = below short call (safe)

    result.update({
        "underlying": round(underlying, 2),
        "dte_remaining": dte,
        "short_put_strike": float(row["put_short_strike"]),
        "short_call_strike": float(row["call_short_strike"]),
        "short_put_delta": None if short_put_delta is None else round(short_put_delta, 4),
        "short_call_delta": None if short_call_delta is None else round(short_call_delta, 4),
        "dist_to_short_put": round(dist_to_put, 2),
        "dist_to_short_call": round(dist_to_call, 2),
        "cost_to_close": None if cost_to_close is None else round(cost_to_close, 2),
        "unrealized_pnl": None if unrealized is None else round(unrealized, 2),
    })

    # --- Triggers (delta / strike-breach primary) ---
    triggers = result["triggers"]
    if short_put_delta is not None and abs(short_put_delta) >= cfg.defense_delta:
        triggers.append("DELTA_BREACH_PUT")
    if short_call_delta is not None and short_call_delta >= cfg.defense_delta:
        triggers.append("DELTA_BREACH_CALL")
    if underlying <= float(row["put_short_strike"]):
        triggers.append("STRIKE_TOUCHED_PUT")
    if underlying >= float(row["call_short_strike"]):
        triggers.append("STRIKE_TOUCHED_CALL")
    if dte <= cfg.min_dte_hold:
        triggers.append("GAMMA_RISK")
    if unrealized is not None and unrealized >= cfg.profit_take_pct * credit * 100 * contracts:
        triggers.append("PROFIT_TARGET")

    return result


def analyze_open(cfg: Config = DEFAULT, fetch: bool = True) -> list[dict]:
    """Analyze every open position. Fetches a fresh chain per ticker (only needed expirations)."""
    df = positions_mod.open_positions()
    if df.empty:
        return []

    results = []
    for ticker, group in df.groupby("ticker"):
        exps = sorted(group["expiration"].astype(str).unique())
        if fetch:
            chain_df = chain_mod.fetch_chain(str(ticker), cfg, expirations=exps)
        else:
            chain_df = chain_mod.load_chain(str(ticker))
        for _, row in group.iterrows():
            results.append(analyze_position(row, chain_df, cfg))
    return results
