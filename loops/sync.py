"""Hermes Cloud Studio — VM sync loop (60s, paginated prospects+activities) — MERGED-011."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import httpx

from core.state import (
    SYNC_INTERVAL,
    VM_API_URL,
    get_db,
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
        for p in vm_prospects:
            vm_id = p.get("id")
            existing = conn.execute("SELECT id FROM prospects WHERE vm_id = ?", (vm_id,)).fetchone()
            if existing:
                conn.execute("""
                    UPDATE prospects SET
                        name=?, business_name=?, category=?, phone=?, email=?,
                        address=?, city=?, state=?, website=?, has_website=?,
                        google_maps_url=?, google_rating=?, google_reviews=?,
                        photo_ref=?,
                        social_instagram=?, social_facebook=?, source=?,
                        score=?, stage=?, audit_summary=?,
                        outreach_message=?, outreach_status=?,
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
                    p.get("outreach_status"), vm_id,
                ))
            else:
                conn.execute("""
                    INSERT INTO prospects (
                        vm_id, name, business_name, category, phone, email,
                        address, city, state, website, has_website,
                        google_maps_url, google_rating, google_reviews,
                        photo_ref,
                        social_instagram, social_facebook, source,
                        score, stage, audit_summary,
                        outreach_message, outreach_status, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    p.get("outreach_status"), p.get("created_at"),
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
        logger.info("Sync OK — %d prospects (%d new), %d activities (%d new)", total_p, synced_p, total_a, synced_a)
        result = {"ok": True, "prospects": total_p, "new_prospects": synced_p, "activities": total_a, "new_activities": synced_a}
        await ws_manager.broadcast({"type": "sync", "data": result})
        return result

    except Exception as e:
        logger.error("Sync DB error: %s", e)
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


async def sync_loop():
    """Background loop that syncs from VM every SYNC_INTERVAL seconds."""
    await asyncio.sleep(2)
    while True:
        await sync_from_vm()
        await asyncio.sleep(SYNC_INTERVAL)
