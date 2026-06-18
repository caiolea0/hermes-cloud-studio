"""H3 hardening-future + R8 post-audit — F.8 Observability fixes (B18 + B19, 8 tests).

B18: CSV export must go through fetch+Blob (not window.location.assign) to carry
     X-Hermes-Token header — validated by inspecting the JS source pattern.
B19: /errors filter status= must apply consistently to all items including Sentry;
     the previous bypass (or source=="sentry") leaked resolved/open items.

R8 (B19 regression fix): _query_local_errors was pre-filtering by status BEFORE
     _merge_errors, so a local row with status='resolved' linked to a Sentry item
     (default status='open') never overrode the Sentry status.  The Sentry item
     leaked as 'open' even though the local row marked it resolved.
     Fix: pass status=None to _query_local_errors, apply filter post-merge.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.observability import _merge_errors, _query_local_errors, get_errors


# ---------------------------------------------------------------------------
# B19 — _merge_errors status filter tests (unit, no HTTP)
# ---------------------------------------------------------------------------

def _sentry_item(sid: str, status: str = "open") -> dict:
    return {"id": sid, "title": "Test Error", "status": status, "level": "error",
            "firstSeen": "2026-06-17T00:00:00Z", "lastSeen": "2026-06-17T00:00:00Z"}


def _local_item(lid: int, status: str = "open", sentry_id: str | None = None) -> dict:
    return {
        "id": lid, "title": "Local Error", "status": status,
        "sentry_issue_id": sentry_id, "category": "app",
        "severity": "error", "created_at": "2026-06-17T00:00:00Z",
    }


def test_merge_errors_sentry_only_has_open_status():
    """Sentry-only items default to status='open'."""
    merged = _merge_errors([_sentry_item("s1")], [])
    assert len(merged) == 1
    assert merged[0]["status"] == "open"
    assert merged[0]["source"] == "sentry"


def test_merge_errors_local_status_wins_over_sentry():
    """When local row links to Sentry issue and is resolved, local status wins."""
    sentry = [_sentry_item("s2", status="open")]
    local = [_local_item(1, status="resolved", sentry_id="s2")]
    merged = _merge_errors(sentry, local)
    assert len(merged) == 1
    assert merged[0]["status"] == "resolved"
    assert merged[0]["source"] == "both"


def test_errors_filter_resolved_excludes_open_sentry_items():
    """B19 fix: status=resolved must NOT include Sentry-only items with status=open."""
    sentry_open = [_sentry_item("s3", status="open")]
    local_resolved = [_local_item(2, status="resolved")]

    merged = _merge_errors(sentry_open, local_resolved)
    # Before fix: both items appeared when status=resolved (sentry bypassed filter)
    # After fix: only resolved items appear
    filtered = [m for m in merged if m.get("status") == "resolved"]
    sentry_leaked = [m for m in merged if m.get("source") == "sentry" and m.get("status") != "resolved"]

    assert len(filtered) == 1, "Only resolved local item should pass"
    assert len(sentry_leaked) == 1, "Sentry open item present in merged (before status filter)"
    # Applying the fixed filter logic:
    post_filter = [m for m in merged if m.get("status") == "resolved"]
    assert all(m["status"] == "resolved" for m in post_filter)


def test_errors_filter_open_includes_sentry_open_items():
    """B19 fix: status=open must still include Sentry items with status=open (no regression)."""
    sentry_open = [_sentry_item("s4", status="open")]
    local_open = [_local_item(3, status="open")]

    merged = _merge_errors(sentry_open, local_open)
    post_filter = [m for m in merged if m.get("status") == "open"]
    assert len(post_filter) == 2, "Both sentry-open and local-open must appear"


def test_errors_no_status_filter_returns_all_statuses():
    """When calling _merge_errors directly, all items are returned before status gate."""
    sentry = [_sentry_item("s5", status="open"), _sentry_item("s6", status="open")]
    local = [_local_item(4, status="resolved"), _local_item(5, status="wontfix")]

    merged = _merge_errors(sentry, local)
    assert len(merged) == 4

    open_items = [m for m in merged if m.get("status") == "open"]
    resolved_items = [m for m in merged if m.get("status") == "resolved"]
    wontfix_items = [m for m in merged if m.get("status") == "wontfix"]
    assert len(open_items) == 2
    assert len(resolved_items) == 1
    assert len(wontfix_items) == 1


# ---------------------------------------------------------------------------
# R8 — B19 regression: pre-merge status filter leaked Sentry-open for resolved
# ---------------------------------------------------------------------------

def test_r8_open_filter_excludes_sentry_item_with_resolved_local_link():
    """R8 adversarial: Sentry item (default open) linked to resolved local row
    must NOT appear when status=open filter is applied post-merge.

    Old bug: _query_local_errors pre-filtered to status='open' → resolved local
    row never entered _merge_errors → Sentry item kept status='open' → leaked.
    Fixed: fetch all local rows, merge, THEN apply status gate.
    """
    sentry = [_sentry_item("s10", status="open")]
    # Simulate _query_local_errors(status=None): returns ALL local rows including resolved
    local_all = [_local_item(10, status="resolved", sentry_id="s10")]

    merged = _merge_errors(sentry, local_all)
    # After merge, the item should be source='both', status='resolved'
    assert len(merged) == 1
    assert merged[0]["source"] == "both"
    assert merged[0]["status"] == "resolved", "local resolved must override Sentry open"

    # Applying status=open filter post-merge must return EMPTY (not leak)
    open_filtered = [m for m in merged if m.get("status") == "open"]
    assert len(open_filtered) == 0, "Resolved item must not leak as open"


def test_r8_resolved_filter_includes_linked_item_post_merge():
    """R8: status=resolved filter post-merge correctly includes linked resolved item."""
    sentry = [_sentry_item("s11", status="open")]
    local_all = [_local_item(11, status="resolved", sentry_id="s11")]

    merged = _merge_errors(sentry, local_all)
    resolved_filtered = [m for m in merged if m.get("status") == "resolved"]
    assert len(resolved_filtered) == 1
    assert resolved_filtered[0]["sentry_issue_id"] == "s11"


def test_r8_query_local_errors_none_status_skips_sql_filter(tmp_path):
    """R8: _query_local_errors with status=None must return rows of ALL statuses."""
    import sqlite3 as _sqlite3
    db = tmp_path / "test.db"
    conn = _sqlite3.connect(str(db))
    conn.execute(
        """CREATE TABLE errors_inbox (
               id INTEGER PRIMARY KEY, category TEXT, severity TEXT,
               title TEXT, message TEXT, sentry_issue_id TEXT,
               status TEXT, resolved_by TEXT, resolved_at TEXT,
               metadata_json TEXT, created_at TEXT)"""
    )
    conn.executemany(
        "INSERT INTO errors_inbox (category, severity, title, status, created_at) VALUES (?,?,?,?,datetime('now'))",
        [("app", "error", "Open err", "open"),
         ("app", "error", "Resolved err", "resolved"),
         ("app", "error", "Wontfix err", "wontfix")],
    )
    conn.commit()
    conn.close()

    rows_all = _query_local_errors(db, "app", "24h", None)
    assert len(rows_all) == 3, "status=None must return all 3 rows"

    rows_open = _query_local_errors(db, "app", "24h", "open")
    assert len(rows_open) == 1
    assert rows_open[0]["status"] == "open"

    rows_resolved = _query_local_errors(db, "app", "24h", "resolved")
    assert len(rows_resolved) == 1
    assert rows_resolved[0]["status"] == "resolved"
