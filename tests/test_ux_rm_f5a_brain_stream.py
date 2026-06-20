"""UX-RM-F5-A — Brain Streaming + Cmd+K AI Mode tests.

Tests:
  1. SSE endpoint returns text/event-stream content-type
  2. stream_decide yields thought + final events (async generator)
  3. Rate limit enforced (429 + Retry-After) after N+1 requests
  4. command_palette.js: slash prefix detected as AI mode
  5. command_palette.js: ?ask prefix detected as AI mode
  6. brain.ai_query_used event logged to brain_decisions table path

Run:
  pytest tests/test_ux_rm_f5a_brain_stream.py -v
"""
from __future__ import annotations

import asyncio
import re
from collections import deque
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent
COMP = ROOT / "dashboard" / "components"


# ── T1: SSE endpoint content-type ──────────────────────────────────────────

def test_brain_stream_endpoint_returns_sse_content_type():
    """POST /api/brain/stream-decide StreamingResponse must have text/event-stream media_type."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from api.brain import router as brain_router

    app = FastAPI()
    app.include_router(brain_router)

    # Patch Brain.stream_decide to yield a single final event (no real LLM)
    async def _mock_stream_decide(self, prompt, context=None, intent_hint=None):
        yield {"type": "thought", "chunk": "Analisando...", "iteration": 1}
        yield {"type": "final", "answer": "Mock answer", "confidence": 0.9, "iterations": 1, "status": "completed", "intent": "answer_owner"}

    with patch("api.brain.Brain.stream_decide", _mock_stream_decide):
        # Reset rate limit state before test
        import api.brain as brain_api
        brain_api._BRAIN_STREAM_TIMESTAMPS.clear()

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/brain/stream-decide",
                json={"prompt": "test question"},
                headers={"X-Hermes-Token": "test"},
            )
        assert resp.status_code == 200, f"Expected 200 got {resp.status_code}"
        ct = resp.headers.get("content-type", "")
        assert "text/event-stream" in ct, f"Expected text/event-stream, got: {ct}"


# ── T2: stream_decide yields thought + final events ─────────────────────────

@pytest.mark.asyncio
async def test_brain_stream_yields_thought_tool_final_events():
    """Brain.stream_decide() must yield at least one thought event and one final event."""
    from brain.decide import Brain
    from brain._smoke import MockDispatcher

    # MockDispatcher: canned LLM response with final_answer immediately (no tool call)
    dispatcher = MockDispatcher()
    brain = Brain(dispatcher=dispatcher)

    events: list[dict[str, Any]] = []
    async for event in brain.stream_decide(prompt="What is the answer?"):
        events.append(event)

    types = [e.get("type") for e in events]
    assert "thought" in types, f"Expected thought event. Got types: {types}"
    assert "final" in types, f"Expected final event. Got types: {types}"

    final = next(e for e in events if e.get("type") == "final")
    assert "answer" in final, "Final event must contain 'answer' key"
    assert "confidence" in final, "Final event must contain 'confidence' key"
    assert "intent" in final, "Final event must contain 'intent' key"


# ── T3: rate limit 429 ───────────────────────────────────────────────────────

def test_brain_stream_rate_limit_enforced():
    """After BRAIN_STREAM_MAX_RPM requests, next request returns 429 with Retry-After."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from api.brain import router as brain_router
    import api.brain as brain_api

    app = FastAPI()
    app.include_router(brain_router)

    async def _mock_stream_decide(self, prompt, context=None, intent_hint=None):
        yield {"type": "final", "answer": "ok", "confidence": 1.0, "iterations": 0, "status": "completed", "intent": "answer_owner"}

    with patch("api.brain.Brain.stream_decide", _mock_stream_decide):
        # Force rate limit: fill deque to capacity
        brain_api._BRAIN_STREAM_TIMESTAMPS.clear()
        import time
        now = time.monotonic()
        for _ in range(brain_api._BRAIN_STREAM_RPM):
            brain_api._BRAIN_STREAM_TIMESTAMPS.append(now)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/brain/stream-decide",
                json={"prompt": "should be rate limited"},
                headers={"X-Hermes-Token": "test"},
            )

        assert resp.status_code == 429, f"Expected 429 rate limit, got {resp.status_code}"
        assert "Retry-After" in resp.headers, "Must include Retry-After header"

    # Cleanup
    brain_api._BRAIN_STREAM_TIMESTAMPS.clear()


# ── T4: palette slash prefix → AI mode detection ────────────────────────────

def test_command_palette_ai_mode_slash_prefix():
    """command_palette.js must contain logic detecting '/' prefix as AI mode trigger."""
    src = (COMP / "command_palette.js").read_text(encoding="utf-8")

    # _handleInputChange or similar method should check startsWith('/')
    assert "startsWith('/')" in src or 'startsWith("/")' in src, (
        "command_palette.js must check startsWith('/') for AI mode"
    )
    assert "_aiMode" in src, "command_palette.js must have _aiMode state"
    assert "_submitAIQuery" in src, "command_palette.js must have _submitAIQuery method"


# ── T5: palette ?ask prefix → AI mode detection ─────────────────────────────

def test_command_palette_ai_mode_question_prefix():
    """command_palette.js must detect '?ask ' prefix as alternative AI mode trigger."""
    src = (COMP / "command_palette.js").read_text(encoding="utf-8")

    assert "?ask " in src or "?ask" in src, (
        "command_palette.js must check '?ask' prefix for AI mode"
    )
    assert "AbortController" in src, "command_palette.js must use AbortController for SSE abort"
    assert "stream-decide" in src, "command_palette.js must call /api/brain/stream-decide"


# ── T6: WS telemetry after stream ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ai_events_logged_brain_decisions_table():
    """stream_decide endpoint broadcasts brain.ai_query_used after stream completes."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from api.brain import router as brain_router
    import api.brain as brain_api

    app = FastAPI()
    app.include_router(brain_router)

    broadcast_calls: list[dict] = []

    async def _mock_broadcast(payload: dict) -> None:
        broadcast_calls.append(payload)

    async def _mock_stream_decide(self, prompt, context=None, intent_hint=None):
        yield {"type": "final", "answer": "telemetry test", "confidence": 0.7, "iterations": 1, "status": "completed", "intent": "answer_owner"}

    brain_api._BRAIN_STREAM_TIMESTAMPS.clear()

    mock_ws_manager = MagicMock()
    mock_ws_manager.broadcast = AsyncMock(side_effect=_mock_broadcast)

    with patch("api.brain.Brain.stream_decide", _mock_stream_decide), \
         patch("core.state.ws_manager", mock_ws_manager):
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/brain/stream-decide",
                json={"prompt": "telemetry test"},
                headers={"X-Hermes-Token": "test"},
            )

    assert resp.status_code == 200

    # The WS broadcast may happen in the generator after the response body is consumed.
    # Give async tasks a tick to fire if needed.
    await asyncio.sleep(0.05)

    # PA-F2: brain.* WS broadcasts use event_type (not type) after standardization
    ai_query_events = [e for e in broadcast_calls if e.get("event_type") == "brain.ai_query_used"]
    assert len(ai_query_events) >= 1, (
        f"Expected brain.ai_query_used broadcast. Got: {broadcast_calls}"
    )
    ev = ai_query_events[0]
    assert "prompt_length" in ev, "brain.ai_query_used must include prompt_length"
    assert "intent" in ev, "brain.ai_query_used must include intent"

    brain_api._BRAIN_STREAM_TIMESTAMPS.clear()
