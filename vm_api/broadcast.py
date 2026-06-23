"""POST /api/daemon/broadcast — recebe eventos do daemon e retransmite via WS.

Fix do 404 que o daemon.orchestrator._broadcast() recebia desde a era F1:
daemon chama POST LOCAL_API_URL/api/daemon/broadcast → este endpoint → ws_manager.broadcast()
Auth: X-Hermes-Token (auth_middleware padrão da VM API).
"""
import logging

from fastapi import APIRouter, Request

router = APIRouter()
logger = logging.getLogger("hermes_api_v2")


@router.post("/api/daemon/broadcast")
async def daemon_broadcast(request: Request):
    from vm_core.ws import ws_manager

    try:
        event = await request.json()
        await ws_manager.broadcast(event)
        return {"ok": True, "connections": ws_manager.connection_count()}
    except Exception as exc:
        logger.warning("daemon_broadcast error: %s", exc)
        return {"ok": False, "error": str(exc)}


@router.get("/api/daemon/ws_stats")
async def ws_stats():
    from vm_core.ws import ws_manager

    return {"connections": ws_manager.connection_count()}
