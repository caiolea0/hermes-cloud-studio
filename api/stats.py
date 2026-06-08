"""Hermes Cloud Studio — Pipeline stats (MERGED-011)."""
from __future__ import annotations

from fastapi import APIRouter

from core.state import get_db

router = APIRouter()


@router.get("/api/stats")
async def get_stats(days: int = 7):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM pipeline_stats ORDER BY date DESC LIMIT ?", (days,)
        ).fetchall()
        return {"stats": [dict(r) for r in rows]}
    finally:
        conn.close()
