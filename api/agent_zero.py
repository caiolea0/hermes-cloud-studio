"""Hermes Cloud Studio — Agent Zero direct status + chat (MERGED-011)."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

import core.state as state
from core.ai import call_agent_zero
from core.models import AgentZeroChatRequest
from core.state import AGENT_ZERO_URL

router = APIRouter()


@router.get("/api/agent-zero/status")
async def agent_zero_status():
    """Check Agent Zero availability and info."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{AGENT_ZERO_URL}/api/health")
            online = resp.status_code == 200
    except Exception:  # noqa: silenciado intencional — fallback de sonda
        online = False

    # Check Ollama models
    ollama_models = []
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{AGENT_ZERO_URL.rsplit(':', 1)[0]}:11434/api/tags")
            if resp.status_code == 200:
                ollama_models = [m["name"] for m in resp.json().get("models", [])]
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass

    return {
        "online": online,
        "url": AGENT_ZERO_URL,
        "ollama_models": ollama_models,
        "context_id": state._agent_zero_context_id,
    }


@router.post("/api/agent-zero/chat")
async def agent_zero_chat(req: AgentZeroChatRequest):
    """Direct chat with Agent Zero."""
    try:
        result = await call_agent_zero(req.message, req.context_id or "", timeout=300)
        return result
    except Exception as e:
        raise HTTPException(503, f"Agent Zero indisponivel: {e}")
