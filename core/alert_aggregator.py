"""F.7 C4 — Bug aggregator for cobaia 24h export (D6 PIVOT).

aggregate_bugs_24h() pulls failures from 3 local DB sources:
  1. skill_runs (status='failed')
  2. errors_inbox (category LIKE '%cobaia%' or '%linkedin%', unresolved)
  3. mcp_calls (error IS NOT NULL, requester LIKE 'brain-f7%')

render_markdown_summary() produces structured markdown for owner Claude paste.
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("hermes.alert_aggregator")


def _db_path() -> Path:
    try:
        from core.state import DB_PATH
        return DB_PATH
    except Exception:
        return Path(__file__).parent.parent / "hermes_local.db"


def _error_signature(msg: str, source: str = "", category: str = "") -> str:
    """Dedup key: MD5 of source+category+first-120-chars-of-msg."""
    raw = f"{source}:{category}:{str(msg)[:120]}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def aggregate_bugs_24h(
    account_handle: str = "cobaia",
    hours: int = 24,
    db: Path | None = None,
) -> dict[str, Any]:
    """Aggregate failures from 3 sources over the last `hours` hours.

    Returns:
        {account_handle, hours, total, unique, by_category, top_errors,
         trace_samples, timeline, generated_at}
    """
    db_path = db if db is not None else _db_path()
    interval = f"-{hours} hours"

    all_errors: list[dict[str, Any]] = []
    all_errors.extend(_query_skill_runs(db_path, interval))
    all_errors.extend(_query_errors_inbox(db_path, interval))
    all_errors.extend(_query_mcp_calls(db_path, interval))

    deduped = _dedup_errors(all_errors)

    by_category: dict[str, int] = {}
    for e in all_errors:
        src = e.get("source", "unknown")
        by_category[src] = by_category.get(src, 0) + 1

    top_errors = sorted(deduped, key=lambda x: x.get("count", 1), reverse=True)[:10]

    trace_samples = [
        {
            "signature": e.get("signature"),
            "source": e.get("source"),
            "message": str(e.get("message", ""))[:200],
            "count": e.get("count", 1),
            "first_seen": e.get("first_seen"),
            "last_seen": e.get("last_seen"),
        }
        for e in top_errors[:5]
    ]

    return {
        "account_handle": account_handle,
        "hours": hours,
        "total": len(all_errors),
        "unique": len(deduped),
        "by_category": by_category,
        "top_errors": top_errors,
        "trace_samples": trace_samples,
        "timeline": _build_timeline(all_errors, hours),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _query_skill_runs(db: Path, interval: str) -> list[dict[str, Any]]:
    if not db.exists():
        return []
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            if not conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='skill_runs'"
            ).fetchone():
                return []
            rows = conn.execute(
                """SELECT id, skill_name, status, error_message, created_at
                   FROM skill_runs
                   WHERE status = 'failed'
                     AND created_at > datetime('now', ?)
                   ORDER BY created_at DESC LIMIT 200""",
                (interval,),
            ).fetchall()
            return [
                {
                    "source": "skill_runs",
                    "message": r["error_message"] or f"skill failed: {r['skill_name']}",
                    "category": r["skill_name"] or "unknown_skill",
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("skill_runs query failed: %s", exc)
        return []


def _query_errors_inbox(db: Path, interval: str) -> list[dict[str, Any]]:
    if not db.exists():
        return []
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            if not conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='errors_inbox'"
            ).fetchone():
                return []
            rows = conn.execute(
                """SELECT id, category, severity, title, message, status, created_at
                   FROM errors_inbox
                   WHERE (category LIKE '%cobaia%' OR category LIKE '%linkedin%')
                     AND status != 'resolved'
                     AND created_at > datetime('now', ?)
                   ORDER BY created_at DESC LIMIT 200""",
                (interval,),
            ).fetchall()
            return [
                {
                    "source": "errors_inbox",
                    "message": r["message"] or r["title"] or "errors_inbox error",
                    "category": r["category"] or "unknown",
                    "severity": r["severity"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("errors_inbox query failed: %s", exc)
        return []


def _query_mcp_calls(db: Path, interval: str) -> list[dict[str, Any]]:
    if not db.exists():
        return []
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            if not conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='mcp_calls'"
            ).fetchone():
                return []
            rows = conn.execute(
                """SELECT id, tool_name, error, requester, created_at
                   FROM mcp_calls
                   WHERE error IS NOT NULL
                     AND requester LIKE 'brain-f7%'
                     AND created_at > datetime('now', ?)
                   ORDER BY created_at DESC LIMIT 200""",
                (interval,),
            ).fetchall()
            return [
                {
                    "source": "mcp_calls",
                    "message": r["error"] or f"mcp error: {r['tool_name']}",
                    "category": r["tool_name"] or "unknown_tool",
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("mcp_calls query failed: %s", exc)
        return []


def _dedup_errors(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group rows by error signature, track count + first/last seen."""
    groups: dict[str, dict[str, Any]] = {}
    for r in rows:
        sig = _error_signature(
            r.get("message", ""),
            r.get("source", ""),
            r.get("category", ""),
        )
        if sig not in groups:
            groups[sig] = {
                "signature": sig,
                "source": r.get("source"),
                "message": r.get("message", ""),
                "category": r.get("category", "unknown"),
                "count": 0,
                "first_seen": r.get("created_at"),
                "last_seen": r.get("created_at"),
            }
        g = groups[sig]
        g["count"] += 1
        ts = r.get("created_at") or ""
        if ts and ts < (g["first_seen"] or "z"):
            g["first_seen"] = ts
        if ts and ts > (g["last_seen"] or ""):
            g["last_seen"] = ts
    return list(groups.values())


def _build_timeline(rows: list[dict[str, Any]], hours: int) -> list[dict[str, Any]]:
    """Bucket errors by hour slot (YYYY-MM-DD HH)."""
    buckets: dict[str, int] = {}
    for r in rows:
        ts = r.get("created_at", "") or ""
        if len(ts) >= 13:
            slot = ts[:13]
            buckets[slot] = buckets.get(slot, 0) + 1
    return [{"hour": h, "count": c} for h, c in sorted(buckets.items())]


def render_markdown_summary(data: dict[str, Any]) -> str:
    """Render Claude-friendly markdown from aggregate_bugs_24h() output."""
    account = data.get("account_handle", "cobaia")
    hours = data.get("hours", 24)
    total = data.get("total", 0)
    unique = data.get("unique", 0)
    generated_at = str(data.get("generated_at", ""))[:19]
    by_category = data.get("by_category", {})
    top_errors = data.get("top_errors", [])
    trace_samples = data.get("trace_samples", [])

    lines: list[str] = [
        f"## Hermes Cobaia Bug Export — {account}",
        f"**Periodo:** ultimas {hours}h | **Gerado:** {generated_at}",
        f"**Total erros:** {total} | **Unique signatures:** {unique}",
        "",
        "### Por categoria",
        "| Fonte | Erros |",
        "|---|---|",
    ]
    for src, cnt in sorted(by_category.items(), key=lambda x: -x[1]):
        lines.append(f"| `{src}` | {cnt} |")

    if top_errors:
        lines.extend(["", "### Top erros (deduplicados)"])
        for i, e in enumerate(top_errors[:10], 1):
            lines.append(
                f"{i}. **[{e.get('source', '?')}]** `{e.get('category', '?')}` "
                f"x{e.get('count', 1)} — sig `{e.get('signature', '?')}`"
            )
            msg = str(e.get("message", ""))[:120]
            lines.append(f"   > {msg}")

    if trace_samples:
        lines.extend(["", "### Trace samples"])
        for s in trace_samples:
            lines.append(
                f"- `{s.get('signature')}` ({s.get('source')}/{s.get('category')}) "
                f"x{s.get('count', 1)} | first: {str(s.get('first_seen') or '')[:19]}"
            )
            msg_text = str(s.get("message", ""))[:200]
            lines.append(f"  ```\n  {msg_text}\n  ```")

    lines.extend([
        "",
        "---",
        "_Cobaia Bug Export F.7 C4 — cole nesta sessao Claude para fix_",
    ])
    return "\n".join(lines)
