"""Hermes Cloud Studio — AI helpers compartilhados (Agent Zero + Claude CLI fallback).

Extraido de server.py durante MERGED-011 (split monolitos).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

import core.state as state
from core.models import ClaudeCommand
from core.state import (
    AGENT_ZERO_API_KEY,
    AGENT_ZERO_URL,
    get_db,
    logger,
)


async def call_agent_zero(message: str, context_id: str = "", timeout: float = 300) -> dict:
    """Call Agent Zero API on VM. Returns {"response": str, "context_id": str, "provider": "agent_zero"}."""
    payload = {"message": message}
    if context_id:
        payload["context_id"] = context_id
    elif state._agent_zero_context_id:
        payload["context_id"] = state._agent_zero_context_id

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{AGENT_ZERO_URL}/api/api_message",
                json=payload,
                headers={"X-API-KEY": AGENT_ZERO_API_KEY, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("context_id"):
                state._agent_zero_context_id = data["context_id"]
            return {
                "response": data.get("response", "(sem resposta)"),
                "context_id": data.get("context_id", ""),
                "provider": "agent_zero",
            }
    except Exception as e:
        logger.warning(f"Agent Zero indisponivel ({e}), tentando Claude CLI...")
        raise


async def call_claude_cli(command: str, timeout: float = 120) -> dict:
    """Fallback: execute via Claude Code CLI (claude -p)."""
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    output = stdout.decode("utf-8", errors="replace").strip()
    error = stderr.decode("utf-8", errors="replace").strip()
    return {
        "response": output or error or "(sem output)",
        "context_id": "",
        "provider": "claude_cli",
    }


async def call_ai(message: str, context_id: str = "", timeout: float = 300) -> dict:
    """Unified AI caller: Agent Zero first, Claude CLI fallback."""
    try:
        return await call_agent_zero(message, context_id, timeout)
    except Exception:
        try:
            return await call_claude_cli(message, min(timeout, 120))
        except Exception as e:
            return {"response": f"Erro: AI indisponivel — {e}", "context_id": "", "provider": "none"}


async def execute_claude_command(cmd: ClaudeCommand) -> dict:
    """Execute a command via Agent Zero (primary) or Claude Code CLI (fallback).

    Cria task em hermes_local.db, atualiza com resultado, devolve {task_id, status, result, provider}.
    Importado por outros routers (prospects/strategy, tasks/send-to-claude).
    """
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO tasks (title, description, status, assigned_to, created_by) "
            "VALUES (?, ?, 'running', 'agent_zero', 'dashboard')",
            (cmd.command[:200], cmd.context),
        )
        task_id = cur.lastrowid
        conn.execute(
            "INSERT INTO activities (type, title, description) VALUES (?, ?, ?)",
            ("task", f"AI: {cmd.command[:80]}", "Executando via Agent Zero..."),
        )
        conn.commit()
    finally:
        conn.close()

    try:
        ai_result = await call_ai(cmd.command, timeout=300)
        result = ai_result["response"]
        provider = ai_result["provider"]

        conn = get_db()
        try:
            conn.execute(
                "UPDATE tasks SET status = 'completed', result = ?, completed_at = ? WHERE id = ?",
                (result[:5000], datetime.now(timezone.utc).isoformat(), task_id),
            )
            conn.execute(
                "INSERT INTO activities (type, title, description) VALUES (?, ?, ?)",
                ("task", f"AI concluiu ({provider}): {cmd.command[:60]}", result[:200]),
            )
            conn.commit()
        finally:
            conn.close()

        return {"task_id": task_id, "status": "completed", "result": result[:5000], "provider": provider}

    except Exception as e:
        conn = get_db()
        try:
            conn.execute("UPDATE tasks SET status = 'failed', result = ? WHERE id = ?", (str(e)[:500], task_id))
            conn.commit()
        finally:
            conn.close()
        return {"task_id": task_id, "status": "error", "result": str(e)[:500]}
