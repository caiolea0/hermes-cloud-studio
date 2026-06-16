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


# ── F.7 C5 — KPI computation + autotune detection ──────────────────────────

# D3.1/D3.2/D3.3 crystallized thresholds
KPI_THRESHOLDS: dict[str, float] = {
    "reply_rate": 0.08,        # D3.1: reply_rate > 8%
    "accept_rate": 0.20,       # D3.2: accept_rate > 20%
    "view_to_connect": 0.03,   # D3.3: view→connect > 3%
}

# Minimum rows required before breach detection (avoids false alarm on sparse data)
_MIN_SAMPLE_DAYS = 1


def _compute_kpis_from_rows(rows: list[dict]) -> dict[str, float]:
    """Aggregate daily metric rows into KPI floats."""
    total_connects = sum(r.get("connects_sent", 0) or 0 for r in rows)
    total_replies = sum(r.get("replies_received", 0) or 0 for r in rows)
    total_accepts = sum(r.get("connects_accepted", 0) or 0 for r in rows)
    total_views = sum(r.get("views_count", 0) or 0 for r in rows)
    return {
        "reply_rate": total_replies / max(total_connects, 1),
        "accept_rate": total_accepts / max(total_connects, 1),
        "view_to_connect": total_connects / max(total_views, 1),
    }


def compute_kpi_7d_avg(
    account_handle: str,
    db_path: Optional[Path] = None,
) -> dict:
    """Compute 7-day KPI averages + today's values + trend direction.

    Returns:
        {
            kpis: {reply_rate: float, accept_rate: float, view_to_connect: float},
            kpis_today: {...},
            sample_days: int,
            trend: {reply_rate: 'up'|'down'|'flat', ...},
            thresholds: KPI_THRESHOLDS,
        }
    """
    conn = _get_db(db_path)
    try:
        rows = conn.execute(
            """SELECT date, views_count, connects_sent, connects_accepted,
                      replies_received, engagements_count, errors_count
               FROM cobaia_daily_metrics
               WHERE account_handle = ?
               ORDER BY date DESC LIMIT 7""",
            (account_handle,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {
            "kpis": {k: 0.0 for k in KPI_THRESHOLDS},
            "kpis_today": {k: 0.0 for k in KPI_THRESHOLDS},
            "sample_days": 0,
            "trend": {k: "flat" for k in KPI_THRESHOLDS},
            "thresholds": KPI_THRESHOLDS,
        }

    all_rows = [dict(r) for r in rows]
    kpis_7d = _compute_kpis_from_rows(all_rows)

    today_str = date.today().isoformat()
    today_rows = [r for r in all_rows if r.get("date") == today_str]
    kpis_today = _compute_kpis_from_rows(today_rows) if today_rows else {k: 0.0 for k in KPI_THRESHOLDS}

    # Trend: compare first-half 7d vs second-half
    trend: dict[str, str] = {}
    if len(all_rows) >= 4:
        first_half = all_rows[len(all_rows) // 2:]   # older half (rows are DESC so last = oldest)
        second_half = all_rows[: len(all_rows) // 2]  # newer half
        kpis_old = _compute_kpis_from_rows(first_half)
        kpis_new = _compute_kpis_from_rows(second_half)
        for kpi in KPI_THRESHOLDS:
            delta = kpis_new[kpi] - kpis_old[kpi]
            trend[kpi] = "up" if delta > 0.005 else "down" if delta < -0.005 else "flat"
    else:
        trend = {k: "flat" for k in KPI_THRESHOLDS}

    return {
        "kpis": kpis_7d,
        "kpis_today": kpis_today,
        "sample_days": len(all_rows),
        "trend": trend,
        "thresholds": KPI_THRESHOLDS,
    }


def detect_sustained_low_kpi(
    account_handle: str,
    hours: int = 24,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Return list of KPIs below D3 thresholds for at least `hours` hours.

    Since cobaia_daily_metrics has daily granularity, hours is converted to days
    (ceil). Minimum _MIN_SAMPLE_DAYS of data required; sparse data → empty list.

    Returns:
        [
            {
                kpi: str,
                value: float,
                threshold: float,
                sustained_hours: int,
                sample_days: int,
            },
            ...
        ]
    """
    import math
    days_needed = max(_MIN_SAMPLE_DAYS, math.ceil(hours / 24))

    conn = _get_db(db_path)
    try:
        rows = conn.execute(
            """SELECT date, views_count, connects_sent, connects_accepted,
                      replies_received, engagements_count
               FROM cobaia_daily_metrics
               WHERE account_handle = ?
               ORDER BY date DESC LIMIT ?""",
            (account_handle, days_needed),
        ).fetchall()
    finally:
        conn.close()

    if len(rows) < _MIN_SAMPLE_DAYS:
        return []

    row_dicts = [dict(r) for r in rows]
    kpis = _compute_kpis_from_rows(row_dicts)

    breached: list[dict] = []
    for kpi_name, threshold in KPI_THRESHOLDS.items():
        value = kpis[kpi_name]
        if value < threshold:
            breached.append({
                "kpi": kpi_name,
                "value": round(value, 6),
                "threshold": threshold,
                "sustained_hours": len(row_dicts) * 24,
                "sample_days": len(row_dicts),
            })
    return breached


def get_last_autotune_trigger(
    account_handle: str,
    kpi_name: str,
    cooldown_hours: int = 72,
    db_path: Optional[Path] = None,
) -> Optional[dict]:
    """Return most recent autotune trigger for (account, kpi) within cooldown_hours.

    Returns None if no trigger found within cooldown window (safe to re-trigger).
    Returns dict row if cooldown active (caller must skip).
    """
    conn = _get_db(db_path)
    try:
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cobaia_autotune_triggers'"
        ).fetchone()
        if not existing:
            return None
        row = conn.execute(
            """SELECT id, trigger_at, kpi_value, result_status, synthesis_run_id
               FROM cobaia_autotune_triggers
               WHERE account_handle = ?
                 AND kpi_breached = ?
                 AND trigger_at > datetime('now', ?)
               ORDER BY trigger_at DESC LIMIT 1""",
            (account_handle, kpi_name, f"-{cooldown_hours} hours"),
        ).fetchone()
        return dict(row) if row else None
    except Exception:
        return None
    finally:
        conn.close()
