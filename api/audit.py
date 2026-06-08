"""Hermes Cloud Studio — Audit batch + work queue (MERGED-011)."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from core.models import AuditConfig
from core.state import VM_API_URL, get_db

router = APIRouter()


@router.post("/api/audit/start")
async def start_audit(config: AuditConfig):
    """Start batch audit on VM."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{VM_API_URL}/api/audit/start?batch_size={config.batch_size}&stage={config.stage}"
            )
            if r.status_code == 200:
                return r.json()
            return {"status": "error", "detail": f"VM returned {r.status_code}"}
    except Exception as e:
        raise HTTPException(502, f"Could not reach VM: {e}")


@router.get("/api/audit/status")
async def audit_status():
    """Get audit batch progress from VM."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{VM_API_URL}/api/audit/status")
            if r.status_code == 200:
                return r.json()
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass
    return {"running": False, "total": 0, "done": 0, "results": [], "errors": []}


@router.post("/api/audit/prospect/{prospect_id}")
async def audit_single_prospect(prospect_id: int):
    """Audit a single prospect via VM."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{VM_API_URL}/api/audit/prospect/{prospect_id}")
            if r.status_code == 200:
                return r.json()
            return {"status": "error", "detail": f"VM returned {r.status_code}"}
    except Exception as e:
        raise HTTPException(502, f"Could not reach VM: {e}")


@router.get("/api/workqueue")
async def get_work_queue(limit: int = 20):
    """Generate prioritized daily work queue.

    Priority order:
    1. Audited prospects with score >= 70 that have no outreach yet
    2. Discovered prospects without website (ready to audit)
    3. Prospects with outreach ready but not sent
    """
    conn = get_db()
    try:
        queue = []

        # 1. High-score audited — ready for outreach generation
        rows = conn.execute("""
            SELECT * FROM prospects
            WHERE stage = 'audited' AND score >= 70
                AND (outreach_message IS NULL OR outreach_message = '')
            ORDER BY score DESC LIMIT ?
        """, (limit,)).fetchall()
        for r in rows:
            queue.append({**dict(r), "action": "generate_outreach", "action_label": "Gerar Proposta",
                          "priority": "high", "reason": f"Score {r['score']} — pronto para abordagem"})

        # 2. Outreach ready but not sent
        rows2 = conn.execute("""
            SELECT * FROM prospects
            WHERE stage = 'outreach' AND outreach_status = 'ready'
                AND outreach_message IS NOT NULL AND outreach_message != ''
            ORDER BY score DESC LIMIT ?
        """, (limit,)).fetchall()
        for r in rows2:
            queue.append({**dict(r), "action": "send_outreach", "action_label": "Enviar WhatsApp",
                          "priority": "high", "reason": "Proposta pronta — enviar agora"})

        # 3. Top unaudited prospects
        rows3 = conn.execute("""
            SELECT * FROM prospects
            WHERE stage IN ('discovered', 'new')
                AND (audit_summary IS NULL OR audit_summary = '')
                AND has_website = 0
            ORDER BY google_reviews DESC, google_rating DESC LIMIT ?
        """, (limit,)).fetchall()
        for r in rows3:
            rating = r['google_rating'] or 0
            reviews = r['google_reviews'] or 0
            queue.append({**dict(r), "action": "audit", "action_label": "Auditar",
                          "priority": "medium", "reason": f"Sem site — {rating}/5 ({reviews} reviews)"})

        return {"queue": queue[:limit * 2], "total": len(queue)}
    finally:
        conn.close()
