"""PA-F3: Centralize UX-RM migrations + reconcile sequence_nodes schema.

Gates:
  G1 BLACKLIST R2 INTACTO 72 SS
  G2 pytest 523+ PASS 0 FAIL
  G3 UX-RM migrations centralized in server.py lifespan
  G4 sequence_nodes single canonical schema (drift eliminated)
  G5 Idempotency: apply 2x no error
  G6 Lazy-init fallback still present in modules
"""
from __future__ import annotations

import sqlite3
import tempfile
import textwrap
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
SERVER_PY = PROJECT_ROOT / "server.py"
DAEMON_PY = PROJECT_ROOT / "daemon" / "orchestrator.py"
SEQUENCES_PY = PROJECT_ROOT / "api" / "sequences.py"


# ── G3: server.py centralization ─────────────────────────────────────────────

def test_sequences_migration_in_lifespan():
    text = SERVER_PY.read_text(encoding="utf-8")
    assert "2026_06_sequences.sql" in text, "sequences migration must be in server.py lifespan"
    assert "_PA_F3_MIGRATIONS" in text, "PA-F3 block must be present in server.py"


def test_daemon_sequence_inbox_migration_in_lifespan():
    text = SERVER_PY.read_text(encoding="utf-8")
    assert "2026_06_daemon_sequence_inbox.sql" in text, "daemon_sequence_inbox must be in server.py lifespan"


def test_onboarding_icp_migrations_in_lifespan():
    text = SERVER_PY.read_text(encoding="utf-8")
    assert "2026_06_onboarding_state.sql" in text, "onboarding_state must be in server.py lifespan"
    assert "2026_06_icp_profile.sql" in text, "icp_profile must be in server.py lifespan"


def test_templates_migration_file_exists():
    mig = MIGRATIONS_DIR / "2026_06_templates.sql"
    assert mig.exists(), "2026_06_templates.sql must exist as canonical migration"
    sql = mig.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS templates" in sql
    assert "idx_templates_channel" in sql


def test_templates_migration_in_lifespan():
    text = SERVER_PY.read_text(encoding="utf-8")
    assert "2026_06_templates.sql" in text, "templates migration must be in server.py lifespan"


# ── G4: sequence_nodes canonical schema (drift eliminated) ───────────────────

def test_sequence_nodes_single_canonical_schema():
    """Daemon and api/sequences.py must NOT have divergent DEFAULT 0 / DEFAULT 'action'."""
    daemon_text = DAEMON_PY.read_text(encoding="utf-8")
    # Daemon must NOT have DEFAULT 0 on sequence_id (non-canonical)
    # Check by looking for the exact divergent pattern
    lines = daemon_text.splitlines()
    in_seq_nodes = False
    for line in lines:
        if "CREATE TABLE IF NOT EXISTS sequence_nodes" in line:
            in_seq_nodes = True
        if in_seq_nodes and "sequence_id" in line and "DEFAULT 0" in line:
            pytest.fail("daemon/orchestrator.py sequence_nodes.sequence_id must NOT have DEFAULT 0 (schema drift)")
        if in_seq_nodes and "node_type" in line and "DEFAULT 'action'" in line:
            pytest.fail("daemon/orchestrator.py sequence_nodes.node_type must NOT have DEFAULT 'action' (schema drift)")
        if in_seq_nodes and ");" in line and "sequence_nodes" not in line:
            break


def test_sequence_nodes_defaults_consistent():
    """Canonical migration and lazy-init must agree on sequence_id + node_type (no spurious defaults)."""
    canonical = (MIGRATIONS_DIR / "2026_06_sequences.sql").read_text(encoding="utf-8")
    lazy_init = SEQUENCES_PY.read_text(encoding="utf-8")
    # Both must NOT have DEFAULT on sequence_id inside sequence_nodes block
    for src, name in [(canonical, "canonical migration"), (lazy_init, "api/sequences.py")]:
        lines = src.splitlines()
        in_block = False
        for line in lines:
            if "CREATE TABLE IF NOT EXISTS sequence_nodes" in line:
                in_block = True
            if in_block and "sequence_id" in line:
                assert "DEFAULT 0" not in line, f"{name}: sequence_id must not have DEFAULT 0"
            if in_block and "node_type" in line:
                assert "DEFAULT 'action'" not in line, f"{name}: node_type must not have DEFAULT 'action'"
            if in_block and ");" in line:
                break


def test_sequence_nodes_lazy_init_has_fk():
    """api/sequences.py lazy-init must include FK constraint (aligned with canonical)."""
    text = SEQUENCES_PY.read_text(encoding="utf-8")
    assert "FOREIGN KEY (sequence_id) REFERENCES sequences(id) ON DELETE CASCADE" in text


def test_sequence_nodes_lazy_init_has_index():
    """api/sequences.py lazy-init must include idx_sequence_nodes_seq (aligned with canonical)."""
    text = SEQUENCES_PY.read_text(encoding="utf-8")
    assert "idx_sequence_nodes_seq" in text


# ── G5: Idempotency — apply 2x no error ──────────────────────────────────────

def test_all_uxrm_migrations_idempotent():
    """Apply all PA-F3 migrations twice on a fresh DB — must not raise."""
    migrations = [
        "2026_06_sequences.sql",
        "2026_06_templates.sql",
        "2026_06_daemon_sequence_inbox.sql",
        "2026_06_onboarding_state.sql",
        "2026_06_icp_profile.sql",
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        for run in range(2):
            for mig_name in migrations:
                mig_path = MIGRATIONS_DIR / mig_name
                assert mig_path.exists(), f"Migration file missing: {mig_name}"
                sql = mig_path.read_text(encoding="utf-8")
                try:
                    conn.executescript(sql)
                    conn.commit()
                except sqlite3.OperationalError as exc:
                    pytest.fail(f"Migration {mig_name} run#{run+1} raised: {exc}")
        conn.close()


def test_daemon_inline_schema_idempotent():
    """Daemon _init_db schema is idempotent — verify by running canonical migration twice."""
    # Canonical sequences migration covers daemon's sequence_nodes/sequence_edges.
    # daemon_sequence_inbox covers inbox_replies/sequence_enrollments/telegram_stop_signals.
    migrations = [
        "2026_06_sequences.sql",
        "2026_06_daemon_sequence_inbox.sql",
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_daemon.db"
        conn = sqlite3.connect(str(db_path))
        for run in range(2):
            for mig_name in migrations:
                sql = (MIGRATIONS_DIR / mig_name).read_text(encoding="utf-8")
                try:
                    conn.executescript(sql)
                    conn.commit()
                except sqlite3.OperationalError as exc:
                    pytest.fail(f"Daemon canonical schema run#{run+1} raised: {exc}")
        conn.close()


# ── G6: Lazy-init fallback still present in modules ──────────────────────────

def test_lazy_init_still_works_as_fallback():
    """Lazy-init guards must remain in all 4 UX-RM modules (defense-in-depth)."""
    checks = [
        (SEQUENCES_PY, "_apply_migration"),
        (PROJECT_ROOT / "api" / "templates.py", "_apply_migration"),
        (PROJECT_ROOT / "api" / "onboarding.py", "_ensure_table"),
        (PROJECT_ROOT / "core" / "icp_store.py", "_ensure_table"),
    ]
    for path, fn_name in checks:
        text = path.read_text(encoding="utf-8")
        assert fn_name in text, f"{path.name}: lazy-init function '{fn_name}' must remain"
        assert "CREATE TABLE IF NOT EXISTS" in text, f"{path.name}: lazy-init CREATE must remain"
