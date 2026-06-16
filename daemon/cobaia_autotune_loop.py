"""F.7 C5 — Cobaia autotune APScheduler job (09:15 BRT daily).

Job 'cobaia_autotune_daily_check' fires at 09:15 BRT (15 min after email digest C4).
Guards:
  - Skip if warmup paused (D4 state machine)
  - Skip if weekends (D2.3 crystallized)
  - Skip if current_day < 14 (KPIs not yet stabilized during ramp phase)
  - Skip if cobaia_warmup_state not found (warmup not started)

On trigger: inserts cobaia_autotune_triggers + synthesis_runs (F.4.2 REUSE).
No owner confirm needed (D10 reactive automatic).
"""
from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger("hermes.cobaia.autotune_loop")

_WARMUP_STABILIZATION_DAYS = 14


def _run_autotune_check() -> None:
    """Synchronous APScheduler job callback."""
    try:
        # Weekend gate (D2.3)
        if datetime.date.today().weekday() >= 5:
            logger.info("cobaia autotune: skipped — weekend")
            return

        # Warmup state gate
        try:
            from linkedin.cobaia_warmup import CobaiaWarmupManager
            from linkedin.config import CobaiaConfig
            mgr = CobaiaWarmupManager(cfg=CobaiaConfig())
            status = mgr.get_status()
        except Exception as exc:
            logger.warning("cobaia autotune: cannot read warmup state: %s", exc)
            return

        if not status.get("exists"):
            logger.info("cobaia autotune: skipped — warmup not started")
            return

        phase = status.get("phase")
        if phase == "paused":
            logger.info("cobaia autotune: skipped — warmup paused")
            return

        current_day = status.get("current_day", 0)
        if current_day < _WARMUP_STABILIZATION_DAYS:
            logger.info(
                "cobaia autotune: skipped — day %d < %d stabilization threshold",
                current_day, _WARMUP_STABILIZATION_DAYS,
            )
            return

        account_handle = status.get("account_handle", "cobaia")

        # Run detection + trigger
        from core.cobaia_autotune import detect_and_trigger
        result = detect_and_trigger(account_handle=account_handle)

        if result["triggered"] > 0:
            logger.info(
                "cobaia autotune: %d synthesis queued for %s: %s",
                result["triggered"], account_handle, result["triggered_kpis"],
            )
        elif result["skipped"] > 0:
            logger.info(
                "cobaia autotune: %d breach(es) detected but skipped (72h cooldown)",
                result["skipped"],
            )
        else:
            logger.info("cobaia autotune: no breaches for %s", account_handle)

    except Exception as exc:
        logger.error("cobaia autotune job exception: %s", exc, exc_info=True)


def init_cobaia_autotune_scheduler(scheduler) -> bool:
    """Register cobaia_autotune_daily_check job on existing APScheduler instance.

    Fires at 09:15 BRT (15 min after email digest C4 at 09:00).
    Returns True if registered, False if APScheduler unavailable.
    """
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("APScheduler not installed — autotune scheduler disabled")
        return False
    try:
        scheduler.add_job(
            _run_autotune_check,
            trigger=CronTrigger(hour=9, minute=15, timezone="America/Cuiaba"),
            id="cobaia_autotune_daily_check",
            replace_existing=True,
            name="Cobaia autotune daily check (F.7 C5)",
            misfire_grace_time=3600,
        )
        logger.info("cobaia_autotune_daily_check registered — next fire: 09:15 BRT")
        return True
    except Exception as exc:
        logger.error("autotune scheduler registration failed: %s", exc)
        return False
