"""
UX-RM-F6-A — Canvas Sequence Builder: backend schema + API + frontend structure.
Tests: migration idempotency, CRUD endpoints, JS file existence, HTML page + nav.
Gates: G1 BLACKLIST R2 INTACTO 65 SS, G2 pytest 470+ PASS.
"""
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).parent.parent
COMPONENTS = ROOT / "dashboard" / "components"
INDEX_HTML = ROOT / "dashboard" / "index.html"
APP_JS = ROOT / "dashboard" / "app.js"
MIGRATION = ROOT / "migrations" / "2026_06_sequences.sql"


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


# ─────────────────────────────────────────────────────────────────────────────
# G1: Migration file exists and is idempotent SQL
# ─────────────────────────────────────────────────────────────────────────────

def test_sequences_migration_file_exists():
    assert MIGRATION.is_file(), "migrations/2026_06_sequences.sql not found"


def test_sequences_migration_idempotent(tmp_path):
    """Migration SQL must be runnable twice without error (IF NOT EXISTS)."""
    sql = _read(MIGRATION)
    db_path = tmp_path / "test_seq.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(sql)
    conn.executescript(sql)  # second run must not raise
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert "sequences" in tables
    assert "sequence_nodes" in tables
    assert "sequence_edges" in tables


# ─────────────────────────────────────────────────────────────────────────────
# API fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client(tmp_path):
    db_path = tmp_path / "f6a_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_read(MIGRATION))
    conn.close()

    def _fake_get_db():
        c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c

    with patch("api.sequences.get_db", _fake_get_db), \
         patch("core.state.get_db", _fake_get_db):
        from server import app
        yield TestClient(app)


@pytest.fixture
def auth_headers():
    from core.state import AUTH_TOKEN
    return {"X-Hermes-Token": AUTH_TOKEN}


# ─────────────────────────────────────────────────────────────────────────────
# G2: POST /api/sequences returns id
# ─────────────────────────────────────────────────────────────────────────────

def test_create_sequence_endpoint_returns_id(api_client, auth_headers):
    payload = {
        "name": "Campanha LI Cuiaba",
        "description": "Teste F6-A",
        "canvas_json": {
            "nodes": [
                {"id": "n_start", "type": "start", "x": 100, "y": 80, "config": {}},
                {"id": "n_end",   "type": "end",   "x": 100, "y": 300, "config": {}},
            ],
            "edges": [{"from": "n_start", "to": "n_end", "type": "default"}],
        },
    }
    r = api_client.post("/api/sequences", json=payload, headers=auth_headers)
    assert r.status_code == 201, r.text
    data = r.json()
    assert "id" in data
    assert isinstance(data["id"], int)


# ─────────────────────────────────────────────────────────────────────────────
# G3: GET /api/sequences/{id} returns nodes + edges
# ─────────────────────────────────────────────────────────────────────────────

def test_get_sequence_returns_nodes_edges(api_client, auth_headers):
    payload = {
        "name": "Seq Completa",
        "canvas_json": {
            "nodes": [
                {"id": "n1", "type": "start",  "x": 100, "y": 80,  "config": {}},
                {"id": "n2", "type": "action", "channel": "linkedin", "action": "connect", "x": 100, "y": 200, "config": {}},
                {"id": "n3", "type": "end",    "x": 100, "y": 350, "config": {}},
            ],
            "edges": [
                {"from": "n1", "to": "n2", "type": "default"},
                {"from": "n2", "to": "n3", "type": "default"},
            ],
        },
    }
    create_r = api_client.post("/api/sequences", json=payload, headers=auth_headers)
    seq_id = create_r.json()["id"]

    r = api_client.get(f"/api/sequences/{seq_id}", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "sequence" in data
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 3
    assert len(data["edges"]) == 2


# ─────────────────────────────────────────────────────────────────────────────
# G4: PUT /api/sequences/{id} replaces canvas
# ─────────────────────────────────────────────────────────────────────────────

def test_update_sequence_replaces_canvas_json(api_client, auth_headers):
    create_r = api_client.post("/api/sequences", json={
        "name": "Seq Update Test",
        "canvas_json": {"nodes": [{"id": "n1", "type": "start", "x": 0, "y": 0, "config": {}}], "edges": []},
    }, headers=auth_headers)
    seq_id = create_r.json()["id"]

    update_r = api_client.put(f"/api/sequences/{seq_id}", json={
        "name": "Seq Updated",
        "canvas_json": {
            "nodes": [
                {"id": "n1", "type": "start", "x": 50, "y": 50, "config": {}},
                {"id": "n2", "type": "delay", "x": 50, "y": 180, "config": {"delay_days": 5}},
            ],
            "edges": [{"from": "n1", "to": "n2", "type": "default"}],
        },
    }, headers=auth_headers)
    assert update_r.status_code == 200

    get_r = api_client.get(f"/api/sequences/{seq_id}", headers=auth_headers)
    data = get_r.json()
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
    assert data["sequence"]["name"] == "Seq Updated"


# ─────────────────────────────────────────────────────────────────────────────
# G5: GET /api/sequences returns array (excludes archived)
# ─────────────────────────────────────────────────────────────────────────────

def test_list_sequences_returns_array(api_client, auth_headers):
    for i in range(3):
        api_client.post("/api/sequences", json={
            "name": f"Seq {i}", "canvas_json": {"nodes": [], "edges": []},
        }, headers=auth_headers)

    r = api_client.get("/api/sequences", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "sequences" in data
    assert isinstance(data["sequences"], list)
    assert len(data["sequences"]) >= 3


# ─────────────────────────────────────────────────────────────────────────────
# G6: Frontend file existence
# ─────────────────────────────────────────────────────────────────────────────

def test_sequence_canvas_file_exists():
    path = COMPONENTS / "sequence_canvas.js"
    assert path.is_file(), "sequence_canvas.js not found"


def test_sequence_canvas_exposes_singleton():
    """sequence_canvas.js must expose window.sequenceCanvas singleton."""
    content = _read(COMPONENTS / "sequence_canvas.js")
    assert "window.sequenceCanvas" in content
    assert "window.HermesSequenceCanvas" in content


# ─────────────────────────────────────────────────────────────────────────────
# G7: index.html page section + nav item
# ─────────────────────────────────────────────────────────────────────────────

def test_page_sequences_added_to_index_html():
    content = _read(INDEX_HTML)
    assert 'id="page-sequences"' in content, "page-sequences div not found in index.html"


def test_sequences_nav_in_outreach_group():
    content = _read(INDEX_HTML)
    assert 'data-page="sequences"' in content, "sequences nav item not found"
    assert "navigate('sequences')" in content, "navigate('sequences') call not found"


# ─────────────────────────────────────────────────────────────────────────────
# G8: app.js PAGE_TO_GROUP + titles + navigate case
# ─────────────────────────────────────────────────────────────────────────────

def test_sequences_page_title_in_app_js():
    content = _read(APP_JS)
    assert "sequences: 'Sequences'" in content or 'sequences: "Sequences"' in content, \
        "sequences title not found in app.js titles map"


def test_sequences_navigate_case_in_app_js():
    content = _read(APP_JS)
    assert "page === 'sequences'" in content or 'page === "sequences"' in content, \
        "sequences navigate case not found in app.js"
