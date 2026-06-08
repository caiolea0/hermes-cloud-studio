"""Hermes Cloud Studio — Internal endpoints (loopback+X-Internal-Token only) — MERGED-011."""
from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, HTTPException, Request

from config import settings
from core.state import (
    VM_API_URL,
    _check_internal,
    get_db,
    logger,
    ws_manager,
)

router = APIRouter()


@router.post("/api/internal/account_type_set")
async def account_type_set(request: Request):
    """Receive an account_type detected by the browser extension (content script).
    Forwards to VM which updates its cache (~/.hermes/data/linkedin_account_type.json).
    """
    _check_internal(request)
    body = await request.json()
    account_type = (body.get("account_type") or "").strip()
    if account_type not in ("free", "premium", "sales_navigator"):
        raise HTTPException(400, "invalid account_type")
    token = settings.vm_auth_token
    if not token:
        return {"ok": False, "error": "HERMES_VM_AUTH_TOKEN not set on PC"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{VM_API_URL}/api/internal/account_type_set",
                json={
                    "account_type": account_type,
                    "evidence": body.get("evidence", []),
                    "detected_from": body.get("detected_from", "extension"),
                    "page_url": body.get("page_url"),
                },
                headers={"X-Hermes-Token": token},
            )
            vm_data = r.json() if r.status_code == 200 else {"ok": False}
    except Exception as e:
        return {"ok": False, "error": f"VM forward failed: {e}"}
    if vm_data.get("ok"):
        try:
            await ws_manager.broadcast({"type": "linkedin_account_type_updated", "account_type": account_type})
        except Exception:  # noqa: silenciado intencional — WS/broadcast opcional
            pass
    return vm_data


@router.post("/api/internal/li_at_rotate")
async def rotate_li_at(request: Request):
    """Receive a new li_at cookie from the local sync script and forward to VM.

    The script (scripts/li_at_sync.py) reads Chrome's cookie DB once a day.
    Only accepts 127.0.0.1 (same-host). Also broadcasts a status reload event.
    """
    _check_internal(request)
    body = await request.json()
    li_at = (body.get("li_at") or "").strip()
    if not li_at or len(li_at) < 30:
        raise HTTPException(400, "li_at missing or too short")
    token = settings.vm_auth_token
    if not token:
        return {"ok": False, "error": "HERMES_VM_AUTH_TOKEN not set on PC"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{VM_API_URL}/api/internal/li_at_update",
                json={"li_at": li_at},
                headers={"X-Hermes-Token": token},
            )
            vm_ok = r.status_code == 200 and r.json().get("ok")
            if not vm_ok:
                return {"ok": False, "vm_status": r.status_code, "vm_body": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": f"VM forward failed: {e}"}
    if vm_ok:
        try:
            await ws_manager.broadcast({"type": "linkedin_session_rotated"})
        except Exception:  # noqa: silenciado intencional — WS/broadcast opcional
            pass
    return {"ok": vm_ok}


@router.post("/api/internal/linkedin/event")
async def receive_linkedin_event(request: Request):
    """VM-only callback: VM hermes_api.py pushes progress events here.

    Updates local DB partial_results + broadcasts WS event linkedin_progress.
    Only accepts requests from 127.0.0.1 (SSH tunnel makes VM appear as localhost).
    """
    _check_internal(request)
    body = await request.json()
    cid = body.get("campaign_id")
    if not cid:
        return {"ok": False}
    try:
        conn = get_db()
        if body.get("partial_results") is not None or body.get("progress") is not None:
            conn.execute("""
                UPDATE linkedin_campaigns
                SET results = COALESCE(?, results),
                    progress = COALESCE(?, progress)
                WHERE id = ?
            """, (
                json.dumps(body["partial_results"]) if body.get("partial_results") else None,
                body.get("progress"),
                cid,
            ))
            conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"internal event DB update failed: {e}")
    try:
        await ws_manager.broadcast({"type": "linkedin_progress", "data": body})
    except Exception:  # noqa: silenciado intencional — WS/broadcast opcional
        pass
    return {"ok": True}
