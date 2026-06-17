"""F.7 C1/C3/C4/C5/C6 — Cobaia warmup API endpoints.

All endpoints require X-Hermes-Token auth (enforced by server.py auth_middleware).
F.7 C6: Real execution wired via VM dispatch (_vm_cobaia_c6_patch.py on VM).

Endpoints (C1):
  POST /api/linkedin/cobaia/start-warmup  {account_handle?, config?}
  POST /api/linkedin/cobaia/pause         {reason?}
  POST /api/linkedin/cobaia/resume
  GET  /api/linkedin/cobaia/status

Endpoints (C3):
  GET  /api/linkedin/cobaia/metrics?days=7
  GET  /api/linkedin/cobaia/timeline
  POST /api/linkedin/cobaia/emergency-stop  (alias → pause)

Endpoints (C4 — D6 PIVOT Bug Export + health-score + sentry-env):
  GET  /api/cobaia/bug-export?hours=24&format=json|markdown
  GET  /api/cobaia/health-score
  GET  /api/cobaia/sentry-env

Endpoints (C5 — Autotune):
  GET  /api/cobaia/autotune-history
  GET  /api/cobaia/autotune-status
  POST /api/cobaia/autotune-trigger-manual

Endpoints (C6 — Pre-flight + F.7 closeout report):
  GET  /api/cobaia/preflight
  GET  /api/cobaia/f7-report
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


class VerifyEmailRequest(BaseModel):
    email: str


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


# ── F.7 C4 — Bug Export + Health Score + Sentry Env ──────────────────────────

COBAIA_SENTRY_ENV = "cobaia-live"


@router.get("/api/cobaia/bug-export")
async def cobaia_bug_export(
    hours: int = Query(default=24, ge=1, le=168),
    format: str = Query(default="json", pattern="^(json|markdown)$"),
    account_handle: str = Query(default="cobaia"),
):
    """D6 PIVOT — Aggregate failures from 3 sources + render structured export.

    Aggregates skill_runs failures, errors_inbox (cobaia/linkedin), mcp_calls errors.
    Returns JSON dict or markdown summary (Claude-paste ready).
    """
    from core.alert_aggregator import aggregate_bugs_24h, render_markdown_summary
    from fastapi.responses import PlainTextResponse

    try:
        data = aggregate_bugs_24h(account_handle=account_handle, hours=hours)
    except Exception as exc:
        logger.error("cobaia bug-export error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    _sentry_breadcrumb("cobaia.bug_export_requested", {"hours": hours, "format": format})

    if format == "markdown":
        md = render_markdown_summary(data)
        return PlainTextResponse(content=md, media_type="text/markdown; charset=utf-8")
    return data


@router.get("/api/cobaia/health-score")
async def cobaia_health_score(account_handle: str = Query(default="cobaia")):
    """Composite 0-100 health score: errors (50pts) + cooldown (25pts) + warmup (25pts)."""
    from core.alert_aggregator import aggregate_bugs_24h
    from core.state import get_db

    score = 100
    breakdown: dict[str, object] = {}

    # Component 1: errors in last 1h (up to -50 pts)
    try:
        bug_data = aggregate_bugs_24h(account_handle=account_handle, hours=1)
        errors_1h = bug_data.get("total", 0)
        error_penalty = min(50, errors_1h * 10)
        score -= error_penalty
        breakdown["errors_1h"] = errors_1h
        breakdown["error_penalty"] = error_penalty
    except Exception:
        breakdown["errors_1h"] = "unavailable"

    # Component 2: cooldown state (−25 if not ok)
    try:
        conn = get_db()
        warmup_row = conn.execute(
            "SELECT phase, consecutive_errors FROM cobaia_warmup_state WHERE account_handle = ?",
            (account_handle,),
        ).fetchone()
        conn.close()
        if warmup_row:
            phase = warmup_row["phase"] if hasattr(warmup_row, "__getitem__") else warmup_row[0]
            consec = warmup_row["consecutive_errors"] if hasattr(warmup_row, "__getitem__") else warmup_row[1]
            breakdown["warmup_phase"] = phase
            breakdown["consecutive_errors"] = consec
            if phase == "paused":
                score -= 25
                breakdown["warmup_penalty"] = 25
            elif consec and consec > 0:
                penalty = min(25, int(consec) * 5)
                score -= penalty
                breakdown["warmup_penalty"] = penalty
            else:
                breakdown["warmup_penalty"] = 0
        else:
            breakdown["warmup_phase"] = "not_started"
    except Exception as exc:
        logger.debug("cobaia health-score warmup query error: %s", exc)
        breakdown["warmup_phase"] = "unavailable"

    score = max(0, score)
    return {
        "account_handle": account_handle,
        "health_score": score,
        "grade": "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D",
        "breakdown": breakdown,
    }


@router.get("/api/cobaia/sentry-env")
async def cobaia_sentry_env():
    """Return Sentry environment tag for cobaia captures (F.7 C4 config)."""
    return {
        "environment": COBAIA_SENTRY_ENV,
        "description": "Sentry environment tag for all cobaia-related captures",
    }


# ── F.7 C5 — Autotune endpoints ───────────────────────────────────────────────

class ManualAutotuneRequest(BaseModel):
    kpi: str
    reason: Optional[str] = None


@router.get("/api/cobaia/autotune-history")
async def cobaia_autotune_history(
    days: int = Query(default=30, ge=1, le=365),
    account_handle: str = Query(default="cobaia"),
):
    """Return list of autotune trigger rows for last N days."""
    from core.state import get_db
    try:
        conn = get_db()
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cobaia_autotune_triggers'"
        ).fetchone()
        if not existing:
            conn.close()
            return {"account_handle": account_handle, "days": days, "rows": [], "total": 0}
        rows = conn.execute(
            """SELECT id, account_handle, trigger_at, kpi_breached, kpi_value, kpi_threshold,
                      sustained_hours, synthesis_run_id, result_status, result_pr_url, created_at
               FROM cobaia_autotune_triggers
               WHERE account_handle = ?
                 AND trigger_at > datetime('now', ?)
               ORDER BY trigger_at DESC""",
            (account_handle, f"-{days} days"),
        ).fetchall()
        conn.close()
        result = [dict(r) for r in rows]
        return {"account_handle": account_handle, "days": days, "rows": result, "total": len(result)}
    except Exception as exc:
        logger.error("cobaia autotune-history error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/cobaia/autotune-status")
async def cobaia_autotune_status(account_handle: str = Query(default="cobaia")):
    """Return current cooldown state + last trigger per KPI + KPI 7d averages."""
    from core.cobaia_metrics import KPI_THRESHOLDS, compute_kpi_7d_avg, get_last_autotune_trigger
    from core.cobaia_autotune import COOLDOWN_HOURS

    kpi_status: dict = {}
    for kpi_name in KPI_THRESHOLDS:
        last = get_last_autotune_trigger(account_handle, kpi_name, cooldown_hours=COOLDOWN_HOURS)
        kpi_status[kpi_name] = {
            "threshold": KPI_THRESHOLDS[kpi_name],
            "cooldown_active": last is not None,
            "last_trigger": last,
        }

    kpi_avgs = compute_kpi_7d_avg(account_handle)

    return {
        "account_handle": account_handle,
        "cooldown_hours": COOLDOWN_HOURS,
        "kpi_thresholds": KPI_THRESHOLDS,
        "kpi_7d": kpi_avgs,
        "cooldown_status": kpi_status,
    }


@router.post("/api/cobaia/autotune-trigger-manual")
async def cobaia_autotune_trigger_manual(req: ManualAutotuneRequest):
    """Owner-forced autotune synthesis trigger — bypasses 72h cooldown.

    Audit trail: inserts cobaia_autotune_triggers with result_status='manual_override'
    and synthesis_runs with trigger_source='cobaia_autotune_manual_{kpi}'.
    """
    from core.cobaia_metrics import KPI_THRESHOLDS, compute_kpi_7d_avg
    from core.cobaia_autotune import (
        COBAIA_REQUESTER, _db_path, _ensure_autotune_table, _get_db,
        _insert_trigger_row, _queue_synthesis_run,
    )
    from datetime import datetime, timezone
    import uuid

    kpi = req.kpi
    if kpi not in KPI_THRESHOLDS:
        raise HTTPException(
            status_code=422,
            detail=f"kpi must be one of {list(KPI_THRESHOLDS.keys())}",
        )

    now = datetime.now(timezone.utc).isoformat()
    kpi_avgs = compute_kpi_7d_avg(req.kpi or "cobaia")
    kpi_value = kpi_avgs["kpis"].get(kpi, 0.0)
    kpi_threshold = KPI_THRESHOLDS[kpi]

    db = _db_path()
    run_id = _queue_synthesis_run(kpi, "cobaia", now)
    trigger_id = str(uuid.uuid4())
    conn = _get_db(db)
    try:
        _ensure_autotune_table(conn)
        _insert_trigger_row(
            conn, trigger_id, "cobaia",
            kpi, kpi_value, kpi_threshold,
            0, run_id, now,
        )
        # Mark as manual override
        conn.execute(
            "UPDATE cobaia_autotune_triggers SET result_status = ? WHERE id = ?",
            ("manual_override", trigger_id),
        )
        conn.commit()
    finally:
        conn.close()

    _sentry_breadcrumb("cobaia.autotune_manual_trigger", {
        "kpi": kpi, "value": kpi_value, "reason": req.reason, "run_id": run_id,
    })
    logger.info(
        "cobaia autotune MANUAL trigger: kpi=%s value=%.4f reason=%s run_id=%s",
        kpi, kpi_value, req.reason, run_id,
    )
    return {
        "status": "queued",
        "trigger_id": trigger_id,
        "synthesis_run_id": run_id,
        "kpi": kpi,
        "kpi_value": kpi_value,
        "kpi_threshold": kpi_threshold,
        "bypass_cooldown": True,
        "reason": req.reason,
    }


# ── F.7 C6 — Pre-flight checks + closeout report ─────────────────────────────


@router.get("/api/cobaia/preflight")
async def cobaia_preflight():
    """Run all pre-flight checks from F7-PREP.md §5 before activating cobaia.

    Returns {checks: {name: {pass, detail}}, all_pass, timestamp}.
    Non-blocking: each check is best-effort (True if check unavailable).
    """
    import asyncio
    from datetime import datetime, timezone

    checks: dict = {}
    all_pass = True

    # C1: Webhook production live (expects 401 from unauthenticated POST)
    try:
        import httpx
        from core.state import VM_API_URL
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                f"{VM_API_URL.replace('8420', '').rstrip('/')}"
                "/api/skills/webhook/pr-merged",
                json={},
            )
        ok = r.status_code in (401, 403)
        checks["webhook_live"] = {"pass": ok, "detail": f"HTTP {r.status_code}"}
    except Exception as exc:
        checks["webhook_live"] = {"pass": False, "detail": str(exc)[:100]}
    all_pass = all_pass and checks["webhook_live"]["pass"]

    # C2: Quarantine cron timer active on VM
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            from core.state import VM_API_URL, AUTH_TOKEN
            r = await client.get(
                f"{VM_API_URL}/api/skills/quarantine-timer-status",
                headers={"X-Hermes-Token": AUTH_TOKEN},
            )
        ok = r.status_code == 200 and r.json().get("active", False)
        checks["quarantine_timer"] = {"pass": ok, "detail": r.json() if r.status_code == 200 else f"HTTP {r.status_code}"}
    except Exception as exc:
        checks["quarantine_timer"] = {"pass": False, "detail": str(exc)[:100]}
    all_pass = all_pass and checks["quarantine_timer"]["pass"]

    # C3: Brain intents available (at least 6 in registry)
    try:
        from brain.intents import INTENT_REGISTRY
        count = len(INTENT_REGISTRY)
        ok = count >= 6
        checks["brain_intents"] = {"pass": ok, "detail": f"{count} intents registered"}
    except Exception as exc:
        checks["brain_intents"] = {"pass": False, "detail": str(exc)[:100]}
    all_pass = all_pass and checks["brain_intents"]["pass"]

    # C4: MCP Gateway health
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get("http://localhost:55401/health")
        ok = r.status_code == 200 and r.json().get("status") == "ok"
        checks["mcp_gateway"] = {"pass": ok, "detail": r.json() if ok else f"HTTP {r.status_code}"}
    except Exception as exc:
        checks["mcp_gateway"] = {"pass": False, "detail": str(exc)[:100]}
    all_pass = all_pass and checks["mcp_gateway"]["pass"]

    # C5: At least 1 cobaia-relevant skill active
    try:
        from core.state import VM_API_URL, AUTH_TOKEN
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{VM_API_URL}/api/hermes/skills",
                headers={"X-Hermes-Token": AUTH_TOKEN},
            )
        if r.status_code == 200:
            skills = r.json() if isinstance(r.json(), list) else r.json().get("skills", [])
            active = [s["name"] for s in skills if s.get("active")]
            cobaia_skills = [n for n in active if "linkedin" in n.lower()]
            ok = len(cobaia_skills) > 0
            checks["skills_active"] = {"pass": ok, "detail": f"active LinkedIn skills: {cobaia_skills}"}
        else:
            checks["skills_active"] = {"pass": False, "detail": f"HTTP {r.status_code}"}
    except Exception as exc:
        checks["skills_active"] = {"pass": False, "detail": str(exc)[:100]}
    all_pass = all_pass and checks["skills_active"]["pass"]

    # C6: LinkedIn health (not blocked/challenge)
    try:
        from core.state import VM_API_URL, AUTH_TOKEN
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{VM_API_URL}/api/linkedin/health",
                headers={"X-Hermes-Token": AUTH_TOKEN},
            )
        if r.status_code == 200:
            state = r.json().get("overall_status") or r.json().get("state")
            ok = state in ("ok", "cooldown")  # cooldown acceptable, not blocked/challenge
            checks["linkedin_health"] = {"pass": ok, "detail": f"state={state}"}
        else:
            checks["linkedin_health"] = {"pass": False, "detail": f"HTTP {r.status_code}"}
    except Exception as exc:
        checks["linkedin_health"] = {"pass": False, "detail": str(exc)[:100]}
    all_pass = all_pass and checks["linkedin_health"]["pass"]

    # C7: Required DB tables exist
    try:
        from core.state import get_db
        required = [
            "cobaia_warmup_state", "cobaia_daily_metrics", "cobaia_autotune_triggers",
            "skill_runs", "mcp_calls", "errors_inbox",
        ]
        conn = get_db()
        existing = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        missing = [t for t in required if t not in existing]
        ok = len(missing) == 0
        checks["db_tables"] = {
            "pass": ok,
            "detail": f"missing: {missing}" if missing else f"all {len(required)} tables present",
        }
    except Exception as exc:
        checks["db_tables"] = {"pass": False, "detail": str(exc)[:100]}
    all_pass = all_pass and checks["db_tables"]["pass"]

    # C8: Sentry SDK importable
    try:
        import sentry_sdk  # noqa: F401
        checks["sentry_sdk"] = {"pass": True, "detail": "sentry_sdk importable"}
    except ImportError:
        checks["sentry_sdk"] = {"pass": False, "detail": "sentry_sdk not installed (optional)"}
    # Sentry is optional — doesn't affect all_pass

    return {
        "all_pass": all_pass,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "C8 sentry_sdk is optional — not included in all_pass gate",
    }


@router.get("/api/cobaia/f7-report")
async def cobaia_f7_report(days: int = Query(default=14, ge=1, le=90)):
    """F.7 closeout report — metrics summary for the warmup period.

    Aggregates daily metrics, KPI trends, autotune history, alert summary.
    Returns data suitable for Brain intent=weekly_report or owner review.
    """
    from core.cobaia_metrics import compute_kpi_7d_avg
    from core.state import get_db
    from datetime import datetime, timezone

    cfg_handle = "cobaia"
    try:
        from linkedin.config import CobaiaConfig
        cfg_handle = CobaiaConfig().account_handle
    except Exception:
        pass

    report: dict = {
        "account_handle": cfg_handle,
        "report_days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Warmup state
    try:
        from linkedin.cobaia_warmup import CobaiaWarmupManager
        from linkedin.config import CobaiaConfig
        status = CobaiaWarmupManager(cfg=CobaiaConfig()).get_status()
        report["warmup"] = {
            "exists": status.get("exists"),
            "current_day": status.get("current_day"),
            "phase": status.get("phase"),
            "started_at": status.get("started_at"),
        }
    except Exception as exc:
        report["warmup"] = {"error": str(exc)[:100]}

    # KPI averages (7d)
    try:
        report["kpi_7d"] = compute_kpi_7d_avg(cfg_handle)
    except Exception as exc:
        report["kpi_7d"] = {"error": str(exc)[:100]}

    # Daily metrics aggregate
    try:
        from datetime import date, timedelta
        conn = get_db()
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        rows = conn.execute(
            """SELECT date, views_count, connects_sent, connects_accepted,
                      replies_received, engagements_count, errors_count
               FROM cobaia_daily_metrics
               WHERE account_handle = ? AND date >= ?
               ORDER BY date ASC""",
            (cfg_handle, cutoff),
        ).fetchall()
        conn.close()
        daily = [dict(r) for r in rows]
        totals = {
            "views": sum(r.get("views_count", 0) for r in daily),
            "connects_sent": sum(r.get("connects_sent", 0) for r in daily),
            "connects_accepted": sum(r.get("connects_accepted", 0) for r in daily),
            "replies": sum(r.get("replies_received", 0) for r in daily),
            "engagements": sum(r.get("engagements_count", 0) for r in daily),
            "errors": sum(r.get("errors_count", 0) for r in daily),
        }
        report["daily_metrics"] = {"rows": daily, "totals": totals, "days_with_data": len(daily)}
    except Exception as exc:
        report["daily_metrics"] = {"error": str(exc)[:100]}

    # Autotune history
    try:
        conn = get_db()
        has_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cobaia_autotune_triggers'"
        ).fetchone()
        if has_table:
            at_rows = conn.execute(
                """SELECT kpi_breached, result_status, trigger_at
                   FROM cobaia_autotune_triggers
                   WHERE account_handle = ?
                   ORDER BY trigger_at DESC LIMIT 10""",
                (cfg_handle,),
            ).fetchall()
            report["autotune_triggers"] = [dict(r) for r in at_rows]
        else:
            report["autotune_triggers"] = []
        conn.close()
    except Exception as exc:
        report["autotune_triggers"] = {"error": str(exc)[:100]}

    # Alert summary (errors_inbox cobaia category last N days)
    try:
        from datetime import timedelta
        conn = get_db()
        cutoff_dt = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        err_count = conn.execute(
            """SELECT COUNT(*) FROM errors_inbox
               WHERE (category LIKE '%cobaia%' OR category LIKE '%linkedin%')
                 AND created_at > ? AND status != 'resolved'""",
            (cutoff_dt,),
        ).fetchone()
        conn.close()
        report["open_alerts"] = err_count[0] if err_count else 0
    except Exception as exc:
        report["open_alerts"] = {"error": str(exc)[:100]}

    return report


# ============================================================
# F.7 P5 — Hunter.io email verifier endpoints (Task 6 + MCP HARD REQ)
# Validates email deliverability ANTES warmup send (bounce >2% queima domain)
# ============================================================

@router.post("/api/cobaia/verify-email")
async def cobaia_verify_email(req: VerifyEmailRequest):
    """Verify email deliverability via Hunter.io v2.

    Returns {status, score, smtp_check, mx_records, disposable, webmail, cached}.
    status: valid | invalid | accept_all | unknown | quota_exhausted | format_invalid | no_api_key
    """
    from core.email_verifier import EmailVerifier
    verifier = EmailVerifier()
    try:
        result = await verifier.verify_email(req.email)
    finally:
        await verifier.aclose()
    _sentry_breadcrumb("cobaia.verify_email", {
        "email": req.email,
        "status": result.get("status"),
        "cached": result.get("cached"),
    })
    if result.get("status") in {"valid", "accept_all"}:
        logger.info("hunter verify OK: %s status=%s score=%s",
                    req.email, result.get("status"), result.get("score"))
    elif result.get("status") == "invalid":
        logger.warning("hunter verify BLOCKED: %s (invalid — skip warmup)", req.email)
    return result


@router.get("/api/cobaia/hunter-usage")
async def cobaia_hunter_usage():
    """Track Hunter.io account quota (free tier 25 verifies/mo)."""
    from core.email_verifier import EmailVerifier
    verifier = EmailVerifier()
    try:
        usage = await verifier.check_account_usage()
    finally:
        await verifier.aclose()
    return usage
