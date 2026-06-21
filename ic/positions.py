"""CSV-backed database of iron condor positions.

The "database" is a single CSV at ``data/positions.csv``. Fills are entered manually
(no broker API), so this module just owns the schema and safe load/add/update/close
operations keyed by an integer ``id``.
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd

from .config import data_path

POSITIONS_CSV = data_path("positions.csv")

COLUMNS = [
    "id", "ticker", "strategy", "status",
    "open_date", "expiration", "dte_at_open", "contracts",
    "put_long_strike", "put_short_strike", "call_short_strike", "call_long_strike",
    "credit_received", "underlying_at_open",
    "short_put_delta_at_open", "short_call_delta_at_open",
    "close_date", "close_debit", "realized_pnl", "notes",
]

STATUSES = {"open", "closed", "rolled"}


def load() -> pd.DataFrame:
    """Return the positions table, creating an empty one (with headers) if absent."""
    if not os.path.exists(POSITIONS_CSV):
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(POSITIONS_CSV)
    # Tolerate older files missing newer columns.
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df[COLUMNS]


def _save(df: pd.DataFrame) -> None:
    os.makedirs(os.path.dirname(POSITIONS_CSV), exist_ok=True)
    df[COLUMNS].to_csv(POSITIONS_CSV, index=False)


def _next_id(df: pd.DataFrame) -> int:
    if df.empty or df["id"].dropna().empty:
        return 1
    return int(df["id"].dropna().astype(int).max()) + 1


def add(position: dict) -> int:
    """Append a new position. Defaults strategy/status/open_date; returns the new id."""
    df = load()
    new_id = _next_id(df)
    row = {c: position.get(c) for c in COLUMNS}
    row["id"] = new_id
    row.setdefault("strategy", "iron_condor")
    row["strategy"] = row.get("strategy") or "iron_condor"
    row["status"] = row.get("status") or "open"
    row["open_date"] = row.get("open_date") or date.today().isoformat()
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _save(df)
    return new_id


def update(position_id: int, **fields) -> None:
    """In-place update of the row with ``id == position_id``."""
    df = load()
    mask = df["id"].astype("Int64") == int(position_id)
    if not mask.any():
        raise KeyError(f"No position with id {position_id}")
    for key, value in fields.items():
        if key not in COLUMNS:
            raise KeyError(f"Unknown column: {key}")
        # Columns load as float64 when previously all-NaN; widen to object so we can store
        # strings (dates) or mixed values without pandas raising LossySetitemError.
        if df[key].dtype != object and isinstance(value, str):
            df[key] = df[key].astype(object)
        df.loc[mask, key] = value
    _save(df)


def close(position_id: int, close_debit: float, close_date: str | None = None) -> float:
    """Close a position: record the debit paid, realized P&L, and mark status=closed.

    Realized P&L = (credit received - debit paid) x 100 x contracts.
    Returns the realized P&L.
    """
    df = load()
    mask = df["id"].astype("Int64") == int(position_id)
    if not mask.any():
        raise KeyError(f"No position with id {position_id}")
    row = df[mask].iloc[0]
    contracts = float(row.get("contracts") or 1)
    credit = float(row.get("credit_received") or 0)
    realized = (credit - float(close_debit)) * 100 * contracts
    update(
        position_id,
        status="closed",
        close_debit=close_debit,
        close_date=close_date or date.today().isoformat(),
        realized_pnl=round(realized, 2),
    )
    return round(realized, 2)


def open_positions() -> pd.DataFrame:
    """Subset of positions with status == 'open'."""
    df = load()
    return df[df["status"] == "open"]
