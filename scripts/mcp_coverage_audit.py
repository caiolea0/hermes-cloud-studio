"""F.5.5 — MCP Coverage Audit mensal.

Cron monthly day 15 10h BRT (`0 10 15 * *` America/Cuiaba).
Output `.claude/audits/mcp-coverage/MCP-COVERAGE-{YYYY-MM}.md` + JSON sibling.
Optional `--commit` triggers `git add` + `git commit` path-scoped (D2).

Usage:
    python scripts/mcp_coverage_audit.py --period 2026-06
    python scripts/mcp_coverage_audit.py --period 2026-06 --commit
    python scripts/mcp_coverage_audit.py --db ~/.hermes/data/command_center.db --period 2026-06

Cross-ref: PLAN.md F.5.5 D0-D6 + .claude/MCP-ENFORCEMENT-STRATEGY.md section 6.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vm_core.mcp_tiering import aggregate_by_tier, classify_drift, classify_tier  # noqa: E402

AUDIT_DIR = ROOT / ".claude" / "audits" / "mcp-coverage"
DEFAULT_DB = ROOT / "hermes_local.db"
SEED_PATH = ROOT / ".claude" / "mcp_registry_seed.json"


def get_period_bounds(period: str) -> tuple[datetime, datetime]:
    """period='2026-06' -> (UTC start, UTC end-of-month)."""
    year_s, month_s = period.split("-")
    year, month = int(year_s), int(month_s)
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1) - timedelta(seconds=1)
    else:
        end = datetime(year, month + 1, 1) - timedelta(seconds=1)
    return start, end


def verify_query_plan(conn: sqlite3.Connection) -> dict:
    """D6 EXPLAIN QUERY PLAN — confirma idx_mcp_calls_server_tool_time usado.

    SQLite-specific. F.future port Postgres: substituir por EXPLAIN ANALYZE.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT server, tool, COUNT(*) FROM mcp_calls
            WHERE created_at > datetime('now', '-30 days')
            GROUP BY server, tool
            """
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError as exc:
        return {"index_used": "idx_mcp_calls_server_tool_time", "uses_index": False,
                "plan": f"ERROR: {exc}"}
    plan_str = " | ".join(str(r[-1]) for r in rows)
    uses_index = "idx_mcp_calls_server_tool_time" in plan_str
    if not uses_index:
        import logging
        logging.warning(
            "AUDIT: query NOT using idx_mcp_calls_server_tool_time. Plan: %s",
            plan_str,
        )
    return {"index_used": "idx_mcp_calls_server_tool_time", "uses_index": uses_index,
            "plan": plan_str}


def _drift_reason(runtime_tier: str, call_match: dict | None) -> str:
    if runtime_tier == "orphan":
        return "registered active but zero calls 30d"
    if runtime_tier == "warning":
        last = call_match.get("last_call") if call_match else "unknown"
        return f"last call 7-30d ago ({last})"
    if runtime_tier == "deprecated":
        last = call_match.get("last_call") if call_match else "unknown"
        return f"last call >30d ago ({last})"
    return "drift detected"


def _load_seed() -> list[dict]:
    if not SEED_PATH.exists():
        return []
    doc = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return doc.get("rows", doc if isinstance(doc, list) else [])


def run_audit(period: str, db_path: Path) -> dict:
    """Core audit logic — returns D3 schema dict.

    Empty mcp_calls table OK (initial deploy F.5.5 antes calls). Items vem
    da seed registry com runtime_tier=orphan.
    """
    start, end = get_period_bounds(period)
    if not db_path.exists():
        return _empty_result(period, start, end, note=f"DB not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        existing = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "mcp_calls" not in existing:
            return _empty_result(period, start, end, note="mcp_calls table missing — apply F.5.3 migrations")

        explain = verify_query_plan(conn)

        call_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT server, tool, COUNT(*) as calls,
                       ROUND(AVG(duration_ms), 1) as avg_ms,
                       MAX(created_at) as last_call,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as errors
                FROM mcp_calls
                WHERE created_at > datetime('now', '-30 days')
                GROUP BY server, tool
                """
            ).fetchall()
        ]
    finally:
        conn.close()

    seed_rows = _load_seed()
    call_map = {(r["server"], r["tool"]): r for r in call_rows}

    items: list[dict] = []
    drift_items: list[dict] = []
    for reg in seed_rows:
        server = reg["server"]
        registry_tier = reg.get("tier", "active")
        for tool in reg.get("tools", []):
            call = call_map.get((server, tool))
            last_call = call["last_call"] if call else None
            runtime_tier = classify_tier(server, tool, last_call, registry_tier)
            drift = classify_drift(registry_tier, runtime_tier)
            item = {
                "server": server,
                "tool": tool,
                "tier": runtime_tier,
                "registry_tier": registry_tier,
                "calls": call["calls"] if call else 0,
                "avg_ms": call["avg_ms"] if call else None,
                "errors": call["errors"] if call else 0,
                "last_call": last_call,
                "drift": drift,
                "chapter_owner": reg.get("chapter_owner"),
            }
            items.append(item)
            if drift:
                drift_items.append({
                    "server": server,
                    "tool": tool,
                    "registry_tier": registry_tier,
                    "runtime_tier": runtime_tier,
                    "reason": _drift_reason(runtime_tier, call),
                })

    summary = {
        "total_tools": len(items),
        "by_tier": aggregate_by_tier(items),
        "drift_count": len(drift_items),
        "total_calls_30d": sum(i["calls"] for i in items),
        "errors_30d": sum(i["errors"] for i in items),
    }

    return {
        "period": {"start": start.isoformat() + "Z", "end": end.isoformat() + "Z"},
        "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        "summary": summary,
        "items": items,
        "drift_detected": drift_items,
        "explain_query_plan": explain,
    }


def _empty_result(period: str, start: datetime, end: datetime, note: str) -> dict:
    return {
        "period": {"start": start.isoformat() + "Z", "end": end.isoformat() + "Z"},
        "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        "summary": {"total_tools": 0, "by_tier": {}, "drift_count": 0,
                    "total_calls_30d": 0, "errors_30d": 0},
        "items": [],
        "drift_detected": [],
        "explain_query_plan": {"index_used": None, "uses_index": False, "plan": ""},
        "note": note,
    }


def render_md(result: dict) -> str:
    """D3 owner-friendly MD: summary + DRIFT section + tier breakdown + index health."""
    s = result["summary"]
    period = result["period"]["start"][:7]
    by_tier = s.get("by_tier", {})
    total_calls = s.get("total_calls_30d", 0)
    err = s.get("errors_30d", 0)
    err_pct = (err / total_calls * 100) if total_calls > 0 else 0.0

    lines = [
        f"# MCP Coverage Report — {period}",
        "",
        f"**Period**: {result['period']['start'][:10]} to {result['period']['end'][:10]}  ",
        f"**Generated**: {result['generated_at']}",
        "",
        "## Summary",
        f"- Total tools: {s.get('total_tools', 0)}",
        f"- **Active** (called last 7d): {by_tier.get('active', 0)}",
        f"- **Warning** (7-30d): {by_tier.get('warning', 0)}",
        f"- **Orphan** (zero calls 30d): {by_tier.get('orphan', 0)}",
        f"- **Deprecated**: {by_tier.get('deprecated', 0)}",
        f"- **Quarantine**: {by_tier.get('quarantine', 0)}",
        f"- **Reserved**: {by_tier.get('reserved', 0)}",
        f"- **DRIFT DETECTED**: {s.get('drift_count', 0)} {'WARN' if s.get('drift_count', 0) else 'OK'}",
        f"- Total calls: {total_calls:,} | Errors: {err} ({err_pct:.2f}%)",
        "",
    ]
    if result.get("note"):
        lines += [f"> NOTE: {result['note']}", ""]

    drift = result.get("drift_detected", [])
    if drift:
        lines += [
            "## DRIFT DETECTED",
            "",
            "| Server | Tool | Registry | Runtime | Reason |",
            "|---|---|---|---|---|",
        ]
        for d in drift:
            lines.append(
                f"| {d['server']} | {d['tool']} | {d['registry_tier']} | "
                f"{d['runtime_tier']} | {d['reason']} |"
            )
        lines.append("")

    if result.get("items"):
        lines += [
            "## Tier Breakdown",
            "",
            "| Server | Tool | Tier | Calls | Avg ms | Errors | Last Call |",
            "|---|---|---|---|---|---|---|",
        ]
        sorted_items = sorted(result["items"], key=lambda x: (-x["calls"], x["server"], x["tool"]))
        for it in sorted_items:
            avg = it["avg_ms"] if it["avg_ms"] is not None else "-"
            last = it["last_call"] if it["last_call"] else "-"
            lines.append(
                f"| {it['server']} | {it['tool']} | {it['tier']} | {it['calls']} | "
                f"{avg} | {it['errors']} | {last} |"
            )
        lines.append("")

    eqp = result["explain_query_plan"]
    status = "OK" if eqp.get("uses_index") else "WARN"
    detail = "used by aggregate query" if eqp.get("uses_index") else "NOT USED — performance risk"
    lines += [
        "## Index Health",
        f"{status} {eqp.get('index_used') or 'no idx'} {detail}",
        "",
    ]
    return "\n".join(lines)


def commit_audit(md_path: Path, json_path: Path, period: str, summary: dict) -> None:
    """D2 git commit auto path-scoped (.claude/audits/mcp-coverage/*)."""
    by_tier = summary.get("by_tier", {})
    msg = (
        f"docs(audit): MCP coverage {period} "
        f"({by_tier.get('active', 0)} active, "
        f"{by_tier.get('warning', 0)} warning, "
        f"{by_tier.get('orphan', 0)} orphan, "
        f"{summary.get('drift_count', 0)} drift)"
    )
    try:
        md_rel = str(md_path.relative_to(ROOT)).replace("\\", "/")
        json_rel = str(json_path.relative_to(ROOT)).replace("\\", "/")
        subprocess.run(["git", "add", md_rel, json_rel], cwd=str(ROOT), check=True)
        subprocess.run(["git", "commit", "-m", msg], cwd=str(ROOT), check=True)
        print(f"git commit OK: {msg}")
    except subprocess.CalledProcessError as exc:
        print(f"WARN: git commit failed (rc={exc.returncode})", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP coverage audit mensal (F.5.5)")
    parser.add_argument("--period", default=datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m"),
                        help="YYYY-MM (default current UTC month)")
    parser.add_argument("--db", default=str(DEFAULT_DB),
                        help=f"SQLite path (default {DEFAULT_DB})")
    parser.add_argument("--commit", action="store_true",
                        help="Auto git commit MD+JSON after write (D2)")
    args = parser.parse_args()

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    db_path = Path(args.db).expanduser()

    result = run_audit(args.period, db_path)

    md_path = AUDIT_DIR / f"MCP-COVERAGE-{args.period}.md"
    json_path = AUDIT_DIR / f"MCP-COVERAGE-{args.period}.json"

    md_path.write_text(render_md(result), encoding="utf-8")
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {md_path.name} + {json_path.name}")
    print(f"  total_tools={result['summary']['total_tools']} "
          f"drift={result['summary']['drift_count']} "
          f"calls_30d={result['summary']['total_calls_30d']} "
          f"errors_30d={result['summary']['errors_30d']}")

    if args.commit:
        commit_audit(md_path, json_path, args.period, result["summary"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
