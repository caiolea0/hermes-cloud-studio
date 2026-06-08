"""Hermes Cloud Studio — LinkedIn scheduler loop (dispatch scheduled campaigns) — MERGED-011."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import httpx

from core.state import (
    VM_API_URL,
    _telegram_notify,
    get_db,
    is_subsystem_paused,
    logger,
    spawn,
    ws_manager,
)


async def linkedin_scheduler_loop():
    """Every 30s: find scheduled campaigns whose scheduled_for has elapsed AND
    all gates are clear, then dispatch them. Postpones (recomputes scheduled_for)
    if gates still active."""
    await asyncio.sleep(20)
    while True:
        try:
            # F.2.2 — Skip iteration quando subsistema 'linkedin' pausado.
            if is_subsystem_paused("linkedin"):
                logger.info(
                    "linkedin_scheduler_loop skip — linkedin paused",
                    extra={"category": "subsystem_pause", "subsystem": "linkedin"},
                )
                await asyncio.sleep(30)
                continue
            now_iso = datetime.now(timezone.utc).isoformat()
            conn = get_db()
            try:
                rows = conn.execute(
                    "SELECT id, type, config FROM linkedin_campaigns "
                    "WHERE status='scheduled' AND scheduled_for <= ? "
                    "ORDER BY scheduled_for ASC",
                    (now_iso,)
                ).fetchall()
            finally:
                conn.close()

            for r in rows:
                cid = r["id"]
                ctype = r["type"]
                try:
                    cfg = json.loads(r["config"] or "{}")
                except Exception:  # noqa: silenciado intencional — fallback de sonda
                    cfg = {}

                # Late import: api.linkedin importa core.state que importa state; circular se top-level.
                from api.linkedin import _compute_schedule_state
                new_sched, reasons = await _compute_schedule_state()
                if new_sched:
                    msg = " · ".join(reasons)
                    conn2 = get_db()
                    try:
                        conn2.execute(
                            "UPDATE linkedin_campaigns SET scheduled_for=?, schedule_reason=? "
                            "WHERE id=? AND status='scheduled'",
                            (new_sched, msg, cid)
                        )
                        conn2.commit()
                    finally:
                        conn2.close()
                    try:
                        await ws_manager.broadcast({
                            "type": "linkedin_progress",
                            "data": {"campaign_id": cid, "status": "scheduled",
                                     "scheduled_for": new_sched, "schedule_reason": msg}
                        })
                    except Exception:  # noqa: silenciado intencional — WS/broadcast opcional
                        pass
                    continue

                conn3 = get_db()
                try:
                    conn3.execute(
                        "UPDATE linkedin_campaigns SET status='pending', "
                        "started_at=?, scheduled_for=NULL, schedule_reason=NULL "
                        "WHERE id=? AND status='scheduled'",
                        (datetime.now(timezone.utc).isoformat(), cid)
                    )
                    conn3.commit()
                finally:
                    conn3.close()

                try:
                    await ws_manager.broadcast({
                        "type": "linkedin_progress",
                        "data": {"campaign_id": cid, "status": "pending",
                                 "msg": "Scheduler disparou campanha agendada"}
                    })
                except Exception:  # noqa: silenciado intencional — WS/broadcast opcional
                    pass

                async def _fire(cid=cid, ctype=ctype, cfg=cfg):
                    try:
                        async with httpx.AsyncClient(timeout=30) as client:
                            r = await client.post(
                                f"{VM_API_URL}/api/linkedin/campaigns/{ctype}",
                                json={"campaign_id": cid, **cfg},
                            )
                            ack = r.json() if r.status_code == 200 else {"ok": False}
                            if not ack.get("ok"):
                                raise RuntimeError(f"VM rejected: HTTP {r.status_code}")
                        type_label = {"view": "Visitar Perfis", "engage": "Engajar Posts",
                                      "connect": "Enviar Conexões", "discover": "Descobrir Empresas"}.get(ctype, ctype)
                        await _telegram_notify(
                            f"🚀 Hermes disparou campanha agendada #{cid} ({type_label})"
                        )
                    except Exception as e:
                        logger.error(f"Scheduler dispatch error for #{cid}: {e}")
                        conn_e = get_db()
                        try:
                            conn_e.execute(
                                "UPDATE linkedin_campaigns SET status='error', completed_at=? WHERE id=?",
                                (datetime.now(timezone.utc).isoformat(), cid)
                            )
                            conn_e.commit()
                        finally:
                            conn_e.close()
                spawn(_fire())
        except Exception as e:
            logger.warning(f"linkedin_scheduler_loop error: {e}")
        await asyncio.sleep(30)
