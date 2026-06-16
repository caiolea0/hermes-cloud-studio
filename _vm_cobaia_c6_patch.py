"""F.7 C6 — VM patch: Cobaia session dispatch endpoint.

APPLY TO VM:
  1. scp _vm_cobaia_c6_patch.py hermes-gcp@136.115.74.69:~/.hermes/scripts/cobaia_c6_patch.py
  2. In hermes_api_v2.py, add near the bottom (before app.include_router calls):
       from scripts.cobaia_c6_patch import router as cobaia_session_router
       app.include_router(cobaia_session_router)
  3. Restart: systemctl --user restart hermes-api.service
  4. Verify: curl http://localhost:8420/api/linkedin/cobaia/run-session-status

REQUIRED ENV VARS (add to ~/.hermes/.env on VM):
  COBAIA_LI_AT=<li_at cookie value — get via Chrome DevTools → LinkedIn cookies>
  COBAIA_ACCOUNT_EMAIL=<email used to create cobaia account>
  COBAIA_ACCOUNT_TYPE=free
  COBAIA_SESSION_FILE=~/.hermes/sessions/cobaia.json  (auto-created on first run)

MIGRATION (apply once):
  sqlite3 ~/.hermes/data/command_center.db \
    < ~/hermes-cloud-studio/migrations/2026_06_cobaia_autotune_triggers.sql

ARCHITECTURE:
  PC scheduler (09:00 BRT) → POST /api/linkedin/cobaia/run-session → this endpoint
  → background task runs LinkedIn automation (lurking/ramp/normal per phase)
  → results pushed back to PC via HERMES_PC_EVENT_URL

GUARDS:
  - COBAIA_LI_AT not set → skip gracefully (status='skipped')
  - Patchright unavailable → skip gracefully
  - Any exception in background task → log, don't crash API
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("hermes.cobaia.vm_session")
router = APIRouter()

_HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
_DB_PATH = _HERMES_HOME / "data" / "command_center.db"
_SESSION_DIR = _HERMES_HOME / "sessions"


class CobaiaRunSessionRequest(BaseModel):
    phase: str           # lurking | ramp | normal
    caps: dict           # {views: int, connects: int, engagements: int}
    account_handle: str = "cobaia"


@router.post("/api/linkedin/cobaia/run-session")
async def cobaia_run_session(req: CobaiaRunSessionRequest):
    """Dispatch cobaia LinkedIn session based on warmup phase.

    Called by PC cobaia_warmup_scheduler.py at 09:00 BRT.
    Uses COBAIA_LI_AT env var for LinkedIn authentication.
    """
    cobaia_li_at = os.environ.get("COBAIA_LI_AT", "").strip()
    if not cobaia_li_at:
        logger.info("cobaia run-session: COBAIA_LI_AT not configured → skip")
        return {
            "session_id": None,
            "status": "skipped",
            "reason": "cobaia_li_at_not_configured",
            "phase": req.phase,
            "actions_planned": 0,
            "metrics": {},
        }

    session_id = str(uuid.uuid4())
    actions_planned = _estimate_actions(req.phase, req.caps)

    asyncio.ensure_future(
        _run_session_bg(
            session_id=session_id,
            phase=req.phase,
            caps=req.caps,
            account_handle=req.account_handle,
            li_at=cobaia_li_at,
        )
    )

    logger.info(
        "cobaia session queued: id=%s phase=%s planned=%s handle=%s",
        session_id, req.phase, actions_planned, req.account_handle,
    )
    return {
        "session_id": session_id,
        "status": "queued",
        "phase": req.phase,
        "caps": req.caps,
        "actions_planned": actions_planned,
        "metrics": {},
    }


@router.get("/api/linkedin/cobaia/run-session-status")
async def cobaia_session_status():
    """Health probe — confirms endpoint is wired up correctly."""
    configured = bool(os.environ.get("COBAIA_LI_AT", "").strip())
    return {
        "status": "ok",
        "cobaia_configured": configured,
        "cobaia_account": os.environ.get("COBAIA_ACCOUNT_EMAIL", "not_set"),
    }


# ── helpers ──────────────────────────────────────────────────────────────────


def _estimate_actions(phase: str, caps: dict) -> int:
    if phase == "lurking":
        return min(caps.get("engagements", 0), 3) + min(caps.get("views", 0), 5)
    return caps.get("engagements", 0) + caps.get("views", 0) + caps.get("connects", 0)


def _ensure_cobaia_session_file(li_at: str) -> Optional[str]:
    """Create minimal Playwright storage_state file with cobaia's LI_AT cookie.

    Returns path string, or None if creation fails.
    """
    session_file = os.environ.get("COBAIA_SESSION_FILE", "").strip()
    if not session_file:
        session_file = str(_SESSION_DIR / "cobaia.json")

    path = Path(session_file).expanduser()
    if path.exists():
        return str(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "cookies": [{
            "name": "li_at",
            "value": li_at,
            "domain": ".linkedin.com",
            "path": "/",
            "expires": -1,
            "httpOnly": True,
            "secure": True,
            "sameSite": "None",
        }],
        "origins": [],
    }
    try:
        path.write_text(json.dumps(state))
        logger.info("cobaia session file created: %s", path)
        return str(path)
    except Exception as exc:
        logger.error("cobaia session file creation failed: %s", exc)
        return None


def _get_cobaia_linkedin_config(session_file: str):
    """Build LinkedInConfig for cobaia account."""
    from linkedin.config import LinkedInConfig  # type: ignore[import]
    return LinkedInConfig(
        account_email=os.environ.get("COBAIA_ACCOUNT_EMAIL", ""),
        account_type=os.environ.get("COBAIA_ACCOUNT_TYPE", "free"),
        session_file=session_file,
        headless=False,  # production always headless=False (stealth req)
        pre_outreach_enabled=True,
        pre_outreach_duration_seconds=180,
    )


async def _run_session_bg(
    session_id: str,
    phase: str,
    caps: dict,
    account_handle: str,
    li_at: str,
) -> None:
    """Background task: run LinkedIn session via existing Patchright flows."""
    metrics = {
        "views": 0, "connects": 0, "accepted": 0,
        "replies": 0, "engagements": 0, "errors": 0,
    }
    try:
        session_file = _ensure_cobaia_session_file(li_at)
        if not session_file:
            logger.error("cobaia session bg: session file unavailable, skipping")
            return

        cfg = _get_cobaia_linkedin_config(session_file)

        if phase == "lurking":
            eng = await _do_engagement(cfg, min(caps.get("engagements", 3), 3))
            metrics["engagements"] = eng
            view = await _do_profile_browse(cfg, min(caps.get("views", 5), 5))
            metrics["views"] = view

        elif phase == "ramp":
            eng = await _do_engagement(cfg, caps.get("engagements", 5))
            metrics["engagements"] = eng
            if caps.get("connects", 0) > 0:
                conn = await _do_connections(cfg, caps["connects"])
                metrics["connects"] = conn

        else:
            # normal phase
            eng = await _do_engagement(cfg, caps.get("engagements", 15))
            metrics["engagements"] = eng
            conn = await _do_connections(cfg, caps.get("connects", 10))
            metrics["connects"] = conn

        _persist_metrics(account_handle, metrics)
        await _push_metrics_pc(account_handle, session_id, metrics)
        logger.info("cobaia session completed: id=%s metrics=%s", session_id, metrics)

    except Exception as exc:
        metrics["errors"] += 1
        logger.error(
            "cobaia session bg exception: id=%s error=%s", session_id, exc, exc_info=True,
        )
        _persist_metrics(account_handle, metrics)


async def _do_engagement(cfg, count: int) -> int:
    """Run engagement flow via existing engager.py. Returns actions completed."""
    if count <= 0:
        return 0
    try:
        from linkedin.engager import run_engagement_session  # type: ignore[import]
        result = await run_engagement_session(config=cfg, max_engagements=count)
        return int(result.get("engaged", 0))
    except ImportError:
        logger.warning("cobaia: engager.run_engagement_session not available")
        return 0
    except Exception as exc:
        logger.warning("cobaia engagement failed: %s", exc)
        return 0


async def _do_profile_browse(cfg, count: int) -> int:
    """Browse profiles using viewer.py. Returns profiles viewed."""
    if count <= 0:
        return 0
    try:
        from linkedin.viewer import run_viewer_session  # type: ignore[import]
        result = await run_viewer_session(config=cfg, max_profiles=count)
        return int(result.get("viewed", 0))
    except ImportError:
        logger.warning("cobaia: viewer.run_viewer_session not available")
        return 0
    except Exception as exc:
        logger.warning("cobaia profile browse failed: %s", exc)
        return 0


async def _do_connections(cfg, count: int) -> int:
    """Send connection requests via connector.py. Returns sent count."""
    if count <= 0:
        return 0
    try:
        from linkedin.connector import run_connector_session  # type: ignore[import]
        result = await run_connector_session(config=cfg, max_connections=count)
        return int(result.get("connected", 0))
    except ImportError:
        logger.warning("cobaia: connector.run_connector_session not available")
        return 0
    except Exception as exc:
        logger.warning("cobaia connector failed: %s", exc)
        return 0


def _persist_metrics(account_handle: str, metrics: dict) -> None:
    """Upsert cobaia_daily_metrics on VM DB (incremental delta)."""
    try:
        today = date.today().isoformat()
        conn = sqlite3.connect(str(_DB_PATH))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
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
                    metrics.get("views", 0), metrics.get("connects", 0),
                    metrics.get("accepted", 0), metrics.get("replies", 0),
                    metrics.get("engagements", 0), metrics.get("errors", 0),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("cobaia _persist_metrics error: %s", exc)


async def _push_metrics_pc(account_handle: str, session_id: str, metrics: dict) -> None:
    """Push session metrics to PC via HERMES_PC_EVENT_URL (fire-and-forget)."""
    pc_url = os.environ.get("HERMES_PC_EVENT_URL", "").strip()
    if not pc_url:
        return
    try:
        import httpx
        payload = {
            "event_type": "cobaia.session_completed",
            "session_id": session_id,
            "account_handle": account_handle,
            "metrics": metrics,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(pc_url, json=payload)
    except Exception as exc:
        logger.debug("_push_metrics_pc failed (non-critical): %s", exc)
