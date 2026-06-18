"""UX-RM-F1-A: Kill C1+C2 critical mocks — pipelines.py + cobaia_warmup.py.

Gates:
  G3a: zero random.randint/choice in api/pipelines.py + linkedin/cobaia_warmup.py
  G3b: stub_execute_skill deleted from cobaia_warmup
  C1: pipeline search returns [] on failure, never fake profiles
  C2: orchestrator uses real VM dispatch, raises on stub path
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parent.parent


# ── G3a: zero random.* in C1+C2 files ──────────────────────────────────────

def test_pipelines_no_random_import():
    """api/pipelines.py must not import random (C1 fake-data removed)."""
    src = (REPO / "api" / "pipelines.py").read_text(encoding="utf-8")
    assert "import random" not in src, "api/pipelines.py still imports random"


def test_pipelines_no_random_calls():
    """api/pipelines.py must contain zero random.randint/choice calls."""
    src = (REPO / "api" / "pipelines.py").read_text(encoding="utf-8")
    assert "random.randint" not in src
    assert "random.choice" not in src


def test_cobaia_warmup_no_random_generation():
    """linkedin/cobaia_warmup.py must not call random.randint/choice."""
    src = (REPO / "linkedin" / "cobaia_warmup.py").read_text(encoding="utf-8")
    assert "random.randint" not in src
    assert "random.choice" not in src


# ── G3b: stub_execute_skill deleted ─────────────────────────────────────────

def test_cobaia_warmup_stub_execute_skill_deleted():
    """stub_execute_skill must not exist in linkedin/cobaia_warmup.py (deleted in F1-A)."""
    src = (REPO / "linkedin" / "cobaia_warmup.py").read_text(encoding="utf-8")
    assert "stub_execute_skill" not in src, (
        "stub_execute_skill still present in cobaia_warmup.py — not deleted"
    )


def test_cobaia_warmup_mock_success_deleted():
    """mock_success sentinel must not appear in linkedin/cobaia_warmup.py."""
    src = (REPO / "linkedin" / "cobaia_warmup.py").read_text(encoding="utf-8")
    assert "mock_success" not in src


# ── C1: pipeline search returns empty on failure, not random profiles ────────

def test_pipelines_search_empty_on_failure(monkeypatch):
    """_execute_linkedin_viewer must return profiles=[] and source=unavailable
    when both real viewer (ImportError) and VM are unavailable."""
    import asyncio
    import builtins

    dummy_conn = MagicMock()
    dummy_conn.execute.return_value = MagicMock(fetchone=lambda: None, fetchall=lambda: [])
    dummy_conn.commit = MagicMock()
    dummy_conn.close = MagicMock()

    import api.pipelines as pm

    monkeypatch.setattr(pm, "get_db", lambda: dummy_conn)

    logs = []

    # Patch builtins.__import__ to raise ImportError on linkedin module
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "linkedin":
            raise ImportError("patchright not installed on PC")
        return real_import(name, *args, **kwargs)

    async def _run():
        with patch("builtins.__import__", side_effect=fake_import):
            with patch("httpx.AsyncClient") as mock_cls:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_ctx.post = AsyncMock(side_effect=Exception("connection refused"))
                mock_cls.return_value = mock_ctx

                return await pm._execute_linkedin_viewer(
                    exec_id=1,
                    targets={"roles": ["tech recruiter"], "location": "Cuiaba", "max_profiles": 50},
                    prompt="tech recruiters cuiaba",
                    add_log=lambda msg, **kw: logs.append(msg),
                )

    result = asyncio.run(_run())

    assert result["profiles"] == [], f"Expected empty profiles, got {len(result['profiles'])}"
    assert result["profiles_visited"] == 0
    assert result.get("source") == "unavailable"
    assert result.get("simulated") is False


# ── C2: orchestrator raises on stub path, uses real dispatch ────────────────

def test_cobaia_warmup_raises_on_stub_path_detected(monkeypatch):
    """_exec_cobaia_warmup must raise RuntimeError if dispatch returns stub=True."""
    import asyncio
    from daemon import orchestrator as omod

    daemon = omod.HermesDaemon.__new__(omod.HermesDaemon)
    daemon.log_event = AsyncMock()

    stub_dispatch = {"stub": True, "result": "mock_success", "actions_taken": 0}

    async def _run():
        with patch("daemon.cobaia_warmup_scheduler._dispatch_cobaia_session_to_vm", return_value=stub_dispatch):
            with patch("brain.decide.Brain") as MockBrain:
                mock_brain = MagicMock()
                mock_brain.decide = AsyncMock(return_value={"final_answer": {
                    "action": "profile_view",
                    "skill_name": "linkedin-engagement",
                    "status": "ok",
                }})
                MockBrain.return_value = mock_brain

                with pytest.raises(RuntimeError, match="F1-A: stub path reached"):
                    await daemon._exec_cobaia_warmup({
                        "account_handle": "test-cobaia",
                        "phase": "lurking",
                        "current_day": 3,
                        "caps_today": {"views": 4},
                        "today_metrics": {},
                    })

    asyncio.run(_run())


def test_cobaia_warmup_real_dispatch_used(monkeypatch):
    """_exec_cobaia_warmup must call _dispatch_cobaia_session_to_vm (not stub)."""
    import asyncio
    from daemon import orchestrator as omod

    daemon = omod.HermesDaemon.__new__(omod.HermesDaemon)
    daemon.log_event = AsyncMock()

    real_result = {"status": "queued", "session_id": "sess-abc123", "actions_planned": 3}
    dispatch_calls = []

    def fake_dispatch(phase, caps, account_handle):
        dispatch_calls.append((phase, caps, account_handle))
        return real_result

    async def _run():
        with patch("daemon.cobaia_warmup_scheduler._dispatch_cobaia_session_to_vm", side_effect=fake_dispatch):
            with patch("brain.decide.Brain") as MockBrain:
                mock_brain = MagicMock()
                mock_brain.decide = AsyncMock(return_value={"final_answer": {
                    "action": "profile_view",
                    "skill_name": "linkedin-engagement",
                    "status": "ok",
                }})
                MockBrain.return_value = mock_brain

                with patch("core.cobaia_metrics.update_cobaia_daily_metric"):
                    return await daemon._exec_cobaia_warmup({
                        "account_handle": "test-cobaia",
                        "phase": "lurking",
                        "current_day": 3,
                        "caps_today": {"views": 4},
                        "today_metrics": {},
                    })

    result = asyncio.run(_run())

    assert len(dispatch_calls) == 1, "Expected exactly 1 real dispatch call"
    assert dispatch_calls[0][0] == "lurking"
    assert result.get("dispatched") is True
    assert result.get("session_id") == "sess-abc123"
    assert result.get("stub") is None, "Result must not contain stub=True"
