"""Market-regime analysis: recent price history + implied/realized volatility.

Deterministic facts for the ``iron-condor`` skill. ``regime()`` looks back a few
months and returns realized-vol levels, trend vs moving averages, ranges/drawdown, ATM
implied vol, the IV-vs-RV premium, and an expected move — plus plain-English regime/trend
labels. The skill maps these facts to strategy parameters (delta, wings, skew).
"""

from __future__ import annotations

import math
import os
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

from . import chain as chain_mod
from .config import Config, DEFAULT, data_path


def _annualized_vol(log_ret: pd.Series, n: int) -> float:
    """Annualized realized volatility (%) from the last ``n`` daily log returns."""
    tail = log_ret.tail(n)
    if len(tail) < 2:
        return float("nan")
    return float(tail.std() * math.sqrt(252) * 100)


def _vol_regime_label(rv21: float) -> str:
    if rv21 < 13:
        return "low"
    if rv21 < 20:
        return "moderate"
    if rv21 < 30:
        return "elevated"
    return "high"


def _trend_label(spot: float, sma20: float, sma50: float) -> str:
    if spot > sma20 > sma50:
        return "strong_up"
    if spot > sma50:
        return "up"
    if spot < sma20 < sma50:
        return "strong_down"
    if spot < sma50:
        return "down"
    return "neutral"


def _atm_iv(chain_df: pd.DataFrame, cfg: Config) -> tuple[float | None, str | None, int | None]:
    """ATM implied vol (%) at the nearest expiration inside the DTE window."""
    sub = chain_df[(chain_df["dte"] >= cfg.dte_min) & (chain_df["dte"] <= cfg.dte_max)]
    if sub.empty:
        return None, None, None
    exp = sorted(sub["expiration"].unique())[0]
    e = sub[sub["expiration"] == exp]
    S = float(e["underlying"].iloc[0])
    atm_idx = (e["strike"] - S).abs().idxmin()
    iv = e.loc[atm_idx, "impliedVolatility"]
    iv_pct = round(float(iv) * 100, 1) if iv and iv > 0 else None
    return iv_pct, str(exp), int(e["dte"].iloc[0])


def regime(ticker: str, lookback: str = "6mo", cfg: Config = DEFAULT,
           persist_chain: bool = True) -> dict:
    """Compute the price/volatility regime for ``ticker``.

    Fetches price history (``lookback`` period) and a fresh option chain. When
    ``persist_chain`` is True the chain is written to ``data/<ticker>_chain.csv`` so a
    subsequent ``recommend --no-fetch`` can reuse it without a second download.
    """
    ticker = ticker.upper()
    tkr = yf.Ticker(chain_mod.to_yf(ticker))
    hist = tkr.history(period=lookback)
    close = hist["Close"]
    spot = float(close.iloc[-1])
    log_ret = np.log(close / close.shift(1)).dropna()

    rv21, rv63, rv126 = (_annualized_vol(log_ret, n) for n in (21, 63, 126))
    sma20 = float(close.rolling(20).mean().iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1])

    def window(n):
        w = close.tail(n)
        return {
            "low": round(float(w.min()), 2),
            "high": round(float(w.max()), 2),
            "range_pct": round(100 * (float(w.max()) / float(w.min()) - 1), 1),
            "change_pct": round(100 * (spot / float(w.iloc[0]) - 1), 1),
        }

    roll_max = close.tail(63).cummax()
    max_dd = float((close.tail(63) / roll_max - 1).min()) * 100

    # Fresh chain (persisted) for ATM IV + expected move, so a follow-up
    # `recommend --no-fetch` can reuse it without a second download.
    chain_df = chain_mod.fetch_chain(ticker, cfg)
    if persist_chain:
        path = data_path(f"{chain_mod.file_token(ticker)}_chain.csv")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        chain_df.to_csv(path, index=False)

    atm_iv, iv_exp, iv_dte = _atm_iv(chain_df, cfg)
    iv_rv_premium = None if atm_iv is None else round(atm_iv - rv21, 1)
    # 1-SD expected move to the IV expiration (calendar-day convention).
    expected_move = None
    if atm_iv is not None and iv_dte:
        expected_move = round(spot * (atm_iv / 100) * math.sqrt(iv_dte / 365), 2)

    return {
        "ticker": ticker,
        "lookback": lookback,
        "spot": round(spot, 2),
        "realized_vol": {"d21": round(rv21, 1), "d63": round(rv63, 1), "d126": round(rv126, 1)},
        "sma20": round(sma20, 2),
        "sma50": round(sma50, 2),
        "windows": {"d21": window(21), "d63": window(63), "d126": window(126)},
        "max_drawdown_63d_pct": round(max_dd, 1),
        "atm_iv": atm_iv,
        "atm_iv_expiration": iv_exp,
        "atm_iv_dte": iv_dte,
        "iv_rv_premium": iv_rv_premium,
        "expected_move_1sd": expected_move,
        "vol_regime": _vol_regime_label(rv21),
        "trend": _trend_label(spot, sma20, sma50),
        "premium_label": (None if iv_rv_premium is None
                          else "rich" if iv_rv_premium > 0 else "cheap"),
        "asof": datetime.now().date().isoformat(),
    }
