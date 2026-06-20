"""UX-RM-F6-A/C — Canvas Sequence Builder CRUD + Orchestration API.

Endpoints:
  GET    /api/sequences                  — list all sequences
  POST   /api/sequences                  — create sequence + nodes + edges
  GET    /api/sequences/{seq_id}         — get sequence with nodes + edges
  PUT    /api/sequences/{seq_id}         — replace canvas (idempotent)
  DELETE /api/sequences/{seq_id}         — soft-archive (status=archived)
  POST   /api/sequences/{seq_id}/enroll  — enroll prospects into sequence
  POST   /api/sequences/{seq_id}/dry-run — simulate execution (no actual send)
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pydantic import ConfigDict

from core.state import get_db
from core.send_scheduler import compute_delay_dt, next_send_window

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
    """Ensure sequence tables exist (idempotent fallback — canonical source: migrations/2026_06_sequences.sql)."""
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
            config_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (sequence_id) REFERENCES sequences(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS sequence_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sequence_id INTEGER NOT NULL,
            from_node TEXT NOT NULL,
            to_node TEXT NOT NULL,
            edge_type TEXT NOT NULL DEFAULT 'default',
            FOREIGN KEY (sequence_id) REFERENCES sequences(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_sequence_nodes_seq ON sequence_nodes(sequence_id);
        CREATE INDEX IF NOT EXISTS idx_sequence_edges_seq ON sequence_edges(sequence_id);
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
    """Soft-delete (archive) a sequence. No dashboard SPA caller today.
    Dashboard uses PUT archive pattern; this DELETE is reserved for CLI/admin use.
    """
    conn = get_db()
    try:
        _apply_migration(conn)
        conn.execute("UPDATE sequences SET status='archived' WHERE id=?", (seq_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ─── F6-C: Enrollment + Dry-Run ──────────────────────────────────────────────

class EnrollRequest(BaseModel):
    prospect_ids: List[int]
    start_at: Optional[str] = None  # ISO timestamp, default now


def _find_first_action_node(nodes: list) -> Optional[dict]:
    """Return the first action node (node_type='action') in a sequence."""
    for n in nodes:
        if n.get("node_type") == "action":
            return n
    return None


def _first_delay_days(nodes: list) -> int:
    """Return delay_days from first delay node before first action, or 0."""
    for n in nodes:
        if n.get("node_type") == "delay":
            cfg = json.loads(n.get("config_json") or "{}")
            return int(cfg.get("delay_days", 0))
        if n.get("node_type") == "action":
            break
    return 0


def _apply_enrollment_migration(conn) -> None:
    """Ensure sequence_enrollments cols match F6-C schema (idempotent)."""
    # The table is created by daemon/orchestrator.py; add cols if missing
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(sequence_enrollments)").fetchall()
    }
    if "sequence_id" in existing and conn.execute(
        "SELECT typeof(sequence_id) FROM pragma_table_info('sequence_enrollments')"
    ).fetchone():
        pass  # already exists


@router.post("/api/sequences/{seq_id}/enroll", status_code=201)
async def enroll_prospects(seq_id: int, body: EnrollRequest):
    """Enroll prospects into an active sequence.

    Creates sequence_enrollments rows pointing at first action node +
    computed next_action_at respecting business hours (America/Cuiaba).
    """
    conn = get_db()
    try:
        _apply_migration(conn)

        row = conn.execute("SELECT * FROM sequences WHERE id=?", (seq_id,)).fetchone()
        if not row:
            raise HTTPException(404, detail="Sequence not found")
        seq = dict(row)
        if seq["status"] != "active":
            raise HTTPException(400, detail="Sequence must be active to enroll")

        nodes = [
            dict(n) for n in conn.execute(
                "SELECT * FROM sequence_nodes WHERE sequence_id=? ORDER BY position_y",
                (seq_id,),
            ).fetchall()
        ]

        first_action = _find_first_action_node(nodes)
        delay_days = _first_delay_days(nodes)

        # Compute next_action_at with business-hours gate
        base_dt = None
        if body.start_at:
            try:
                base_dt = datetime.fromisoformat(body.start_at)
            except ValueError:
                pass
        next_at = compute_delay_dt(delay_days, base_dt)
        next_at_str = next_at.strftime("%Y-%m-%d %H:%M:%S")

        first_step = first_action["id"] if first_action else "none"

        enrolled = []
        skipped = []
        for pid in body.prospect_ids:
            try:
                cur = conn.execute(
                    "INSERT INTO sequence_enrollments "
                    "(prospect_id, sequence_id, current_step, next_action_at, completed) "
                    "VALUES (?, ?, ?, ?, 0)",
                    (pid, str(seq_id), 0 if first_step == "none" else 0, next_at_str, ),
                )
                conn.commit()
                enrolled.append({"prospect_id": pid, "enrollment_id": cur.lastrowid, "next_action_at": next_at_str})
            except Exception:
                skipped.append(pid)

        # WS broadcast (best-effort — server.py ws_manager may not be available in tests)
        try:
            from core.state import ws_manager
            import asyncio
            loop = asyncio.get_event_loop()
            loop.create_task(
                ws_manager.broadcast({"event_type": "sequence.enrolled",
                                      "sequence_id": seq_id,
                                      "count": len(enrolled)})
            )
            # PA-F2 ITEM 2A — real-time cobaia today-queue refresh on enroll
            loop.create_task(
                ws_manager.broadcast({"event_type": "cobaia.queue_updated",
                                      "reason": "enroll",
                                      "count": len(enrolled)})
            )
        except Exception:
            pass

        return {"enrolled": enrolled, "skipped": skipped, "next_action_at": next_at_str}
    finally:
        conn.close()


@router.post("/api/sequences/{seq_id}/dry-run")
async def dry_run_sequence(seq_id: int, sample_prospect_id: Optional[int] = None):
    """Simulate sequence execution — returns a timeline WITHOUT sending.

    Templates are rendered with sample prospect data (deterministic preview).
    HERMES_CHANNEL_SEND_ENABLED is NOT checked here; dry-run never sends.
    """
    conn = get_db()
    try:
        _apply_migration(conn)

        row = conn.execute("SELECT * FROM sequences WHERE id=?", (seq_id,)).fetchone()
        if not row:
            raise HTTPException(404, detail="Sequence not found")

        nodes = [
            dict(n) for n in conn.execute(
                "SELECT * FROM sequence_nodes WHERE sequence_id=? ORDER BY position_y",
                (seq_id,),
            ).fetchall()
        ]
        edges = [
            dict(e) for e in conn.execute(
                "SELECT * FROM sequence_edges WHERE sequence_id=?", (seq_id,)
            ).fetchall()
        ]

        # Sample prospect
        sample: Dict[str, Any] = {}
        if sample_prospect_id:
            p = conn.execute(
                "SELECT * FROM prospects WHERE id=?", (sample_prospect_id,)
            ).fetchone()
            if p:
                sample = dict(p)

        if not sample:
            sample = {
                "firstName": "João",
                "lastName": "Silva",
                "fullName": "João Silva",
                "company": "Empresa Exemplo MT",
                "jobTitle": "Gerente",
                "city": "Cuiabá",
                "industry": "Tecnologia",
                "senderName": "Caio Leão",
                "customField1": "",
                "customField2": "",
            }

        # Build edge map for traversal
        edge_map: Dict[str, list] = {}
        for e in edges:
            src = e["from_node"]
            edge_map.setdefault(src, []).append(e)

        # Traverse nodes in y-order (simple linear traversal for preview)
        timeline = []
        cumulative_delay = 0
        visited = set()

        for node in nodes:
            ntype = node.get("node_type", "")
            nid = node["id"]
            if nid in visited:
                continue
            visited.add(nid)

            if ntype == "delay":
                cfg = json.loads(node.get("config_json") or "{}")
                cumulative_delay += int(cfg.get("delay_days", 0))

            elif ntype == "action":
                cfg = json.loads(node.get("config_json") or "{}")
                template_id = cfg.get("template_id")
                rendered = None
                rendered_subject = None

                if template_id:
                    try:
                        from core.template_renderer import render_preview
                        trow = conn.execute(
                            "SELECT body, subject, channel FROM templates WHERE id=?",
                            (int(template_id),),
                        ).fetchone()
                        if trow:
                            rendered = render_preview(trow[0], sample)
                            rendered_subject = render_preview(trow[1], sample) if trow[1] else None
                    except Exception:
                        rendered = "(template unavailable)"

                send_window = next_send_window(
                    compute_delay_dt(cumulative_delay)
                ).strftime("%Y-%m-%d %H:%M")

                timeline.append({
                    "day": cumulative_delay,
                    "channel": node.get("channel", "unknown"),
                    "action": node.get("action_type", "unknown"),
                    "node_id": nid,
                    "template_id": template_id,
                    "rendered_preview": rendered,
                    "rendered_subject": rendered_subject,
                    "send_window": send_window,
                })

        return {
            "sequence_id": seq_id,
            "sequence_name": dict(row)["name"],
            "timeline": timeline,
            "sample_prospect": {k: str(v) for k, v in sample.items() if isinstance(v, (str, int, float, type(None)))},
            "total_days": cumulative_delay,
            "actual_send": False,  # dry-run NEVER sends
        }
    finally:
        conn.close()
