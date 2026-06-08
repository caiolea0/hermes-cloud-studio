"""Hermes Cloud Studio — Claude/Agent Zero unified execute endpoint (MERGED-011)."""
from __future__ import annotations

from fastapi import APIRouter

from core.ai import execute_claude_command
from core.models import ClaudeCommand

router = APIRouter()


@router.post("/api/claude/execute")
async def execute_claude_command_endpoint(cmd: ClaudeCommand):
    """Execute a command via Agent Zero (primary) or Claude Code CLI (fallback)."""
    return await execute_claude_command(cmd)
