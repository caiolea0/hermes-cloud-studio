"""F.7 C1 — Cobaia warmup daily APScheduler job.

Job 'cobaia_warmup_daily_check' fires at 09:00 BRT (America/Cuiaba).
Increments current_day, computes phase, checks auto-pause, emits WS events.

LinkedIn execution is STUBBED in C1 (MOCK-DRIVEN). Real wiring in C6.

Usage (wired in server.py lifespan via init_cobaia_scheduler):
    from daemon.cobaia_warmup_scheduler import init_cobaia_scheduler
    init_cobaia_scheduler(scheduler)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger("hermes.cobaia.scheduler")


def _run_daily_check():
    """Synchronous job callback for APScheduler."""
    try:
        from linkedin.cobaia_warmup import CobaiaWarmupManager
        from linkedin.config import CobaiaConfig
        mgr = CobaiaWarmupManager(cfg=CobaiaConfig())
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
        # STUB skill execution (lurking phase: fire linkedin-engagement mock)
        if phase == "lurking":
            stub_result = mgr.stub_execute_skill("linkedin-engagement", phase)
            logger.info("cobaia skill stub: %s", stub_result)
    except Exception as exc:
        logger.error("cobaia daily_check exception: %s", exc, exc_info=True)


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
        pass


def _sentry_alert(data: dict):
    try:
        import sentry_sdk
        sentry_sdk.capture_message(
            f"cobaia auto-paused: {data.get('reason')}",
            level="warning",
            extras=data,
        )
    except Exception:
        pass


def init_cobaia_scheduler(scheduler) -> bool:
    """Register cobaia_warmup_daily_check job on existing APScheduler instance.

    Returns True if registered, False if APScheduler unavailable.
    """
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
            name="Cobaia warmup daily check (F.7 C1)",
            misfire_grace_time=3600,  # fire up to 1h late if server was down
        )
        logger.info("cobaia_warmup_daily_check registered — next fire: 09:00 BRT")
        return True
    except Exception as exc:
        logger.error("cobaia scheduler registration failed: %s", exc)
        return False
