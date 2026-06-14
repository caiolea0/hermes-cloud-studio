"""F.9.1 — Pipeline Studio Visual backend CRUD + step library REUSE F.5.

Cross-ref: .claude/PLAN.md § "F.9 Decisões Cristalizadas" D1/D2/D5.

D2 — TABLE DEDICADA pipeline_drafts (CRUD + version auto + ab_group nullable A/B).
D3 — pipeline_runs_granular (F.9.2 executor grava per-step).
D5 — 5 templates seed (templates/pipeline_seed/*.yaml).

Step library REUSE F.5 gateway 9 MCPs via local mcp_registry table (PC mirror).
Fallback VM api proxy quando hermes_api_v2 wire-up; ambos source-of-truth gateway
config.yaml. NÃO scan local skills/ (PLAN.md MCP HARD REQUIREMENTS Task 1b).

Endpoints:
- GET    /api/pipeline-studio/drafts            — list with status filter + paginate
- POST   /api/pipeline-studio/drafts            — create draft (YAML validation)
- GET    /api/pipeline-studio/drafts/{id}       — get single draft
- PUT    /api/pipeline-studio/drafts/{id}       — update + version auto-increment
- DELETE /api/pipeline-studio/drafts/{id}       — soft delete = archive (audit preservation)
- GET    /api/pipeline-studio/steps             — aggregate 9 MCPs × tools as steps
- GET    /api/pipeline-studio/templates         — 5 seed templates from filesystem
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.state import DB_PATH, VM_API_URL

log = logging.getLogger("hermes.api.pipeline_studio")

router = APIRouter(prefix="/api/pipeline-studio", tags=["pipeline-studio"])

_ALLOWED_STATUS = {"draft", "active", "archived"}
_ALLOWED_AB_GROUP = {"A", "B"}


# ---------------------------------------------------------------------------
# Pydantic schemas (D9 pattern F.6.1 / F.8.2)
# ---------------------------------------------------------------------------

class PipelineDraftCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    yaml_blob: str = Field(..., min_length=1)
    tags: Optional[list[str]] = Field(default_factory=list)


class PipelineDraftUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    yaml_blob: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(draft|active|archived)$")
    tags: Optional[list[str]] = None
    ab_group: Optional[str] = Field(None, pattern="^(A|B)$")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table_exists() -> bool:
    if not DB_PATH.exists():
        return False
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pipeline_drafts'"
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _validate_yaml(blob: str) -> None:
    """Raise HTTPException 400 if YAML malformed or missing 'steps' key."""
    try:
        parsed = yaml.safe_load(blob)
    except yaml.YAMLError as exc:
        raise HTTPException(400, f"yaml_invalid: {exc}")
    if not isinstance(parsed, dict) or "steps" not in parsed:
        raise HTTPException(400, "yaml must be dict with 'steps' key")
    if not isinstance(parsed["steps"], list) or not parsed["steps"]:
        raise HTTPException(400, "yaml 'steps' must be non-empty list")


# ---------------------------------------------------------------------------
# GET /drafts — list with filter + pagination
# ---------------------------------------------------------------------------

@router.get("/drafts")
async def list_drafts(
    status: Optional[str] = Query(None, description="draft | active | archived"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    if status is not None and status not in _ALLOWED_STATUS:
        raise HTTPException(400, f"status must be one of {sorted(_ALLOWED_STATUS)}")
    if not _ensure_table_exists():
        return JSONResponse(
            content={"items": [], "total": 0, "offset": offset, "limit": limit,
                     "note": "pipeline_drafts missing — apply migrations/2026_06_pipeline_studio.sql"},
            headers={"X-Total-Count": "0"},
        )

    where = "WHERE status = ?" if status else ""
    params: list[Any] = [status] if status else []

    conn = _connect()
    try:
        total_row = conn.execute(
            f"SELECT COUNT(*) AS c FROM pipeline_drafts {where}", params
        ).fetchone()
        total = int(total_row["c"]) if total_row else 0

        rows = conn.execute(
            f"""SELECT id, name, description, version, status, tags, ab_group,
                       owner, created_at, updated_at, last_executed_at
                FROM pipeline_drafts
                {where}
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
        items = [dict(r) for r in rows]
    finally:
        conn.close()

    return JSONResponse(
        content={"items": items, "total": total, "offset": offset, "limit": limit},
        headers={"X-Total-Count": str(total)},
    )


# ---------------------------------------------------------------------------
# POST /drafts — create
# ---------------------------------------------------------------------------

@router.post("/drafts", status_code=201)
async def create_draft(req: PipelineDraftCreate):
    _validate_yaml(req.yaml_blob)
    if not _ensure_table_exists():
        raise HTTPException(503, "pipeline_drafts table missing — apply migration")

    draft_id = str(uuid.uuid4())
    tags_json = json.dumps(req.tags or [])

    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO pipeline_drafts (id, name, description, yaml_blob, tags)
               VALUES (?, ?, ?, ?, ?)""",
            (draft_id, req.name, req.description, req.yaml_blob, tags_json),
        )
        conn.commit()
    finally:
        conn.close()

    return {"id": draft_id, "name": req.name, "version": 1, "status": "draft"}


# ---------------------------------------------------------------------------
# GET /drafts/{id}
# ---------------------------------------------------------------------------

@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str):
    if not _ensure_table_exists():
        raise HTTPException(503, "pipeline_drafts table missing")
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM pipeline_drafts WHERE id = ?", (draft_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "draft_not_found")
        return dict(row)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# PUT /drafts/{id} — update + version auto-increment
# ---------------------------------------------------------------------------

@router.put("/drafts/{draft_id}")
async def update_draft(draft_id: str, req: PipelineDraftUpdate):
    if not _ensure_table_exists():
        raise HTTPException(503, "pipeline_drafts table missing")

    if req.yaml_blob is not None:
        _validate_yaml(req.yaml_blob)

    set_clauses: list[str] = []
    params: list[Any] = []
    for field in ("name", "description", "yaml_blob", "status", "ab_group"):
        val = getattr(req, field)
        if val is not None:
            set_clauses.append(f"{field} = ?")
            params.append(val)
    if req.tags is not None:
        set_clauses.append("tags = ?")
        params.append(json.dumps(req.tags))

    if not set_clauses:
        raise HTTPException(400, "no fields to update")

    set_clauses.append("version = version + 1")
    set_clauses.append("updated_at = CURRENT_TIMESTAMP")
    params.append(draft_id)

    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT version FROM pipeline_drafts WHERE id = ?", (draft_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(404, "draft_not_found")

        conn.execute(
            f"UPDATE pipeline_drafts SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )
        conn.commit()
        new_version = int(existing["version"]) + 1
    finally:
        conn.close()

    return {"id": draft_id, "version": new_version, "ok": True}


# ---------------------------------------------------------------------------
# DELETE /drafts/{id} — soft delete = archive (D2: audit preservation, NÃO hard DELETE)
# ---------------------------------------------------------------------------

@router.delete("/drafts/{draft_id}", status_code=204)
async def archive_draft(draft_id: str):
    if not _ensure_table_exists():
        raise HTTPException(503, "pipeline_drafts table missing")
    conn = _connect()
    try:
        cur = conn.execute(
            """UPDATE pipeline_drafts
               SET status = 'archived', updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND status != 'archived'""",
            (draft_id,),
        )
        conn.commit()
        if cur.rowcount == 0:
            existing = conn.execute(
                "SELECT id FROM pipeline_drafts WHERE id = ?", (draft_id,)
            ).fetchone()
            if not existing:
                raise HTTPException(404, "draft_not_found")
            raise HTTPException(409, "draft_already_archived")
    finally:
        conn.close()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# GET /steps — step library REUSE F.5 gateway 9 MCPs (PLAN MCP HARD REQ Task 1b)
# ---------------------------------------------------------------------------

def _query_local_mcp_registry() -> dict[str, Any]:
    """Local PC mcp_registry (mirror gateway config.yaml via scripts/seed_mcp_registry.py)."""
    if not DB_PATH.exists():
        return {"steps": [], "total": 0, "source": "no_db",
                "note": "hermes_local.db missing"}
    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mcp_registry'"
        ).fetchone()
        if not existing:
            return {"steps": [], "total": 0, "source": "no_registry",
                    "note": "mcp_registry missing — run scripts/seed_mcp_registry.py"}

        rows = conn.execute(
            """SELECT server, tools, tier, chapter_owner, required_by_dc, status
               FROM mcp_registry
               WHERE status = 'active'"""
        ).fetchall()

        steps: list[dict[str, Any]] = []
        for r in rows:
            tools_field = r["tools"] or "[]"
            try:
                tools = json.loads(tools_field) if isinstance(tools_field, str) else (tools_field or [])
            except Exception:
                tools = []
            req_by_field = r["required_by_dc"] or "[]"
            try:
                req_by = json.loads(req_by_field) if isinstance(req_by_field, str) else (req_by_field or [])
            except Exception:
                req_by = []
            for tool_name in tools:
                steps.append({
                    "id": f"{r['server']}.{tool_name}",
                    "category": "mcp_tool",
                    "mcp_server": r["server"],
                    "tool_name": tool_name,
                    "tier": r["tier"],
                    "chapter_owner": r["chapter_owner"],
                    "required_by_dc": req_by,
                    "description": f"MCP {r['server']}.{tool_name}",
                })
        return {"steps": steps, "total": len(steps),
                "source": "pc_local_mcp_registry",
                "mcp_count": len(rows)}
    finally:
        conn.close()


@router.get("/steps")
async def list_step_library():
    """Aggregate 9 MCPs × tools as first-class pipeline steps.

    Strategy: VM api proxy primary → PC local mcp_registry fallback.
    Both reflect gateway config.yaml source-of-truth (BLACKLIST R2 compliant —
    nunca scan local skills/ filesystem).
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{VM_API_URL}/api/mcp/coverage/latest")
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", []) or []
                steps: list[dict[str, Any]] = []
                seen: set[str] = set()
                for it in items:
                    server = it.get("server")
                    tool = it.get("tool")
                    if not server or not tool:
                        continue
                    key = f"{server}.{tool}"
                    if key in seen:
                        continue
                    seen.add(key)
                    steps.append({
                        "id": key,
                        "category": "mcp_tool",
                        "mcp_server": server,
                        "tool_name": tool,
                        "tier": it.get("registry_tier") or it.get("tier"),
                        "chapter_owner": it.get("chapter_owner"),
                        "required_by_dc": [],
                        "description": f"MCP {key}",
                    })
                if steps:
                    return {"steps": steps, "total": len(steps),
                            "source": "vm_api_proxy",
                            "mcp_count": len(set(s["mcp_server"] for s in steps))}
    except Exception as exc:
        log.debug("VM proxy failed, falling back to local: %s", type(exc).__name__)

    return _query_local_mcp_registry()


# ---------------------------------------------------------------------------
# GET /templates — 5 seed YAML from filesystem
# ---------------------------------------------------------------------------

@router.get("/templates")
async def list_templates():
    seed_dir = Path(__file__).resolve().parent.parent / "templates" / "pipeline_seed"
    templates: list[dict[str, Any]] = []
    if not seed_dir.exists():
        return {"templates": [], "total": 0,
                "note": f"seed dir missing: {seed_dir}"}

    for yaml_file in sorted(seed_dir.glob("*.yaml")):
        try:
            raw = yaml_file.read_text(encoding="utf-8")
            parsed = yaml.safe_load(raw)
            if not isinstance(parsed, dict):
                continue
            templates.append({
                "id": yaml_file.stem,
                "name": parsed.get("name", yaml_file.stem),
                "description": parsed.get("description", ""),
                "tags": parsed.get("tags", []) or [],
                "steps_count": len(parsed.get("steps", []) or []),
                "yaml_blob": raw,
            })
        except Exception as exc:
            log.warning("Skip malformed template %s: %s", yaml_file.name, exc)

    return {"templates": templates, "total": len(templates),
            "source": str(seed_dir)}
