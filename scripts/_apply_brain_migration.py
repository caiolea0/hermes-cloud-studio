"""One-shot helper to apply F.6.1 brain migration locally.

Idempotent (CREATE TABLE IF NOT EXISTS). Run: python scripts/_apply_brain_migration.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "hermes_local.db"
SQL = ROOT / "migrations" / "2026_06_brain_runs_decisions.sql"

if not DB.exists():
    print(f"ERROR: {DB} not found", file=sys.stderr)
    sys.exit(1)
if not SQL.exists():
    print(f"ERROR: {SQL} not found", file=sys.stderr)
    sys.exit(1)

conn = sqlite3.connect(str(DB))
conn.executescript(SQL.read_text(encoding="utf-8"))
conn.commit()

rows = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'brain_%' ORDER BY name"
).fetchall()
print(f"brain tables: {[r[0] for r in rows]}")

for table in ("brain_runs", "brain_decisions"):
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    idxs = conn.execute(f"PRAGMA index_list({table})").fetchall()
    print(f"  {table}: {len(cols)} cols, {len(idxs)} indexes")

conn.close()
print("OK")
