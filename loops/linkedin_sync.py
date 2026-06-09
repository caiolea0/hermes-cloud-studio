"""Hermes Cloud Studio — LinkedIn campaigns sync loop (10s) — MERGED-011.

F.2.3 — canonical emitter pro subsystem='linkedin' (linkedin_scheduler defers WS broadcast aqui
pra evitar double-emit; ver loops/linkedin_scheduler.py).
"""
from __future__ import annotations

import asyncio
import json
import time

import httpx

from core.state import (
    VM_API_URL,
    _local_error_until_ack,
    get_db,
    is_subsystem_paused,
    logger,
    ws_manager,
)


async def sync_linkedin_campaigns():
    """Pull running LinkedIn campaigns from VM and update local DB +
    broadcast WS event if state changed. Runs every 10s."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{VM_API_URL}/api/linkedin/campaigns?limit=50")
            if r.status_code != 200:
                return
            data = r.json()
            campaigns = data.get("campaigns", [])
    except Exception:  # noqa: silenciado intencional — fallback seguro
        return

    if not campaigns:
        return

    conn = get_db()
    try:
        any_change = False
        for c in campaigns:
            local = conn.execute(
                "SELECT status, progress FROM linkedin_campaigns WHERE id=?",
                (c["id"],)
            ).fetchone()
            if not local:
                conn.execute("""
                    INSERT INTO linkedin_campaigns
                      (id, type, config, status, progress, total, results, log, started_at, completed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    c["id"], c.get("type"),
                    json.dumps(c.get("config")) if isinstance(c.get("config"), (dict, list)) else (c.get("config") or "{}"),
                    c.get("status"), c.get("progress", 0), c.get("total", 0),
                    json.dumps(c.get("results")) if c.get("results") else None,
                    json.dumps(c.get("log", [])) if isinstance(c.get("log"), list) else (c.get("log") or "[]"),
                    c.get("started_at"), c.get("completed_at"),
                ))
                any_change = True
            elif local["status"] in ("scheduled", "cancelled"):
                # v6: PC owns these states. Skip — never let VM overwrite scheduled/cancelled.
                pass
            elif str(c["id"]) in _local_error_until_ack:
                # MERGED-016: erro de dispatch pendente de ack — não sobrescrever com dados da VM
                logger.debug("sync skip overwrite campaign %s (local error pendente)", c["id"])
            elif local["status"] != c.get("status") or local["progress"] != c.get("progress"):
                conn.execute("""
                    UPDATE linkedin_campaigns
                    SET status=?, progress=?, results=?, completed_at=?
                    WHERE id=?
                """, (
                    c.get("status"), c.get("progress", 0),
                    json.dumps(c.get("results")) if c.get("results") else None,
                    c.get("completed_at"),
                    c["id"],
                ))
                any_change = True
                try:
                    await ws_manager.broadcast({
                        "type": "linkedin_progress",
                        "data": {
                            "campaign_id": c["id"],
                            "status": c.get("status"),
                            "progress": c.get("progress", 0),
                            "partial_results": c.get("results"),
                        }
                    })
                except Exception:  # noqa: silenciado intencional — fallback seguro
                    pass
        if any_change:
            conn.commit()
    finally:
        conn.close()


# F.2.3 — transition tracking pra broadcast daemon.subsystem_status SOMENTE em mudança.
# Canonical emitter pro subsystem='linkedin' (linkedin_scheduler é log-only).
_paused_state: bool = False


async def _emit_subsystem_transition(now_paused: bool) -> None:
    global _paused_state
    if now_paused == _paused_state:
        return
    _paused_state = now_paused
    try:
        await ws_manager.broadcast({
            "type": "daemon.subsystem_status",
            "subsystem": "linkedin",
            "status": "paused" if now_paused else "healthy",
            "emitter": "linkedin_sync_loop",
            "ts": time.time(),
        })
    except Exception:
        logger.exception("linkedin_sync_loop: ws broadcast subsystem_status falhou")


async def linkedin_sync_loop():
    """10s LinkedIn campaigns sync. Lighter than the 60s general sync.

    F.2.2 — Skip iteration quando subsistema 'linkedin' pausado.
    F.2.3 — broadcast daemon.subsystem_status SOMENTE em transição (idle↔paused).
    """
    await asyncio.sleep(5)
    while True:
        try:
            paused = is_subsystem_paused("linkedin")
            await _emit_subsystem_transition(paused)
            if paused:
                logger.info(
                    "linkedin_sync_loop skip — linkedin paused",
                    extra={"category": "subsystem_pause", "subsystem": "linkedin"},
                )
            else:
                await sync_linkedin_campaigns()
        except Exception as e:
            logger.warning(f"linkedin_sync_loop error: {e}")
        await asyncio.sleep(10)
