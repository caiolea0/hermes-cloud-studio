"""Hermes Cloud Studio — Tunnel supervisor status + control widget (MERGED-011)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from core.state import PROJECT_ROOT

router = APIRouter()


def _tunnel_state_path() -> Path:
    return PROJECT_ROOT / "logs" / "tunnel_supervisor_state.json"


def _tunnel_supervisor_pid() -> Optional[int]:
    """Procura processo rodando tunnel_supervisor.py. Tenta pythonw + python."""
    import subprocess as _sp
    for name in ("pythonw.exe", "python.exe"):
        try:
            out = _sp.check_output(
                ["wmic", "process", "where", f"name='{name}'",
                 "get", "ProcessId,CommandLine", "/format:csv"],
                text=True, stderr=_sp.DEVNULL, timeout=5,
            )
            for line in out.splitlines():
                if "tunnel_supervisor.py" in line:
                    for p in reversed(line.strip().split(",")):
                        if p.strip().isdigit():
                            return int(p.strip())
        except Exception:  # noqa: silenciado intencional — tenta próximo binário python
            continue
    return None


@router.get("/api/tunnel/status")
async def tunnel_status():
    """Status do tunnel_supervisor (lido do state.json + check de PID)."""
    state = {}
    sp = _tunnel_state_path()
    if sp.exists():
        try:
            state = json.loads(sp.read_text(encoding="utf-8"))
        except Exception:  # noqa: silenciado intencional — state.json corrompido cai p/ default vazio
            pass
    pid = _tunnel_supervisor_pid()
    alive_via_heartbeat = False
    try:
        from datetime import datetime as _dt
        ua = state.get("updated_at", "")
        if ua:
            _u = _dt.fromisoformat(ua.replace("Z", "+00:00") if ua.endswith("Z") else ua)
            if _u.tzinfo is None:
                _u = _u.replace(tzinfo=timezone.utc)
            age = (_dt.now(timezone.utc) - _u).total_seconds()
            alive_via_heartbeat = age < 90
    except Exception:  # noqa: silenciado intencional — heartbeat parse best-effort
        pass
    supervisor_running = (pid is not None) or alive_via_heartbeat
    healthy = bool(state.get("egress_residential")) and supervisor_running
    actions = state.get("actions") or []
    return {
        "healthy": healthy,
        "supervisor_pid": pid,
        "supervisor_running": supervisor_running,
        "supervisor_alive_via_heartbeat": alive_via_heartbeat,
        "socks5_listening": state.get("socks5_listening", False),
        "vm_tunnel_landed": state.get("vm_tunnel_landed", False),
        "egress_residential": state.get("egress_residential", False),
        "egress_ip": state.get("egress_ip", ""),
        "last_action": actions[-1] if actions else None,
        "updated_at": state.get("updated_at"),
    }


@router.post("/api/tunnel/control")
async def tunnel_control(request: Request):
    """Start/stop/restart o supervisor. body: {action: 'start'|'stop'|'restart'}"""
    import subprocess as _sp
    body = await request.json()
    action = (body or {}).get("action", "")
    if action not in ("start", "stop", "restart"):
        raise HTTPException(400, "action invalida (start|stop|restart)")

    bat = PROJECT_ROOT / "scripts" / "tunnel_supervisor.bat"

    def _stop():
        pid = _tunnel_supervisor_pid()
        if pid:
            try:
                _sp.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
                return {"stopped_pid": pid}
            except Exception as e:
                return {"error": str(e)}
        return {"stopped_pid": None}

    def _start():
        if not bat.exists():
            return {"error": f"{bat} nao encontrado"}
        try:
            _sp.Popen(["cmd.exe", "/c", str(bat)], creationflags=0x08000000)  # CREATE_NO_WINDOW
            return {"spawned": True}
        except Exception as e:
            return {"error": str(e)}

    if action == "stop":
        result = _stop()
    elif action == "start":
        if _tunnel_supervisor_pid():
            result = {"already_running": True}
        else:
            result = _start()
    else:
        result = {"stop": _stop(), "start": _start()}
    return {"action": action, "result": result}
