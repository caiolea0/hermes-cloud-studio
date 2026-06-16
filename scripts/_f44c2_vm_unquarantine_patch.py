"""F.4.4 C2 FIX — Patch hermes_api.py on VM to add unquarantine endpoint.

Usage (from PC):
    scp scripts/_f44c2_vm_unquarantine_patch.py hermes-gcp@136.115.74.69:/tmp/
    ssh hermes-gcp@136.115.74.69 'python3 /tmp/_f44c2_vm_unquarantine_patch.py'

Idempotency guard: skips if '/api/skills/' + '{name}' + '/unquarantine' already in file.
"""
import sys
from pathlib import Path

TARGET = Path.home() / ".hermes" / "scripts" / "hermes_api.py"
content = TARGET.read_text(encoding="utf-8")

if "/unquarantine" in content:
    print("ALREADY PATCHED — skipping.")
    sys.exit(0)

ENDPOINT_CODE = '''
# ---------------------------------------------------------------------------
# F.4.4 C2 2026-06-16 — POST /api/skills/{name}/unquarantine (D5)
# ---------------------------------------------------------------------------
import shutil as _f44c2_shutil

@app.post("/api/skills/{skill_name}/unquarantine")
async def skills_unquarantine(skill_name: str, request: Request):
    """F.4.4 C2 — Restore a quarantined skill YAML from _quarantine/ to skills/."""
    HERMES_HOME_PATH = Path.home() / ".hermes"
    skills_dir = HERMES_HOME_PATH / "skills"
    quarantine_dir = skills_dir / "_quarantine"

    src_yaml = quarantine_dir / f"{skill_name}.yaml"
    src_yml = quarantine_dir / f"{skill_name}.yml"
    src = src_yaml if src_yaml.exists() else (src_yml if src_yml.exists() else None)

    if src is None:
        raise HTTPException(404, f"Skill '{skill_name}' not found in quarantine dir")

    dest = skills_dir / src.name
    if dest.exists():
        raise HTTPException(409, f"Conflict: {dest} already exists in skills/")

    # Non-blocking lock check (shared with webhook + quarantine cron)
    import fcntl as _f44c2_fcntl
    lock_fd = open("/tmp/hermes-sync.lock", "w")
    try:
        _f44c2_fcntl.flock(lock_fd, _f44c2_fcntl.LOCK_EX | _f44c2_fcntl.LOCK_NB)
    except BlockingIOError:
        lock_fd.close()
        raise HTTPException(409, "Sync lock busy — retry after 30s")

    try:
        _f44c2_shutil.move(str(src), str(dest))
    finally:
        _f44c2_fcntl.flock(lock_fd, _f44c2_fcntl.LOCK_UN)
        lock_fd.close()

    import uuid as _f44c2_uuid
    import json as _f44c2_json
    run_id = str(_f44c2_uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    body_raw = await request.body()
    try:
        unquarantine_reason = _f44c2_json.loads(body_raw).get("reason", "manual_unquarantine")
    except Exception:
        unquarantine_reason = "manual_unquarantine"

    conn = get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO skill_sync_runs "
            "(id, trigger_type, sync_status, started_at, completed_at, error_message, affected_skills) "
            "VALUES (?, 'manual_unquarantine', 'unquarantined', ?, ?, ?, ?)",
            (run_id, started_at, started_at, unquarantine_reason, _f44c2_json.dumps([skill_name])),
        )
        conn.commit()
    finally:
        conn.close()

    # Fire-and-forget push to PC
    try:
        import httpx as _hx
        _pc_url = PC_EVENT_URL.replace(
            "/api/internal/linkedin/event",
            "/api/internal/skill-sync/event",
        )
        async with _hx.AsyncClient(timeout=3.0) as _cli:
            await _cli.post(_pc_url, json={
                "type": "brain.skill_unquarantined",
                "skill_name": skill_name,
                "reason": unquarantine_reason,
                "run_id": run_id,
            })
    except Exception:
        pass

    return {
        "status": "ok",
        "skill_name": skill_name,
        "restored_to": str(dest),
        "run_id": run_id,
    }

'''

MAIN_MARKER = '\nif __name__ == "__main__":'
idx = content.rfind(MAIN_MARKER)
if idx == -1:
    print("ERROR: could not find __main__ block")
    sys.exit(1)

new_content = content[:idx] + ENDPOINT_CODE + content[idx:]
TARGET.write_text(new_content, encoding="utf-8")
print(f"PATCHED: {TARGET} (+{len(ENDPOINT_CODE)} chars)")
