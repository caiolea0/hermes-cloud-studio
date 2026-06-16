"""F.7 C1/C3 — Cobaia warmup API endpoints.

All endpoints require X-Hermes-Token auth (enforced by server.py auth_middleware).
LinkedIn execution is MOCK-DRIVEN in C1/C3; real wiring in C6.

Endpoints (C1):
  POST /api/linkedin/cobaia/start-warmup  {account_handle?, config?}
  POST /api/linkedin/cobaia/pause         {reason?}
  POST /api/linkedin/cobaia/resume
  GET  /api/linkedin/cobaia/status

Endpoints (C3):
  GET  /api/linkedin/cobaia/metrics?days=7
  GET  /api/linkedin/cobaia/timeline
  POST /api/linkedin/cobaia/emergency-stop  (alias → pause)
"""
from __future__ import annotations

import logging
from typing import Optional

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger("hermes.cobaia")
router = APIRouter()


class StartWarmupRequest(BaseModel):
    account_handle: Optional[str] = None


class PauseRequest(BaseModel):
    reason: Optional[str] = None


def _manager():
    from linkedin.cobaia_warmup import CobaiaWarmupManager
    from linkedin.config import CobaiaConfig
    return CobaiaWarmupManager(cfg=CobaiaConfig())


def _ws_emit(event_type: str, data: dict):
    try:
        from core.state import ws_manager
        import asyncio
        import json
        payload = json.dumps({"type": event_type, **data})
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(ws_manager.broadcast(payload))
    except Exception:
        pass  # WS emit is best-effort


def _sentry_breadcrumb(message: str, data: dict):
    try:
        import sentry_sdk
        sentry_sdk.add_breadcrumb(category="cobaia", message=message, data=data, level="info")
    except Exception:
        pass


@router.post("/api/linkedin/cobaia/start-warmup")
async def cobaia_start_warmup(req: StartWarmupRequest):
    mgr = _manager()
    try:
        state = mgr.start_warmup(account_handle=req.account_handle)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.error("cobaia start-warmup error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    _sentry_breadcrumb("cobaia.warmup_started", {"account_handle": state.get("account_handle")})
    _ws_emit("cobaia.warmup_started", state)
    logger.info("cobaia warmup started: %s day=0 phase=lurking", state.get("account_handle"))
    return state


@router.post("/api/linkedin/cobaia/pause")
async def cobaia_pause(req: PauseRequest):
    mgr = _manager()
    try:
        state = mgr.pause(reason=req.reason or "manual_pause")
    except Exception as exc:
        logger.error("cobaia pause error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    _ws_emit("cobaia.paused", state)
    logger.info("cobaia paused: %s reason=%s", state.get("account_handle"), req.reason)
    return state


@router.post("/api/linkedin/cobaia/resume")
async def cobaia_resume():
    mgr = _manager()
    try:
        state = mgr.resume()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("cobaia resume error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    _ws_emit("cobaia.resumed", state)
    logger.info("cobaia resumed: %s phase=%s day=%s", state.get("account_handle"), state.get("phase"), state.get("current_day"))
    return state


@router.get("/api/linkedin/cobaia/status")
async def cobaia_status():
    mgr = _manager()
    try:
        return mgr.get_status()
    except Exception as exc:
        logger.error("cobaia status error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/linkedin/cobaia/emergency-stop")
async def cobaia_emergency_stop(req: PauseRequest):
    """D4 alias — semantic emergency stop → pause. Same as /pause."""
    mgr = _manager()
    try:
        state = mgr.pause(reason=req.reason or "emergency_stop")
    except Exception as exc:
        logger.error("cobaia emergency-stop error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    _sentry_breadcrumb("cobaia.emergency_stop", {"account_handle": state.get("account_handle")})
    _ws_emit("cobaia.paused", {**state, "emergency": True})
    logger.warning("cobaia EMERGENCY STOP: %s", state.get("account_handle"))
    return {**state, "emergency": True}


@router.get("/api/linkedin/cobaia/metrics")
async def cobaia_metrics(days: int = Query(default=7, ge=1, le=30)):
    """Return aggregated daily metrics for the last N days."""
    from core.cobaia_metrics import get_cobaia_today_metrics
    from linkedin.config import CobaiaConfig
    cfg = CobaiaConfig()
    account_handle = cfg.account_handle
    result = []
    try:
        from core.state import get_db
        import sqlite3
        conn = get_db()
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        rows = conn.execute(
            """SELECT * FROM cobaia_daily_metrics
               WHERE account_handle = ? AND date >= ?
               ORDER BY date ASC""",
            (account_handle, cutoff)
        ).fetchall()
        conn.close()
        result = [dict(r) for r in rows] if rows else []
    except Exception as exc:
        logger.warning("cobaia metrics DB error: %s", exc)

    # Always include today even if no row yet
    today_str = date.today().isoformat()
    dates_present = {r["date"] for r in result}
    if today_str not in dates_present:
        result.append({
            "date": today_str,
            "account_handle": account_handle,
            "views_count": 0, "connects_sent": 0, "connects_accepted": 0,
            "replies_received": 0, "engagements_count": 0, "errors_count": 0,
        })

    # Compute KPI rates
    total_connects = sum(r.get("connects_sent", 0) for r in result)
    total_replies = sum(r.get("replies_received", 0) for r in result)
    total_views = sum(r.get("views_count", 0) for r in result)
    total_accepts = sum(r.get("connects_accepted", 0) for r in result)
    total_engagements = sum(r.get("engagements_count", 0) for r in result)

    reply_rate = round(total_replies / max(total_connects, 1), 4)
    accept_rate = round(total_accepts / max(total_connects, 1), 4)
    view_to_connect = round(total_connects / max(total_views, 1), 4)

    return {
        "account_handle": account_handle,
        "days": days,
        "daily": result,
        "totals": {
            "connects_sent": total_connects,
            "connects_accepted": total_accepts,
            "replies_received": total_replies,
            "views_count": total_views,
            "engagements_count": total_engagements,
        },
        "kpis": {
            "reply_rate": reply_rate,
            "accept_rate": accept_rate,
            "view_to_connect": view_to_connect,
            "thresholds": {
                "reply_rate_target": 0.08,
                "accept_rate_target": 0.20,
                "view_to_connect_target": 0.03,
            },
        },
    }


@router.get("/api/linkedin/cobaia/timeline")
async def cobaia_timeline():
    """Return 14-day timeline data for the warmup progress visualization."""
    from linkedin.config import CobaiaConfig
    from linkedin.cobaia_warmup import _compute_phase, _compute_caps
    cfg = CobaiaConfig()
    mgr = _manager()
    status = mgr.get_status()

    if not status.get("exists"):
        return {"exists": False, "days": []}

    current_day = status.get("current_day", 0)
    total_days = cfg.warmup_days
    timeline = []

    for d in range(total_days + 1):
        phase = _compute_phase(d, cfg)
        caps = _compute_caps(phase, d, cfg)
        is_today = d == current_day
        is_future = d > current_day
        is_paused = status.get("phase") == "paused" and is_today

        timeline.append({
            "day": d,
            "phase": "paused" if is_paused else phase,
            "is_today": is_today,
            "is_future": is_future,
            "caps": caps,
        })

    return {
        "exists": True,
        "account_handle": status.get("account_handle"),
        "current_day": current_day,
        "total_days": total_days,
        "overall_phase": status.get("phase"),
        "started_at": status.get("started_at"),
        "days": timeline,
    }
