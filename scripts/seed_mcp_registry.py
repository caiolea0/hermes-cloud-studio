"""F.5.3 Commit 1 — seed mcp_registry idempotente.

Lê .claude/mcp_registry_seed.json e INSERT ON CONFLICT UPDATE.
Rerun seguro: INSERT vira UPDATE (preserva created_at, atualiza updated_at + tools/status/required_by_dc/tier).

Uso:
    python scripts/seed_mcp_registry.py            # PC db (hermes_local.db)
    python scripts/seed_mcp_registry.py --vm       # VM db (~/.hermes/data/command_center.db) — F.5.3+

Cross-ref: PLAN.md F.5.3 D3 + .claude/MCP-ENFORCEMENT-STRATEGY.md section 5.2.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = PROJECT_ROOT / ".claude" / "mcp_registry_seed.json"
PC_DB = PROJECT_ROOT / "hermes_local.db"
MIGRATION_REGISTRY = PROJECT_ROOT / "migrations" / "2026_06_mcp_registry.sql"
MIGRATION_CALLS = PROJECT_ROOT / "migrations" / "2026_06_mcp_calls.sql"


def _ensure_table(conn: sqlite3.Connection) -> None:
    """Apply CREATE TABLE migrations idempotente (mcp_registry + mcp_calls)."""
    for mig in (MIGRATION_REGISTRY, MIGRATION_CALLS):
        # CREATE TABLE IF NOT EXISTS is idempotent — applying always is safe and cheap.
        sql = mig.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.commit()


def seed(db_path: Path) -> dict[str, int]:
    """Insert/update rows from seed JSON. Returns counts {inserted, updated, total}."""
    seed_data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    rows = seed_data.get("rows", [])
    if not rows:
        raise ValueError(f"Seed JSON has no rows: {SEED_PATH}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        _ensure_table(conn)

        # Count pre-existing rows for inserted/updated breakdown
        existing_servers = {
            r[0] for r in conn.execute("SELECT server FROM mcp_registry").fetchall()
        }
        inserted = 0
        updated = 0

        sql = """
        INSERT INTO mcp_registry (server, tools, status, chapter_owner, required_by_dc, tier, oauth_required, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(server) DO UPDATE SET
            tools = excluded.tools,
            status = excluded.status,
            chapter_owner = excluded.chapter_owner,
            required_by_dc = excluded.required_by_dc,
            tier = excluded.tier,
            oauth_required = excluded.oauth_required,
            updated_at = CURRENT_TIMESTAMP
        """
        for row in rows:
            server = row["server"]
            params = (
                server,
                json.dumps(row.get("tools", [])),
                row.get("status", "active"),
                row["chapter_owner"],
                json.dumps(row.get("required_by_dc", [])),
                row.get("tier", "active"),
                int(row.get("oauth_required", 1)),
            )
            conn.execute(sql, params)
            if server in existing_servers:
                updated += 1
            else:
                inserted += 1

        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM mcp_registry").fetchone()[0]
        return {"inserted": inserted, "updated": updated, "total": total}
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed mcp_registry idempotente")
    parser.add_argument("--db", type=Path, default=PC_DB, help="SQLite DB path (default: hermes_local.db)")
    parser.add_argument("--vm", action="store_true", help="Use VM DB path ~/.hermes/data/command_center.db")
    args = parser.parse_args()

    if args.vm:
        db_path = Path.home() / ".hermes" / "data" / "command_center.db"
    else:
        db_path = args.db

    if not db_path.exists():
        print(f"[seed] DB not found: {db_path} — creating new SQLite file", file=sys.stderr)

    print(f"[seed] target DB: {db_path}", file=sys.stderr)
    counts = seed(db_path)
    print(
        f"[seed] DONE inserted={counts['inserted']} updated={counts['updated']} total={counts['total']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
