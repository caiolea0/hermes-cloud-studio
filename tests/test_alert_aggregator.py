"""F.7 C4 — alert_aggregator unit tests (8 tests, temp SQLite DB).

All tests use isolated temp DBs — no production state touched.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.alert_aggregator import (
    _dedup_errors,
    _error_signature,
    aggregate_bugs_24h,
    render_markdown_summary,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path) -> Path:
    """Empty temp DB (tables created per-test)."""
    return tmp_path / "test_aggregator.db"


@pytest.fixture
def db_with_skill_runs(tmp_db) -> Path:
    """Temp DB with skill_runs table and 3 failed rows."""
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(
        """CREATE TABLE skill_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name TEXT,
            status TEXT,
            error_message TEXT,
            created_at TEXT
        )"""
    )
    conn.executemany(
        "INSERT INTO skill_runs (skill_name, status, error_message, created_at) VALUES (?,?,?,?)",
        [
            ("linkedin-engagement", "failed", "timeout after 30s", "2099-01-01 08:00:00"),
            ("linkedin-engagement", "failed", "timeout after 30s", "2099-01-01 08:01:00"),
            ("linkedin-connector", "failed", "rate limit hit", "2099-01-01 08:02:00"),
        ],
    )
    conn.commit()
    conn.close()
    return tmp_db


@pytest.fixture
def db_with_errors_inbox(tmp_db) -> Path:
    """Temp DB with errors_inbox table and 2 cobaia-category rows."""
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(
        """CREATE TABLE errors_inbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            severity TEXT,
            title TEXT,
            message TEXT,
            sentry_issue_id TEXT,
            status TEXT,
            resolved_by TEXT,
            resolved_at TEXT,
            metadata_json TEXT,
            created_at TEXT
        )"""
    )
    conn.executemany(
        "INSERT INTO errors_inbox (category, severity, title, message, status, created_at) "
        "VALUES (?,?,?,?,?,?)",
        [
            ("cobaia", "error", "warmup failed", "CobaiaError: day advance failed", "open", "2099-01-01 07:00:00"),
            ("linkedin-campaign", "warning", "rate throttle", "429 Too Many Requests", "open", "2099-01-01 07:30:00"),
        ],
    )
    conn.commit()
    conn.close()
    return tmp_db


@pytest.fixture
def db_with_mcp_calls(tmp_db) -> Path:
    """Temp DB with mcp_calls table and 1 error row with brain-f7 requester."""
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(
        """CREATE TABLE mcp_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT,
            error TEXT,
            requester TEXT,
            created_at TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO mcp_calls (tool_name, error, requester, created_at) VALUES (?,?,?,?)",
        ("linkedin_viewer", "connection refused", "brain-f7-cobaia", "2099-01-01 09:00:00"),
    )
    conn.commit()
    conn.close()
    return tmp_db


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_aggregate_bugs_24h_groups_categories(db_with_skill_runs):
    """aggregate_bugs_24h groups by source category correctly."""
    data = aggregate_bugs_24h(db=db_with_skill_runs, hours=9999)
    assert data["total"] == 3
    assert data["by_category"]["skill_runs"] == 3
    assert data["by_category"].get("errors_inbox", 0) == 0


def test_aggregate_bugs_24h_dedups_signature(db_with_skill_runs):
    """Two rows with same error message + skill → 1 unique signature, count=2."""
    data = aggregate_bugs_24h(db=db_with_skill_runs, hours=9999)
    # "timeout after 30s" from linkedin-engagement appears twice → deduped to 1
    sigs_engagement = [
        e for e in data["top_errors"]
        if e.get("category") == "linkedin-engagement" and e.get("count", 0) == 2
    ]
    assert len(sigs_engagement) == 1, f"Expected 1 deduped engagement error, got: {data['top_errors']}"


def test_aggregate_bugs_24h_empty_db_returns_zero(tmp_db):
    """Empty (non-existent) DB returns zero totals without crashing."""
    data = aggregate_bugs_24h(db=tmp_db, hours=24)
    assert data["total"] == 0
    assert data["unique"] == 0
    assert isinstance(data["generated_at"], str)


def test_aggregate_bugs_24h_all_three_sources(tmp_path):
    """All 3 sources (skill_runs + errors_inbox + mcp_calls) are queried."""
    db = tmp_path / "combined.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE skill_runs (id INTEGER PRIMARY KEY, skill_name TEXT, "
        "status TEXT, error_message TEXT, created_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE errors_inbox (id INTEGER PRIMARY KEY, category TEXT, severity TEXT, "
        "title TEXT, message TEXT, status TEXT, created_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE mcp_calls (id INTEGER PRIMARY KEY, tool_name TEXT, "
        "error TEXT, requester TEXT, created_at TEXT)"
    )
    conn.execute("INSERT INTO skill_runs VALUES (1,'skill_a','failed','err1','2099-01-01 01:00:00')")
    conn.execute("INSERT INTO errors_inbox VALUES (2,'cobaia','error','t','msg1','open','2099-01-01 02:00:00')")
    conn.execute("INSERT INTO mcp_calls VALUES (3,'tool_a','err_mcp','brain-f7-cobaia','2099-01-01 03:00:00')")
    conn.commit()
    conn.close()

    data = aggregate_bugs_24h(db=db, hours=9999)
    assert data["total"] == 3
    assert set(data["by_category"].keys()) == {"skill_runs", "errors_inbox", "mcp_calls"}


def test_render_markdown_summary_structured():
    """render_markdown_summary returns structured markdown with required sections."""
    sample = {
        "account_handle": "test-cobaia",
        "hours": 24,
        "total": 5,
        "unique": 3,
        "generated_at": "2099-01-01T09:00:00+00:00",
        "by_category": {"skill_runs": 3, "errors_inbox": 2},
        "top_errors": [
            {
                "signature": "abc123",
                "source": "skill_runs",
                "category": "linkedin-engagement",
                "count": 3,
                "message": "timeout error",
                "first_seen": "2099-01-01 07:00:00",
                "last_seen": "2099-01-01 08:00:00",
            }
        ],
        "trace_samples": [
            {
                "signature": "abc123",
                "source": "skill_runs",
                "category": "linkedin-engagement",
                "count": 3,
                "message": "timeout error",
                "first_seen": "2099-01-01 07:00:00",
            }
        ],
        "timeline": [],
    }
    md = render_markdown_summary(sample)
    assert "## Hermes Cobaia Bug Export" in md
    assert "test-cobaia" in md
    assert "### Por categoria" in md
    assert "skill_runs" in md
    assert "### Top erros" in md
    assert "linkedin-engagement" in md
    assert "### Trace samples" in md
    assert "cole nesta sessao claude" in md.lower()


def test_dedup_errors_counts_correctly():
    """_dedup_errors groups identical messages and counts occurrences."""
    rows = [
        {"source": "skill_runs", "message": "timeout", "category": "skill_a", "created_at": "2099-01-01 01:00"},
        {"source": "skill_runs", "message": "timeout", "category": "skill_a", "created_at": "2099-01-01 02:00"},
        {"source": "skill_runs", "message": "other error", "category": "skill_b", "created_at": "2099-01-01 03:00"},
    ]
    result = _dedup_errors(rows)
    assert len(result) == 2
    by_cat = {r["category"]: r["count"] for r in result}
    assert by_cat["skill_a"] == 2
    assert by_cat["skill_b"] == 1


def test_error_signature_consistent():
    """Same inputs produce identical signature; different inputs differ."""
    sig_a = _error_signature("timeout", "skill_runs", "skill_a")
    sig_b = _error_signature("timeout", "skill_runs", "skill_a")
    sig_c = _error_signature("other", "skill_runs", "skill_a")
    assert sig_a == sig_b
    assert sig_a != sig_c
    assert len(sig_a) == 12


def test_aggregate_bugs_missing_tables_returns_graceful(tmp_db):
    """DB exists but without expected tables → returns zero, no exception."""
    tmp_db.touch()
    data = aggregate_bugs_24h(db=tmp_db, hours=24)
    assert data["total"] == 0
    assert data["by_category"] == {}
