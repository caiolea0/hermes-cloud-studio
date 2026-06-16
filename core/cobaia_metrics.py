"""F.7 C2 — Cobaia daily metrics helpers.

Thin SQLite wrappers over cobaia_warmup_state + cobaia_daily_metrics tables.
All writes are idempotent (INSERT OR IGNORE for date rows).

MOCK-DRIVEN: actual LinkedIn skill results update these counters;
real LinkedIn calls wired in C6.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

_DEFAULT_DB = Path(__file__).parent.parent / "hermes_local.db"

_VALID_METRICS = frozenset([
    "views_count",
    "connects_sent",
    "connects_accepted",
    "replies_received",
    "engagements_count",
    "errors_count",
])


def _get_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or _DEFAULT_DB
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def update_cobaia_daily_metric(
    account_handle: str,
    metric_name: str,
    delta: int = 1,
    db_path: Optional[Path] = None,
) -> int:
    """Increment metric_name by delta for account_handle today.

    Returns new value. Raises ValueError if metric_name not in _VALID_METRICS.
    """
    if metric_name not in _VALID_METRICS:
        raise ValueError(f"invalid metric_name={metric_name!r}, valid={sorted(_VALID_METRICS)}")
    today = date.today().isoformat()
    conn = _get_db(db_path)
    try:
        conn.execute(
            """INSERT OR IGNORE INTO cobaia_daily_metrics
               (date, account_handle, views_count, connects_sent, connects_accepted,
                replies_received, engagements_count, errors_count)
               VALUES (?, ?, 0, 0, 0, 0, 0, 0)""",
            (today, account_handle)
        )
        conn.execute(
            f"UPDATE cobaia_daily_metrics SET {metric_name} = {metric_name} + ? "
            "WHERE date = ? AND account_handle = ?",
            (delta, today, account_handle)
        )
        conn.commit()
        row = conn.execute(
            f"SELECT {metric_name} FROM cobaia_daily_metrics WHERE date = ? AND account_handle = ?",
            (today, account_handle)
        ).fetchone()
        return row[metric_name] if row else 0
    finally:
        conn.close()


def get_cobaia_today_metrics(
    account_handle: str,
    db_path: Optional[Path] = None,
) -> dict:
    """Return today's metric row for account_handle (all zeros if no row yet)."""
    today = date.today().isoformat()
    conn = _get_db(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM cobaia_daily_metrics WHERE date = ? AND account_handle = ?",
            (today, account_handle)
        ).fetchone()
        if row:
            return dict(row)
        return {
            "date": today,
            "account_handle": account_handle,
            "views_count": 0,
            "connects_sent": 0,
            "connects_accepted": 0,
            "replies_received": 0,
            "engagements_count": 0,
            "errors_count": 0,
        }
    finally:
        conn.close()


def count_consecutive_errors_24h(
    account_handle: str,
    db_path: Optional[Path] = None,
) -> int:
    """Return consecutive_errors from cobaia_warmup_state (per D4 pattern)."""
    conn = _get_db(db_path)
    try:
        row = conn.execute(
            "SELECT consecutive_errors FROM cobaia_warmup_state WHERE account_handle = ?",
            (account_handle,)
        ).fetchone()
        return row["consecutive_errors"] if row else 0
    finally:
        conn.close()
