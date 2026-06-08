"""Hermes Cloud Studio — Daemon state, log, decisions, channels, timeline (MERGED-011)."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Query, Request

from core.state import get_db, ws_manager

router = APIRouter()


@router.get("/api/daemon/state")
async def get_daemon_state():
    """Get current daemon state, energy, channels, stats."""
    conn = get_db()
    row = conn.execute("SELECT * FROM daemon_state WHERE id = 1").fetchone()
    conn.close()
    if not row:
        return {"state": "offline", "energy": 0, "stats_today": {}, "channels": {}}
    return {
        "state": row["state"],
        "current_task_type": row["current_task_type"],
        "current_task_detail": row["current_task_detail"],
        "energy": row["energy"],
        "last_heartbeat": row["last_heartbeat"],
        "stats_today": json.loads(row["stats_today"]) if row["stats_today"] else {},
        "stats_week": json.loads(row["stats_week"]) if row["stats_week"] else {},
    }


@router.post("/api/daemon/pause")
async def pause_daemon(minutes: int = Query(default=60)):
    """Pause daemon for N minutes."""
    conn = get_db()
    conn.execute("UPDATE daemon_state SET state = 'paused' WHERE id = 1")
    conn.commit()
    conn.close()
    await ws_manager.broadcast({"type": "daemon_state", "state": "paused", "detail": f"Paused for {minutes}m"})
    return {"ok": True, "paused_for": minutes}


@router.post("/api/daemon/resume")
async def resume_daemon():
    """Resume daemon from pause."""
    conn = get_db()
    conn.execute("UPDATE daemon_state SET state = 'idle' WHERE id = 1")
    conn.commit()
    conn.close()
    await ws_manager.broadcast({"type": "daemon_state", "state": "idle", "detail": "Resumed"})
    return {"ok": True}


@router.get("/api/daemon/log")
async def get_daemon_log(limit: int = Query(default=50), category: Optional[str] = None):
    """Get daemon activity log for live feed."""
    conn = get_db()
    if category:
        rows = conn.execute(
            "SELECT * FROM daemon_log WHERE category = ? ORDER BY timestamp DESC LIMIT ?",
            (category, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM daemon_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "level": r["level"],
            "category": r["category"],
            "message": r["message"],
            "metadata": json.loads(r["metadata"]) if r["metadata"] else None,
            "visual_event": json.loads(r["visual_event"]) if r["visual_event"] else None,
        }
        for r in rows
    ]


@router.get("/api/daemon/decisions")
async def get_daemon_decisions(limit: int = Query(default=20)):
    """Get recent AI decisions with reasoning."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM daemon_decisions ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "action": r["action"],
            "reason": r["reason"],
            "context": json.loads(r["context"]) if r["context"] else None,
        }
        for r in rows
    ]


@router.get("/api/daemon/channels")
async def get_daemon_channels():
    """Get channel states for health cards."""
    conn = get_db()
    conn.execute("SELECT stats_today FROM daemon_state WHERE id = 1").fetchone()
    conn.close()
    return {
        "linkedin": {"daily_used": 0, "daily_limit": 70, "health": 1.0, "warmup_day": 14, "warmup_complete": True, "is_active": True},
        "email": {"daily_used": 0, "daily_limit": 75, "health": 1.0, "warmup_day": 0, "warmup_complete": False, "is_active": True},
        "whatsapp": {"daily_used": 0, "daily_limit": 25, "health": 1.0, "warmup_day": 0, "warmup_complete": False, "is_active": False},
        "instagram": {"daily_used": 0, "daily_limit": 50, "health": 1.0, "warmup_day": 0, "warmup_complete": False, "is_active": False},
    }


@router.get("/api/daemon/timeline")
async def get_daemon_timeline():
    """Get 24h activity timeline for visual bar."""
    conn = get_db()
    rows = conn.execute("""
        SELECT
            strftime('%H', timestamp) as hour,
            category,
            COUNT(*) as count
        FROM daemon_log
        WHERE date(timestamp) = date('now')
        GROUP BY hour, category
        ORDER BY hour
    """).fetchall()
    conn.close()

    timeline = {}
    for h in range(24):
        timeline[str(h).zfill(2)] = {"categories": {}, "total": 0}
    for r in rows:
        h = r["hour"]
        if h in timeline:
            timeline[h]["categories"][r["category"]] = r["count"]
            timeline[h]["total"] += r["count"]

    return timeline


@router.post("/api/daemon/broadcast")
async def daemon_broadcast(request: Request):
    """Internal endpoint for daemon to broadcast events to connected WebSocket clients."""
    body = await request.json()
    await ws_manager.broadcast(body)
    return {"ok": True}
