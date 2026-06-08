"""Hermes Cloud Studio — Hermes meta endpoints (status, sync, skills, memory) — MERGED-011."""
from __future__ import annotations

import socket
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter

from config import settings
from core.state import (
    AGENT_ZERO_URL,
    SYNC_INTERVAL,
    VM_API_URL,
    get_db,
)

router = APIRouter()


MEMORY_API_URL = settings.agentmemory_url


@router.get("/api/hermes/status")
async def hermes_status():
    conn = get_db()
    try:
        last_sync = conn.execute("SELECT value FROM sync_state WHERE key = 'last_sync'").fetchone()
        vm_status = conn.execute("SELECT value FROM sync_state WHERE key = 'vm_status'").fetchone()
        total_synced = conn.execute("SELECT value FROM sync_state WHERE key = 'total_synced'").fetchone()
    finally:
        conn.close()

    status = {
        "vm_url": VM_API_URL,
        "vm_reachable": (vm_status[0] == "online") if vm_status else False,
        "last_sync": last_sync[0] if last_sync else None,
        "total_synced": int(total_synced[0]) if total_synced else 0,
        "sync_interval_seconds": SYNC_INTERVAL,
        "agent_zero": {"online": False, "url": AGENT_ZERO_URL},
        "ollama": {"online": False, "models": []},
        "agentmemory": {"online": False},
    }

    # Probe leve /api/_ping (~50ms)
    status["vm_reachable"] = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{VM_API_URL}/api/_ping")
            if r.status_code == 200:
                status["vm_reachable"] = True
                status["vm_probe_method"] = "ping"
    except Exception:
        try:
            if last_sync and last_sync[0]:
                from datetime import datetime as _dt
                _ls = str(last_sync[0])
                if _ls.endswith("Z"):
                    _ls = _ls[:-1] + "+00:00"
                _last = _dt.fromisoformat(_ls)
                _age = (_dt.now(timezone.utc) - _last).total_seconds()
                if _age < 180:
                    status["vm_reachable"] = True
                    status["vm_probe_method"] = "recent_sync_cache"
                    status["vm_probe_cache_age_s"] = round(_age)
        except Exception:
            pass  # noqa: fallback best-effort

    if status.get("vm_reachable"):
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(f"{VM_API_URL}/api/dashboard")
                if r.status_code == 200:
                    vm_data = r.json()
                    status["vm_prospects"] = vm_data.get("total_prospects", 0)
                    status["vm_stages"] = vm_data.get("by_stage", {})
        except Exception:
            pass  # noqa: extras opcionais nao bloqueiam status

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{AGENT_ZERO_URL}/api/health")
            status["agent_zero"]["online"] = r.status_code == 200
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass

    try:
        vm_ip = AGENT_ZERO_URL.rsplit(":", 1)[0]
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{vm_ip}:11434/api/tags")
            if r.status_code == 200:
                status["ollama"]["online"] = True
                status["ollama"]["models"] = [m["name"] for m in r.json().get("models", [])]
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get("http://localhost:3141/")
            status["agentmemory"]["online"] = r.status_code < 500
    except Exception:
        try:
            with socket.create_connection(("127.0.0.1", 3141), timeout=2):
                status["agentmemory"]["online"] = True
        except Exception:  # noqa: silenciado intencional — fallback de sonda
            status["agentmemory"]["online"] = False

    return status


@router.post("/api/hermes/sync")
async def trigger_sync():
    """Manually trigger a sync from VM."""
    # Late import: sync_from_vm vive em server.py (sera movido pra loops/ em proximo commit)
    from server import sync_from_vm
    return await sync_from_vm()


@router.get("/api/hermes/skills")
async def get_skills():
    """List all Hermes Agent skills from VM."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{VM_API_URL}/api/hermes/skills")
            if r.status_code == 200:
                return r.json()
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass
    return []


@router.patch("/api/hermes/skills/{name}")
async def toggle_skill(name: str, body: dict):
    """Toggle skill active state on VM."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.patch(f"{VM_API_URL}/api/hermes/skills/{name}", json=body)
            if r.status_code == 200:
                return r.json()
            return {"error": "VM returned " + str(r.status_code)}
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/hermes/memory")
async def get_memory():
    """Get memory items from AgentMemory service."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{MEMORY_API_URL}/api/memory", params={"limit": 50})
            if r.status_code == 200:
                items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
                facts = [i for i in items if i.get("type") in ("fact", "bug", "workflow", "architecture")]
                prefs = [i for i in items if i.get("type") == "preference"]
                patterns = [i for i in items if i.get("type") == "pattern"]
                return {"facts": facts, "preferences": prefs, "patterns": patterns}
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass
    return {"facts": [], "preferences": [], "patterns": []}


@router.post("/api/hermes/memory")
async def create_memory(body: dict):
    """Create a new memory item."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{MEMORY_API_URL}/api/memory", json={
                "type": body.get("type", "fact"),
                "content": body.get("content", ""),
                "concepts": body.get("concepts", []),
            })
            if r.status_code in (200, 201):
                return r.json()
    except Exception as e:
        return {"error": str(e)}
    return {"error": "Failed to create memory item"}


@router.delete("/api/hermes/memory/{item_id}")
async def delete_memory(item_id: str):
    """Delete a memory item."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.delete(f"{MEMORY_API_URL}/api/memory/{item_id}")
            if r.status_code in (200, 204):
                return {"ok": True}
    except Exception as e:
        return {"error": str(e)}
    return {"error": "Failed to delete memory item"}
