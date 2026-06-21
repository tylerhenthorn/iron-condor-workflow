"""Tunable defaults for the iron condor toolkit.

Every value here is overridable via CLI flags (see ``ic/cli.py``). Keeping them in one
dataclass makes the strategy parameters explicit and easy to tweak without hunting
through the code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Directory where chain and position CSVs live. Override with IC_DATA_DIR.
DATA_DIR = os.environ.get("IC_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))


@dataclass
class Config:
    # --- Entry selection ---
    target_delta: float = 0.10   # short strikes placed near this absolute delta (~1.3 SD)
    dte_min: int = 30            # minimum days-to-expiration for entry
    dte_max: int = 45            # maximum days-to-expiration for entry
    wing_width: float = 5.0      # distance (in strike points) from short to long leg

    # --- Management triggers ---
    defense_delta: float = 0.30  # short-strike |delta| at/above this fires DELTA_BREACH
    min_dte_hold: int = 21       # DTE at/below this fires GAMMA_RISK (gamma/assignment risk)
    profit_take_pct: float = 0.50  # capture this fraction of credit -> PROFIT_TARGET (secondary)

    # --- Pricing ---
    r: float = 0.045             # risk-free rate used for Black-Scholes greeks


DEFAULT = Config()


def data_path(filename: str) -> str:
    """Absolute path to a file inside the data directory (created on demand by callers)."""
    return os.path.join(DATA_DIR, filename)
