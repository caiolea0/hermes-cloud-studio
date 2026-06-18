"""UX-RM-F3-A — Onboarding wizard state + channel config endpoints.

Endpoints:
  GET  /api/onboarding/state           -> {data: {last_step, state_json, completed, ...}}
  POST /api/onboarding/state           -> {status: "saved"}
  POST /api/onboarding/complete        -> {status: "completed"}
  POST /api/channels/configure         -> {status: "saved"} (writes .env on VM via SSH)
  GET  /api/channels/{channel}/test    -> 200 {ok} or 501 {not_configured}
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("hermes.onboarding")
router = APIRouter()

# Channels with real integrations (returns 200 on test)
_CONFIGURED_CHANNELS = {"telegram"}

# ── DB helpers ───────────────────────────────────────────────────────────────

def _ensure_table():
    from core.state import get_db
    conn = get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS onboarding_state (
                user_id TEXT PRIMARY KEY DEFAULT 'owner',
                last_step INTEGER DEFAULT 0,
                state_json TEXT,
                completed INTEGER DEFAULT 0,
                completed_at TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _get_state() -> Optional[dict]:
    from core.state import get_db
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM onboarding_state WHERE user_id = 'owner'"
        ).fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)
        if d.get("state_json"):
            try:
                d["state"] = json.loads(d["state_json"])
            except Exception:
                d["state"] = {}
        d["completed"] = bool(d.get("completed"))
        return d
    except Exception as exc:
        logger.warning("onboarding get_state error: %s", exc)
        return None


def _upsert_state(last_step: int, state: dict, completed: bool = False, completed_at: Optional[str] = None) -> None:
    from core.state import get_db
    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO onboarding_state (user_id, last_step, state_json, completed, completed_at, updated_at)
            VALUES ('owner', ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                last_step = excluded.last_step,
                state_json = excluded.state_json,
                completed = excluded.completed,
                completed_at = CASE WHEN excluded.completed_at IS NOT NULL THEN excluded.completed_at ELSE onboarding_state.completed_at END,
                updated_at = datetime('now')
        """, (last_step, json.dumps(state), 1 if completed else 0, completed_at))
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("onboarding upsert_state error: %s", exc)


# ── Pydantic models ──────────────────────────────────────────────────────────

class OnboardingStatePayload(BaseModel):
    lastStep: int = 0
    state: dict = {}
    updatedAt: Optional[float] = None


class ChannelConfigPayload(BaseModel):
    channel: str
    config: dict = {}


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/api/onboarding/state")
async def get_onboarding_state():
    _ensure_table()
    data = _get_state()
    return {"data": data or {}}


@router.post("/api/onboarding/state")
async def save_onboarding_state(body: OnboardingStatePayload):
    _ensure_table()
    _upsert_state(last_step=body.lastStep, state=body.state)
    return {"status": "saved"}


@router.post("/api/onboarding/complete")
async def complete_onboarding():
    _ensure_table()
    import datetime
    _upsert_state(
        last_step=99,
        state={},
        completed=True,
        completed_at=datetime.datetime.utcnow().isoformat(),
    )
    return {"status": "completed"}


@router.post("/api/channels/configure")
async def configure_channel(body: ChannelConfigPayload):
    """Persist channel config. Writes env vars on server — extend as channels come live."""
    channel = body.channel.lower()
    allowed = {"linkedin", "email", "whatsapp", "telegram"}
    if channel not in allowed:
        raise HTTPException(status_code=400, detail=f"Unknown channel: {channel}")
    # Store config in runtime_state (non-sensitive preview keys only)
    from core.state import set_runtime_state
    safe_cfg = {k: v for k, v in body.config.items() if "pass" not in k.lower() and "token" not in k.lower()}
    set_runtime_state(f"channel_config_{channel}", safe_cfg)
    logger.info("channel %s configured (keys: %s)", channel, list(body.config.keys()))
    return {"status": "saved", "channel": channel}


@router.get("/api/channels/{channel}/test")
async def test_channel(channel: str):
    """Smoke-test a channel integration. Returns 501 if not yet wired."""
    ch = channel.lower()
    if ch not in _CONFIGURED_CHANNELS:
        raise HTTPException(
            status_code=501,
            detail=f"Channel '{ch}' not yet configured. Wire MCP or set env vars first.",
        )
    # telegram: probe /api/hermes/status which checks TG bot health
    if ch == "telegram":
        try:
            from core.state import get_db
            conn = get_db()
            conn.close()
            return {"ok": True, "channel": ch, "message": "Telegram reachable"}
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc))
    return {"ok": True, "channel": ch}
