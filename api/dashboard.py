"""Hermes Cloud Studio — Dashboard root + summary endpoints (MERGED-011)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import FileResponse

from core.state import DASHBOARD_DIR, get_db

router = APIRouter()


@router.get("/")
async def serve_dashboard():
    return FileResponse(DASHBOARD_DIR / "index.html")


@router.get("/api/dashboard")
async def get_dashboard():
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0]
        by_stage = dict(conn.execute(
            "SELECT stage, COUNT(*) FROM prospects GROUP BY stage"
        ).fetchall())
        by_city = dict(conn.execute(
            "SELECT city, COUNT(*) FROM prospects GROUP BY city ORDER BY COUNT(*) DESC LIMIT 20"
        ).fetchall())
        recent_activities = [dict(r) for r in conn.execute(
            "SELECT * FROM activities ORDER BY created_at DESC LIMIT 20"
        ).fetchall()]
        active_tasks = [dict(r) for r in conn.execute(
            "SELECT * FROM tasks WHERE status IN ('pending', 'running') ORDER BY created_at DESC LIMIT 10"
        ).fetchall()]
        top_prospects = [dict(r) for r in conn.execute(
            "SELECT * FROM prospects WHERE score > 0 ORDER BY score DESC LIMIT 10"
        ).fetchall()]
        with_website = conn.execute("SELECT COUNT(*) FROM prospects WHERE has_website = 1").fetchone()[0]
        without_website = conn.execute("SELECT COUNT(*) FROM prospects WHERE has_website = 0").fetchone()[0]

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_stats = conn.execute(
            "SELECT * FROM pipeline_stats WHERE date = ?", (today,)
        ).fetchone()

        total_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        pending_tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'pending'").fetchone()[0]

        return {
            "total_prospects": total,
            "with_website": with_website,
            "without_website": without_website,
            "by_stage": by_stage,
            "by_city": by_city,
            "recent_activities": recent_activities,
            "active_tasks": active_tasks,
            "top_prospects": top_prospects,
            "today_stats": dict(today_stats) if today_stats else None,
            "total_tasks": total_tasks,
            "pending_tasks": pending_tasks,
            "hermes_status": "online",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        conn.close()
