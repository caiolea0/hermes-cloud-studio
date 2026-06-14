"""One-shot helper to apply F.8.1 observability migration locally.

Idempotent (CREATE TABLE IF NOT EXISTS + INSERT OR IGNORE). Mirror pattern from
scripts/_apply_brain_migration.py.

Run: python scripts/_apply_observability_migration.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "hermes_local.db"
SQL = ROOT / "migrations" / "2026_06_observability.sql"

if not DB.exists():
    print(f"ERROR: {DB} not found", file=sys.stderr)
    sys.exit(1)
if not SQL.exists():
    print(f"ERROR: {SQL} not found", file=sys.stderr)
    sys.exit(1)

conn = sqlite3.connect(str(DB))
conn.executescript(SQL.read_text(encoding="utf-8"))
conn.commit()

# Verify 3 tables created
rows = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' "
    "AND name IN ('mcp_pricing','perf_metrics','errors_inbox') ORDER BY name"
).fetchall()
print(f"observability tables: {[r[0] for r in rows]}")

for table in ("mcp_pricing", "perf_metrics", "errors_inbox"):
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    idxs = conn.execute(f"PRAGMA index_list({table})").fetchall()
    print(f"  {table}: {len(cols)} cols, {len(idxs)} indexes")

# Seed count
seed = conn.execute("SELECT COUNT(*) FROM mcp_pricing").fetchone()[0]
print(f"  mcp_pricing seed rows: {seed}")
free_count = conn.execute(
    "SELECT COUNT(*) FROM mcp_pricing WHERE cost_per_credit_usd = 0 "
    "AND cost_per_1k_tokens_in_usd = 0"
).fetchone()[0]
print(f"  mcp_pricing FREE rows: {free_count}")

conn.close()
print("OK")
