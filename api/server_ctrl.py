"""Hermes Cloud Studio — Server control (restart/shutdown PC + VM) — MERGED-011."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from fastapi import APIRouter

from config import settings
from core.state import spawn

router = APIRouter()


@router.post("/api/server/restart-local")
async def server_restart_local():
    """Schedule a local server restart. Tauri's health loop or systemd respawns.
    On Windows (no systemd), we exit the process — Tauri's lib.rs health monitor
    detects port 55000 closed and re-launches `python server.py`.
    """
    async def _shutdown():
        await asyncio.sleep(0.5)
        os._exit(0)
    spawn(_shutdown())
    return {"ok": True, "note": "processo encerrando — Tauri vai reiniciar em ~10s"}


@router.post("/api/server/shutdown-local")
async def server_shutdown_local():
    """Graceful shutdown of the local server (no auto-restart)."""
    try:
        flag = settings.hermes_home / "data" / "no_relaunch.flag"
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text(datetime.now(timezone.utc).isoformat())
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass

    async def _shutdown():
        await asyncio.sleep(0.5)
        os._exit(0)
    spawn(_shutdown())
    return {"ok": True, "note": "servidor desligando — fechar Tauri também"}


@router.post("/api/server/restart-vm")
async def server_restart_vm():
    """Restart hermes-api.service on the VM via SSH."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            f"{settings.vm_user}@{settings.vm_host}",
            "systemctl --user restart hermes-api.service && echo OK",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        out = stdout.decode().strip()
        err = stderr.decode().strip()
        if "OK" in out:
            return {"ok": True, "note": "VM reiniciada"}
        return {"ok": False, "error": err or out or "comando falhou"}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "SSH timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/server/restart-all")
async def server_restart_all():
    """Restart VM first, then local (which auto-respawns via Tauri)."""
    vm_result = await server_restart_vm()
    if not vm_result.get("ok"):
        return {"ok": False, "error": f"VM falhou: {vm_result.get('error')}"}

    async def _shutdown():
        await asyncio.sleep(1.0)
        os._exit(0)
    spawn(_shutdown())
    return {"ok": True, "note": "VM reiniciada + local reiniciando"}
