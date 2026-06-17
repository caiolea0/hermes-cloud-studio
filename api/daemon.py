"""Hermes Cloud Studio — Daemon state, log, decisions, channels, timeline (MERGED-011).

F.2.1 — Subsystems endpoint + pause/resume individual.
Persiste em `runtime_state.subsystem_pauses` (JSON map name -> until_ts) via
set_runtime_state pattern (NÃO ALTER TABLE) pra evitar migration race PC/VM.
"""
from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from core.limiter import limiter
from core.state import (
    PROJECT_ROOT,
    get_db,
    get_runtime_state,
    set_runtime_state,
    ws_manager,
)

router = APIRouter()


# F.2.1 — 6 subsistemas controlavéis individualmente (alinhado GUARDRAILS §F.2)
SUBSYSTEMS = ("linkedin", "email", "scraper", "audit", "daemon", "tunnel")


def _load_pauses() -> dict[str, float]:
    """Lê runtime_state.subsystem_pauses, descartando entries expiradas."""
    raw = get_runtime_state("subsystem_pauses", {}) or {}
    if not isinstance(raw, dict):
        return {}
    now = time.time()
    return {k: float(v) for k, v in raw.items() if isinstance(v, (int, float)) and float(v) > now}


def _save_pauses(pauses: dict[str, float]) -> None:
    set_runtime_state("subsystem_pauses", pauses)


def _tunnel_state() -> dict:
    sp = PROJECT_ROOT / "logs" / "tunnel_supervisor_state.json"
    if not sp.exists():
        return {}
    try:
        return json.loads(sp.read_text(encoding="utf-8"))
    except Exception:  # noqa: silenciado intencional — state.json corrompido cai p/ default
        return {}


@router.get("/api/daemon/state")
async def get_daemon_state():
    """Get current daemon state, energy, channels, stats."""
    conn = get_db()
    row = conn.execute("SELECT * FROM daemon_state WHERE id = 1").fetchone()
    conn.close()
    if not row:
        return {"state": "offline", "energy": 0, "stats_today": {}, "channels": {}}
    return {
        "state": row["state"],
        "current_task_type": row["current_task_type"],
        "current_task_detail": row["current_task_detail"],
        "energy": row["energy"],
        "last_heartbeat": row["last_heartbeat"],
        "stats_today": json.loads(row["stats_today"]) if row["stats_today"] else {},
        "stats_week": json.loads(row["stats_week"]) if row["stats_week"] else {},
    }


@router.post("/api/daemon/pause")
async def pause_daemon(minutes: int = Query(default=60)):
    """Pause daemon for N minutes."""
    conn = get_db()
    conn.execute("UPDATE daemon_state SET state = 'paused' WHERE id = 1")
    conn.commit()
    conn.close()
    await ws_manager.broadcast({"type": "daemon_state", "state": "paused", "detail": f"Paused for {minutes}m"})
    return {"ok": True, "paused_for": minutes}


@router.post("/api/daemon/resume")
async def resume_daemon():
    """Resume daemon from pause."""
    conn = get_db()
    conn.execute("UPDATE daemon_state SET state = 'idle' WHERE id = 1")
    conn.commit()
    conn.close()
    await ws_manager.broadcast({"type": "daemon_state", "state": "idle", "detail": "Resumed"})
    return {"ok": True}


@router.get("/api/daemon/log")
async def get_daemon_log(limit: int = Query(default=50), category: Optional[str] = None):
    """Get daemon activity log for live feed."""
    conn = get_db()
    if category:
        rows = conn.execute(
            "SELECT * FROM daemon_log WHERE category = ? ORDER BY timestamp DESC LIMIT ?",
            (category, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM daemon_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "level": r["level"],
            "category": r["category"],
            "message": r["message"],
            "metadata": json.loads(r["metadata"]) if r["metadata"] else None,
            "visual_event": json.loads(r["visual_event"]) if r["visual_event"] else None,
        }
        for r in rows
    ]


@router.get("/api/daemon/decisions")
async def get_daemon_decisions(limit: int = Query(default=20)):
    """Get recent AI decisions with reasoning."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM daemon_decisions ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "action": r["action"],
            "reason": r["reason"],
            "context": json.loads(r["context"]) if r["context"] else None,
        }
        for r in rows
    ]


@router.get("/api/daemon/channels")
async def get_daemon_channels():
    """Get channel states for health cards — real DB data (B21)."""
    li_state = get_runtime_state("li_health_last_state", None)
    li_health = 1.0 if li_state in (None, "ok") else 0.4 if li_state == "cooldown" else 0.0

    # LinkedIn campaigns daily stats from local DB
    li_daily_used = 0
    li_daily_limit = 70
    li_warmup_day = 0
    li_warmup_complete = False
    try:
        conn = get_db()
        try:
            row = conn.execute("""
                SELECT COUNT(*) as cnt FROM linkedin_campaigns
                WHERE date(created_at) = date('now') AND status IN ('completed','running')
            """).fetchone()
            li_daily_used = row["cnt"] if row else 0
        finally:
            conn.close()
    except Exception:
        pass

    # LinkedIn rate-limiter warmup state (best-effort)
    try:
        from config import settings
        from linkedin import LinkedInConfig
        from linkedin.limiter import RateLimiter as LiRateLimiter
        _li_cfg = LinkedInConfig(
            account_email=settings.linkedin_email or "default",
            account_type=settings.linkedin_account_type,
        )
        _li_stats = LiRateLimiter(_li_cfg).get_stats()
        li_daily_used = _li_stats.get("views_today", li_daily_used)
        li_daily_limit = _li_stats.get("daily_view_limit", li_daily_limit)
        li_warmup_day = _li_stats.get("warmup_day", 0)
        li_warmup_complete = bool(_li_stats.get("warmup_complete", False))
    except Exception:
        pass

    # Email daily stats from EmailLimiter
    em_daily_used = 0
    em_daily_limit = 40
    em_warmup_day = 0
    em_warmup_complete = False
    try:
        from config import settings as _settings
        from channels.email.config import EmailConfig
        from channels.email.limiter import EmailLimiter
        _em_cfg = EmailConfig.from_settings()
        _em_lim = EmailLimiter(_em_cfg)
        em_stats = _em_lim.stats()
        em_daily_used = em_stats.get("daily_sent", 0)
        em_daily_limit = em_stats.get("daily_cap", 40)
        em_warmup_day = em_stats.get("warmup_day", 0)
        em_warmup_complete = em_warmup_day >= em_stats.get("warmup_days_total", 14)
    except Exception:
        pass

    em_health = max(0.0, 1.0 - (em_daily_used / max(1, em_daily_limit)))

    return {
        "linkedin": {
            "daily_used": li_daily_used,
            "daily_limit": li_daily_limit,
            "health": li_health,
            "warmup_day": li_warmup_day,
            "warmup_complete": li_warmup_complete,
            "is_active": li_state in (None, "ok"),
            "state": li_state or "ok",
        },
        "email": {
            "daily_used": em_daily_used,
            "daily_limit": em_daily_limit,
            "health": round(em_health, 3),
            "warmup_day": em_warmup_day,
            "warmup_complete": em_warmup_complete,
            "is_active": True,
        },
        "whatsapp": {"daily_used": 0, "daily_limit": 25, "health": None, "status": "not_configured", "is_active": False},
        "instagram": {"daily_used": 0, "daily_limit": 50, "health": None, "status": "not_configured", "is_active": False},
    }


@router.get("/api/daemon/timeline")
async def get_daemon_timeline():
    """Get 24h activity timeline for visual bar."""
    conn = get_db()
    rows = conn.execute("""
        SELECT
            strftime('%H', timestamp) as hour,
            category,
            COUNT(*) as count
        FROM daemon_log
        WHERE date(timestamp) = date('now')
        GROUP BY hour, category
        ORDER BY hour
    """).fetchall()
    conn.close()

    timeline = {}
    for h in range(24):
        timeline[str(h).zfill(2)] = {"categories": {}, "total": 0}
    for r in rows:
        h = r["hour"]
        if h in timeline:
            timeline[h]["categories"][r["category"]] = r["count"]
            timeline[h]["total"] += r["count"]

    return timeline


@router.post("/api/daemon/broadcast")
async def daemon_broadcast(request: Request):
    """Internal endpoint for daemon to broadcast events to connected WebSocket clients."""
    body = await request.json()
    await ws_manager.broadcast(body)
    return {"ok": True}


# ---------------------------------------------------------------------------
# F.2.1 — Subsystems snapshot + pause/resume individual
# ---------------------------------------------------------------------------


@router.get("/api/daemon/subsystems")
async def get_daemon_subsystems():
    """Snapshot agregado dos 6 subsistemas (linkedin/email/scraper/audit/daemon/tunnel).

    Lê:
    - daemon_state row (state global + last_heartbeat)
    - runtime_state.subsystem_pauses (paused map name -> until_ts)
    - tunnel_supervisor_state.json (egress residential)

    Status normalizado: 'paused' | 'healthy' | 'warning' | 'error' | 'offline'.
    """
    pauses = _load_pauses()
    now = time.time()

    conn = get_db()
    row = conn.execute(
        "SELECT state, last_heartbeat, current_task_type, current_task_detail, stats_today "
        "FROM daemon_state WHERE id = 1"
    ).fetchone()
    conn.close()

    daemon_state_value = row["state"] if row else "offline"
    last_heartbeat = row["last_heartbeat"] if row else None
    stats_today = {}
    if row and row["stats_today"]:
        try:
            stats_today = json.loads(row["stats_today"])
        except Exception:  # noqa: silenciado intencional — stats_today legacy/corrupto
            stats_today = {}

    tstate = _tunnel_state()

    def _entry(name: str, status: str, **extra) -> dict:
        paused_until = pauses.get(name)
        if paused_until:
            status = "paused"
        return {
            "name": name,
            "status": status,
            "paused": bool(paused_until),
            "paused_until_ts": paused_until,
            "paused_seconds_remaining": int(paused_until - now) if paused_until else 0,
            **extra,
        }

    subsystems = [
        _entry(
            "daemon",
            status=(daemon_state_value if daemon_state_value in {"idle", "working", "paused", "error"} else "offline"),
            current_task_type=(row["current_task_type"] if row else None),
            current_task_detail=(row["current_task_detail"] if row else None),
            last_heartbeat=last_heartbeat,
        ),
        _entry(
            "linkedin",
            status="healthy" if daemon_state_value != "offline" else "offline",
            actions_today=int(stats_today.get("linkedin", 0)),
        ),
        _entry(
            "email",
            status="healthy" if daemon_state_value != "offline" else "offline",
            actions_today=int(stats_today.get("email", 0)),
        ),
        _entry(
            "scraper",
            status="healthy" if daemon_state_value != "offline" else "offline",
            actions_today=int(stats_today.get("scraper", 0)),
        ),
        _entry(
            "audit",
            status="healthy" if daemon_state_value != "offline" else "offline",
            actions_today=int(stats_today.get("audit", 0)),
        ),
        _entry(
            "tunnel",
            status=(
                "healthy" if tstate.get("egress_residential") else
                "error" if tstate else "offline"
            ),
            egress_ip=tstate.get("egress_ip", ""),
            socks5_listening=tstate.get("socks5_listening", False),
            vm_tunnel_landed=tstate.get("vm_tunnel_landed", False),
            updated_at=tstate.get("updated_at"),
        ),
    ]

    return {
        "subsystems": subsystems,
        "global_state": daemon_state_value,
        "server_time": now,
    }


def _assert_known_subsystem(name: str) -> None:
    if name not in SUBSYSTEMS:
        raise HTTPException(
            404,
            f"subsistema '{name}' desconhecido. Válidos: {','.join(SUBSYSTEMS)}",
        )


async def _pause_subsystem_core(name: str, minutes: int) -> float:
    """Core pause logic — set runtime_state + broadcast WS daemon.subsystem_status.

    Idempotente: re-pause SUBSTITUI paused_until_ts (não estende cumulative).
    Reusado pelo endpoint individual F.2.1 e pelo panic F.2.5b (all/pause).
    Retorna until_ts (epoch seconds). Não valida `name` — caller deve validar.
    """
    pauses = _load_pauses()
    until_ts = time.time() + (minutes * 60)
    pauses[name] = until_ts
    _save_pauses(pauses)
    await ws_manager.broadcast(
        {
            "type": "daemon.subsystem_status",
            "subsystem": name,
            "status": "paused",
            "paused_until_ts": until_ts,
            "minutes": minutes,
        }
    )
    return until_ts


@router.post("/api/daemon/subsystems/all/pause")
@limiter.limit("5/minute")
async def pause_all_subsystems(request: Request, minutes: int = Query(default=5, ge=1, le=720)):
    """Panic button — pausa TODOS os 6 subsistemas por N minutos (best-effort sequential).

    F.2.5b. Reusa `_pause_subsystem_core` em loop, captura exceções per-subsistema,
    NÃO atomic (se 3º falhar, primeiros 2 ficam pausados — owner vê failed[] e decide retry).

    Idempotente: re-panic SUBSTITUI paused_until_ts existente (não estende cumulative).
    Re-panic 5min sobre pausa antiga 10min = ficam todos pausados 5min a partir de NOW.

    Broadcasts: 1 daemon.subsystem_status por subsistema pausado com sucesso (sequencial).
    Frontend SubsystemTileGrid F.2.5a faz update incremental per-tile.

    Rate-limit baixo (5/min) porque panic não deve ser alta frequência — anti-abuse.

    NÃO incluso (defer F.2.future ou F.6 Brain audit):
    - Telegram notification panic event
    - Audit trail em activities table
    """
    paused: list[str] = []
    failed: list[dict] = []
    last_until_ts: Optional[float] = None
    for name in SUBSYSTEMS:
        try:
            until_ts = await _pause_subsystem_core(name, minutes)
            paused.append(name)
            last_until_ts = until_ts
        except Exception as exc:  # noqa: best-effort partial success — logado e retornado
            import logging
            logging.getLogger(__name__).exception("panic pause %s failed", name)
            failed.append({"name": name, "error": str(exc)[:200]})
    return {
        "ok": len(paused) > 0,
        "minutes": minutes,
        "paused_until_ts": last_until_ts,
        "paused": paused,
        "failed": failed,
    }


@router.post("/api/daemon/subsystems/{name}/pause")
@limiter.limit("30/minute")
async def pause_subsystem(request: Request, name: str, minutes: int = Query(default=60, ge=1, le=720)):
    """Pausa um subsistema por N minutos. Persiste em runtime_state.subsystem_pauses."""
    _assert_known_subsystem(name)
    until_ts = await _pause_subsystem_core(name, minutes)
    return {"ok": True, "name": name, "paused_until_ts": until_ts, "minutes": minutes}


@router.post("/api/daemon/subsystems/{name}/resume")
@limiter.limit("30/minute")
async def resume_subsystem(request: Request, name: str):
    """Remove pausa de um subsistema. No-op se não estava pausado."""
    _assert_known_subsystem(name)
    pauses = _load_pauses()
    was_paused = pauses.pop(name, None) is not None
    _save_pauses(pauses)
    event = {
        "type": "daemon.subsystem_status",
        "subsystem": name,
        "status": "active",
    }
    await ws_manager.broadcast(event)
    return {"ok": True, "name": name, "was_paused": was_paused}
