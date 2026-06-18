"""DAL for icp_profile table — UX-RM-F3-B."""
from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger("hermes.icp_store")

_ARRAY_KEYS = frozenset({
    "industries", "job_titles", "seniority_levels",
    "countries", "states", "cities",
    "keywords_include", "keywords_exclude",
})

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS icp_profile (
    user_id TEXT PRIMARY KEY DEFAULT 'owner',
    industries TEXT,
    company_size_min INTEGER,
    company_size_max INTEGER,
    revenue_range TEXT,
    job_titles TEXT,
    seniority_levels TEXT,
    countries TEXT,
    states TEXT,
    cities TEXT,
    keywords_include TEXT,
    keywords_exclude TEXT,
    max_prospects_per_day INTEGER DEFAULT 5,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
)
"""


def _ensure_table() -> None:
    from core.state import get_db
    conn = get_db()
    try:
        conn.execute(_CREATE_SQL)
        conn.commit()
    finally:
        conn.close()


def _to_db(data: dict) -> dict:
    """Serialize list fields to JSON strings for SQLite."""
    out = {}
    for k, v in data.items():
        if k in _ARRAY_KEYS:
            out[k] = json.dumps(v if isinstance(v, list) else [], ensure_ascii=False)
        else:
            out[k] = v
    return out


def _from_db(row: dict) -> dict:
    """Deserialize JSON string fields back to lists."""
    out = {}
    for k, v in row.items():
        if k in _ARRAY_KEYS and isinstance(v, str):
            try:
                out[k] = json.loads(v)
            except Exception:
                out[k] = []
        else:
            out[k] = v
    return out


def get_current_user_profile() -> Optional[dict]:
    _ensure_table()
    from core.state import get_db
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM icp_profile WHERE user_id = 'owner'"
        ).fetchone()
        conn.close()
        return _from_db(dict(row)) if row else None
    except Exception as exc:
        logger.warning("icp_store get_profile error: %s", exc)
        return None


def upsert_profile(data: dict) -> None:
    _ensure_table()
    from core.state import get_db
    try:
        safe = _to_db({k: v for k, v in data.items() if k != "user_id"})
        if not safe:
            return
        cols = ", ".join(safe.keys())
        placeholders = ", ".join(["?"] * len(safe))
        updates = ", ".join(f"{k} = excluded.{k}" for k in safe)
        conn = get_db()
        conn.execute(
            f"""
            INSERT INTO icp_profile (user_id, {cols}, updated_at)
            VALUES ('owner', {placeholders}, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                {updates},
                updated_at = datetime('now')
            """,
            list(safe.values()),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("icp_store upsert_profile error: %s", exc)
