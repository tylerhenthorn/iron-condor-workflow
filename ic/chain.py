"""Fetch an options chain from yfinance and annotate every row with Black-Scholes delta.

Refactor of the original ``fetch-chain.py``: works for any ticker, uses the self-contained
greeks in :mod:`ic.greeks` (no ``py_vollib``), and writes to ``data/<ticker>_chain.csv``.
"""

from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import yfinance as yf

from . import greeks
from .config import Config, DEFAULT, data_path


def spot_price(tkr: "yf.Ticker") -> float:
    """Latest traded price for the underlying."""
    return float(tkr.history(period="1d")["Close"].iloc[-1])


def fetch_chain(ticker: str, cfg: Config = DEFAULT, expirations=None) -> pd.DataFrame:
    """Return a DataFrame of the full option chain for ``ticker`` with a ``delta`` column.

    Columns are whatever yfinance provides (strike, bid, ask, impliedVolatility,
    openInterest, volume, ...) plus ``underlying``, ``expiration``, ``type`` ("C"/"P"),
    ``dte``, and ``delta``. ``expirations`` may be an iterable subset of expiry strings to
    limit the fetch (used by the analyzer); defaults to all listed expirations.
    """
    tkr = yf.Ticker(ticker)
    S = spot_price(tkr)
    today = datetime.now().date()
    listed = list(tkr.options)
    if expirations is not None:
        # Only request expirations the broker actually still lists (skip expired ones).
        exps = [e for e in expirations if e in listed]
    else:
        exps = listed

    frames = []
    for exp in exps:
        chain = tkr.option_chain(exp)
        dte = max((datetime.strptime(exp, "%Y-%m-%d").date() - today).days, 1)
        T = dte / 365.0
        for df, flag in [(chain.calls, "c"), (chain.puts, "p")]:
            df = df.assign(underlying=S, expiration=exp, type=flag.upper(), dte=dte)
            df["delta"] = df.apply(
                lambda row: greeks.delta(flag, S, row["strike"], T, cfg.r, row["impliedVolatility"])
                if row["impliedVolatility"] and row["impliedVolatility"] > 0 else None,
                axis=1,
            )
            frames.append(df)

    return pd.concat(frames, ignore_index=True)


def write_chain(ticker: str, cfg: Config = DEFAULT) -> str:
    """Fetch and persist the chain to ``data/<ticker>_chain.csv``; return the path."""
    df = fetch_chain(ticker, cfg)
    os.makedirs(os.path.dirname(data_path(f"{ticker}_chain.csv")), exist_ok=True)
    path = data_path(f"{ticker.upper()}_chain.csv")
    df.to_csv(path, index=False)
    return path


def load_chain(ticker: str) -> pd.DataFrame:
    """Load the most recently written chain CSV for ``ticker``."""
    return pd.read_csv(data_path(f"{ticker.upper()}_chain.csv"))
