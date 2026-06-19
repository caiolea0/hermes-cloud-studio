"""UX-RM-F6-C — Tests: sequence orchestration + scheduling + dry-run.

Gate: +12 tests (G2: total 496+).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import types
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

# ─── Minimal FastAPI app for testing sequences ────────────────────────────────

def _make_app(tmp_db: str):
    """Build a minimal FastAPI app with sequences router, using tmp_db."""
    from fastapi import FastAPI
    import core.state as state_mod

    def _get_test_db():
        conn = sqlite3.connect(tmp_db)
        conn.row_factory = sqlite3.Row
        return conn

    original_get_db = state_mod.get_db
    state_mod.get_db = _get_test_db

    from api.sequences import router
    from api.templates import router as tpl_router

    app = FastAPI()
    app.include_router(router)
    app.include_router(tpl_router)
    yield app, _get_test_db

    state_mod.get_db = original_get_db


@pytest.fixture()
def seq_client(tmp_path):
    """TestClient wired to a temp SQLite DB."""
    db = str(tmp_path / "test.db")

    # pre-create prospects table so enroll can query it
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE IF NOT EXISTS prospects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_name TEXT, name TEXT, phone TEXT, website TEXT,
        city TEXT DEFAULT 'Cuiabá', category TEXT,
        firstName TEXT, lastName TEXT, fullName TEXT,
        company TEXT, jobTitle TEXT, industry TEXT,
        email TEXT, stage TEXT DEFAULT 'discovered', score INTEGER DEFAULT 0,
        has_website INTEGER DEFAULT 0, audit_summary TEXT,
        created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')),
        version INTEGER DEFAULT 1, last_synced_version INTEGER DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sequence_enrollments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prospect_id INTEGER NOT NULL,
        sequence_id TEXT NOT NULL DEFAULT 'default',
        current_step INTEGER NOT NULL DEFAULT 0,
        next_action_at TIMESTAMP NOT NULL,
        completed INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (prospect_id, sequence_id)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sequences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL DEFAULT 'owner',
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'draft',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sequence_nodes (
        id TEXT PRIMARY KEY,
        sequence_id INTEGER NOT NULL,
        node_type TEXT NOT NULL,
        channel TEXT,
        action_type TEXT,
        position_x REAL NOT NULL DEFAULT 0,
        position_y REAL NOT NULL DEFAULT 0,
        config_json TEXT NOT NULL DEFAULT '{}'
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sequence_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sequence_id INTEGER NOT NULL,
        from_node TEXT NOT NULL,
        to_node TEXT NOT NULL,
        edge_type TEXT NOT NULL DEFAULT 'default'
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL DEFAULT 'owner',
        name TEXT NOT NULL,
        channel TEXT NOT NULL,
        action_type TEXT,
        subject TEXT,
        body TEXT NOT NULL,
        category TEXT DEFAULT 'intro',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""")
    conn.commit()
    conn.close()

    from fastapi import FastAPI
    import core.state as state_mod
    import api.sequences as seq_mod
    import api.templates as tpl_mod

    def _get_test_db():
        c = sqlite3.connect(db)
        c.row_factory = sqlite3.Row
        return c

    # Patch both the state module AND the already-imported local references
    old_state = state_mod.get_db
    old_seq = seq_mod.get_db
    old_tpl = tpl_mod.get_db
    state_mod.get_db = _get_test_db
    seq_mod.get_db = _get_test_db
    tpl_mod.get_db = _get_test_db

    # Patch ws_manager to avoid actual websocket calls
    mock_ws = MagicMock()
    mock_ws.broadcast = AsyncMock(return_value=None)
    old_ws = getattr(state_mod, "ws_manager", None)
    state_mod.ws_manager = mock_ws

    from api.sequences import router
    from api.templates import router as tpl_router

    app = FastAPI()
    app.include_router(router)
    app.include_router(tpl_router)

    with TestClient(app) as client:
        yield client, db

    state_mod.get_db = old_state
    seq_mod.get_db = old_seq
    tpl_mod.get_db = old_tpl
    if old_ws is not None:
        state_mod.ws_manager = old_ws


def _create_sequence(client, status="draft") -> int:
    r = client.post("/api/sequences", json={"name": "Test Seq"})
    assert r.status_code == 201
    seq_id = r.json()["id"]
    if status == "active":
        r2 = client.put(f"/api/sequences/{seq_id}", json={"status": "active"})
        assert r2.status_code == 200
    return seq_id


def _add_node(db, seq_id, node_type="action", channel="linkedin", action_type="message", y=0.0):
    import uuid
    nid = str(uuid.uuid4())[:8]
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO sequence_nodes (id, sequence_id, node_type, channel, action_type, position_y, config_json) "
        "VALUES (?,?,?,?,?,?,?)",
        (nid, seq_id, node_type, channel, action_type, y, json.dumps({"delay_days": 2} if node_type == "delay" else {})),
    )
    conn.commit()
    conn.close()
    return nid


def _add_edge(db, seq_id, from_node, to_node, edge_type="default"):
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO sequence_edges (sequence_id, from_node, to_node, edge_type) VALUES (?,?,?,?)",
        (seq_id, from_node, to_node, edge_type),
    )
    conn.commit()
    conn.close()


# ─── Item 1 Tests: Enrollment ─────────────────────────────────────────────────

def test_enroll_creates_sequence_enrollments(seq_client):
    client, db = seq_client
    seq_id = _create_sequence(client, status="active")
    _add_node(db, seq_id, node_type="action", y=10.0)

    r = client.post(f"/api/sequences/{seq_id}/enroll", json={"prospect_ids": [1, 2, 3]})
    assert r.status_code == 201
    data = r.json()
    assert len(data["enrolled"]) == 3
    # Check DB
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT * FROM sequence_enrollments WHERE sequence_id=?", (str(seq_id),)).fetchall()
    conn.close()
    assert len(rows) == 3


def test_enroll_rejects_draft_sequence(seq_client):
    client, db = seq_client
    seq_id = _create_sequence(client, status="draft")

    r = client.post(f"/api/sequences/{seq_id}/enroll", json={"prospect_ids": [1]})
    assert r.status_code == 400
    assert "active" in r.json()["detail"].lower()


def test_enroll_computes_next_action_at(seq_client):
    client, db = seq_client
    seq_id = _create_sequence(client, status="active")
    # Add delay then action
    _add_node(db, seq_id, node_type="delay", y=5.0)
    _add_node(db, seq_id, node_type="action", y=10.0)

    r = client.post(f"/api/sequences/{seq_id}/enroll", json={"prospect_ids": [10]})
    assert r.status_code == 201
    data = r.json()
    next_at_str = data["next_action_at"]
    # Should be a valid datetime string
    dt = datetime.strptime(next_at_str, "%Y-%m-%d %H:%M:%S")
    # Should be tomorrow or later (delay_days=2 from delay node)
    # Compare date only to avoid timezone offset issues
    today = datetime.utcnow().date()
    assert dt.date() > today


def test_get_due_sequence_steps_joins_nodes(tmp_path):
    """_get_due_sequence_steps should JOIN sequence_nodes for node details."""
    import asyncio
    import sqlite3 as sl

    db = str(tmp_path / "orch.db")
    conn = sl.connect(db)
    conn.execute("""CREATE TABLE IF NOT EXISTS sequence_enrollments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prospect_id INTEGER NOT NULL,
        sequence_id TEXT NOT NULL DEFAULT 'default',
        current_step TEXT NOT NULL DEFAULT '0',
        next_action_at TIMESTAMP NOT NULL,
        completed INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sequence_nodes (
        id TEXT PRIMARY KEY,
        sequence_id INTEGER,
        node_type TEXT,
        channel TEXT,
        action_type TEXT,
        position_x REAL DEFAULT 0,
        position_y REAL DEFAULT 0,
        config_json TEXT DEFAULT '{}'
    )""")
    # Insert node
    conn.execute("INSERT INTO sequence_nodes (id, sequence_id, node_type, channel, action_type) VALUES ('n1', 1, 'action', 'linkedin', 'message')")
    # Insert enrollment pointing at node n1 with past due date
    conn.execute("INSERT INTO sequence_enrollments (prospect_id, sequence_id, current_step, next_action_at) VALUES (5, '1', 'n1', datetime('now', '-1 hour'))")
    conn.commit()
    conn.close()

    # Patch DB_PATH in orchestrator
    import daemon.orchestrator as orch_mod
    old_path = orch_mod.DB_PATH
    orch_mod.DB_PATH = tmp_path / "orch.db"
    try:
        daemon = object.__new__(orch_mod.HermesDaemon)
        steps = asyncio.run(daemon._get_due_sequence_steps())
        assert len(steps) == 1
        step = steps[0]
        assert step["node_type"] == "action"
        assert step["channel"] == "linkedin"
    finally:
        orch_mod.DB_PATH = old_path


def test_advance_enrollment_completes_on_end_node(tmp_path):
    """_advance_enrollment marks completed=1 when next node is 'end'."""
    import asyncio
    import sqlite3 as sl

    db = str(tmp_path / "ae.db")
    conn = sl.connect(db)
    conn.execute("""CREATE TABLE IF NOT EXISTS sequence_enrollments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prospect_id INTEGER NOT NULL,
        sequence_id TEXT NOT NULL DEFAULT 'default',
        current_step TEXT NOT NULL DEFAULT '0',
        next_action_at TIMESTAMP NOT NULL DEFAULT (datetime('now')),
        completed INTEGER NOT NULL DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sequence_nodes (
        id TEXT PRIMARY KEY,
        sequence_id INTEGER,
        node_type TEXT,
        channel TEXT,
        action_type TEXT,
        position_x REAL DEFAULT 0,
        position_y REAL DEFAULT 0,
        config_json TEXT DEFAULT '{}'
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sequence_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sequence_id INTEGER,
        from_node TEXT,
        to_node TEXT,
        edge_type TEXT DEFAULT 'default'
    )""")
    conn.execute("INSERT INTO sequence_enrollments (prospect_id, sequence_id, current_step, next_action_at) VALUES (1, '1', 'action1', datetime('now'))")
    conn.execute("INSERT INTO sequence_nodes (id, sequence_id, node_type) VALUES ('action1', 1, 'action')")
    conn.execute("INSERT INTO sequence_nodes (id, sequence_id, node_type) VALUES ('end1', 1, 'end')")
    conn.execute("INSERT INTO sequence_edges (sequence_id, from_node, to_node) VALUES (1, 'action1', 'end1')")
    conn.commit()
    conn.close()

    import daemon.orchestrator as orch_mod
    old_path = orch_mod.DB_PATH
    orch_mod.DB_PATH = tmp_path / "ae.db"
    try:
        daemon = object.__new__(orch_mod.HermesDaemon)
        asyncio.run(
            daemon._advance_enrollment(1, "1", "action1")
        )
        conn2 = sl.connect(db)
        row = conn2.execute("SELECT completed FROM sequence_enrollments WHERE id=1").fetchone()
        conn2.close()
        assert row[0] == 1
    finally:
        orch_mod.DB_PATH = old_path


def test_advance_enrollment_follows_edges(tmp_path):
    """_advance_enrollment advances current_step to next action node."""
    import asyncio
    import sqlite3 as sl

    db = str(tmp_path / "ae2.db")
    conn = sl.connect(db)
    for sql in [
        """CREATE TABLE sequence_enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, prospect_id INTEGER,
            sequence_id TEXT, current_step TEXT, next_action_at TIMESTAMP,
            completed INTEGER DEFAULT 0)""",
        """CREATE TABLE sequence_nodes (id TEXT PRIMARY KEY, sequence_id INTEGER,
            node_type TEXT, channel TEXT, action_type TEXT,
            position_x REAL DEFAULT 0, position_y REAL DEFAULT 0,
            config_json TEXT DEFAULT '{}')""",
        """CREATE TABLE sequence_edges (id INTEGER PRIMARY KEY AUTOINCREMENT,
            sequence_id INTEGER, from_node TEXT, to_node TEXT, edge_type TEXT DEFAULT 'default')""",
    ]:
        conn.execute(sql)
    conn.execute("INSERT INTO sequence_enrollments VALUES (1, 1, '1', 'n1', datetime('now'), 0)")
    conn.execute("INSERT INTO sequence_nodes (id, sequence_id, node_type) VALUES ('n1', 1, 'action')")
    conn.execute("INSERT INTO sequence_nodes (id, sequence_id, node_type, config_json) VALUES ('n2', 1, 'action', '{}')")
    conn.execute("INSERT INTO sequence_edges (sequence_id, from_node, to_node) VALUES (1, 'n1', 'n2')")
    conn.commit()
    conn.close()

    import daemon.orchestrator as orch_mod
    old_path = orch_mod.DB_PATH
    orch_mod.DB_PATH = tmp_path / "ae2.db"
    try:
        daemon = object.__new__(orch_mod.HermesDaemon)
        asyncio.run(
            daemon._advance_enrollment(1, "1", "n1")
        )
        conn2 = sl.connect(db)
        row = conn2.execute("SELECT current_step, completed FROM sequence_enrollments WHERE id=1").fetchone()
        conn2.close()
        assert row[1] == 0  # not completed
        assert row[0] == "n2"
    finally:
        orch_mod.DB_PATH = old_path


# ─── Item 2 Tests: Scheduler ──────────────────────────────────────────────────

def test_send_scheduler_business_hours():
    """next_send_window returns a time within 09:00-19:00."""
    from core.send_scheduler import next_send_window
    # Use a Monday at 06:00 (before business hours)
    from datetime import datetime
    base = datetime(2026, 6, 22, 6, 0, 0)  # Monday 06:00
    result = next_send_window(base)
    assert result.hour == 9
    assert result.minute == 0


def test_send_scheduler_skips_weekend():
    """next_send_window skips Saturday and Sunday."""
    from core.send_scheduler import next_send_window
    from datetime import datetime
    # Saturday 2026-06-20
    base = datetime(2026, 6, 20, 10, 0, 0)  # Saturday
    result = next_send_window(base)
    # Should advance to Monday (weekday 0)
    assert result.weekday() < 5  # Mon-Fri


def test_send_scheduler_jitter_within_max():
    """jitter_send_time offset is <= max_minutes."""
    from core.send_scheduler import jitter_send_time, next_send_window
    from datetime import datetime
    base = datetime(2026, 6, 23, 10, 0, 0)  # Monday
    slot = next_send_window(base)
    for _ in range(50):
        jittered = jitter_send_time(slot, max_minutes=30)
        diff_minutes = (jittered - slot).total_seconds() / 60
        assert 0 <= diff_minutes <= 30


# ─── Item 3 Tests: Dry-Run ────────────────────────────────────────────────────

def test_dry_run_returns_timeline(seq_client):
    client, db = seq_client
    seq_id = _create_sequence(client, status="draft")
    _add_node(db, seq_id, node_type="delay", y=5.0)
    _add_node(db, seq_id, node_type="action", channel="linkedin", action_type="message", y=10.0)

    r = client.post(f"/api/sequences/{seq_id}/dry-run")
    assert r.status_code == 200
    data = r.json()
    assert "timeline" in data
    assert data["actual_send"] is False
    # Should have at least one action step
    actions = [t for t in data["timeline"] if t["action"] != "unknown" or t["channel"] != "unknown"]
    assert len(data["timeline"]) >= 1


def test_dry_run_renders_templates(seq_client):
    client, db = seq_client
    seq_id = _create_sequence(client, status="active")

    # Create a template first
    tr = client.post("/api/templates", json={
        "name": "Test Template",
        "channel": "linkedin",
        "action_type": "message",
        "body": "Oi {{firstName}}, bem-vindo!",
    })
    assert tr.status_code == 201
    tpl_id = tr.json()["id"]

    # Add action node with template_id
    nid = _add_node(db, seq_id, node_type="action", channel="linkedin", action_type="message", y=5.0)
    # Update config_json with template_id
    conn = sqlite3.connect(db)
    conn.execute("UPDATE sequence_nodes SET config_json=? WHERE id=?",
                 (json.dumps({"template_id": tpl_id}), nid))
    conn.commit()
    conn.close()

    r = client.post(f"/api/sequences/{seq_id}/dry-run")
    assert r.status_code == 200
    tl = r.json()["timeline"]
    assert len(tl) >= 1
    # The rendered_preview should contain sample firstName substituted
    rendered = tl[0].get("rendered_preview") or ""
    assert "João" in rendered or "[firstName]" in rendered  # fallback if no match


def test_dry_run_no_actual_send(seq_client, monkeypatch):
    """Dry-run must never trigger HERMES_CHANNEL_SEND_ENABLED path."""
    client, db = seq_client
    seq_id = _create_sequence(client, status="active")
    _add_node(db, seq_id, node_type="action", channel="linkedin", action_type="message", y=5.0)

    # Even if send is enabled, dry-run must return actual_send=False
    monkeypatch.setenv("HERMES_CHANNEL_SEND_ENABLED", "1")

    r = client.post(f"/api/sequences/{seq_id}/dry-run")
    assert r.status_code == 200
    assert r.json()["actual_send"] is False
