"""UX-RM-F5-B — Citation Pills + Multimodal Paste + Brain Sidebar tests.

Tests:
  1. test_citation_resolver_skill_returns_url
  2. test_citation_resolver_memory_returns_snippet
  3. test_brain_stream_request_accepts_image_b64
  4. test_brain_stream_image_analysis_intent
  5. test_palette_paste_image_triggers_ai_mode
  6. test_brain_sidebar_file_exists
  7. test_brain_sidebar_history_localstorage_namespace

Run:
  pytest tests/test_ux_rm_f5b_polish.py -v
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent
COMP = ROOT / "dashboard" / "components"


# ── T1: citation resolver skill → URL ────────────────────────────────────────

def test_citation_resolver_skill_returns_url():
    """resolve_citation('skill', ...) must return a dict with url and source_type='skill'."""
    from brain.citation_resolver import resolve_citation

    result = resolve_citation("skill", "cobaia_warmup")
    assert isinstance(result, dict), "resolve_citation must return dict"
    assert "url" in result, "result must have 'url' key"
    assert result.get("source_type") == "skill", f"source_type must be 'skill', got {result.get('source_type')}"
    assert result.get("source_id") == "cobaia_warmup", "source_id must be preserved"
    # URL must be a valid string (can be '#skills' or a path)
    assert isinstance(result["url"], str) and result["url"], "url must be non-empty string"


# ── T2: citation resolver memory → snippet keys present ─────────────────────

def test_citation_resolver_memory_returns_snippet():
    """resolve_citation('memory', ...) must return dict with url, title, snippet keys."""
    from brain.citation_resolver import resolve_citation

    result = resolve_citation("memory", "brain_warmup_state")
    assert isinstance(result, dict)
    for key in ("url", "title", "snippet", "source_type", "source_id"):
        assert key in result, f"result must have '{key}' key"
    assert result["source_type"] == "memory"
    assert result["source_id"] == "brain_warmup_state"


# ── T3: BrainStreamRequest accepts image_b64 ─────────────────────────────────

def test_brain_stream_request_accepts_image_b64():
    """BrainStreamRequest must validate image_b64 as optional string field."""
    from api.brain import BrainStreamRequest

    # Without image
    req_no_img = BrainStreamRequest(prompt="test question")
    assert req_no_img.image_b64 is None, "image_b64 must default to None"

    # With image (small valid base64)
    import base64
    sample_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20).decode()
    req_with_img = BrainStreamRequest(prompt="analyze this", image_b64=sample_b64)
    assert req_with_img.image_b64 == sample_b64, "image_b64 must be stored as-is"


# ── T4: stream_decide returns graceful 501 when image_b64 provided ───────────

@pytest.mark.asyncio
async def test_brain_stream_image_analysis_intent():
    """stream_decide with image_b64 must yield thought + final with status=not_implemented."""
    from brain.decide import Brain
    from brain._smoke import MockDispatcher

    brain = Brain(dispatcher=MockDispatcher())
    events = []
    async for event in brain.stream_decide(
        prompt="describe this image",
        image_b64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    ):
        events.append(event)

    types = [e.get("type") for e in events]
    assert "thought" in types, f"Expected thought event, got: {types}"
    assert "final" in types, f"Expected final event, got: {types}"

    final = next(e for e in events if e.get("type") == "final")
    assert final.get("status") == "not_implemented", (
        f"image_b64 path must yield not_implemented status, got: {final.get('status')}"
    )
    assert final.get("intent") == "image_analysis", (
        f"intent must be 'image_analysis', got: {final.get('intent')}"
    )
    # Answer must explain limitation gracefully (not silent fail)
    assert final.get("answer") and len(str(final.get("answer"))) > 10, (
        "Final answer must have non-empty explanation for image analysis stub"
    )


# ── T5: palette paste image → AI mode (JS source check) ─────────────────────

def test_palette_paste_image_triggers_ai_mode():
    """command_palette.js must contain paste handler + _handleImagePaste + image_b64 POST."""
    src = (COMP / "command_palette.js").read_text(encoding="utf-8")

    assert "_handleImagePaste" in src, (
        "command_palette.js must define _handleImagePaste method"
    )
    assert "addEventListener('paste'" in src or 'addEventListener("paste"' in src, (
        "command_palette.js must add paste event listener"
    )
    assert "image_b64" in src, (
        "command_palette.js must include image_b64 in POST body"
    )
    assert "_blobToBase64" in src, (
        "command_palette.js must have _blobToBase64 helper"
    )
    assert "_pendingImage" in src, (
        "command_palette.js must track _pendingImage state"
    )


# ── T6: brain_sidebar.js file exists ─────────────────────────────────────────

def test_brain_sidebar_file_exists():
    """dashboard/components/brain_sidebar.js must exist and expose HermesBrainSidebar."""
    sidebar_path = COMP / "brain_sidebar.js"
    assert sidebar_path.exists(), "brain_sidebar.js must exist in dashboard/components/"

    src = sidebar_path.read_text(encoding="utf-8")
    assert "HermesBrainSidebar" in src, "brain_sidebar.js must define window.HermesBrainSidebar"
    assert "show" in src, "HermesBrainSidebar must expose show() method"
    assert "close" in src, "HermesBrainSidebar must expose close() method"
    assert "askFollowUp" in src, "HermesBrainSidebar must expose askFollowUp() method"
    assert "stream-decide" in src, "brain_sidebar.js must call /api/brain/stream-decide"


# ── T7: brain_sidebar localStorage namespace ─────────────────────────────────

def test_brain_sidebar_history_localstorage_namespace():
    """brain_sidebar.js must use 'hermes.brain.sidebar.history' localStorage key (max 10 turns)."""
    sidebar_path = COMP / "brain_sidebar.js"
    src = sidebar_path.read_text(encoding="utf-8")

    assert "hermes.brain.sidebar.history" in src, (
        "brain_sidebar.js must use localStorage key 'hermes.brain.sidebar.history'"
    )
    assert "MAX_TURNS" in src or "max 10" in src.lower() or "10" in src, (
        "brain_sidebar.js must limit conversation history to max turns"
    )
