#!/usr/bin/env python3
"""F.3.4 — Lab artifacts cleanup standalone (dual-mode: DB-driven OR FS-driven).

Mode 1 (DB-driven, PC): Quando hermes_local.db tem lab_runs table (F.3.1 schema),
deleta artifacts/<run_id>/ com lab_runs.started_at < now-30d AND pinned=0. DB row
preservada (metadata leve), apenas filesystem dir removido.

Mode 2 (FS-driven, VM): Quando DB ausente OR sem lab_runs table, fallback pra walk
artifacts_root + filtro mtime < now-30d. Pinning via arquivo sentinela `.pinned`
dentro do run_dir (touch /home/hermes-gcp/linkedin/lab/artifacts/<run_id>/.pinned).

Decisao arquitetural F.3.4: lab_runs DB vive no PC (hermes_local.db), artifacts no
VM disk. VM crontab roda Mode 2 (FS-driven), PC pode rodar Mode 1 on-demand.

Flags:
    --dry-run    Log apenas, NAO delete (defensive primeira execucao)
    --age-days N Custom threshold (default 30)
    --db PATH    Custom DB path (default ~/.hermes/data/command_center.db)

Crontab VM entry sugerida (Mode 2 auto-detected):
    0 3 * * * cd /home/hermes-gcp && python3 scripts/lab_cleanup.py >> ~/logs/lab_cleanup.log 2>&1
"""
from __future__ import annotations
import argparse
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="Lab artifacts cleanup")
    p.add_argument("--dry-run", action="store_true", help="Log apenas, NAO delete")
    p.add_argument("--age-days", type=int, default=30, help="Threshold age days (default 30)")
    p.add_argument("--db", type=str, default="", help="Custom DB path")
    p.add_argument("--artifacts-root", type=str, default="", help="Custom artifacts root")
    return p.parse_args()


def resolve_paths(args):
    home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    db_path = Path(args.db) if args.db else home / "data" / "command_center.db"
    artifacts_root = (
        Path(args.artifacts_root)
        if args.artifacts_root
        else Path.home() / "linkedin" / "lab" / "artifacts"
    )
    return db_path, artifacts_root


def query_runs_to_cleanup(db_path: Path, threshold_ts: float):
    """Mode 1 DB-driven. Returns (mode_name, list[(run_id, artifacts_path)]) ou
    (None, None) se DB/table ausentes (caller faz fallback Mode 2)."""
    if not db_path.exists():
        print(
            f"INFO: DB not found at {db_path}, falling back to FS-driven mode",
            file=sys.stderr,
        )
        return None, None

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='lab_runs'"
        )
        if not cur.fetchone():
            print(
                "INFO: lab_runs table not found in DB, falling back to FS-driven mode",
                file=sys.stderr,
            )
            return None, None

        cur = conn.execute(
            "SELECT run_id, artifacts_path FROM lab_runs WHERE started_at < ? AND pinned = 0",
            (threshold_ts,),
        )
        return "db", [(row["run_id"], row["artifacts_path"]) for row in cur.fetchall()]
    finally:
        conn.close()


def scan_artifacts_fs(artifacts_root: Path, threshold_ts: float):
    """Mode 2 FS-driven. Walk artifacts_root subdirs, retorna candidates onde
    mtime < threshold AND nao tem sentinela .pinned. Returns list[(dir_name, path_str)]."""
    if not artifacts_root.exists():
        print(
            f"WARN: artifacts_root not found at {artifacts_root}, nothing to scan",
            file=sys.stderr,
        )
        return []

    candidates = []
    try:
        for entry in artifacts_root.iterdir():
            if not entry.is_dir():
                continue
            pinned_marker = entry / ".pinned"
            if pinned_marker.exists():
                print(f"SKIP pinned {entry.name} (.pinned sentinel present)")
                continue
            try:
                mtime = entry.stat().st_mtime
            except Exception as e:
                print(f"SKIP stat error {entry}: {e}", file=sys.stderr)
                continue
            if mtime < threshold_ts:
                candidates.append((entry.name, str(entry)))
    except Exception as e:
        print(f"ERROR walking {artifacts_root}: {e}", file=sys.stderr)
        return []

    return candidates


def cleanup_artifacts(candidates, artifacts_root: Path, dry_run: bool):
    """Delete artifact dirs. Returns summary {deleted, freed_bytes, errors}."""
    summary = {"deleted": 0, "freed_bytes": 0, "errors": 0, "skipped_missing": 0}

    try:
        artifacts_resolved = artifacts_root.resolve()
    except Exception as e:
        print(f"ERROR resolving artifacts_root {artifacts_root}: {e}", file=sys.stderr)
        summary["errors"] += 1
        return summary

    for run_id, artifacts_path in candidates:
        if artifacts_path:
            run_dir = Path(artifacts_path)
        else:
            run_dir = artifacts_root / run_id

        try:
            resolved = run_dir.resolve()
            if not str(resolved).startswith(str(artifacts_resolved)):
                print(
                    f"SKIP unsafe path {run_dir} (not inside {artifacts_root})",
                    file=sys.stderr,
                )
                summary["errors"] += 1
                continue
        except Exception as e:
            print(f"SKIP path resolve error {run_dir}: {e}", file=sys.stderr)
            summary["errors"] += 1
            continue

        if not run_dir.exists():
            print(f"SKIP missing {run_dir}")
            summary["skipped_missing"] += 1
            continue

        try:
            size = sum(f.stat().st_size for f in run_dir.rglob("*") if f.is_file())
        except Exception:
            size = 0

        action = "DRY-RUN" if dry_run else "DELETE"
        print(f"{action} run_id={run_id} path={run_dir} size={size}")

        if not dry_run:
            try:
                shutil.rmtree(run_dir)
                summary["deleted"] += 1
                summary["freed_bytes"] += size
            except Exception as e:
                print(f"ERROR deleting {run_dir}: {e}", file=sys.stderr)
                summary["errors"] += 1
        else:
            summary["deleted"] += 1
            summary["freed_bytes"] += size

    return summary


def main():
    args = parse_args()
    db_path, artifacts_root = resolve_paths(args)
    threshold_ts = time.time() - (args.age_days * 86400)

    print(f"=== Lab Cleanup started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    print(f"DB: {db_path}")
    print(f"Artifacts root: {artifacts_root}")
    print(
        f"Age threshold: {args.age_days} days (delete if started_at < "
        f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(threshold_ts))})"
    )
    print(f"Mode: {'DRY-RUN (no deletes)' if args.dry_run else 'REAL (delete artifacts)'}")
    print()

    mode, candidates = query_runs_to_cleanup(db_path, threshold_ts)
    if mode is None:
        mode = "fs"
        candidates = scan_artifacts_fs(artifacts_root, threshold_ts)
    print(f"Mode resolved: {mode.upper()}-driven")
    print(f"Candidates: {len(candidates)} run_ids")

    if not candidates:
        print("No candidates. Exit.")
        return 0

    summary = cleanup_artifacts(candidates, artifacts_root, args.dry_run)

    print()
    print("=== Summary ===")
    print(f"Deleted: {summary['deleted']}")
    print(
        f"Freed: {summary['freed_bytes']} bytes "
        f"({summary['freed_bytes']/1024/1024:.1f} MB)"
    )
    print(f"Errors: {summary['errors']}")
    print(f"Skipped missing: {summary['skipped_missing']}")

    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
