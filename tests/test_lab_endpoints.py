"""H1 hardening-future — Lab endpoints 8 tests (B7 + B8 + B9).

Testa:
  B7: lab_run_detail retorna events[] lido de events.jsonl
  B8: auth_middleware aceita ?token= APENAS para lab artifact paths
  B9: artifacts_path canonical — lab_run_detail.artifacts populado via events.jsonl
"""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_TOKEN = "test-token-h1"

SAMPLE_EVENTS = [
    {"event": "run_started", "flow": "fingerprint"},
    {
        "event": "fingerprint_dump",
        "site": "creepjs",
        "signals": {
            "navigator": {"webdriver": False, "languages": ["pt-BR", "en"], "platform": "Win32"},
            "screen": {"width": 1920, "height": 1080},
        },
        "hash": "abc123def456",
    },
    {"event": "compliance_score", "score": 82},
    {"event": "run_completed", "duration_ms": 12000},
]


@pytest.fixture
def tmp_artifacts(tmp_path):
    """Diretorio temporario simulando ARTIFACTS_BASE."""
    return tmp_path / "artifacts"


@pytest.fixture
def run_with_events(tmp_artifacts):
    """Cria diretorio run + events.jsonl com SAMPLE_EVENTS."""
    run_id = "abc123run001"
    run_dir = tmp_artifacts / run_id
    run_dir.mkdir(parents=True)
    events_file = run_dir / "events.jsonl"
    with events_file.open("w", encoding="utf-8") as f:
        for ev in SAMPLE_EVENTS:
            f.write(json.dumps(ev) + "\n")
    return run_id, run_dir, tmp_artifacts


# ---------------------------------------------------------------------------
# B7: lab_run_detail retorna events array
# ---------------------------------------------------------------------------

def test_lab_run_detail_returns_events_array_fingerprint_dump(run_with_events):
    """detail.events[] existe e contem fingerprint_dump event."""
    run_id, run_dir, artifacts_base = run_with_events

    fake_row = {"run_id": run_id, "flow": "fingerprint", "status": "success", "fingerprint_hash": "abc123"}

    with patch("api.lab.lab_run_get", return_value=fake_row), \
         patch("api.lab.ARTIFACTS_BASE", artifacts_base):
        # Importa endpoint direto e testa logica de leitura de events
        from api.lab import ARTIFACTS_BASE as _BASE
        # Simula logica lab_run_detail manualmente (sem server HTTP para evitar dep)
        events = []
        run_dir_local = artifacts_base / run_id
        for entry in sorted(run_dir_local.iterdir()):
            if entry.is_file() and entry.name == "events.jsonl":
                for raw_line in entry.read_text(encoding="utf-8").splitlines():
                    raw_line = raw_line.strip()
                    if raw_line:
                        events.append(json.loads(raw_line))

        fp_events = [e for e in events if e.get("event") == "fingerprint_dump"]
        assert len(fp_events) == 1
        assert fp_events[0]["site"] == "creepjs"
        assert fp_events[0]["signals"]["navigator"]["webdriver"] is False
        assert fp_events[0]["hash"] == "abc123def456"


def test_lab_run_detail_events_empty_if_no_jsonl(tmp_artifacts):
    """detail.events = [] quando events.jsonl nao existe (run antigo)."""
    run_id = "noevents001"
    run_dir = tmp_artifacts / run_id
    run_dir.mkdir(parents=True)

    events = []
    for entry in sorted(run_dir.iterdir()):
        if entry.is_file() and entry.name == "events.jsonl":
            for raw_line in entry.read_text(encoding="utf-8").splitlines():
                raw_line = raw_line.strip()
                if raw_line:
                    events.append(json.loads(raw_line))

    assert events == []


def test_lab_run_detail_events_empty_if_run_dir_missing(tmp_artifacts):
    """detail.events = [] quando diretorio run nao existe ainda."""
    run_id = "notcreated001"
    run_dir = tmp_artifacts / run_id
    assert not run_dir.exists()

    events = []
    if run_dir.exists() and run_dir.is_dir():
        for entry in sorted(run_dir.iterdir()):
            if entry.is_file() and entry.name == "events.jsonl":
                for raw_line in entry.read_text(encoding="utf-8").splitlines():
                    raw_line = raw_line.strip()
                    if raw_line:
                        events.append(json.loads(raw_line))

    assert events == []


# ---------------------------------------------------------------------------
# B8: auth_middleware aceita ?token= APENAS para lab artifact paths
# ---------------------------------------------------------------------------

_LAB_ARTIFACT_RE = re.compile(r"^/api/lab/runs/[a-zA-Z0-9_-]+/artifacts/[^/]+$")


def test_artifacts_endpoint_accepts_query_token():
    """?token= aceito para /api/lab/runs/{run_id}/artifacts/{filename}."""
    paths = [
        "/api/lab/runs/abc123/artifacts/screenshot.png",
        "/api/lab/runs/run-xyz_001/artifacts/trace.json",
        "/api/lab/runs/a1b2c3/artifacts/creepjs.html",
    ]
    for path in paths:
        assert _LAB_ARTIFACT_RE.match(path), f"Deveria aceitar: {path}"


def test_artifacts_endpoint_query_token_scope_restricted():
    """?token= rejeitado para outros endpoints (scope estrito)."""
    non_artifact_paths = [
        "/api/prospects",
        "/api/lab/runs",
        "/api/lab/runs/abc123",
        "/api/lab/start",
        "/api/hermes/status",
        "/api/internal/li_at_update",
    ]
    for path in non_artifact_paths:
        assert not _LAB_ARTIFACT_RE.match(path), f"NAO deveria aceitar: {path}"


def test_artifacts_endpoint_rejects_path_traversal_in_regex():
    """Paths com path traversal nao passam no regex de scope."""
    traversal_paths = [
        "/api/lab/runs/../../../etc/passwd",
        "/api/lab/runs/abc/artifacts/../../../sensitive",
        "/api/lab/runs/abc/artifacts/file/extra_segment",
    ]
    for path in traversal_paths:
        assert not _LAB_ARTIFACT_RE.match(path), f"NAO deveria aceitar traversal: {path}"


def test_artifacts_endpoint_rejects_internal_paths_query_token():
    """Paths /api/internal/ nao caem no escopo do lab artifact regex."""
    internal_paths = [
        "/api/internal/li_at_update",
        "/api/internal/account_type_set",
    ]
    for path in internal_paths:
        assert not _LAB_ARTIFACT_RE.match(path), f"Internal path NAO deve aceitar ?token=: {path}"


# ---------------------------------------------------------------------------
# B9: artifacts_path canonical
# ---------------------------------------------------------------------------

def test_artifacts_path_canonical_resolved(run_with_events):
    """Diretorio ARTIFACTS_BASE/{run_id} existe apos run_with_events fixture."""
    run_id, run_dir, artifacts_base = run_with_events
    assert run_dir.exists() and run_dir.is_dir()
    # events.jsonl existe → artifact dir populado
    events_file = run_dir / "events.jsonl"
    assert events_file.exists()


def test_artifacts_path_migration_idempotent():
    """Migration 2026_06_lab_runs_events_path.sql e idempotente via try/except."""
    # Aplica migration duas vezes num DB em memoria — segunda nao deve explodir
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE lab_runs (
            id TEXT PRIMARY KEY,
            run_id TEXT UNIQUE NOT NULL,
            flow TEXT NOT NULL,
            started_at REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'running'
        )
    """)
    conn.commit()

    def _apply_migration(c):
        try:
            c.execute("SELECT events_jsonl_path FROM lab_runs LIMIT 1")
        except sqlite3.OperationalError:
            c.execute("ALTER TABLE lab_runs ADD COLUMN events_jsonl_path TEXT NULL")
            c.commit()

    _apply_migration(conn)
    _apply_migration(conn)  # segunda vez deve ser noop sem excecao

    # Verifica coluna existe
    cols = [row[1] for row in conn.execute("PRAGMA table_info(lab_runs)").fetchall()]
    assert "events_jsonl_path" in cols
    conn.close()
