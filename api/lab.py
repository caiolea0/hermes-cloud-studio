"""Hermes Cloud Studio — Lab Cockpit API (F.3.1).

Backend pra Lab Cockpit dashboard. Dispara lab_runner.py na VM via SSH async,
captura stdout, broadcast WS namespace lab.* em tempo real, persiste runs em
hermes_local.db tabela lab_runs.

Endpoints (auth fail-closed via X-Hermes-Token middleware global):
- POST /api/lab/start              — spawn SSH ssh hermes-gcp@VM "python3 -m linkedin.lab.lab_runner ..."
- POST /api/lab/runs/{id}/abort    — kill SSH process, status='aborted'
- GET  /api/lab/runs               — list paginated (limit, offset, status filter)
- GET  /api/lab/runs/{id}          — detail + artifacts filelist (cached PC mirror)
- GET  /api/lab/runs/{id}/artifacts/{filename} — FileResponse (path-sanitized)

Concurrent gate: 409 Conflict se já há run status='running' (cobaia single
profile, fingerprint binding fragile — só 1 lab por vez).

Rate-limit: POST /start @limiter.limit("3/minute") — lab runs caros.

GUARDRAILS embedded (não burlar):
- 🛑 NUNCA aceitar account_email/profile via body pra prod conta real Caio
  durante F.3 dev. Hardcoded em LINKEDIN_LAB_* env vars na VM.
- 🛑 NUNCA bypass path traversal sanitize em artifacts/{filename} — sempre
  os.path.basename + verify resolved startswith artifacts_dir.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import settings
from core.limiter import limiter
from core.state import (
    PROJECT_ROOT,
    lab_run_create,
    lab_run_get,
    lab_run_is_running,
    lab_run_update,
    lab_runs_list,
    spawn,
    ws_manager,
)

logger = logging.getLogger("hermes.lab")
router = APIRouter()


# ---------------------------------------------------------------------------
# Constantes / paths
# ---------------------------------------------------------------------------

ARTIFACTS_BASE = (PROJECT_ROOT / "linkedin" / "lab" / "artifacts").resolve()
ARTIFACTS_BASE.mkdir(parents=True, exist_ok=True)

ALLOWED_FLOWS = {"fingerprint", "login", "viewer"}

# F.3.5: whitelist 7 event types (sync linkedin/lab/_event_emit.py ALLOWED_EVENTS).
# Mapping 1:1 evt_name -> WS broadcast type lab.<evt_name>. Unknown -> step_progress + warn.
ALLOWED_EVENT_TYPES = frozenset({
    "run_started", "step_progress", "screenshot_captured",
    "compliance_score", "fingerprint_dump", "run_completed", "run_failed",
})

# In-memory registry de processos SSH em execucao (abort target)
_running_processes: dict[str, asyncio.subprocess.Process] = {}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class LabStartRequest(BaseModel):
    flow: str = Field(..., description="fingerprint | login | viewer")
    search: Optional[str] = Field(default=None, description="Viewer search term")
    profile_index: Optional[int] = Field(default=0, ge=0, le=10)
    sites: Optional[str] = Field(default=None, description="CSV subset fingerprint sites")


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

async def _broadcast(event: str, **payload: Any) -> None:
    """Broadcast WS namespace lab.* — fire and forget."""
    try:
        msg = {"type": event, "timestamp": time.time(), **payload}
        await ws_manager.broadcast(msg)
    except Exception:  # noqa: silenciado intencional — WS broadcast best-effort
        logger.exception("lab broadcast falhou: %s", event)


def _build_ssh_command(flow: str, run_id: str, req: LabStartRequest) -> list[str]:
    """Monta ssh + python3 lab_runner CLI args. Sem shell=True (anti-injection)."""
    vm_host = settings.vm_host
    vm_user = settings.vm_user
    # Args lab_runner — flow obrigatorio + flow-specific extras
    runner_args = ["python3", "-m", "linkedin.lab.lab_runner", "--flow", flow]
    if flow == "viewer":
        if req.search:
            runner_args += ["--search", req.search]
        runner_args += ["--profile-index", str(req.profile_index or 0)]
    elif flow == "fingerprint":
        if req.sites:
            runner_args += ["--sites", req.sites]
    # Profile-name sufixo run_id pra user_data_dir isolado por run
    runner_args += ["--profile-name", f"f3run_{run_id[:8]}"]

    # xvfb-run wrapper (VM Linux headless, headful patchright)
    full_cmd = ["xvfb-run", "-a"] + runner_args

    # SSH com BatchMode (sem prompt senha), key auth, ConnectTimeout 15s
    ssh_args = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        "-o", "ServerAliveInterval=30",
        f"{vm_user}@{vm_host}",
        # Comando remoto: cd ~ pra resolver linkedin.lab pacote
        "cd ~ && " + " ".join(_shell_quote(a) for a in full_cmd),
    ]
    return ssh_args


def _shell_quote(arg: str) -> str:
    """Quote bash-safe (POSIX shell em VM Linux). Single-quote escaping."""
    if not arg or any(c in arg for c in ' \t\n\'"\\$`!*?[]{}<>|&;()#~'):
        return "'" + arg.replace("'", "'\\''") + "'"
    return arg


async def _stream_run(run_id: str, proc: asyncio.subprocess.Process, started_at: float) -> None:
    """Consome stdout/stderr line-by-line, parseia JSON events, broadcast WS.

    F.3.1: lab_runner ainda emite print() texto. Parse best-effort — linhas que
    NAO sao JSON viram step_progress text-only. F.3.2 vai padronizar emit JSON
    events nativos no lab_runner.
    """
    stderr_tail: list[str] = []
    last_score: Optional[int] = None
    fingerprint_hash: Optional[str] = None

    async def _read_stream(stream: Optional[asyncio.StreamReader], is_stderr: bool) -> None:
        nonlocal last_score, fingerprint_hash
        if stream is None:
            return
        while True:
            try:
                raw = await stream.readline()
            except Exception:
                break
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            if is_stderr:
                stderr_tail.append(line)
                if len(stderr_tail) > 50:
                    stderr_tail.pop(0)
            # Tenta parse JSON event (F.3.2 vai garantir formato)
            event_payload: Optional[dict] = None
            if line.startswith("{") and line.endswith("}"):
                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, dict) and "event" in parsed:
                        event_payload = parsed
                except Exception:
                    event_payload = None
            if event_payload:
                evt_name = str(event_payload.get("event", "step_progress"))
                # Captura state local pra DB persistencia (preserva comportamento existente)
                if evt_name == "compliance_score":
                    score = event_payload.get("score")
                    if isinstance(score, (int, float)):
                        last_score = int(score)
                elif evt_name == "fingerprint_dump":
                    # F.3.5 BUG #1 fix: era "fingerprint", emit usa "fingerprint_dump"
                    fp = event_payload.get("hash")
                    if isinstance(fp, str):
                        fingerprint_hash = fp
                # F.3.5: WS broadcast 1:1 namespace mapping preservando event identity.
                # Unknown event types -> fallback step_progress + warn (forward compat).
                if evt_name in ALLOWED_EVENT_TYPES:
                    ws_event_type = f"lab.{evt_name}"
                else:
                    logger.warning(
                        "F.3.5 lab event_type fora whitelist: %s — fallback step_progress",
                        evt_name,
                    )
                    ws_event_type = "lab.step_progress"
                # Payload completo broadcast (sanitizer F.3.2 ja strip sensitive emit-side)
                await _broadcast(
                    ws_event_type,
                    run_id=run_id,
                    stream="stderr" if is_stderr else "stdout",
                    **{k: v for k, v in event_payload.items() if k != "event"},
                )
            else:
                # Texto plano viraprogress generico (F.3.1 fallback)
                await _broadcast(
                    "lab.step_progress",
                    run_id=run_id,
                    message=line,
                    stream="stderr" if is_stderr else "stdout",
                )

    # Le ambos streams em paralelo
    await asyncio.gather(
        _read_stream(proc.stdout, is_stderr=False),
        _read_stream(proc.stderr, is_stderr=True),
        return_exceptions=True,
    )
    rc = await proc.wait()
    completed_at = time.time()
    duration_ms = int((completed_at - started_at) * 1000)

    # Pop registry (abort already removed se foi externo)
    _running_processes.pop(run_id, None)

    # Status final — distinguir abort (status já='aborted' no DB) vs natural exit
    current = lab_run_get(run_id)
    if current and current.get("status") == "aborted":
        # Abort path ja persistiu status — apenas broadcast final
        await _broadcast(
            "lab.run_aborted",
            run_id=run_id,
            duration_ms=duration_ms,
        )
        return

    if rc == 0:
        lab_run_update(
            run_id,
            status="success",
            completed_at=completed_at,
            duration_ms=duration_ms,
            compliance_score=last_score,
            fingerprint_hash=fingerprint_hash,
        )
        await _broadcast(
            "lab.run_completed",
            run_id=run_id,
            status="success",
            duration_ms=duration_ms,
            compliance_score=last_score,
        )
    else:
        err = "\n".join(stderr_tail[-10:]) or f"exit_code={rc}"
        lab_run_update(
            run_id,
            status="failed",
            completed_at=completed_at,
            duration_ms=duration_ms,
            error_message=err[:2000],
            compliance_score=last_score,
            fingerprint_hash=fingerprint_hash,
        )
        await _broadcast(
            "lab.run_failed",
            run_id=run_id,
            error=err[:500],
            duration_ms=duration_ms,
        )


def _resolve_artifact_path(run_id: str, filename: str) -> Path:
    """Sanitize filename + verify resolved path dentro de ARTIFACTS_BASE/<run_id>/.

    Levanta HTTPException 400 se path traversal detectado.
    """
    # Strip diretorio + caracteres perigosos
    safe_name = os.path.basename(filename)
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(400, "filename invalido")
    # Run_id deve ser hex-safe (UUID)
    safe_run = "".join(c for c in run_id if c.isalnum() or c in "-_")
    if safe_run != run_id:
        raise HTTPException(400, "run_id invalido")
    target = (ARTIFACTS_BASE / safe_run / safe_name).resolve()
    base = (ARTIFACTS_BASE / safe_run).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(400, "path traversal rejeitado")
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "artifact nao encontrado")
    return target


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/lab/start")
@limiter.limit("3/minute")
async def lab_start(request: Request, body: LabStartRequest):
    """Dispara lab_runner.py na VM via SSH async. Retorna {run_id, started_at}.

    Concurrent gate: 409 se ja existe run status='running' (cobaia single profile).
    Auth global X-Hermes-Token (middleware). Rate-limit 3/min.
    """
    flow = body.flow.strip().lower()
    if flow not in ALLOWED_FLOWS:
        raise HTTPException(400, f"flow invalido — deve ser um de {sorted(ALLOWED_FLOWS)}")

    if lab_run_is_running():
        raise HTTPException(
            409,
            "Ja existe um lab run em andamento. Abort o atual antes de iniciar novo (cobaia single profile)."
        )

    run_id = uuid.uuid4().hex[:16]
    started_at = time.time()
    artifacts_rel = f"linkedin/lab/artifacts/{run_id}"
    lab_run_create(run_id=run_id, flow=flow, started_at=started_at, artifacts_path=artifacts_rel)

    ssh_cmd = _build_ssh_command(flow, run_id, body)
    logger.info("F.3 lab start run_id=%s flow=%s cmd=%s", run_id, flow, " ".join(ssh_cmd[:4]) + " ...")

    try:
        proc = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        lab_run_update(
            run_id,
            status="failed",
            completed_at=time.time(),
            error_message=f"ssh spawn falhou: {e!r}"[:2000],
        )
        await _broadcast("lab.run_failed", run_id=run_id, error=f"ssh spawn falhou: {e!r}"[:500])
        raise HTTPException(500, f"falha ao iniciar SSH: {e}")

    _running_processes[run_id] = proc
    await _broadcast("lab.run_started", run_id=run_id, flow=flow, started_at=started_at)

    # spawn() MERGED-015 — referencia forte anti-GC pra task background
    spawn(_stream_run(run_id, proc, started_at))

    return {"run_id": run_id, "flow": flow, "started_at": started_at, "status": "running"}


@router.post("/api/lab/runs/{run_id}/abort")
async def lab_abort(run_id: str):
    """Mata SSH process + marca status='aborted'. 404 se run inexistente."""
    row = lab_run_get(run_id)
    if not row:
        raise HTTPException(404, "run_id desconhecido")
    if row["status"] != "running":
        return {"run_id": run_id, "status": row["status"], "noop": True}

    proc = _running_processes.get(run_id)
    completed_at = time.time()
    duration_ms = int((completed_at - row["started_at"]) * 1000)

    # Marca primeiro DB (race-safe: _stream_run le status='aborted' e nao sobrescreve)
    lab_run_update(
        run_id,
        status="aborted",
        completed_at=completed_at,
        duration_ms=duration_ms,
        error_message="aborted by owner",
    )

    if proc and proc.returncode is None:
        try:
            proc.terminate()
        except Exception:
            logger.exception("proc.terminate falhou run_id=%s", run_id)
        # Da 3s pra SSH respeitar terminate, senao kill
        try:
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                logger.exception("proc.kill falhou run_id=%s", run_id)

    await _broadcast("lab.run_aborted", run_id=run_id, duration_ms=duration_ms)
    return {"run_id": run_id, "status": "aborted", "duration_ms": duration_ms}


@router.get("/api/lab/runs")
async def lab_runs(limit: int = 50, offset: int = 0, status: Optional[str] = None):
    """Lista paginada DESC by started_at. status='all'|None|running|success|failed|aborted."""
    rows = lab_runs_list(limit=limit, offset=offset, status=status)
    return {"runs": rows, "limit": limit, "offset": offset, "count": len(rows)}


@router.get("/api/lab/runs/{run_id}")
async def lab_run_detail(run_id: str):
    """Detail + artifacts filelist (PC mirror). 404 se inexistente."""
    row = lab_run_get(run_id)
    if not row:
        raise HTTPException(404, "run_id desconhecido")
    artifacts: list[dict] = []
    safe_run = "".join(c for c in run_id if c.isalnum() or c in "-_")
    if safe_run == run_id:
        run_dir = (ARTIFACTS_BASE / safe_run).resolve()
        try:
            run_dir.relative_to(ARTIFACTS_BASE)
            if run_dir.exists() and run_dir.is_dir():
                for entry in sorted(run_dir.iterdir()):
                    if entry.is_file():
                        artifacts.append({
                            "filename": entry.name,
                            "size": entry.stat().st_size,
                            "url": f"/api/lab/runs/{run_id}/artifacts/{entry.name}",
                        })
        except ValueError:
            pass
    row["artifacts"] = artifacts
    return row


@router.get("/api/lab/runs/{run_id}/artifacts/{filename}")
async def lab_artifact(run_id: str, filename: str):
    """Serve PNG/JSON/trace via FileResponse. Path traversal-safe."""
    path = _resolve_artifact_path(run_id, filename)
    return FileResponse(path)
