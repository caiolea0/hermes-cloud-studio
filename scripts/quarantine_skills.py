#!/usr/bin/env python3
"""F.4.4 C2 — Skill quarantine cron.

Runs hourly on VM via systemd timer.
Reads skill_runs from command_center.db and moves skills with
success_rate < 0.5 (last MIN_SAMPLE runs) to skills/_quarantine/.

Usage (VM):
    python3 quarantine_skills.py [--dry-run]

Environment:
    HERMES_DB_PATH   path to command_center.db (default: ~/.hermes/data/command_center.db)
    HERMES_SKILLS_DIR path to live skills dir (default: ~/.hermes/skills)
    HERMES_HOME      hermes home dir (default: ~/.hermes)

Exit codes:
    0  success (even if nothing quarantined)
    1  lock busy — concurrent sync in progress
    2  fatal error
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOCK_FILE = "/tmp/hermes-sync.lock"
MIN_SAMPLE = 10          # require at least this many runs before quarantine
THRESHOLD = 0.5          # success_rate below this → quarantine


def _db_path() -> Path:
    env = os.environ.get("HERMES_DB_PATH", "")
    if env:
        return Path(env)
    return Path.home() / ".hermes" / "data" / "command_center.db"


def _skills_dir() -> Path:
    env = os.environ.get("HERMES_SKILLS_DIR", "")
    if env:
        return Path(env)
    return Path.home() / ".hermes" / "skills"


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[quarantine_skills {ts}] {msg}", file=sys.stderr)


def _skill_runs_success_rate(
    conn: sqlite3.Connection, skill_name: str, limit: int = MIN_SAMPLE
) -> dict[str, Any]:
    # NOTE: similar logic exists in core/skill_proposals.get_skill_runs_success_rate (PC).
    # Duplication is intentional — this script runs on VM where core/ is not importable.
    rows = conn.execute(
        "SELECT status FROM skill_runs WHERE skill_name = ? ORDER BY started_at DESC LIMIT ?",
        (skill_name, limit),
    ).fetchall()
    total = len(rows)
    passed = sum(1 for r in rows if r[0] == "completed")
    return {
        "sample_size": total,
        "passed": passed,
        "failed": total - passed,
        "success_rate": round(passed / total, 3) if total else 0.0,
    }


def _record_quarantine_event(
    conn: sqlite3.Connection,
    skill_name: str,
    reason: str,
    run_id: str,
) -> None:
    started_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT OR IGNORE INTO skill_sync_runs
           (id, trigger_type, pr_number, pr_url, sync_status, started_at,
            completed_at, error_message, affected_skills)
           VALUES (?, 'cron_quarantine', NULL, NULL, 'quarantined', ?, ?, ?, ?)""",
        (run_id, started_at, started_at, reason, json.dumps([skill_name])),
    )
    conn.commit()


def _ws_notify(payload: dict) -> None:
    """Best-effort WS notification via VM internal HTTP."""
    try:
        import urllib.request
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            "http://localhost:8420/api/internal/ws/broadcast",
            data=data,
            headers={"Content-Type": "application/json", "X-Internal-Request": "1"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass


def _sentry_breadcrumb(message: str, data: dict) -> None:
    try:
        import sentry_sdk  # type: ignore[import-not-found]
        sentry_sdk.add_breadcrumb(
            category="skill_quarantine",
            message=message,
            level="warning",
            data=data,
        )
    except Exception:
        pass


def run(dry_run: bool = False) -> dict[str, Any]:
    db = _db_path()
    skills_dir = _skills_dir()
    quarantine_dir = skills_dir / "_quarantine"

    if not db.exists():
        _log(f"DB not found: {db}")
        return {"status": "error", "error": f"DB not found: {db}", "checked": 0, "quarantined": []}

    conn = sqlite3.connect(str(db), timeout=10.0)
    try:
        # Check skill_runs table exists (VM might not have it yet)
        table_exists = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='skill_runs'"
        ).fetchone()[0]
        if not table_exists:
            _log("skill_runs table missing — skip (apply migrations/2026_06_skill_proposals.sql)")
            return {"status": "skipped", "reason": "skill_runs_missing", "checked": 0, "quarantined": []}

        # Enumerate active skills from filesystem
        if not skills_dir.exists():
            _log(f"SKILLS_DIR not found: {skills_dir}")
            return {"status": "error", "error": f"skills dir not found: {skills_dir}", "checked": 0, "quarantined": []}

        yaml_files = [
            f for f in skills_dir.glob("*.yaml")
        ] + [
            f for f in skills_dir.glob("*.yml")
        ]
        if not yaml_files:
            _log("No skill YAML files found — nothing to check")
            return {"status": "ok", "checked": 0, "quarantined": [], "skipped_insufficient_data": []}

        checked = []
        quarantined = []
        skipped_insufficient = []

        for yaml_file in yaml_files:
            skill_name = yaml_file.stem
            stats = _skill_runs_success_rate(conn, skill_name)

            if stats["sample_size"] < MIN_SAMPLE:
                _log(f"SKIP {skill_name}: only {stats['sample_size']}/{MIN_SAMPLE} runs")
                skipped_insufficient.append({"name": skill_name, "sample_size": stats["sample_size"]})
                checked.append(skill_name)
                continue

            checked.append(skill_name)

            if stats["success_rate"] < THRESHOLD:
                reason = (
                    f"success_rate={stats['success_rate']:.2f} < {THRESHOLD} "
                    f"({stats['passed']}/{stats['sample_size']} completed, last {MIN_SAMPLE} runs)"
                )
                _log(f"QUARANTINE {skill_name}: {reason}")

                if not dry_run:
                    quarantine_dir.mkdir(parents=True, exist_ok=True)
                    dest = quarantine_dir / yaml_file.name
                    shutil.move(str(yaml_file), str(dest))
                    run_id = str(uuid.uuid4())
                    _record_quarantine_event(conn, skill_name, reason, run_id)
                    _ws_notify({
                        "type": "brain.skill_quarantined",
                        "skill_name": skill_name,
                        "reason": reason,
                        "run_id": run_id,
                    })
                    _sentry_breadcrumb(
                        f"Skill {skill_name} quarantined",
                        {"skill_name": skill_name, "stats": stats},
                    )

                quarantined.append({"name": skill_name, "reason": reason, "stats": stats})
            else:
                _log(f"OK {skill_name}: success_rate={stats['success_rate']:.2f}")

    finally:
        conn.close()

    result = {
        "status": "dry_run" if dry_run else "ok",
        "checked": len(checked),
        "quarantined": quarantined,
        "skipped_insufficient_data": skipped_insufficient,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return result


def main() -> int:
    import fcntl  # Unix-only; import lazily so module is importable on Windows for tests

    parser = argparse.ArgumentParser(description="Hermes skill quarantine cron")
    parser.add_argument("--dry-run", action="store_true", help="Check only, do not move files")
    args = parser.parse_args()

    # Acquire lock (shared with webhook sync to prevent race)
    lock_fd = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_fd.close()
        _log("LOCK BUSY — concurrent sync in progress, skipping quarantine run")
        print(json.dumps({"status": "lock_busy", "checked": 0, "quarantined": []}))
        return 1

    try:
        result = run(dry_run=args.dry_run)
        print(json.dumps(result))
        return 0
    except Exception as exc:
        _log(f"FATAL: {exc}")
        print(json.dumps({"status": "error", "error": str(exc), "checked": 0, "quarantined": []}))
        return 2
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


if __name__ == "__main__":
    sys.exit(main())
