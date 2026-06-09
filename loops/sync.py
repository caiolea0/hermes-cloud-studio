"""Hermes Cloud Studio — VM sync loop (60s, paginated prospects+activities) — MERGED-011.

MERGED-006: conflict detection via version field. local.last_synced_version
guarda a version VM aplicada pela ultima sincronizacao. Se ambos local e VM
mudaram desde entao -> conflito (conflict_at set + log + ws broadcast).
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone

import httpx

from core.state import (
    SYNC_INTERVAL,
    VM_API_URL,
    get_db,
    is_subsystem_paused,
    logger,
    ws_manager,
)


async def sync_from_vm():
    """Pull ALL prospects and activities from VM API into local SQLite (paginated).

    Importado por trigger_sync (api/hermes.py) e pelo sync_loop deste modulo.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            vm_prospects = []
            offset = 0
            page_size = 500
            while True:
                r = await client.get(
                    f"{VM_API_URL}/api/prospects?limit={page_size}&offset={offset}"
                )
                if r.status_code != 200:
                    break
                batch = r.json().get("prospects", [])
                vm_prospects.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size

            vm_activities = []
            offset = 0
            while True:
                r = await client.get(
                    f"{VM_API_URL}/api/activities?limit={page_size}&offset={offset}"
                )
                if r.status_code != 200:
                    break
                batch = r.json().get("activities", [])
                vm_activities.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size

            r_dashboard = await client.get(f"{VM_API_URL}/api/dashboard")
            vm_dashboard = r_dashboard.json() if r_dashboard.status_code == 200 else {}

            try:
                r_scraper = await client.get(f"{VM_API_URL}/api/scraper/status")
                scraper_data = r_scraper.json() if r_scraper.status_code == 200 else None
            except Exception:  # noqa: silenciado intencional — fallback de sonda
                scraper_data = None

    except Exception as e:
        logger.warning("Sync failed — VM unreachable: %s", e)
        return {"ok": False, "error": str(e)}

    if not vm_prospects and not vm_activities:
        return {"ok": True, "prospects": 0, "new_prospects": 0, "activities": 0, "new_activities": 0}

    conn = get_db()
    try:
        synced_p = 0
        conflicts = 0
        for p in vm_prospects:
            vm_id = p.get("id")
            vm_version = int(p.get("version") or 1)
            existing = conn.execute(
                "SELECT id, version, last_synced_version FROM prospects WHERE vm_id = ?",
                (vm_id,)
            ).fetchone()
            if existing:
                local_version = int(existing["version"] or 1)
                last_synced = int(existing["last_synced_version"] or 0)
                vm_changed = vm_version > last_synced
                local_changed = local_version > max(last_synced, 1)
                if vm_changed and local_changed:
                    # MERGED-006 — conflito: marcar conflict_at, NAO sobrescrever
                    conn.execute(
                        "UPDATE prospects SET conflict_at=? WHERE vm_id=? AND conflict_at IS NULL",
                        (time.time(), vm_id),
                    )
                    conflicts += 1
                    logger.warning(
                        "sync conflict: vm_id=%s local_v=%d vm_v=%d last_synced=%d — preservando local",
                        vm_id, local_version, vm_version, last_synced,
                    )
                    continue
                if not vm_changed:
                    # VM nao mudou desde ultimo sync; nada pra aplicar
                    continue
                # Caso normal: VM mudou, local nao — apply update e atualizar last_synced_version
                conn.execute("""
                    UPDATE prospects SET
                        name=?, business_name=?, category=?, phone=?, email=?,
                        address=?, city=?, state=?, website=?, has_website=?,
                        google_maps_url=?, google_rating=?, google_reviews=?,
                        photo_ref=?,
                        social_instagram=?, social_facebook=?, source=?,
                        score=?, stage=?, audit_summary=?,
                        outreach_message=?, outreach_status=?,
                        version=?, last_synced_version=?,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE vm_id = ?
                """, (
                    p.get("name"), p.get("business_name"), p.get("category"),
                    p.get("phone"), p.get("email"), p.get("address"),
                    p.get("city", "Cuiaba"), p.get("state", "MT"),
                    p.get("website"), p.get("has_website", 0),
                    p.get("google_maps_url"), p.get("google_rating"),
                    p.get("google_reviews", 0), p.get("photo_ref"),
                    p.get("social_instagram"), p.get("social_facebook"),
                    p.get("source", "google_maps"),
                    p.get("score", 0), p.get("stage", "discovered"),
                    p.get("audit_summary"), p.get("outreach_message"),
                    p.get("outreach_status"), vm_version, vm_version, vm_id,
                ))
            else:
                # MERGED-006 — INSERT novo: version=vm_version, last_synced_version=vm_version
                conn.execute("""
                    INSERT INTO prospects (
                        vm_id, name, business_name, category, phone, email,
                        address, city, state, website, has_website,
                        google_maps_url, google_rating, google_reviews,
                        photo_ref,
                        social_instagram, social_facebook, source,
                        score, stage, audit_summary,
                        outreach_message, outreach_status,
                        version, last_synced_version, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    vm_id, p.get("name"), p.get("business_name"), p.get("category"),
                    p.get("phone"), p.get("email"), p.get("address"),
                    p.get("city", "Cuiaba"), p.get("state", "MT"),
                    p.get("website"), p.get("has_website", 0),
                    p.get("google_maps_url"), p.get("google_rating"),
                    p.get("google_reviews", 0), p.get("photo_ref"),
                    p.get("social_instagram"), p.get("social_facebook"),
                    p.get("source", "google_maps"),
                    p.get("score", 0), p.get("stage", "discovered"),
                    p.get("audit_summary"), p.get("outreach_message"),
                    p.get("outreach_status"), vm_version, vm_version,
                    p.get("created_at"),
                ))
                synced_p += 1

        synced_a = 0
        for a in vm_activities:
            vm_id = a.get("id")
            exists = conn.execute("SELECT id FROM activities WHERE vm_id = ?", (vm_id,)).fetchone()
            if not exists:
                vm_prospect_id = a.get("prospect_id")
                local_prospect_id = None
                if vm_prospect_id:
                    row = conn.execute("SELECT id FROM prospects WHERE vm_id = ?", (vm_prospect_id,)).fetchone()
                    if row:
                        local_prospect_id = row[0]
                conn.execute(
                    "INSERT INTO activities (vm_id, type, title, description, prospect_id, metadata, created_at) VALUES (?,?,?,?,?,?,?)",
                    (vm_id, a.get("type"), a.get("title"), a.get("description"),
                     local_prospect_id, a.get("metadata"), a.get("created_at"))
                )
                synced_a += 1

        by_stage = vm_dashboard.get("by_stage", {})
        if by_stage:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            conn.execute("""
                INSERT OR REPLACE INTO pipeline_stats (date, discovered, qualified, audited, outreach_sent)
                VALUES (?, ?, ?, ?, ?)
            """, (
                today,
                by_stage.get("discovered", 0),
                by_stage.get("qualified", 0),
                by_stage.get("audited", 0),
                by_stage.get("outreach", 0),
            ))

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('last_sync', ?, ?)",
            (now, now)
        )
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('vm_status', 'online', ?)",
            (now,)
        )
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('total_synced', ?, ?)",
            (str(len(vm_prospects)), now)
        )
        if scraper_data:
            conn.execute(
                "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('scraper_cache', ?, ?)",
                (json.dumps(scraper_data), now)
            )
        conn.commit()

        total_p = len(vm_prospects)
        total_a = len(vm_activities)
        logger.info(
            "Sync OK — %d prospects (%d new, %d conflicts), %d activities (%d new)",
            total_p, synced_p, conflicts, total_a, synced_a,
        )
        result = {
            "ok": True,
            "prospects": total_p,
            "new_prospects": synced_p,
            "conflicts": conflicts,
            "activities": total_a,
            "new_activities": synced_a,
        }
        await ws_manager.broadcast({"type": "sync", "data": result})
        return result

    except Exception as e:
        logger.error("Sync DB error: %s", e)
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


# F.2.3 — transition tracking pra broadcast daemon.subsystem_status SOMENTE em mudança
# (evita flood WS toda iter de 60s). Canonical emitter pro subsystem='daemon'.
_paused_state: bool = False


async def _emit_subsystem_transition(now_paused: bool) -> None:
    global _paused_state
    if now_paused == _paused_state:
        return
    _paused_state = now_paused
    try:
        await ws_manager.broadcast({
            "type": "daemon.subsystem_status",
            "subsystem": "daemon",
            "status": "paused" if now_paused else "healthy",
            "emitter": "sync_loop",
            "ts": time.time(),
        })
    except Exception:
        logger.exception("sync_loop: ws broadcast subsystem_status falhou")


async def sync_loop():
    """Background loop that syncs from VM every SYNC_INTERVAL seconds.

    F.2.2 — Skip iteration quando subsistema 'daemon' pausado via
    /api/daemon/subsystems/daemon/pause (runtime_state.subsystem_pauses).
    F.2.3 — broadcast daemon.subsystem_status SOMENTE em transição (idle↔paused).
    """
    await asyncio.sleep(2)
    while True:
        paused = is_subsystem_paused("daemon")
        await _emit_subsystem_transition(paused)
        if paused:
            logger.info(
                "sync_loop skip — daemon paused",
                extra={"category": "subsystem_pause", "subsystem": "daemon"},
            )
        else:
            await sync_from_vm()
        await asyncio.sleep(SYNC_INTERVAL)
