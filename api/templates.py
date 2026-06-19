"""UX-RM-F6-B — Templates CRUD API.

Endpoints:
  GET    /api/templates              — list (optional ?channel=)
  POST   /api/templates              — create (validates variables)
  GET    /api/templates/{id}         — get single
  PUT    /api/templates/{id}         — update
  DELETE /api/templates/{id}         — delete
  POST   /api/templates/render       — render with prospect data
  GET    /api/templates/presets      — B2B Cuiaba-MT preset catalogue
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.state import get_db
from core.template_renderer import (
    VALID_VARIABLES,
    extract_variables,
    render,
    render_preview,
)

logger = logging.getLogger("hermes.templates")
router = APIRouter()


# ─── DB migration (idempotent) ───────────────────────────────────────────────

def _apply_migration(conn) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS templates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT    NOT NULL DEFAULT 'owner',
            name        TEXT    NOT NULL,
            channel     TEXT    NOT NULL,
            action_type TEXT,
            subject     TEXT,
            body        TEXT    NOT NULL,
            category    TEXT    DEFAULT 'intro',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_templates_channel ON templates(channel);
    """)
    conn.commit()


# ─── Pydantic models ─────────────────────────────────────────────────────────

class TemplatePayload(BaseModel):
    name: str
    channel: str
    action_type: Optional[str] = None
    subject: Optional[str] = None
    body: str
    category: Optional[str] = "intro"


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    channel: Optional[str] = None
    action_type: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    category: Optional[str] = None


class RenderRequest(BaseModel):
    template_id: int
    prospect_data: dict
    deterministic: bool = False  # True = preview mode (spintax picks first)


# ─── Helpers ─────────────────────────────────────────────────────────────────

VALID_CHANNELS = {"linkedin", "email", "whatsapp"}


def _validate_body_vars(body: str) -> None:
    invalid = extract_variables(body) - VALID_VARIABLES
    if invalid:
        raise HTTPException(400, detail=f"Invalid variables: {sorted(invalid)}")


def _validate_channel(channel: str) -> None:
    if channel not in VALID_CHANNELS:
        raise HTTPException(400, detail=f"channel must be one of {sorted(VALID_CHANNELS)}")


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/api/templates/presets")
async def get_presets():
    """Recommended B2B templates for Cuiaba-MT outreach."""
    return {
        "presets": [
            {
                "name": "LinkedIn Connect Cuiaba",
                "channel": "linkedin",
                "action_type": "connect",
                "category": "intro",
                "body": (
                    "Oi {{firstName}}, vi seu trabalho na {{company}} aqui em {{city}}. "
                    "Adoraria me conectar e trocar ideias sobre {{industry}}!"
                ),
            },
            {
                "name": "LinkedIn Follow-up",
                "channel": "linkedin",
                "action_type": "message",
                "category": "followup",
                "body": (
                    "{{firstName}}, obrigado por aceitar! "
                    "Vi que voces na {{company}} {spintax: estao crescendo|expandiram muito}. "
                    "Trabalho ajudando empresas como a sua a {spintax: escalar vendas|gerar mais leads}. "
                    "Faz sentido um papo rapido?"
                ),
            },
            {
                "name": "Email Proposta",
                "channel": "email",
                "action_type": "email",
                "category": "proposal",
                "subject": "{{firstName}}, proposta para {{company}}",
                "body": (
                    "Ola {{firstName}},\n\n"
                    "Meu nome e {{senderName}}, atuo em design e estrategia digital para empresas em {{city}}.\n\n"
                    "Vi que a {{company}} {spintax: ainda nao tem presenca digital estruturada|poderia ampliar seu alcance online} "
                    "e acredito que posso ajudar.\n\n"
                    "Posso enviar uma proposta personalizada?\n\n"
                    "Att,\nCaio Leao\nDesigner & Estrategista Digital, Cuiaba, MT"
                ),
            },
            {
                "name": "WhatsApp Intro",
                "channel": "whatsapp",
                "action_type": "wa_text",
                "category": "intro",
                "body": (
                    "Oi {{firstName}}, tudo bem? "
                    "Sou o {{senderName}}, designer digital em Cuiaba. "
                    "Vi a {{company}} e queria apresentar uma ideia rapida. Posso?"
                ),
            },
            {
                "name": "LinkedIn Reminder",
                "channel": "linkedin",
                "action_type": "message",
                "category": "reminder",
                "body": (
                    "{{firstName}}, so passando pra retomar o contato. "
                    "Tenho algumas ideias para {{company}} que podem ser interessantes. "
                    "Disponivel para uma conversa rapida?"
                ),
            },
        ]
    }


@router.get("/api/templates")
async def list_templates(channel: Optional[str] = None):
    conn = get_db()
    try:
        _apply_migration(conn)
        if channel:
            rows = conn.execute(
                "SELECT * FROM templates WHERE channel=? ORDER BY updated_at DESC",
                (channel,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM templates ORDER BY updated_at DESC"
            ).fetchall()
        return {"templates": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/api/templates", status_code=201)
async def create_template(body: TemplatePayload):
    _validate_channel(body.channel)
    _validate_body_vars(body.body)
    if body.subject:
        _validate_body_vars(body.subject)
    conn = get_db()
    try:
        _apply_migration(conn)
        cur = conn.execute(
            "INSERT INTO templates (name, channel, action_type, subject, body, category) VALUES (?,?,?,?,?,?)",
            (body.name, body.channel, body.action_type, body.subject, body.body, body.category or "intro"),
        )
        conn.commit()
        return {"id": cur.lastrowid, "ok": True}
    finally:
        conn.close()


@router.get("/api/templates/{template_id}")
async def get_template(template_id: int):
    conn = get_db()
    try:
        _apply_migration(conn)
        row = conn.execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
        if not row:
            raise HTTPException(404, detail="Template not found")
        return {"template": dict(row)}
    finally:
        conn.close()


@router.put("/api/templates/{template_id}")
async def update_template(template_id: int, body: TemplateUpdate):
    conn = get_db()
    try:
        _apply_migration(conn)
        row = conn.execute("SELECT id FROM templates WHERE id=?", (template_id,)).fetchone()
        if not row:
            raise HTTPException(404, detail="Template not found")

        if body.body is not None:
            _validate_body_vars(body.body)
        if body.subject is not None:
            _validate_body_vars(body.subject)
        if body.channel is not None:
            _validate_channel(body.channel)

        updates, params = [], []
        for field in ("name", "channel", "action_type", "subject", "body", "category"):
            val = getattr(body, field)
            if val is not None:
                updates.append(f"{field}=?")
                params.append(val)
        updates.append("updated_at=datetime('now')")
        params.append(template_id)
        conn.execute(f"UPDATE templates SET {', '.join(updates)} WHERE id=?", params)
        conn.commit()
        return {"id": template_id, "ok": True}
    finally:
        conn.close()


@router.delete("/api/templates/{template_id}")
async def delete_template(template_id: int):
    conn = get_db()
    try:
        _apply_migration(conn)
        conn.execute("DELETE FROM templates WHERE id=?", (template_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/api/templates/render")
async def render_template(req: RenderRequest):
    conn = get_db()
    try:
        _apply_migration(conn)
        row = conn.execute("SELECT * FROM templates WHERE id=?", (req.template_id,)).fetchone()
        if not row:
            raise HTTPException(404, detail="Template not found")
        tpl = dict(row)
        fn = render_preview if req.deterministic else render
        rendered_body = fn(tpl["body"], req.prospect_data)
        rendered_subject = fn(tpl["subject"], req.prospect_data) if tpl.get("subject") else None
        return {
            "subject": rendered_subject,
            "body": rendered_body,
            "channel": tpl["channel"],
        }
    finally:
        conn.close()
