"""Hermes Cloud Studio — Outreach message generation (MERGED-011)."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from core.state import VM_API_URL, get_db

router = APIRouter()


@router.post("/api/outreach/generate/{prospect_id}")
async def generate_outreach_for_prospect(prospect_id: int):
    """Generate outreach message for a prospect via VM pipeline."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Prospect not found")
        p = dict(row)
    finally:
        conn.close()

    # Try to generate via VM
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{VM_API_URL}/api/prospects/{p.get('vm_id', prospect_id)}/outreach")
            if r.status_code == 200:
                data = r.json()
                conn = get_db()
                try:
                    conn.execute("""
                        UPDATE prospects SET
                            outreach_message = ?, outreach_status = 'ready',
                            stage = 'outreach', updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (data.get("whatsapp_message", ""), prospect_id))
                    conn.execute(
                        "INSERT INTO activities (type, title, description, prospect_id) VALUES (?,?,?,?)",
                        ("outreach", f"Proposta gerada: {p.get('business_name', p.get('name', '?'))}",
                         f"Servicos: {', '.join(data.get('recommended_services', [])[:3])}", prospect_id)
                    )
                    conn.commit()
                finally:
                    conn.close()
                return data
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass

    # Fallback: generate locally using template
    has_site = bool(p.get("website"))
    name = p.get("business_name") or p.get("name", "")
    city = p.get("city", "Cuiaba")
    category = (p.get("category") or "negocio").lower()
    rating = p.get("google_rating")
    reviews = p.get("google_reviews", 0)

    if not has_site:
        msg = f"Ola! Me chamo Caio Leao, designer e estrategista digital em {city}.\n\n"
        msg += f"Encontrei o(a) *{name}* no Google Maps"
        if rating and rating >= 4.0:
            msg += f" e vi a avaliacao excelente ({rating}/5 com {reviews} avaliacoes)!"
        msg += f".\n\nNotei que voces ainda nao tem site — isso e uma grande oportunidade! "
        msg += f"Posso ajudar o(a) {name} a aparecer no topo do Google e atrair mais clientes.\n\n"
        msg += "Posso enviar exemplos do meu trabalho? Sem compromisso!\n\nCaio Leao\nDesigner & Estrategista Digital"
    else:
        msg = f"Ola! Sou Caio Leao, designer e estrategista digital em {city}.\n\n"
        msg += f"Analisei a presenca digital do(a) *{name}* e identifiquei oportunidades de melhoria.\n\n"
        msg += "Posso compartilhar uma analise gratuita?\n\nCaio Leao\nDesigner & Estrategista Digital"

    conn = get_db()
    try:
        conn.execute("""
            UPDATE prospects SET
                outreach_message = ?, outreach_status = 'ready',
                stage = 'outreach', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (msg, prospect_id))
        conn.execute(
            "INSERT INTO activities (type, title, description, prospect_id) VALUES (?,?,?,?)",
            ("outreach", f"Proposta gerada: {name}", f"Template local — {category}", prospect_id)
        )
        conn.commit()
    finally:
        conn.close()

    return {"whatsapp_message": msg, "prospect_id": prospect_id, "source": "template"}
