"""
UX-RM-F8-B — Polish: mobile responsive + brain queue badge + rate-limit gauge +
sentry banner + panic inline + test fixture fix.

Gates: G1 BLACKLIST R2 INTACTO, G2 pytest 396+ PASS (388 baseline + 8 new) + ZERO ERRORs,
G3-G10 functional gates.
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
STYLES = ROOT / "dashboard" / "styles.css"


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixture (also fixes F8-A today-queue tests if needed)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client_f8b(tmp_path):
    """TestClient with isolated SQLite DB containing cobaia_warmup_schedule table."""
    db_path = tmp_path / "f8b_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cobaia_warmup_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_handle TEXT NOT NULL DEFAULT 'cobaia',
            action TEXT NOT NULL,
            eta TEXT NOT NULL,
            description TEXT,
            completed INTEGER NOT NULL DEFAULT 0,
            skipped INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS brain_runs (
            id TEXT PRIMARY KEY,
            intent TEXT NOT NULL,
            context_json TEXT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP,
            final_state TEXT,
            final_result TEXT,
            total_latency_ms INTEGER,
            total_cost_credits REAL DEFAULT 0.0,
            confidence_score REAL,
            requester TEXT,
            otel_trace_id TEXT
        );
        """
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


# ─────────────────────────────────────────────────────────────────────────────
# ITEM 0 — Fixture applies migration (covers F8-A scenario)
# ─────────────────────────────────────────────────────────────────────────────

def test_today_queue_fixture_applies_migration(api_client_f8b, auth_headers):
    """Fixture creates cobaia_warmup_schedule table — today-queue returns 200."""
    r = api_client_f8b.get("/api/linkedin/cobaia/today-queue", headers=auth_headers)
    assert r.status_code == 200, f"today-queue failed: {r.text}"
    data = r.json()
    assert "queue" in data, "response must have 'queue' key"


def test_today_queue_returns_empty_when_no_rows(api_client_f8b, auth_headers):
    """Empty DB → today-queue returns empty list."""
    r = api_client_f8b.get("/api/linkedin/cobaia/today-queue", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["queue"] == []


# ─────────────────────────────────────────────────────────────────────────────
# ITEM 2 — Brain Queue Stats endpoint
# ─────────────────────────────────────────────────────────────────────────────

def test_brain_queue_stats_endpoint_returns_counts(api_client_f8b, auth_headers):
    """GET /api/brain/queue-stats returns pending + processing + decided_today."""
    r = api_client_f8b.get("/api/brain/queue-stats", headers=auth_headers)
    assert r.status_code == 200, f"queue-stats failed: {r.text}"
    data = r.json()
    assert "pending" in data, "response must have 'pending'"
    assert "processing" in data, "response must have 'processing'"
    assert "decided_today" in data, "response must have 'decided_today'"
    assert isinstance(data["pending"], int), "'pending' must be int"
    assert isinstance(data["processing"], int), "'processing' must be int"
    assert isinstance(data["decided_today"], int), "'decided_today' must be int"


def test_brain_queue_badge_file_exists():
    """cobaia_brain_queue_badge.js must exist."""
    path = COMPONENTS / "cobaia_brain_queue_badge.js"
    assert path.is_file(), "cobaia_brain_queue_badge.js not found"


def test_brain_queue_badge_role_status():
    """Brain queue badge must use role=status + aria-label."""
    content = _read(COMPONENTS / "cobaia_brain_queue_badge.js")
    assert "role" in content and "status" in content, "role=status missing"
    assert "aria-label" in content, "aria-label missing from brain queue badge"


# ─────────────────────────────────────────────────────────────────────────────
# ITEM 3 — Rate-Limit Gauge
# ─────────────────────────────────────────────────────────────────────────────

def test_rate_limit_gauge_file_exists():
    """cobaia_rate_limit_gauge.js must exist."""
    path = COMPONENTS / "cobaia_rate_limit_gauge.js"
    assert path.is_file(), "cobaia_rate_limit_gauge.js not found"


def test_rate_limit_gauge_progressbar_aria():
    """Rate-limit gauge must have progressbar role + aria-valuenow + aria-valuemax."""
    content = _read(COMPONENTS / "cobaia_rate_limit_gauge.js")
    assert "progressbar" in content, "role=progressbar missing in rate_limit_gauge.js"
    assert "aria-valuenow" in content, "aria-valuenow missing"
    assert "aria-valuemax" in content, "aria-valuemax missing"


# ─────────────────────────────────────────────────────────────────────────────
# ITEM 4 — Sentry Banner
# ─────────────────────────────────────────────────────────────────────────────

def test_sentry_banner_file_exists():
    """cobaia_sentry_banner.js must exist."""
    path = COMPONENTS / "cobaia_sentry_banner.js"
    assert path.is_file(), "cobaia_sentry_banner.js not found"


def test_sentry_banner_dismiss_localStorage_key():
    """Sentry banner must use localStorage key 'hermes.sentry_banner.dismissed_until'."""
    content = _read(COMPONENTS / "cobaia_sentry_banner.js")
    assert "hermes.sentry_banner.dismissed_until" in content, "dismiss key missing"
    assert "localStorage.setItem" in content, "localStorage.setItem missing"


def test_sentry_banner_role_alert():
    """Sentry banner must use role=alert for screen reader announcement."""
    content = _read(COMPONENTS / "cobaia_sentry_banner.js")
    assert 'role' in content and 'alert' in content, "role=alert missing in sentry banner"
    assert 'aria-live' in content, "aria-live missing from sentry banner"


# ─────────────────────────────────────────────────────────────────────────────
# ITEM 1 — Mobile CSS breakpoints
# ─────────────────────────────────────────────────────────────────────────────

def test_mobile_breakpoints_in_styles_css():
    """styles.css must have @media max-width: 768px for cobaia operator."""
    content = _read(STYLES)
    assert "max-width: 768px" in content, "@media max-width: 768px breakpoint missing"
    assert "cobaia-operator-grid" in content, ".cobaia-operator-grid missing in CSS"


def test_mobile_480_breakpoint_in_styles_css():
    """styles.css must have @media max-width: 480px for op-kpis-hero single column."""
    content = _read(STYLES)
    assert "max-width: 480px" in content, "@media max-width: 480px breakpoint missing"


# ─────────────────────────────────────────────────────────────────────────────
# ITEM 5 — Inline Panic Confirm
# ─────────────────────────────────────────────────────────────────────────────

def test_panic_inline_in_operator():
    """cobaia_operator.js must include inline panic confirm with alertdialog + keyboard."""
    content = _read(COMPONENTS / "cobaia_operator.js")
    assert "op-panic-inline" in content, "op-panic-inline missing"
    assert "op-panic-confirm" in content, "op-panic-confirm missing"
    assert "alertdialog" in content, "role=alertdialog missing from inline panic"
    assert "Escape" in content, "Esc key handler missing from inline panic"


# ─────────────────────────────────────────────────────────────────────────────
# index.html — New scripts registered
# ─────────────────────────────────────────────────────────────────────────────

def test_index_html_has_f8b_scripts():
    """index.html must reference all 3 F8-B new component scripts."""
    html = _read(ROOT / "dashboard" / "index.html")
    assert "cobaia_brain_queue_badge.js" in html, "cobaia_brain_queue_badge.js not in index.html"
    assert "cobaia_rate_limit_gauge.js" in html, "cobaia_rate_limit_gauge.js not in index.html"
    assert "cobaia_sentry_banner.js" in html, "cobaia_sentry_banner.js not in index.html"
