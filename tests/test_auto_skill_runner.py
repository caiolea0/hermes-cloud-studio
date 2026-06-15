"""F.4.2 C1 — AutoSkillRunner unit tests (PIVOT D1 inline YAML validation)."""
from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

import core.skill_proposals as skill_proposals_module
import core.state as state_module
from core.auto_skill_runner import AutoSkillRunner, _shortid, _slugify
from core.skill_proposals import SkillProposalsManager


@pytest.fixture
def runner_with_tmp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "f42c1.db"
    sql = Path(__file__).parent.parent.joinpath(
        "migrations", "2026_06_skill_proposals.sql"
    ).read_text(encoding="utf-8")
    conn = sqlite3.connect(str(db_path))
    conn.executescript(sql)
    conn.close()

    monkeypatch.setattr(state_module, "DB_PATH", db_path)
    monkeypatch.setattr(skill_proposals_module, "DB_PATH", db_path)

    manager = SkillProposalsManager()
    runner = AutoSkillRunner(dispatcher=None, manager=manager)
    return runner, manager, db_path


# ---------------------------------------------------------------------------
# D1 PIVOT — inline YAML validation
# ---------------------------------------------------------------------------

def test_validate_yaml_inline_valid():
    runner = AutoSkillRunner(dispatcher=None, manager=None)
    yaml_blob = (
        "name: cobaia-daily\n"
        "version: 0.1\n"
        "provider: openrouter\n"
        "model: deepseek-chat:free\n"
    )
    result = runner._validate_yaml_inline(yaml_blob)
    assert result["status"] == "passed"
    assert result["exit_code"] == 0
    assert result["mock"] is True
    assert "Validation OK" in result["stdout"]
    assert result["stderr"] == ""
    assert result["latency_ms"] >= 0


def test_validate_yaml_inline_invalid_missing_key():
    runner = AutoSkillRunner(dispatcher=None, manager=None)
    yaml_blob = "name: only-name\n"
    result = runner._validate_yaml_inline(yaml_blob)
    assert result["status"] == "failed"
    assert result["exit_code"] == 1
    assert "version" in result["stderr"]


def test_validate_yaml_inline_malformed_yaml():
    runner = AutoSkillRunner(dispatcher=None, manager=None)
    yaml_blob = "name: foo\n  bad: indentation\n: : : invalid"
    result = runner._validate_yaml_inline(yaml_blob)
    assert result["status"] == "failed"
    assert result["exit_code"] == 1
    assert (
        "YAMLError" in result["stderr"]
        or "must be a mapping" in result["stderr"]
        or "Missing required" in result["stderr"]
    )


def test_validate_yaml_inline_missing_provider_and_steps():
    runner = AutoSkillRunner(dispatcher=None, manager=None)
    yaml_blob = "name: foo\nversion: 0.1\n"
    result = runner._validate_yaml_inline(yaml_blob)
    assert result["status"] == "failed"
    assert "provider" in result["stderr"]


def test_validate_yaml_inline_steps_only_ok():
    runner = AutoSkillRunner(dispatcher=None, manager=None)
    yaml_blob = "name: pipeline-skill\nversion: 0.2\nsteps:\n  - id: a\n"
    result = runner._validate_yaml_inline(yaml_blob)
    assert result["status"] == "passed"


# ---------------------------------------------------------------------------
# D3 — slugify / shortid helpers
# ---------------------------------------------------------------------------

def test_slugify_basic():
    assert _slugify("Cobaia Monitor Daily") == "cobaia-monitor-daily"
    assert _slugify("UPPER lower 123") == "upper-lower-123"
    assert _slugify("special!@#$chars") == "special-chars"
    assert _slugify("") == "unnamed"


def test_slugify_truncates_40():
    long_name = "a" * 100
    out = _slugify(long_name)
    assert len(out) <= 40


def test_shortid_six_chars():
    full = "a3f9c2d4-1234-5678-9abc-def012345678"
    assert _shortid(full) == "a3f9c2"
    assert _shortid("") == "000000"


# ---------------------------------------------------------------------------
# dispatch_sandbox_test — integration with tmp DB
# ---------------------------------------------------------------------------

def test_dispatch_sandbox_test_persists_passed(runner_with_tmp_db):
    runner, manager, _ = runner_with_tmp_db
    created = manager.create(
        name="dispatch-smoke",
        description="C1 smoke pass",
        yaml_blob=(
            "name: dispatch-smoke\n"
            "version: 0.1\n"
            "provider: openrouter\n"
        ),
    )
    proposal_id = created["id"]
    manager.owner_decision(proposal_id, decision="accept", reason="t")

    result = asyncio.run(runner.dispatch_sandbox_test(proposal_id))
    assert result["ok"] is True
    assert result["new_status"] == "lab_passed"
    assert result["lab_test_result"]["status"] == "passed"

    updated = manager.get(proposal_id)
    assert updated["status"] == "lab_passed"
    assert updated["lab_test_status"] == "passed"
    lab_blob = json.loads(updated["lab_test_result"])
    assert lab_blob["mock"] is True


def test_dispatch_sandbox_test_failed_yaml(runner_with_tmp_db):
    runner, manager, _ = runner_with_tmp_db
    created = manager.create(
        name="bad-yaml",
        description="C1 smoke fail",
        yaml_blob="name: bad\n",
    )
    proposal_id = created["id"]
    manager.owner_decision(proposal_id, decision="accept", reason="t")

    result = asyncio.run(runner.dispatch_sandbox_test(proposal_id))
    assert result["ok"] is False
    assert result["new_status"] == "lab_failed"
    assert result["lab_test_result"]["status"] == "failed"

    updated = manager.get(proposal_id)
    assert updated["status"] == "lab_failed"


def test_dispatch_sandbox_test_proposal_not_found(runner_with_tmp_db):
    runner, _manager, _ = runner_with_tmp_db
    with pytest.raises(LookupError):
        asyncio.run(runner.dispatch_sandbox_test("does-not-exist"))
