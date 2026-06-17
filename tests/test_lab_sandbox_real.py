"""H2 Hardening-Future — F.4 lab sandbox REAL tests.

Tests: subprocess isolated execution, banned pattern detection,
timeout enforcement, gateway dispatch with fallback, _skill_runner
JSON output.

All 10 tests (G2 gate: 175 total = 165 baseline + 10 new).
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SKILLS_MCP_DIR = _REPO_ROOT / "mcps" / "hermes-skills"


# ---------------------------------------------------------------------------
# Helpers — load modules with hyphen-in-path
# ---------------------------------------------------------------------------

def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_runner():
    return _load_module("skill_runner_h2", _SKILLS_MCP_DIR / "_skill_runner.py")


def _load_server():
    """Load server.py; stub fastmcp if not installed (mirrors _smoke.py pattern)."""
    try:
        import fastmcp  # noqa: F401
    except ImportError:
        import types
        stub = types.ModuleType("fastmcp")

        class _StubMCP:
            def __init__(self, name: str) -> None:
                self.name = name

            def tool(self, *a, **kw):
                def deco(fn):
                    return fn
                return deco

            def run(self, **kw) -> None:
                pass

        stub.FastMCP = _StubMCP  # type: ignore[attr-defined]
        sys.modules["fastmcp"] = stub

    if str(_SKILLS_MCP_DIR) not in sys.path:
        sys.path.insert(0, str(_SKILLS_MCP_DIR))
    return _load_module("hermes_skills_server_h2", _SKILLS_MCP_DIR / "server.py")


# ---------------------------------------------------------------------------
# Fixtures (mirror runner_with_tmp_db from test_auto_skill_runner.py)
# ---------------------------------------------------------------------------

import core.skill_proposals as _sp_module
import core.state as _state_module
from core.auto_skill_runner import AutoSkillRunner
from core.skill_proposals import SkillProposalsManager


class _MockDispatcher:
    """Capture-only dispatcher; records invoke_tool calls."""

    def __init__(
        self,
        response: dict | None = None,
        raise_exc: Exception | None = None,
    ):
        self.response = response
        self.raise_exc = raise_exc
        self.calls: list[dict] = []

    async def invoke_tool(self, server, tool, args, requester="brain", caller_chapter=None):
        self.calls.append({
            "server": server, "tool": tool, "args": args, "requester": requester,
            "caller_chapter": caller_chapter,
        })
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response or {"ok": True, "response": {}}


@pytest.fixture
def runner_with_tmp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "h2_test.db"
    sql = (_REPO_ROOT / "migrations" / "2026_06_skill_proposals.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(str(db_path))
    conn.executescript(sql)
    conn.close()

    monkeypatch.setattr(_state_module, "DB_PATH", db_path)
    monkeypatch.setattr(_sp_module, "DB_PATH", db_path)

    manager = SkillProposalsManager()
    runner = AutoSkillRunner(dispatcher=None, manager=manager)
    return runner, manager, db_path


# ---------------------------------------------------------------------------
# 1. test_test_skill_dryrun_accepts_yaml_blob_param
# ---------------------------------------------------------------------------

def test_test_skill_dryrun_accepts_yaml_blob_param():
    """H2 — test_skill_dryrun aceita yaml_blob param e executa subprocess real."""
    server = _load_server()
    valid_yaml = "name: h2-smoke\nversion: 0.1\nprovider: openrouter\n"

    result = asyncio.run(server.test_skill_dryrun(yaml_blob=valid_yaml, input_data={}))

    assert "ok" in result, f"missing 'ok' key: {result}"
    assert result.get("ok") is True, f"expected ok=True got: {result}"
    assert result.get("status") == "passed"
    assert result.get("mock") is False  # real subprocess, not inline


# ---------------------------------------------------------------------------
# 2. test_subprocess_isolated_execution_timeout_60s
# ---------------------------------------------------------------------------

def test_subprocess_isolated_execution_timeout_60s():
    """H2 G5 — asyncio.wait_for timeout enforced; subprocess killed."""
    server = _load_server()

    mock_proc = MagicMock()
    mock_proc.returncode = -1
    mock_proc.kill = MagicMock()
    mock_proc.wait = AsyncMock(return_value=None)

    async def _slow_communicate():
        await asyncio.sleep(300)
        return b"", b""

    mock_proc.communicate = _slow_communicate

    async def _mock_create_subprocess(*args, **kwargs):
        return mock_proc

    async def run():
        with patch("asyncio.create_subprocess_exec", side_effect=_mock_create_subprocess):
            return await server._execute_subprocess_isolated(
                "/tmp/fake.yaml", {}, timeout=1
            )

    result = asyncio.run(run())

    assert result["status"] == "timeout"
    assert result["exit_code"] == -1
    mock_proc.kill.assert_called_once()


# ---------------------------------------------------------------------------
# 3. test_malicious_yaml_os_system_blocked
# ---------------------------------------------------------------------------

def test_malicious_yaml_os_system_blocked():
    """H2 G6 — yaml_blob com os.system( detectado e bloqueado."""
    runner = _load_runner()

    skill_dict = {
        "name": "malicious",
        "version": "0.1",
        "provider": "openrouter",
        "system_prompt": "os.system('rm -rf /')",
    }
    result = runner._validate_and_exec(skill_dict, {})

    assert result["status"] == "failed"
    assert result["exit_code"] == 2
    assert "os.system(" in result["stderr"]
    assert result["mock"] is False


# ---------------------------------------------------------------------------
# 4. test_malicious_yaml_sys_exit_blocked
# ---------------------------------------------------------------------------

def test_malicious_yaml_sys_exit_blocked():
    """H2 G6 — yaml_blob com sys.exit( detectado e bloqueado."""
    runner = _load_runner()

    skill_dict = {
        "name": "exiter",
        "version": "0.1",
        "provider": "openrouter",
        "system_prompt": "call sys.exit(0) to terminate",
    }
    result = runner._validate_and_exec(skill_dict, {})

    assert result["status"] == "failed"
    assert result["exit_code"] == 2
    assert "sys.exit(" in result["stderr"]


# ---------------------------------------------------------------------------
# 5. test_malicious_yaml_eval_exec_blocked
# ---------------------------------------------------------------------------

def test_malicious_yaml_eval_exec_blocked():
    """H2 G6 — yaml_blob com eval( / exec( detectados e bloqueados."""
    runner = _load_runner()

    for banned_code, label in [("eval(input)", "eval("), ("exec(open('x').read())", "exec(")]:
        skill_dict = {
            "name": "injector",
            "version": "0.1",
            "provider": "openrouter",
            "system_prompt": f"run {banned_code}",
        }
        result = runner._validate_and_exec(skill_dict, {})
        assert result["status"] == "failed", f"expected fail for {label}"
        assert result["exit_code"] == 2, f"expected exit_code=2 for {label}"
        assert label in result["stderr"], f"expected {label!r} in stderr"


# ---------------------------------------------------------------------------
# 6. test_infinite_loop_killed_at_timeout
# ---------------------------------------------------------------------------

def test_infinite_loop_killed_at_timeout():
    """H2 G5 — subprocess infinito morto pelo asyncio.wait_for no _execute_subprocess_isolated."""
    async def run():
        # Spawn real subprocess that sleeps 100s; pass timeout=1 → killed.
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "import time; time.sleep(100)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=1)
            return {"killed": False, "stdout": stdout, "stderr": stderr}
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"killed": True}

    result = asyncio.run(run())
    assert result["killed"] is True, "infinite subprocess should have been killed by timeout"


# ---------------------------------------------------------------------------
# 7. test_dispatch_sandbox_test_uses_real_subprocess
# ---------------------------------------------------------------------------

def test_dispatch_sandbox_test_uses_real_subprocess(runner_with_tmp_db):
    """H2 — dispatch_sandbox_test chama gateway com yaml_blob (subprocess path)."""
    runner, manager, _ = runner_with_tmp_db

    # Gateway returns subprocess-style result (mock=False)
    dispatcher = _MockDispatcher(response={
        "ok": True,
        "response": {
            "status": "passed",
            "stdout": "Subprocess sandbox OK",
            "stderr": "",
            "latency_ms": 15,
            "exit_code": 0,
            "mock": False,
        },
    })
    runner.dispatcher = dispatcher

    created = manager.create(
        name="gateway-h2-smoke",
        description="H2 gateway dispatch test",
        yaml_blob="name: gateway-h2-smoke\nversion: 0.1\nprovider: openrouter\n",
    )
    proposal_id = created["id"]
    manager.owner_decision(proposal_id, decision="accept", reason="h2")

    result = asyncio.run(runner.dispatch_sandbox_test(proposal_id))

    # Gateway was called with yaml_blob
    assert len(dispatcher.calls) == 1
    call = dispatcher.calls[0]
    assert call["server"] == "hermes-skills"
    assert call["tool"] == "test_skill_dryrun"
    assert "yaml_blob" in call["args"]
    assert "gateway-h2-smoke" in call["args"]["yaml_blob"]
    assert call["requester"] == "brain-f4"

    # Gateway result (mock=False) propagated
    assert result["ok"] is True
    assert result["lab_test_result"]["mock"] is False


# ---------------------------------------------------------------------------
# 8. test_dispatch_sandbox_test_fallback_inline_if_gateway_down
# ---------------------------------------------------------------------------

def test_dispatch_sandbox_test_fallback_inline_if_gateway_down(runner_with_tmp_db):
    """H2 G7 — fallback inline quando gateway lança exceção."""
    runner, manager, _ = runner_with_tmp_db

    dispatcher = _MockDispatcher(raise_exc=ConnectionError("gateway down"))
    runner.dispatcher = dispatcher

    created = manager.create(
        name="fallback-h2",
        description="H2 fallback test",
        yaml_blob="name: fallback-h2\nversion: 0.1\nprovider: openrouter\n",
    )
    proposal_id = created["id"]
    manager.owner_decision(proposal_id, decision="accept", reason="h2")

    result = asyncio.run(runner.dispatch_sandbox_test(proposal_id))

    # Fallback inline: ok=True + mock=True
    assert result["ok"] is True
    assert result["lab_test_result"]["mock"] is True  # inline fallback

    # Dispatcher was tried (1 call)
    assert len(dispatcher.calls) == 1


# ---------------------------------------------------------------------------
# 9. test_skill_runner_returns_structured_json
# ---------------------------------------------------------------------------

def test_skill_runner_returns_structured_json(tmp_path):
    """H2 — _skill_runner.py executado diretamente retorna JSON estruturado."""
    yaml_path = tmp_path / "test_skill.yaml"
    yaml_path.write_text(
        "name: json-smoke\nversion: 0.1\nprovider: openrouter\n",
        encoding="utf-8",
    )

    async def run():
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(_SKILLS_MCP_DIR / "_skill_runner.py"),
            str(yaml_path),
            "{}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={
                **__import__("os").environ.copy(),
                "PYTHONPATH": str(_REPO_ROOT),
            },
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        return proc.returncode, stdout.decode("utf-8", errors="replace").strip()

    returncode, stdout_text = asyncio.run(run())

    assert returncode == 0, f"expected exit 0, got {returncode}: {stdout_text!r}"

    # Stdout must be valid JSON with expected keys.
    result = json.loads(stdout_text)
    assert result["status"] == "passed"
    assert result["exit_code"] == 0
    assert result["mock"] is False
    assert "Subprocess sandbox OK" in result["stdout"]


# ---------------------------------------------------------------------------
# 10. test_subprocess_cleanup_temp_file
# ---------------------------------------------------------------------------

def test_subprocess_cleanup_temp_file(tmp_path, monkeypatch):
    """H2 — temp file criado para subprocess é removido após execução."""
    server = _load_server()

    # Override TEMP dir to our tmp_path so we can check for leftover files.
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    valid_yaml = "name: cleanup-test\nversion: 0.1\nprovider: openrouter\n"

    asyncio.run(server.test_skill_dryrun(yaml_blob=valid_yaml, input_data={}))

    # No hermes_skill_dryrun_*.yaml files should remain.
    leftover = list(tmp_path.glob("hermes_skill_dryrun_*.yaml"))
    assert leftover == [], f"temp files not cleaned up: {leftover}"
