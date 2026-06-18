"""F.7 C1/C6 — Cobaia warmup daily APScheduler job.

Job 'cobaia_warmup_daily_check' fires at 09:00 BRT (America/Cuiaba).
Increments current_day, computes phase, checks auto-pause, emits WS events.

F.7 C6: Real execution — dispatches to VM /api/linkedin/cobaia/run-session.
Graceful fail: VM unreachable → record_error() + log, scheduler continues.

Usage (wired in server.py lifespan via init_cobaia_scheduler):
    from daemon.cobaia_warmup_scheduler import init_cobaia_scheduler
    init_cobaia_scheduler(scheduler)
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger("hermes.cobaia.scheduler")

# Captured at init_cobaia_scheduler() time — used by _ws_emit for run_coroutine_threadsafe.
# R9: fixes silent NO-OP when _ws_emit is called from an executor thread (APScheduler sync callback).
_MAIN_LOOP: asyncio.AbstractEventLoop | None = None


def _dispatch_cobaia_session_to_vm(phase: str, caps: dict, account_handle: str) -> dict:
    """POST to VM /api/linkedin/cobaia/run-session. Best-effort, never crashes.

    Returns full response dict on success (session_id, status, actions_planned, metrics).
    Returns {"error": reason} on HTTP error or connection failure.
    Returns {"status": "skipped", "reason": ...} if VM returns skipped (COBAIA_LI_AT not set).
    """
    try:
        import httpx
        from core.state import VM_API_URL, AUTH_TOKEN
        payload = {"phase": phase, "caps": caps, "account_handle": account_handle}
        resp = httpx.post(
            f"{VM_API_URL}/api/linkedin/cobaia/run-session",
            json=payload,
            headers={"X-Hermes-Token": AUTH_TOKEN},
            timeout=30.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "skipped":
                logger.info(
                    "cobaia session skipped by VM: %s", data.get("reason", "no_reason"),
                )
            else:
                logger.info(
                    "cobaia session dispatched: phase=%s session_id=%s planned=%s",
                    phase, data.get("session_id"), data.get("actions_planned"),
                )
            return data
        logger.warning("cobaia VM dispatch HTTP %d: %s", resp.status_code, resp.text[:200])
        return {"error": f"vm_http_{resp.status_code}"}
    except Exception as exc:
        logger.warning("cobaia VM dispatch failed (best-effort): %s", exc)
        return {"error": str(exc)[:200]}


def _record_cobaia_metrics(account_handle: str, delta: dict) -> None:
    """Upsert cobaia_daily_metrics for today using incremental deltas from VM result."""
    try:
        from core.state import get_db
        from datetime import date
        today = date.today().isoformat()
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO cobaia_daily_metrics
                    (date, account_handle, views_count, connects_sent, connects_accepted,
                     replies_received, engagements_count, errors_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, account_handle) DO UPDATE SET
                    views_count      = views_count      + excluded.views_count,
                    connects_sent    = connects_sent    + excluded.connects_sent,
                    connects_accepted= connects_accepted+ excluded.connects_accepted,
                    replies_received = replies_received + excluded.replies_received,
                    engagements_count= engagements_count+ excluded.engagements_count,
                    errors_count     = errors_count     + excluded.errors_count
                """,
                (
                    today, account_handle,
                    delta.get("views", 0),
                    delta.get("connects", 0),
                    delta.get("accepted", 0),
                    delta.get("replies", 0),
                    delta.get("engagements", 0),
                    delta.get("errors", 0),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("cobaia _record_cobaia_metrics error: %s", exc)


async def _run_daily_check():
    """Async job callback for APScheduler AsyncIOScheduler — runs in main event loop."""
    try:
        from linkedin.cobaia_warmup import CobaiaWarmupManager
        from linkedin.config import CobaiaConfig
        cfg = CobaiaConfig()
        mgr = CobaiaWarmupManager(cfg=cfg)
        account_handle = cfg.account_handle
        result = mgr.daily_check()
        if result.get("skipped"):
            logger.info("cobaia daily_check skipped: %s", result.get("reason"))
            return
        phase = result.get("phase")
        day = result.get("current_day")
        caps = result.get("caps", {})
        logger.info("cobaia daily_check: day=%s phase=%s caps=%s", day, phase, caps)
        # auto-paused
        if result.get("auto_paused"):
            logger.warning("cobaia AUTO-PAUSED: %s", result.get("reason"))
            _ws_emit("cobaia.auto_paused", result)
            _sentry_alert(result)
            return
        _ws_emit("cobaia.daily_check_done", {"phase": phase, "current_day": day, "caps": caps})
        # F.7 C6 — Real VM dispatch (replaces C1 stub_execute_skill)
        dispatch_result = _dispatch_cobaia_session_to_vm(phase, caps, account_handle)
        if dispatch_result.get("error"):
            mgr.record_error(account_handle)
            logger.warning(
                "cobaia dispatch error → error recorded: %s", dispatch_result["error"],
            )
            _ws_emit("cobaia.session_error", {
                "account_handle": account_handle,
                "error": dispatch_result["error"],
            })
        else:
            # skipped (COBAIA_LI_AT not configured) or queued — only reset errors on queued
            if dispatch_result.get("status") != "skipped":
                mgr.reset_errors(account_handle)
            metrics = dispatch_result.get("metrics") or {}
            if metrics:
                _record_cobaia_metrics(account_handle, metrics)
            _ws_emit("cobaia.session_dispatched", {
                "account_handle": account_handle,
                "session_id": dispatch_result.get("session_id"),
                "status": dispatch_result.get("status"),
                "actions_planned": dispatch_result.get("actions_planned", 0),
                "phase": phase,
            })
    except Exception as exc:
        logger.error("cobaia daily_check exception: %s", exc, exc_info=True)


def _ws_emit(event_type: str, data: dict) -> None:
    # R9: use run_coroutine_threadsafe with _MAIN_LOOP captured at init time.
    # asyncio.get_event_loop() from an executor thread returns a non-running loop → silent NO-OP.
    # broadcast() expects a dict; previous code passed json.dumps() string (double-serialization bug).
    global _MAIN_LOOP
    try:
        from core.state import ws_manager
        if _MAIN_LOOP and _MAIN_LOOP.is_running():
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast({"type": event_type, **data}),
                _MAIN_LOOP,
            )
        else:
            logger.warning("R9: no main loop for WS emit %s", event_type)
    except Exception as exc:
        logger.warning("R9: _ws_emit error for %s: %s", event_type, exc)


def _sentry_alert(data: dict):
    from core.sentry_via_gateway import capture_message_with_extras
    capture_message_with_extras(
        f"cobaia auto-paused: {data.get('reason')}",
        extras=data,
        level="warning",
        requester="brain-f7-cobaia",
    )


def init_cobaia_scheduler(scheduler) -> bool:
    """Register cobaia_warmup_daily_check job on existing APScheduler instance.

    Captures the running event loop for _ws_emit (R9 fix).
    Returns True if registered, False if APScheduler unavailable.
    """
    global _MAIN_LOOP
    try:
        _MAIN_LOOP = asyncio.get_running_loop()
    except RuntimeError:
        _MAIN_LOOP = None
        logger.warning("R9: init_cobaia_scheduler called outside async context — _MAIN_LOOP=None")

    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("APScheduler not installed — cobaia scheduler disabled")
        return False

    try:
        scheduler.add_job(
            _run_daily_check,
            trigger=CronTrigger(hour=9, minute=0, timezone="America/Cuiaba"),
            id="cobaia_warmup_daily_check",
            replace_existing=True,
            name="Cobaia warmup daily check (F.7 C6 — real dispatch)",
            misfire_grace_time=3600,
        )
        logger.info("cobaia_warmup_daily_check registered — next fire: 09:00 BRT")
        return True
    except Exception as exc:
        logger.error("cobaia scheduler registration failed: %s", exc)
        return False
