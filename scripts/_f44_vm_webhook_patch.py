"""F.4.4 FIX — Patch hermes_api.py on VM to add skills webhook endpoint.

Usage (from PC):
    scp scripts/_f44_vm_webhook_patch.py hermes-gcp@136.115.74.69:/tmp/
    ssh hermes-gcp@136.115.74.69 'python3 /tmp/_f44_vm_webhook_patch.py'

This script reads ~/.hermes/scripts/hermes_api.py, inserts the
POST /api/skills/webhook/pr-merged endpoint before the __main__ block,
and writes the file back.

Run once — idempotent check prevents double-patching.
"""
import os
import sys
from pathlib import Path

TARGET = Path.home() / ".hermes" / "scripts" / "hermes_api.py"

content = TARGET.read_text(encoding="utf-8")

# Idempotency guard
if "/api/skills/webhook/pr-merged" in content:
    print("ALREADY PATCHED — skipping.")
    sys.exit(0)

ENDPOINT_CODE = '''
# ---------------------------------------------------------------------------
# F.4.4 FIX 2026-06-16 — GitHub webhook: POST /api/skills/webhook/pr-merged
# ---------------------------------------------------------------------------
import hashlib as _f44_hl
import hmac as _f44_hmac
import ipaddress as _f44_ip
import uuid as _f44_uuid

_F44_GH_RANGES = [
    # IPv4
    _f44_ip.ip_network("140.82.112.0/20"),
    _f44_ip.ip_network("192.30.252.0/22"),
    _f44_ip.ip_network("185.199.108.0/22"),
    _f44_ip.ip_network("143.55.64.0/20"),
    # IPv6 (W10)
    _f44_ip.ip_network("2a0a:a440::/29"),
    _f44_ip.ip_network("2606:50c0::/32"),
]
_f44_table_ensured = False

import re as _f44_re

_F44_SENSITIVE_PATTERNS = [
    (_f44_re.compile(r"ghp_[a-zA-Z0-9]{10,}"), "[REDACTED_GHP]"),
    (_f44_re.compile(r"github_pat_[a-zA-Z0-9_]{10,}", _f44_re.IGNORECASE), "[REDACTED_PAT]"),
    (_f44_re.compile(r"oauth2:[^@\\s]+@"), "oauth2:[REDACTED]@"),
    (_f44_re.compile(r"GITHUB_WEBHOOK_SECRET=\\S+", _f44_re.IGNORECASE), "GITHUB_WEBHOOK_SECRET=[REDACTED]"),
]


def _f44_scrub(text: str) -> str:
    for pat, rep in _F44_SENSITIVE_PATTERNS:
        text = pat.sub(rep, text)
    return text


def _f44_verify_sig(body: bytes, sig: str, secret: str) -> bool:
    if not sig or not sig.startswith("sha256="):
        return False
    expected = "sha256=" + _f44_hmac.new(secret.encode(), body, _f44_hl.sha256).hexdigest()
    return _f44_hmac.compare_digest(expected, sig)


def _f44_client_ip(request) -> str:
    ip = (
        request.headers.get("cf-connecting-ip", "") or
        (request.headers.get("x-forwarded-for", "").split(",")[0]).strip() or
        (request.client.host if request.client else "")
    )
    return ip.strip() or "unknown"


def _f44_ip_ok(ip: str) -> bool:
    try:
        addr = _f44_ip.ip_address(ip)
        return any(addr in net for net in _F44_GH_RANGES)
    except ValueError:
        return False


def _f44_ensure_table():
    conn = get_db()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS skill_sync_runs (
                id TEXT PRIMARY KEY,
                trigger_type TEXT NOT NULL,
                pr_number INTEGER,
                pr_url TEXT,
                sync_status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                error_message TEXT,
                affected_skills TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_skill_sync_runs_status
                ON skill_sync_runs(sync_status);
            CREATE INDEX IF NOT EXISTS idx_skill_sync_runs_started_at
                ON skill_sync_runs(started_at);
        """)
        conn.commit()
    finally:
        conn.close()


def _f44_run_sync(run_id: str):
    import subprocess as _sub
    # Script lives at ~/.hermes/scripts/ or ~/hermes-cloud-studio/scripts/
    script = HERMES_HOME / "scripts" / "sync_skills_repo.sh"
    if not script.exists():
        script = Path.home() / "hermes-cloud-studio" / "scripts" / "sync_skills_repo.sh"
    env = {**os.environ, "HERMES_HOME": str(HERMES_HOME)}
    try:
        result = _sub.run(
            ["bash", str(script), run_id],
            capture_output=True, text=True, timeout=120, env=env,
        )
    except _sub.TimeoutExpired:
        return "failed", [], "sync timed out after 120s"
    except Exception as exc:
        return "failed", [], _f44_scrub(str(exc))

    if result.returncode == 0:
        try:
            import json as _js
            data = _js.loads(result.stdout.strip())
            return data.get("status", "completed"), data.get("affected_skills", []), None
        except Exception:
            return "completed", [], None
    elif result.returncode == 1:
        return "conflict_manual", [], (result.stderr.strip() or "conflict")
    else:
        return "failed", [], (result.stderr.strip() or f"exit {result.returncode}")


@app.post("/api/skills/webhook/pr-merged")
async def skills_webhook_pr_merged(request: Request):
    """F.4.4 — GitHub webhook: sync skills/ on PR merge (HMAC + IP secured)."""
    global _f44_table_ensured
    if not _f44_table_ensured:
        _f44_ensure_table()
        _f44_table_ensured = True

    body = await request.body()

    # HMAC SHA-256 validation — D7 (skip if secret not configured)
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if secret:
        sig = request.headers.get("x-hub-signature-256", "")
        if not _f44_verify_sig(body, sig, secret):
            raise HTTPException(401, "Invalid X-Hub-Signature-256")

    # GitHub IP allowlist — D7
    client_ip = _f44_client_ip(request)
    if not _f44_ip_ok(client_ip):
        raise HTTPException(403, "IP not in GitHub allowlist")

    try:
        import json as _pj
        payload = _pj.loads(body)
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    pr = payload.get("pull_request", {})
    if payload.get("action") != "closed" or not pr.get("merged", False):
        return {"status": "skipped", "reason": "not_merged_pr"}

    if payload.get("_skills_changed", True) is False:
        return {"status": "skipped", "reason": "no_skills_changed"}

    # W3 — X-GitHub-Delivery dedup: same UUID on retry → return cached result
    delivery_id = request.headers.get("x-github-delivery") or None
    if delivery_id:
        conn = get_db()
        try:
            _dup = conn.execute(
                "SELECT id, sync_status FROM skill_sync_runs WHERE delivery_id = ? LIMIT 1",
                (delivery_id,),
            ).fetchone()
        finally:
            conn.close()
        if _dup:
            return {"status": "duplicate", "existing_run_id": _dup[0], "sync_status": _dup[1]}

    run_id = str(_f44_uuid.uuid4())
    pr_number = pr.get("number")
    pr_url = pr.get("html_url", "")
    started_at = datetime.now(timezone.utc).isoformat()

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO skill_sync_runs (id, trigger_type, pr_number, pr_url, sync_status, started_at, delivery_id) "
            "VALUES (?,?,?,?,?,?,?)",
            (run_id, "webhook", pr_number, pr_url, "started", started_at, delivery_id),
        )
        conn.commit()
    finally:
        conn.close()

    # Run sync in thread pool (blocking subprocess)
    loop = asyncio.get_event_loop()
    t0 = time.time()
    sync_status, affected_skills, error_msg = await loop.run_in_executor(
        None, _f44_run_sync, run_id
    )
    latency_ms = int((time.time() - t0) * 1000)

    completed_at = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        import json as _uj
        conn.execute(
            "UPDATE skill_sync_runs SET sync_status=?, completed_at=?, error_message=?, affected_skills=? WHERE id=?",
            (sync_status, completed_at, error_msg, _uj.dumps(affected_skills), run_id),
        )
        conn.commit()
    finally:
        conn.close()

    # Push event to PC (fire-and-forget)
    try:
        import httpx as _hx
        import json as _ej
        _pc_url = PC_EVENT_URL.replace(
            "/api/internal/linkedin/event",
            "/api/internal/skill-sync/event",
        )
        async with _hx.AsyncClient(timeout=3.0) as _cli:
            await _cli.post(_pc_url, json={
                "type": "brain.skill_sync_completed",
                "run_id": run_id,
                "pr_number": pr_number,
                "sync_status": sync_status,
                "affected_skills": affected_skills,
                "latency_ms": latency_ms,
            })
    except Exception:
        pass

    return {
        "status": sync_status,
        "run_id": run_id,
        "pr_number": pr_number,
        "affected_skills": affected_skills,
        "latency_ms": latency_ms,
    }

'''

# Insert before "if __name__"
MAIN_MARKER = '\nif __name__ == "__main__":'
idx = content.rfind(MAIN_MARKER)
if idx == -1:
    print("ERROR: could not find __main__ block in target file")
    sys.exit(1)

new_content = content[:idx] + ENDPOINT_CODE + content[idx:]
TARGET.write_text(new_content, encoding="utf-8")
print(f"PATCHED: {TARGET} (+{len(ENDPOINT_CODE)} chars, endpoint inserted at byte {idx})")
