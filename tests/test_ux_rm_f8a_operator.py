"""
UX-RM-F8-A — Cobaia Operator Mode: layout + day countdown + today's queue + KPI hero.
Tests: file existence, API endpoint, content patterns for WCAG/localStorage/tablist/KPI.
Gates: G1 BLACKLIST R2 INTACTO, G2 pytest 392+ PASS, G3-G6 functional gates.
"""
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).parent.parent
COMPONENTS = ROOT / "dashboard" / "components"


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


# ─────────────────────────────────────────────────────────────────────────────
# G1: File existence (3 new components)
# ─────────────────────────────────────────────────────────────────────────────

def test_cobaia_operator_file_exists():
    path = COMPONENTS / "cobaia_operator.js"
    assert path.is_file(), "cobaia_operator.js not found"


def test_cobaia_day_countdown_file_exists():
    path = COMPONENTS / "cobaia_day_countdown.js"
    assert path.is_file(), "cobaia_day_countdown.js not found"


def test_cobaia_today_queue_file_exists():
    path = COMPONENTS / "cobaia_today_queue.js"
    assert path.is_file(), "cobaia_today_queue.js not found"


# ─────────────────────────────────────────────────────────────────────────────
# G2: API endpoint today-queue returns queue array
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client(tmp_path):
    """TestClient with isolated SQLite DB (no warmup_schedule rows → empty queue)."""
    db_path = tmp_path / "f8a_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE cobaia_warmup_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_handle TEXT NOT NULL DEFAULT 'cobaia',
            action TEXT NOT NULL,
            eta TEXT NOT NULL,
            description TEXT,
            completed INTEGER NOT NULL DEFAULT 0,
            skipped INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    )
    conn.commit()
    conn.close()

    def _fake_get_db():
        c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c

    with patch("api.cobaia.get_db", _fake_get_db), \
         patch("core.state.get_db", _fake_get_db):
        from server import app
        yield TestClient(app)


@pytest.fixture
def auth_headers():
    from core.state import AUTH_TOKEN
    return {"X-Hermes-Token": AUTH_TOKEN}


def test_today_queue_endpoint_returns_queue_array(api_client, auth_headers):
    """GET /api/linkedin/cobaia/today-queue → 200 with queue list."""
    r = api_client.get("/api/linkedin/cobaia/today-queue", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "queue" in data, "response must have 'queue' key"
    assert isinstance(data["queue"], list), "'queue' must be a list"


def test_today_queue_endpoint_empty_when_no_rows(api_client, auth_headers):
    """Empty DB → queue is []."""
    r = api_client.get("/api/linkedin/cobaia/today-queue", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["queue"] == []


# ─────────────────────────────────────────────────────────────────────────────
# G3: localStorage persistence
# ─────────────────────────────────────────────────────────────────────────────

def test_operator_mode_localstorage_persists():
    """cobaia_operator.js must read/write localStorage key 'hermes.cobaia.mode'."""
    content = _read(COMPONENTS / "cobaia_operator.js")
    assert "hermes.cobaia.mode" in content, "localStorage key 'hermes.cobaia.mode' not found"
    assert "localStorage.setItem" in content, "localStorage.setItem not found"
    assert "localStorage.getItem" in content, "localStorage.getItem not found"


# ─────────────────────────────────────────────────────────────────────────────
# G4: Mode toggle role=tablist + aria-selected
# ─────────────────────────────────────────────────────────────────────────────

def test_mode_toggle_role_tablist():
    """Operator layout must include role=tablist with aria-selected tabs."""
    content = _read(COMPONENTS / "cobaia_operator.js")
    assert 'role="tablist"' in content, 'tablist role missing in cobaia_operator.js'
    assert 'role="tab"' in content, 'tab role missing in cobaia_operator.js'
    assert 'aria-selected' in content, 'aria-selected attribute missing from tabs'


# ─────────────────────────────────────────────────────────────────────────────
# G5: KPI hero mounts CobaiaKpiCards into op-kpi-mount
# ─────────────────────────────────────────────────────────────────────────────

def test_kpi_hero_mounts_kpi_cards():
    """cobaia_operator.js must mount CobaiaKpiCards into op-kpi-mount container."""
    content = _read(COMPONENTS / "cobaia_operator.js")
    assert "CobaiaKpiCards" in content, "CobaiaKpiCards not referenced in operator"
    assert "op-kpi-mount" in content, "op-kpi-mount container not found in operator"


# ─────────────────────────────────────────────────────────────────────────────
# G6: Day countdown progressbar WCAG
# ─────────────────────────────────────────────────────────────────────────────

def test_day_countdown_progressbar_aria():
    """cobaia_day_countdown.js must use progressbar role with aria-valuenow/max."""
    content = _read(COMPONENTS / "cobaia_day_countdown.js")
    assert "progressbar" in content, 'role=progressbar missing in cobaia_day_countdown.js'
    assert "aria-valuenow" in content, "aria-valuenow missing"
    assert "aria-valuemax" in content, "aria-valuemax missing"


# ─────────────────────────────────────────────────────────────────────────────
# G7: index.html uses cobaia-page-container + new scripts
# ─────────────────────────────────────────────────────────────────────────────

def test_index_html_uses_operator_container():
    """index.html cobaia page must use cobaia-page-container (dynamic mount point)."""
    html = _read(ROOT / "dashboard" / "index.html")
    assert "cobaia-page-container" in html, "cobaia-page-container not found in index.html"
    assert "cobaia_operator.js" in html, "cobaia_operator.js not in index.html scripts"
    assert "cobaia_day_countdown.js" in html, "cobaia_day_countdown.js not in index.html"
    assert "cobaia_today_queue.js" in html, "cobaia_today_queue.js not in index.html"
