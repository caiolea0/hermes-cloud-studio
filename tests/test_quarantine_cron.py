"""F.4.4 C2 — Quarantine cron unit tests.

Validates:
  - Skills below MIN_SAMPLE threshold are skipped
  - Skills with success_rate < 0.5 are quarantined (file moved)
  - Already-quarantined skills are skipped (idempotent)
  - Lock busy returns early (exit 1)
  - Healthy skills are not quarantined
  - systemd reload called only if skills were quarantined
  - success_rate edge cases (zero runs, 100%, 0%)
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import scripts.quarantine_skills as qs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """Minimal SQLite DB with skill_runs + skill_sync_runs tables."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS skill_runs (
            id TEXT PRIMARY KEY,
            skill_name TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS skill_sync_runs (
            id TEXT PRIMARY KEY,
            trigger_type TEXT NOT NULL,
            pr_number INTEGER,
            pr_url TEXT,
            sync_status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            error_message TEXT,
            affected_skills TEXT
        );
    """)
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def skills_dir(tmp_path):
    """Temp skills directory with sample YAML files."""
    d = tmp_path / "skills"
    d.mkdir()
    (d / "cobaia-daily.yaml").write_text("name: cobaia-daily\nactive: true\n")
    (d / "linkedin-post-generator.yaml").write_text("name: linkedin-post-generator\nactive: true\n")
    return d


def _insert_runs(db: Path, skill_name: str, statuses: list[str]) -> None:
    conn = sqlite3.connect(str(db))
    for status in statuses:
        conn.execute(
            "INSERT INTO skill_runs (id, skill_name, status) VALUES (?, ?, ?)",
            (str(uuid.uuid4()), skill_name, status),
        )
    conn.commit()
    conn.close()


def _run(db: Path, skills_dir: Path, dry_run: bool = False) -> dict:
    with patch.dict(os.environ, {
        "HERMES_DB_PATH": str(db),
        "HERMES_SKILLS_DIR": str(skills_dir),
    }):
        return qs.run(dry_run=dry_run)


# ---------------------------------------------------------------------------
# test_skip_skills_below_min_sample_size
# ---------------------------------------------------------------------------

def test_skip_skills_below_min_sample_size(tmp_db, skills_dir):
    """Skills with fewer than MIN_SAMPLE runs should be skipped (insufficient data)."""
    # Only 5 runs → below MIN_SAMPLE=10
    _insert_runs(tmp_db, "cobaia-daily", ["error"] * 5)
    result = _run(tmp_db, skills_dir)
    assert result["status"] == "ok"
    names = [s["name"] for s in result["skipped_insufficient_data"]]
    assert "cobaia-daily" in names
    assert result["quarantined"] == []


# ---------------------------------------------------------------------------
# test_quarantine_skill_below_threshold
# ---------------------------------------------------------------------------

def test_quarantine_skill_below_threshold(tmp_db, skills_dir):
    """Skill with success_rate < 0.5 (last 10 runs) must be moved to _quarantine/."""
    # 3 completed out of 10 = 0.3 < 0.5
    _insert_runs(tmp_db, "cobaia-daily", ["completed"] * 3 + ["error"] * 7)
    result = _run(tmp_db, skills_dir)
    assert result["status"] == "ok"
    quarantined_names = [q["name"] for q in result["quarantined"]]
    assert "cobaia-daily" in quarantined_names
    # File should have moved to _quarantine/
    assert not (skills_dir / "cobaia-daily.yaml").exists()
    assert (skills_dir / "_quarantine" / "cobaia-daily.yaml").exists()


# ---------------------------------------------------------------------------
# test_skip_already_quarantined (idempotent)
# ---------------------------------------------------------------------------

def test_skip_already_quarantined(tmp_db, skills_dir):
    """If YAML already in _quarantine/, cron sees no file in skills/ — idempotent."""
    # Move the file to _quarantine/ manually first
    q_dir = skills_dir / "_quarantine"
    q_dir.mkdir()
    (skills_dir / "cobaia-daily.yaml").rename(q_dir / "cobaia-daily.yaml")
    # Insert failing runs
    _insert_runs(tmp_db, "cobaia-daily", ["error"] * 10)
    result = _run(tmp_db, skills_dir)
    # cobaia-daily not in skills_dir → not checked → quarantined stays empty
    quarantined_names = [q["name"] for q in result["quarantined"]]
    assert "cobaia-daily" not in quarantined_names


# ---------------------------------------------------------------------------
# test_lock_busy_skips
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="fcntl not available on Windows")
def test_lock_busy_skips(tmp_db, skills_dir):
    """When lock file is busy, main() should return exit code 1."""
    import fcntl

    lock_path = "/tmp/hermes-sync-test.lock"
    # Monkey-patch LOCK_FILE
    orig_lock = qs.LOCK_FILE
    qs.LOCK_FILE = lock_path
    try:
        # Hold the lock externally
        hold_fd = open(lock_path, "w")
        fcntl.flock(hold_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            import sys, io
            with patch("sys.argv", ["quarantine_skills.py"]):
                with patch.dict(os.environ, {
                    "HERMES_DB_PATH": str(tmp_db),
                    "HERMES_SKILLS_DIR": str(skills_dir),
                }):
                    exit_code = qs.main()
            assert exit_code == 1
        finally:
            fcntl.flock(hold_fd, fcntl.LOCK_UN)
            hold_fd.close()
    finally:
        qs.LOCK_FILE = orig_lock


# ---------------------------------------------------------------------------
# test_no_action_if_all_healthy
# ---------------------------------------------------------------------------

def test_no_action_if_all_healthy(tmp_db, skills_dir):
    """Skills with success_rate >= 0.5 must NOT be quarantined."""
    _insert_runs(tmp_db, "cobaia-daily", ["completed"] * 8 + ["error"] * 2)
    result = _run(tmp_db, skills_dir)
    assert result["quarantined"] == []
    assert (skills_dir / "cobaia-daily.yaml").exists()


# ---------------------------------------------------------------------------
# test_no_reload_if_nothing_quarantined
# ---------------------------------------------------------------------------

def test_no_ws_emit_if_nothing_quarantined(tmp_db, skills_dir):
    """_ws_notify should NOT be called if no skills were quarantined."""
    _insert_runs(tmp_db, "cobaia-daily", ["completed"] * 10)
    with patch.object(qs, "_ws_notify") as mock_ws:
        _run(tmp_db, skills_dir)
    mock_ws.assert_not_called()


# ---------------------------------------------------------------------------
# test_compute_success_rate_edge_cases
# ---------------------------------------------------------------------------

def test_compute_success_rate_zero_runs(tmp_db):
    """Zero runs → success_rate=0.0, sample_size=0."""
    conn = sqlite3.connect(str(tmp_db))
    result = qs._skill_runs_success_rate(conn, "nonexistent-skill")
    conn.close()
    assert result["success_rate"] == 0.0
    assert result["sample_size"] == 0


def test_compute_success_rate_all_pass(tmp_db, skills_dir):
    """100% pass rate → not quarantined."""
    _insert_runs(tmp_db, "cobaia-daily", ["completed"] * 10)
    result = _run(tmp_db, skills_dir)
    assert result["quarantined"] == []
    assert (skills_dir / "cobaia-daily.yaml").exists()


def test_compute_success_rate_all_fail(tmp_db, skills_dir):
    """0% pass rate → quarantined."""
    _insert_runs(tmp_db, "cobaia-daily", ["error"] * 10)
    result = _run(tmp_db, skills_dir)
    quarantined_names = [q["name"] for q in result["quarantined"]]
    assert "cobaia-daily" in quarantined_names
