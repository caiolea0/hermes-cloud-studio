"""UX-RM-F6-A — Canvas Sequence Builder CRUD API.

Endpoints:
  GET    /api/sequences           — list all sequences
  POST   /api/sequences           — create sequence + nodes + edges
  GET    /api/sequences/{seq_id}  — get sequence with nodes + edges
  PUT    /api/sequences/{seq_id}  — replace canvas (idempotent)
  DELETE /api/sequences/{seq_id}  — soft-archive (status=archived)
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pydantic import ConfigDict

from core.state import get_db

logger = logging.getLogger("hermes.sequences")
router = APIRouter()


class NodePayload(BaseModel):
    id: str
    type: str
    channel: Optional[str] = None
    action: Optional[str] = None
    x: float = 0
    y: float = 0
    config: Dict[str, Any] = {}


class EdgePayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_node: str = Field(alias="from")
    to: str
    type: str = "default"


class CanvasPayload(BaseModel):
    nodes: List[NodePayload] = []
    edges: List[EdgePayload] = []


class SequenceCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    canvas_json: CanvasPayload = CanvasPayload()


class SequenceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    canvas_json: Optional[CanvasPayload] = None
    status: Optional[str] = None


def _apply_migration(conn):
    """Ensure sequence tables exist (idempotent)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sequences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT 'owner',
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS sequence_nodes (
            id TEXT PRIMARY KEY,
            sequence_id INTEGER NOT NULL,
            node_type TEXT NOT NULL,
            channel TEXT,
            action_type TEXT,
            position_x REAL NOT NULL DEFAULT 0,
            position_y REAL NOT NULL DEFAULT 0,
            config_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS sequence_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sequence_id INTEGER NOT NULL,
            from_node TEXT NOT NULL,
            to_node TEXT NOT NULL,
            edge_type TEXT NOT NULL DEFAULT 'default'
        );
    """)
    conn.commit()


def _insert_canvas(conn, seq_id: int, canvas: CanvasPayload):
    conn.execute("DELETE FROM sequence_nodes WHERE sequence_id=?", (seq_id,))
    conn.execute("DELETE FROM sequence_edges WHERE sequence_id=?", (seq_id,))
    for n in canvas.nodes:
        conn.execute(
            "INSERT INTO sequence_nodes (id, sequence_id, node_type, channel, action_type, position_x, position_y, config_json) VALUES (?,?,?,?,?,?,?,?)",
            (n.id, seq_id, n.type, n.channel, n.action, n.x, n.y, json.dumps(n.config)),
        )
    for e in canvas.edges:
        conn.execute(
            "INSERT INTO sequence_edges (sequence_id, from_node, to_node, edge_type) VALUES (?,?,?,?)",
            (seq_id, e.from_node, e.to, e.type),
        )
    conn.commit()


@router.get("/api/sequences")
async def list_sequences():
    conn = get_db()
    try:
        _apply_migration(conn)
        rows = conn.execute(
            "SELECT id, name, description, status, created_at, updated_at FROM sequences WHERE status != 'archived' ORDER BY updated_at DESC"
        ).fetchall()
        return {"sequences": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/api/sequences", status_code=201)
async def create_sequence(body: SequenceCreate):
    conn = get_db()
    try:
        _apply_migration(conn)
        cur = conn.execute(
            "INSERT INTO sequences (name, description, status) VALUES (?,?,?)",
            (body.name, body.description or "", "draft"),
        )
        seq_id = cur.lastrowid
        conn.commit()
        _insert_canvas(conn, seq_id, body.canvas_json)
        return {"id": seq_id, "status": "draft"}
    finally:
        conn.close()


@router.get("/api/sequences/{seq_id}")
async def get_sequence(seq_id: int):
    conn = get_db()
    try:
        _apply_migration(conn)
        row = conn.execute("SELECT * FROM sequences WHERE id=?", (seq_id,)).fetchone()
        if not row:
            raise HTTPException(404, detail="Sequence not found")
        nodes = conn.execute(
            "SELECT * FROM sequence_nodes WHERE sequence_id=?", (seq_id,)
        ).fetchall()
        edges = conn.execute(
            "SELECT * FROM sequence_edges WHERE sequence_id=?", (seq_id,)
        ).fetchall()
        return {
            "sequence": dict(row),
            "nodes": [dict(n) for n in nodes],
            "edges": [dict(e) for e in edges],
        }
    finally:
        conn.close()


@router.put("/api/sequences/{seq_id}")
async def update_sequence(seq_id: int, body: SequenceUpdate):
    conn = get_db()
    try:
        _apply_migration(conn)
        row = conn.execute("SELECT id FROM sequences WHERE id=?", (seq_id,)).fetchone()
        if not row:
            raise HTTPException(404, detail="Sequence not found")
        updates = []
        params = []
        if body.name is not None:
            updates.append("name=?")
            params.append(body.name)
        if body.description is not None:
            updates.append("description=?")
            params.append(body.description)
        if body.status is not None:
            updates.append("status=?")
            params.append(body.status)
        updates.append("updated_at=datetime('now')")
        params.append(seq_id)
        conn.execute(f"UPDATE sequences SET {', '.join(updates)} WHERE id=?", params)
        conn.commit()
        if body.canvas_json is not None:
            _insert_canvas(conn, seq_id, body.canvas_json)
        return {"id": seq_id, "ok": True}
    finally:
        conn.close()


@router.delete("/api/sequences/{seq_id}")
async def delete_sequence(seq_id: int):
    conn = get_db()
    try:
        _apply_migration(conn)
        conn.execute("UPDATE sequences SET status='archived' WHERE id=?", (seq_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
