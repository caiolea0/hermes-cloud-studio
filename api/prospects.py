"""Hermes Cloud Studio — Prospects CRUD + strategy generation (MERGED-011)."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException

from core.ai import execute_claude_command
from core.models import BulkProspectAction, ClaudeCommand, ProspectCreate, ProspectUpdate
from core.state import get_db

router = APIRouter()


@router.get("/api/prospects")
async def list_prospects(
    stage: Optional[str] = None,
    city: Optional[str] = None,
    category: Optional[str] = None,
    has_website: Optional[bool] = None,
    search: Optional[str] = None,
    min_score: int = 0,
    limit: int = 50,
    offset: int = 0,
):
    conn = get_db()
    try:
        query = "SELECT * FROM prospects WHERE score >= ?"
        count_query = "SELECT COUNT(*) FROM prospects WHERE score >= ?"
        params: list = [min_score]
        count_params: list = [min_score]
        if stage:
            query += " AND stage = ?"
            count_query += " AND stage = ?"
            params.append(stage)
            count_params.append(stage)
        if city:
            query += " AND city = ?"
            count_query += " AND city = ?"
            params.append(city)
            count_params.append(city)
        if category:
            query += " AND category LIKE ?"
            count_query += " AND category LIKE ?"
            params.append(f"%{category}%")
            count_params.append(f"%{category}%")
        if has_website is not None:
            query += " AND has_website = ?"
            count_query += " AND has_website = ?"
            params.append(1 if has_website else 0)
            count_params.append(1 if has_website else 0)
        if search:
            query += " AND (business_name LIKE ? OR name LIKE ? OR category LIKE ? OR city LIKE ?)"
            count_query += " AND (business_name LIKE ? OR name LIKE ? OR category LIKE ? OR city LIKE ?)"
            s = f"%{search}%"
            params.extend([s, s, s, s])
            count_params.extend([s, s, s, s])

        total = conn.execute(count_query, count_params).fetchone()[0]
        query += " ORDER BY score DESC, created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]
        return {"total": total, "count": len(rows), "prospects": rows}
    finally:
        conn.close()


@router.get("/api/prospects/cities")
async def list_cities():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT city, COUNT(*) as count FROM prospects GROUP BY city ORDER BY count DESC"
        ).fetchall()
        return {"cities": [{"city": r[0], "count": r[1]} for r in rows]}
    finally:
        conn.close()


@router.get("/api/prospects/categories")
async def list_categories():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, COUNT(*) as count FROM prospects GROUP BY category ORDER BY count DESC LIMIT 50"
        ).fetchall()
        return {"categories": [{"category": r[0], "count": r[1]} for r in rows]}
    finally:
        conn.close()


@router.get("/api/prospects/{prospect_id}")
async def get_prospect(prospect_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Prospect not found")
        activities = [dict(r) for r in conn.execute(
            "SELECT * FROM activities WHERE prospect_id = ? ORDER BY created_at DESC",
            (prospect_id,)
        ).fetchall()]
        return {**dict(row), "activities": activities}
    finally:
        conn.close()


@router.post("/api/prospects")
async def create_prospect(p: ProspectCreate):
    conn = get_db()
    try:
        has_website = 1 if p.website else 0
        cur = conn.execute(
            """INSERT INTO prospects (name, business_name, category, phone, email,
               address, city, state, website, has_website, google_maps_url,
               google_rating, google_reviews, photo_ref, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (p.name, p.business_name, p.category, p.phone, p.email,
             p.address, p.city, p.state, p.website, has_website,
             p.google_maps_url, p.google_rating, p.google_reviews, p.photo_ref, p.source)
        )
        conn.commit()
        conn.execute(
            "INSERT INTO activities (type, title, prospect_id) VALUES (?, ?, ?)",
            ("discovery", f"Novo prospect: {p.business_name or p.name}", cur.lastrowid)
        )
        conn.commit()
        return {"id": cur.lastrowid, "status": "created"}
    finally:
        conn.close()


@router.patch("/api/prospects/{prospect_id}")
async def update_prospect(prospect_id: int, update: ProspectUpdate):
    conn = get_db()
    try:
        sets = []
        params = []
        for field, value in update.model_dump(exclude_none=True).items():
            sets.append(f"{field} = ?")
            params.append(value)
        if not sets:
            raise HTTPException(400, "No fields to update")
        # MERGED-006 — bump version pra sync conflict detection
        sets.append("updated_at = CURRENT_TIMESTAMP")
        sets.append("version = version + 1")
        params.append(prospect_id)
        conn.execute(f"UPDATE prospects SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        return {"status": "updated"}
    finally:
        conn.close()


@router.post("/api/prospects/{prospect_id}/resolve-conflict")
async def resolve_prospect_conflict(prospect_id: int):
    """MERGED-006 — owner dismiss conflict flag depois de inspecionar/editar manualmente."""
    conn = get_db()
    try:
        cur = conn.execute(
            "UPDATE prospects SET conflict_at = NULL WHERE id = ? AND conflict_at IS NOT NULL",
            (prospect_id,)
        )
        conn.commit()
        if cur.rowcount == 0:
            return {"status": "no_conflict"}
        return {"status": "resolved"}
    finally:
        conn.close()


@router.post("/api/prospects/bulk")
async def bulk_prospect_action(action: BulkProspectAction):
    conn = get_db()
    try:
        if action.action == "stage_change":
            placeholders = ",".join("?" for _ in action.ids)
            conn.execute(
                f"UPDATE prospects SET stage = ?, updated_at = CURRENT_TIMESTAMP, version = version + 1 WHERE id IN ({placeholders})",
                [action.value] + action.ids
            )
        elif action.action == "score_update":
            placeholders = ",".join("?" for _ in action.ids)
            conn.execute(
                f"UPDATE prospects SET score = ?, updated_at = CURRENT_TIMESTAMP, version = version + 1 WHERE id IN ({placeholders})",
                [int(action.value)] + action.ids
            )
        conn.commit()
        return {"status": "updated", "count": len(action.ids)}
    finally:
        conn.close()


@router.post("/api/prospects/{prospect_id}/strategy")
async def generate_strategy(prospect_id: int):
    """Send prospect to Claude Code for marketing strategy generation."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Prospect not found")
        p = dict(row)
    finally:
        conn.close()

    has_site = "com website" if p.get("website") else "SEM website"
    prompt = (
        f"Crie uma estrategia de marketing digital completa para prospectar o cliente: "
        f"{p['business_name']} ({p.get('category', 'negocio')}) em {p.get('city', 'Cuiaba')}, MT. "
        f"O negocio {has_site}. "
        f"Google rating: {p.get('google_rating', 'N/A')}/5 ({p.get('google_reviews', 0)} avaliacoes). "
        f"Telefone: {p.get('phone', 'N/A')}. "
        f"Inclua: 1) Analise do potencial digital, 2) Proposta de servicos personalizados, "
        f"3) Mensagem de abordagem para WhatsApp, 4) Mensagem para email, "
        f"5) Estrategia de conteudo sugerida. "
        f"Responda em portugues brasileiro, tom profissional mas acessivel."
    )
    return await execute_claude_command(ClaudeCommand(command=prompt, context=json.dumps(p, default=str)))
