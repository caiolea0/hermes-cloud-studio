"""F.7 C1 — Cobaia warmup API endpoints.

All endpoints require X-Hermes-Token auth (enforced by server.py auth_middleware).
LinkedIn execution is MOCK-DRIVEN in C1; real wiring in C6.

Endpoints:
  POST /api/linkedin/cobaia/start-warmup  {account_handle?, config?}
  POST /api/linkedin/cobaia/pause         {reason?}
  POST /api/linkedin/cobaia/resume
  GET  /api/linkedin/cobaia/status
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
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
