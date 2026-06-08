"""Hermes Cloud Studio — Activities feed (MERGED-011)."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter

from core.models import ActivityCreate
from core.state import get_db

router = APIRouter()


@router.get("/api/activities")
async def list_activities(limit: int = 50, type: Optional[str] = None, offset: int = 0, prospect_id: Optional[int] = None):
    conn = get_db()
    try:
        conditions = []
        params = []
        if type:
            conditions.append("type = ?")
            params.append(type)
        if prospect_id:
            conditions.append("prospect_id = ?")
            params.append(prospect_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = conn.execute(
            f"SELECT * FROM activities {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset]
        ).fetchall()
        return {"activities": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/api/activities")
async def create_activity(a: ActivityCreate):
    conn = get_db()
    try:
        meta = json.dumps(a.metadata) if a.metadata else None
        conn.execute(
            "INSERT INTO activities (type, title, description, prospect_id, metadata) VALUES (?, ?, ?, ?, ?)",
            (a.type, a.title, a.description, a.prospect_id, meta)
        )
        conn.commit()
        return {"status": "created"}
    finally:
        conn.close()
