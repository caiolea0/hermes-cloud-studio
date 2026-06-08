"""Hermes Cloud Studio — Tasks CRUD + Claude dispatch (MERGED-011)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from core.ai import execute_claude_command
from core.models import ClaudeCommand, TaskCreate, TaskUpdate
from core.state import get_db

router = APIRouter()


@router.get("/api/tasks")
async def list_tasks(status: Optional[str] = None, limit: int = 50, offset: int = 0):
    conn = get_db()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        return {"total": total, "tasks": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/api/tasks")
async def create_task(t: TaskCreate):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO tasks (title, description, priority, assigned_to, created_by) VALUES (?, ?, ?, ?, ?)",
            (t.title, t.description, t.priority, t.assigned_to, t.created_by)
        )
        conn.commit()
        conn.execute(
            "INSERT INTO activities (type, title, description) VALUES (?, ?, ?)",
            ("task", f"Nova task: {t.title}", f"Atribuida a {t.assigned_to}")
        )
        conn.commit()
        return {"id": cur.lastrowid, "status": "created"}
    finally:
        conn.close()


@router.patch("/api/tasks/{task_id}")
async def update_task(task_id: int, update: TaskUpdate):
    conn = get_db()
    try:
        sets = []
        params = []
        for field, value in update.model_dump(exclude_none=True).items():
            sets.append(f"{field} = ?")
            params.append(value)
        if not sets:
            raise HTTPException(400, "No fields to update")
        if update.status == "completed":
            sets.append("completed_at = ?")
            params.append(datetime.now(timezone.utc).isoformat())
        params.append(task_id)
        conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        return {"status": "updated"}
    finally:
        conn.close()


@router.post("/api/tasks/{task_id}/send-to-claude")
async def send_task_to_claude(task_id: int):
    """Execute a task via Claude Code CLI."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Task not found")
        t = dict(row)
    finally:
        conn.close()
    return await execute_claude_command(ClaudeCommand(
        command=f"Execute esta tarefa: {t['title']}\nDetalhes: {t.get('description', 'N/A')}",
        context=t.get("description")
    ))


@router.post("/api/tasks/bulk")
async def bulk_task_action(ids: List[int], action: str, value: str = ""):
    conn = get_db()
    try:
        placeholders = ",".join("?" for _ in ids)
        if action == "status":
            completed = datetime.now(timezone.utc).isoformat() if value == "completed" else None
            conn.execute(
                f"UPDATE tasks SET status = ?, completed_at = ? WHERE id IN ({placeholders})",
                [value, completed] + ids
            )
        elif action == "priority":
            conn.execute(
                f"UPDATE tasks SET priority = ? WHERE id IN ({placeholders})",
                [value] + ids
            )
        conn.commit()
        return {"status": "updated", "count": len(ids)}
    finally:
        conn.close()
