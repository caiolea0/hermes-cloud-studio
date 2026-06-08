"""Hermes Cloud Studio — LinkedIn campaigns + status + passthrough (MERGED-011).

PC orquestra; VM executa. Endpoints aqui sao majoritariamente proxy/orchestration
para os endpoints reais em hermes_api_v2.py na VM.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request

from config import settings
from core.state import (
    VM_API_URL,
    _local_error_until_ack,
    _persist_local_errors,
    get_db,
    logger,
    spawn,
    ws_manager,
)

router = APIRouter()


@router.get("/api/linkedin/rate-limits")
async def linkedin_rate_limits():
    """Get current LinkedIn rate limiter stats and warm-up progress."""
    try:
        from linkedin import LinkedInConfig
        from linkedin.limiter import RateLimiter
        config = LinkedInConfig(
            account_email=settings.linkedin_email or "default",
            account_type=settings.linkedin_account_type,
        )
        limiter = RateLimiter(config)
        return limiter.get_stats()
    except ImportError:
        return {"error": "LinkedIn module not installed", "warmup_multiplier": 0}


@router.get("/api/linkedin/status")
async def linkedin_status():
    """Session health + rate limits — proxied from VM (authoritative source)."""
    vm_session = None
    vm_rate = None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            sess_r, rate_r = await asyncio.gather(
                client.get(f"{VM_API_URL}/api/linkedin/session-check"),
                client.get(f"{VM_API_URL}/api/linkedin/rate-limits"),
                return_exceptions=True,
            )
            if hasattr(sess_r, "json"):
                vm_session = sess_r.json()
            if hasattr(rate_r, "json"):
                vm_rate = rate_r.json()
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass

    if vm_session is not None:
        return {
            "session_ok": vm_session.get("ok", False),
            "account_email": vm_session.get("email") or settings.linkedin_email,
            "account_type": vm_session.get("account_type") or settings.linkedin_account_type,
            "proxy_configured": vm_session.get("proxy_configured", False),
            "proxy_url": vm_session.get("proxy_url"),
            "proxy_alive": vm_session.get("proxy_alive", False),
            "rate_limits": vm_rate or {},
            "source": "vm",
        }

    # VM unreachable — fallback to local guess
    try:
        from linkedin import LinkedInConfig
        from linkedin.limiter import RateLimiter
        config = LinkedInConfig(
            account_email=settings.linkedin_email or "default",
            account_type=settings.linkedin_account_type,
        )
        limiter = RateLimiter(config)
        stats = limiter.get_stats()
        return {
            "session_ok": False,
            "account_email": settings.linkedin_email,
            "account_type": settings.linkedin_account_type,
            "proxy_alive": False,
            "rate_limits": stats,
            "source": "local_fallback",
            "warning": "VM unreachable",
        }
    except Exception as e:
        return {"error": str(e), "session_ok": False, "source": "error"}


@router.post("/api/linkedin/campaigns/{campaign_id}/cancel")
async def linkedin_cancel_scheduled(campaign_id: int):
    """Cancel a scheduled campaign before it fires."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT status FROM linkedin_campaigns WHERE id=?", (campaign_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Campaign not found")
        if row["status"] != "scheduled":
            return {"ok": False, "error": f"Campaign #{campaign_id} is not scheduled (status={row['status']})"}
        conn.execute(
            "UPDATE linkedin_campaigns SET status='cancelled', completed_at=?, "
            "log=COALESCE(log, '[]') WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), campaign_id)
        )
        cur = conn.execute("SELECT log FROM linkedin_campaigns WHERE id=?", (campaign_id,)).fetchone()
        logs = json.loads(cur["log"]) if cur and cur["log"] else []
        logs.append({
            "time": datetime.now(timezone.utc).isoformat(),
            "phase": "cancelled",
            "msg": "Agendamento cancelado pelo usuário",
        })
        conn.execute("UPDATE linkedin_campaigns SET log=? WHERE id=?", (json.dumps(logs), campaign_id))
        conn.commit()
    finally:
        conn.close()
    try:
        await ws_manager.broadcast({
            "type": "linkedin_progress",
            "data": {"campaign_id": campaign_id, "status": "cancelled",
                     "msg": "Agendamento cancelado pelo usuário"}
        })
    except Exception:  # noqa: silenciado intencional — WS/broadcast opcional
        pass
    return {"ok": True, "campaign_id": campaign_id, "status": "cancelled"}


@router.post("/api/linkedin/auth")
async def linkedin_trigger_auth():
    """Trigger LinkedIn auth on VM (opens browser for session establishment)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{VM_API_URL}/api/linkedin/auth")
            return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/api/linkedin/campaigns")
async def list_linkedin_campaigns(limit: int = 20, offset: int = 0):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM linkedin_campaigns ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM linkedin_campaigns").fetchone()[0]
        campaigns = []
        for r in rows:
            c = dict(r)
            c["config"] = json.loads(c["config"]) if c.get("config") else {}
            c["results"] = json.loads(c["results"]) if c.get("results") else None
            c["log"] = json.loads(c["log"]) if c.get("log") else []
            campaigns.append(c)
        return {"campaigns": campaigns, "total": total}
    finally:
        conn.close()


@router.get("/api/linkedin/campaigns/{campaign_id}/log")
async def get_campaign_log(campaign_id: int):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, type, status, progress, total, log, results FROM linkedin_campaigns WHERE id=?",
            (campaign_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Campaign not found")
        c = dict(row)
        c["log"] = json.loads(c["log"]) if c.get("log") else []
        c["results"] = json.loads(c["results"]) if c.get("results") else None
        return c
    finally:
        conn.close()


@router.post("/api/linkedin/campaigns/{campaign_id}/stop")
async def stop_linkedin_campaign(campaign_id: int):
    """Signal VM to stop a running campaign."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE linkedin_campaigns SET status='stopped', completed_at=? WHERE id=? AND status='running'",
            (datetime.now(timezone.utc).isoformat(), campaign_id)
        )
        conn.commit()
    finally:
        conn.close()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{VM_API_URL}/api/linkedin/campaigns/{campaign_id}/stop")
            return r.json()
    except Exception:
        return {"ok": True, "note": "VM unreachable but local status updated"}


async def _compute_schedule_state() -> tuple:
    """Probes VM for current gate state and returns (scheduled_for_iso, reasons[]).

    Returns (None, []) if all 3 gates are clear — campaign can dispatch now.
    Otherwise returns the LATEST ISO timestamp among the active gates, plus
    a list of human-readable reasons (PT-BR).

    Tambem usado por linkedin_scheduler_loop (via late import) — manter assinatura estavel.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            hr, rl = await asyncio.gather(
                client.get(f"{VM_API_URL}/api/linkedin/health"),
                client.get(f"{VM_API_URL}/api/linkedin/rate-limits"),
                return_exceptions=True,
            )
            health = hr.json() if hasattr(hr, "json") else {}
            ratel = rl.json() if hasattr(rl, "json") else {}
    except Exception:  # noqa: silenciado intencional — fallback de sonda
        health, ratel = {}, {}

    candidates = []
    now = datetime.now(timezone.utc)

    if ratel.get("working_hours_ok") is False:
        next_win = ratel.get("next_working_window")
        if next_win:
            try:
                dt = datetime.fromisoformat(next_win)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                reason = ratel.get("working_hours_reason") or "fora do horário"
                candidates.append((dt.astimezone(timezone.utc), f"horário comercial ({reason})"))
            except Exception:  # noqa: silenciado intencional — fallback seguro
                pass

    next_launch = ratel.get("next_launch_in_seconds", 0) or 0
    if next_launch > 0:
        candidates.append((
            now + timedelta(seconds=next_launch),
            f"cooldown 30min entre launches ({(next_launch + 59)//60}min restantes)",
        ))

    if health.get("state") and health.get("state") != "ok":
        retry = health.get("retry_after_seconds") or 0
        state = health.get("state")
        if retry > 0:
            candidates.append((
                now + timedelta(seconds=retry),
                f"LinkedIn {state} (HTTP {health.get('http_code', '?')})",
            ))
        else:
            candidates.append((
                now + timedelta(minutes=5),
                f"LinkedIn {state} ({health.get('reason') or 'verificando recovery'})",
            ))

    if not candidates:
        return None, []

    latest_dt = max(c[0] for c in candidates)
    reasons = [c[1] for c in candidates]
    return latest_dt.isoformat(), reasons


async def _proxy_linkedin_campaign(campaign_type: str, config_data: dict) -> dict:
    """Create local campaign record and dispatch to VM for execution."""
    conn = get_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO linkedin_campaigns (type, config, status, started_at) VALUES (?,?,?,?)",
            (campaign_type, json.dumps(config_data), "pending", now)
        )
        campaign_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    try:
        await ws_manager.broadcast({
            "type": "linkedin_campaign_created",
            "data": {
                "id": campaign_id,
                "type": campaign_type,
                "status": "pending",
                "progress": 0,
                "total": 0,
                "config": config_data,
                "started_at": now,
                "log": [],
                "results": None,
            }
        })
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass

    scheduled_for_iso, schedule_reasons = await _compute_schedule_state()
    if scheduled_for_iso:
        msg = " · ".join(schedule_reasons)
        conn_s = get_db()
        try:
            conn_s.execute(
                "UPDATE linkedin_campaigns SET status='scheduled', "
                "scheduled_for=?, schedule_reason=?, log=? WHERE id=?",
                (scheduled_for_iso, msg,
                 json.dumps([{"time": datetime.now(timezone.utc).isoformat(),
                              "phase": "scheduled", "msg": f"Agendada para {scheduled_for_iso} — {msg}"}]),
                 campaign_id)
            )
            conn_s.commit()
        finally:
            conn_s.close()
        try:
            await ws_manager.broadcast({
                "type": "linkedin_progress",
                "data": {"campaign_id": campaign_id, "status": "scheduled",
                         "scheduled_for": scheduled_for_iso,
                         "schedule_reason": msg}
            })
        except Exception:  # noqa: silenciado intencional — fallback seguro
            pass
        return {
            "ok": True, "campaign_id": campaign_id,
            "status": "scheduled", "scheduled_for": scheduled_for_iso,
            "schedule_reason": msg,
        }

    async def _dispatch():
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"{VM_API_URL}/api/linkedin/campaigns/{campaign_type}",
                    json={"campaign_id": campaign_id, **config_data},
                )
                ack = r.json() if r.status_code == 200 else {"ok": False}
                if not ack.get("ok"):
                    raise RuntimeError(f"VM rejected dispatch: HTTP {r.status_code} {r.text[:200]}")
                logger.info(f"Campaign {campaign_id} dispatched to VM (ack={ack})")
        except Exception as e:
            logger.error(f"LinkedIn campaign dispatch error: {e}")
            _local_error_until_ack[str(campaign_id)] = str(e)
            _persist_local_errors()
            conn3 = get_db()
            try:
                conn3.execute(
                    "UPDATE linkedin_campaigns SET status='error', completed_at=?, "
                    "log=COALESCE(log, '[]') WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(), campaign_id)
                )
                row = conn3.execute("SELECT log FROM linkedin_campaigns WHERE id=?", (campaign_id,)).fetchone()
                logs = json.loads(row["log"]) if row and row["log"] else []
                logs.append({
                    "time": datetime.now(timezone.utc).isoformat(),
                    "msg": f"Falha no dispatch: {e}",
                    "phase": "error",
                })
                conn3.execute("UPDATE linkedin_campaigns SET log=? WHERE id=?",
                              (json.dumps(logs), campaign_id))
                conn3.commit()
            finally:
                conn3.close()
            try:
                await ws_manager.broadcast({
                    "type": "linkedin_progress",
                    "data": {"campaign_id": campaign_id, "status": "error", "msg": str(e)}
                })
            except Exception:  # noqa: silenciado intencional — WS/broadcast opcional
                pass

    spawn(_dispatch())
    return {"ok": True, "campaign_id": campaign_id, "status": "dispatched"}


@router.post("/api/linkedin/campaigns/{campaign_id}/dismiss-error")
async def dismiss_error_campaign(campaign_id: int):
    """Remove erro pendente de dispatch (MERGED-016). Permite sync sobrescrever estado."""
    removed = _local_error_until_ack.pop(str(campaign_id), None)
    if removed is not None:
        _persist_local_errors()
        logger.info("dismiss-error campaign %s: %s", campaign_id, removed)
    return {"ok": True, "campaign_id": campaign_id}


@router.post("/api/linkedin/campaigns/view")
async def start_view_campaign(request: Request):
    data = await request.json()
    return await _proxy_linkedin_campaign("view", data)


@router.post("/api/linkedin/campaigns/engage")
async def start_engage_campaign(request: Request):
    data = await request.json()
    return await _proxy_linkedin_campaign("engage", data)


@router.post("/api/linkedin/campaigns/connect")
async def start_connect_campaign(request: Request):
    data = await request.json()
    return await _proxy_linkedin_campaign("connect", data)


@router.post("/api/linkedin/campaigns/discover")
async def start_discover_campaign(request: Request):
    data = await request.json()
    return await _proxy_linkedin_campaign("discover", data)


# ─── Generic VM passthroughs ─────────────────────────────────────────────

async def _vm_passthrough(method: str, path: str, json_body: dict = None,
                          params: dict = None, timeout: float = 30.0):
    """Generic VM passthrough helper."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.request(method, f"{VM_API_URL}{path}",
                                     json=json_body, params=params)
            return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/linkedin/comment/edit")
async def linkedin_comment_edit(request: Request):
    body = await request.json()
    return await _vm_passthrough("POST", "/api/linkedin/comment/edit", json_body=body, timeout=120)


@router.post("/api/linkedin/comment/delete")
async def linkedin_comment_delete(request: Request):
    body = await request.json()
    return await _vm_passthrough("POST", "/api/linkedin/comment/delete", json_body=body, timeout=120)


@router.get("/api/linkedin/visited")
async def linkedin_visited(limit: int = 100, days: int = 30):
    return await _vm_passthrough("GET", "/api/linkedin/visited",
                                  params={"limit": limit, "days": days})


@router.get("/api/linkedin/profiles")
async def linkedin_profile_by_url(url: str):
    return await _vm_passthrough("GET", "/api/linkedin/profiles",
                                  params={"url": url}, timeout=10)


@router.get("/api/linkedin/companies/lookup")
async def linkedin_company_lookup(name: str):
    return await _vm_passthrough("GET", "/api/linkedin/companies/lookup",
                                  params={"name": name})


@router.post("/api/linkedin/detect-account-type")
async def linkedin_detect_account_type():
    return await _vm_passthrough("POST", "/api/linkedin/detect-account-type", timeout=120)


@router.get("/api/linkedin/health")
async def linkedin_health(force_refresh: bool = False):
    """Pass-through to VM health probe. UI calls this to enable/disable launch buttons."""
    return await _vm_passthrough(
        "GET", "/api/linkedin/health",
        params={"force_refresh": str(force_refresh).lower()},
        timeout=20,
    )


@router.post("/api/linkedin/health/clear")
async def linkedin_health_clear():
    return await _vm_passthrough("POST", "/api/linkedin/health/clear", timeout=10)


@router.post("/api/linkedin/connection/refresh")
async def linkedin_connection_refresh(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass
    return await _vm_passthrough("POST", "/api/linkedin/connection/refresh",
                                  json_body=body, timeout=600)
