"""F.4.4 C1 → MOVED TO VM — F.4.4 FIX 2026-06-16.

GitHub webhook endpoint was originally deployed on PC (server.py) but GitHub
cannot reach PC behind NAT. Moved to VM hermes_api.py which is publicly
accessible via Cloudflare tunnel (hermes-prod, port 8420).

PC server.py no longer includes this router (see server.py F.4.4 FIX comment).
This file kept for reference + future local-test use. VM endpoint is the
source of truth.

Original F.4.4 C1 — GitHub webhook endpoint: POST /api/skills/webhook/pr-merged.

Security (D7):
  - HMAC SHA-256 hmac.compare_digest constant-time (skipped if secret not configured)
  - IP allowlist: 6 GitHub CIDR ranges (4 IPv4 + 2 IPv6). Handles CF-Connecting-IP.
  - SlowAPI 60/minute rate-limit (REUSE core.limiter pattern F.5.3).

Sync flow (D2, D8):
  - W1: asyncio.Lock DEPRECATED — lost on process restart. Replaced by DB flag check
    (_is_sync_in_progress). VM uses fcntl.flock /tmp/hermes-sync.lock (cross-process).
  - W3: X-GitHub-Delivery dedup — duplicate delivery_id returns 200 without re-syncing.
  - SSH subprocess runs sync_skills_repo.sh on VM: git stash + pull + stash pop.
  - Conflict → sync_status='conflict_manual' + WS alert (NÃO auto-force-pop).

Fanout (D6):
  - skill_sync_runs DB row (audit trail, delivery_id for dedup).
  - WS broadcast brain.skill_sync_completed.
  - Sentry breadcrumb + capture on conflict/failure (W6: secrets scrubbed).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac as hmac_mod
import ipaddress
import json
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from core.limiter import limiter
from core.skill_proposals import (
    ensure_skill_sync_runs_table,
    get_skill_sync_run_by_delivery_id,
    insert_skill_sync_run,
    update_skill_sync_run,
)
from core.state import ws_manager

router = APIRouter()

# GitHub webhook delivery IP ranges (https://api.github.com/meta — webhooks field).
# W10: includes IPv6 ranges added by GitHub in 2024; _ip_in_github_ranges() handles both families.
_GH_IP_RANGES: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    # IPv4
    ipaddress.ip_network("140.82.112.0/20"),
    ipaddress.ip_network("192.30.252.0/22"),
    ipaddress.ip_network("185.199.108.0/22"),
    ipaddress.ip_network("143.55.64.0/20"),
    # IPv6 (W10)
    ipaddress.ip_network("2a0a:a440::/29"),
    ipaddress.ip_network("2606:50c0::/32"),
]

_VM_USER = "hermes-gcp"
_VM_HOST = "136.115.74.69"
_SYNC_SCRIPT = "~/hermes-cloud-studio/scripts/sync_skills_repo.sh"


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

def _verify_signature(body: bytes, signature: str, secret: str) -> bool:
    """Constant-time HMAC SHA-256 comparison (D7). Returns True on match."""
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac_mod.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac_mod.compare_digest(expected, signature)


def _ip_in_github_ranges(ip_str: str) -> bool:
    """Return True if ip_str is within GitHub webhook CIDR ranges — IPv4 and IPv6 (D7/W10)."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in net for net in _GH_IP_RANGES)


def _is_sync_in_progress() -> bool:
    """W1: DB-based concurrency check — survives process restart (replaces asyncio.Lock).

    Checks skill_sync_runs for a 'started' row without completed_at.
    The row is inserted BEFORE the sync begins, so concurrent requests see it immediately.
    VM uses fcntl.flock /tmp/hermes-sync.lock for process-level exclusion.
    """
    try:
        conn = _local_connect()
        row = conn.execute(
            """SELECT 1 FROM skill_sync_runs
               WHERE sync_status = 'started' AND completed_at IS NULL LIMIT 1"""
        ).fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def _local_connect():
    """Open DB connection to local hermes_local.db for concurrency flag check."""
    import sqlite3 as _sqlite3
    from core.state import DB_PATH
    conn = _sqlite3.connect(str(DB_PATH), timeout=5.0)
    return conn


def _get_client_ip(request: Request) -> str:
    """Extract real sender IP — handles Cloudflare tunnel forwarding headers."""
    cf_ip = request.headers.get("cf-connecting-ip", "").strip()
    if cf_ip:
        return cf_ip
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


# ---------------------------------------------------------------------------
# VM sync
# ---------------------------------------------------------------------------

def _run_sync_on_vm(run_id: str) -> tuple[str, list[str], Optional[str]]:
    """SSH into VM and run sync_skills_repo.sh. Blocking — called via asyncio.to_thread.

    Returns (sync_status, affected_skills, error_message).
    Exit codes from shell: 0 = completed, 1 = conflict_manual, 2 = pull failure.
    Stdout is JSON: {"status": "...", "affected_skills": [...]}
    """
    cmd = [
        "ssh",
        "-T",
        "-o", "ConnectTimeout=30",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=no",
        f"{_VM_USER}@{_VM_HOST}",
        f"bash {_SYNC_SCRIPT} {run_id}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode == 0:
            try:
                data = json.loads(stdout)
                return (
                    data.get("status", "completed"),
                    data.get("affected_skills", []),
                    None,
                )
            except json.JSONDecodeError:
                return "completed", [], None
        elif result.returncode == 1:
            return "conflict_manual", [], stderr or "git stash pop conflict — resolve manually"
        else:
            return "failed", [], stderr or f"sync_skills_repo.sh exited {result.returncode}"
    except subprocess.TimeoutExpired:
        return "failed", [], "SSH sync timed out after 120s"
    except Exception as exc:  # noqa: BLE001
        return "failed", [], str(exc)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/api/skills/webhook/pr-merged")
@limiter.limit("60/minute")
async def webhook_pr_merged(request: Request) -> JSONResponse:
    """Receive GitHub 'pull_request' webhook; sync skills/ on VM when PR merged."""
    body = await request.body()

    # Lazy settings import avoids circular imports
    from config import settings  # noqa: PLC0415

    webhook_secret: str = getattr(settings, "github_webhook_secret", "") or ""

    # D7 — HMAC SHA-256 (only enforced when secret is configured)
    if webhook_secret:
        signature = request.headers.get("x-hub-signature-256", "")
        if not _verify_signature(body, signature, webhook_secret):
            _sentry_warn("Webhook HMAC validation failed", {"ip": _get_client_ip(request)})
            raise HTTPException(status_code=401, detail="Invalid X-Hub-Signature-256")

    # D7 — IP allowlist (GitHub CIDR ranges)
    client_ip = _get_client_ip(request)
    if not _ip_in_github_ranges(client_ip):
        _sentry_warn("Webhook IP not in GitHub ranges", {"ip": client_ip})
        raise HTTPException(status_code=403, detail="IP not in GitHub allowlist")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Only act on merged PR close events
    action = payload.get("action", "")
    pr = payload.get("pull_request", {})
    if action != "closed" or not pr.get("merged", False):
        return JSONResponse({"status": "skipped", "reason": "not_merged_pr"})

    pr_number: Optional[int] = pr.get("number")
    pr_url: str = pr.get("html_url", "")

    # Fast-path: _skills_changed is an INTERNAL convention — NOT a GitHub-native field.
    # Caller (e.g. future /api/skills/webhook/sync-now) can inject False to skip sync
    # without relying on the shell-side git diff. Default True means "assume changed".
    # W4: documented here; see PLAN.md F.4.4 D8 invariant for rationale.
    if payload.get("_skills_changed", True) is False:
        return JSONResponse({"status": "skipped", "reason": "no_skills_changed"})

    ensure_skill_sync_runs_table()

    # W3 — X-GitHub-Delivery dedup: same delivery_id on retry → return cached result
    delivery_id: Optional[str] = request.headers.get("x-github-delivery") or None
    if delivery_id:
        existing_run = get_skill_sync_run_by_delivery_id(delivery_id)
        if existing_run:
            return JSONResponse({
                "status": "duplicate",
                "existing_run_id": existing_run["id"],
                "sync_status": existing_run["sync_status"],
            })

    # W1 — DB-based concurrency check (replaces asyncio.Lock lost on process restart)
    if _is_sync_in_progress():
        return JSONResponse(
            {"status": "busy", "reason": "sync_in_progress"},
            status_code=409,
            headers={"Retry-After": "30"},
        )

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    insert_skill_sync_run(
        run_id=run_id,
        trigger_type="webhook",
        pr_number=pr_number,
        pr_url=pr_url,
        started_at=started_at,
        delivery_id=delivery_id,
    )

    t0 = datetime.now(timezone.utc)
    sync_status, affected_skills, error_msg = await asyncio.to_thread(
        _run_sync_on_vm, run_id
    )
    latency_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)

    completed_at = datetime.now(timezone.utc).isoformat()
    update_skill_sync_run(
        run_id,
        sync_status=sync_status,
        completed_at=completed_at,
        error_message=error_msg,
        affected_skills=json.dumps(affected_skills),
    )

    # D6 — WS broadcast
    try:
        await ws_manager.broadcast({
            "event_type": "brain.skill_sync_completed",
            "run_id": run_id,
            "pr_number": pr_number,
            "sync_status": sync_status,
            "affected_skills": affected_skills,
            "latency_ms": latency_ms,
        })
    except Exception:  # noqa: BLE001 — broadcast must never block response
        pass

    # D6 — Sentry (W6: scrub secrets from error strings before capture)
    safe_error = _scrub_sensitive(error_msg) if error_msg else None
    _sentry_breadcrumb(
        message=f"PR #{pr_number} skill sync {sync_status}",
        data={"run_id": run_id, "latency_ms": latency_ms},
    )
    if sync_status == "conflict_manual":
        _sentry_warn(
            f"Skill sync conflict PR #{pr_number} — manual stash pop required",
            {"run_id": run_id, "error": safe_error},
        )

    return JSONResponse({
        "status": sync_status,
        "run_id": run_id,
        "pr_number": pr_number,
        "affected_skills": affected_skills,
        "latency_ms": latency_ms,
    })


# ---------------------------------------------------------------------------
# Sentry helpers (graceful — sentry_sdk optional)
# ---------------------------------------------------------------------------

import re as _re

_SENSITIVE_PATTERNS = [
    # GitHub PATs (classic + fine-grained)
    (_re.compile(r"ghp_[a-zA-Z0-9]{10,}"), "[REDACTED_GHP]"),
    (_re.compile(r"github_pat_[a-zA-Z0-9_]{10,}", _re.IGNORECASE), "[REDACTED_PAT]"),
    # oauth2:token@host in clone URLs
    (_re.compile(r"oauth2:[^@\s]+@"), "oauth2:[REDACTED]@"),
    # GITHUB_WEBHOOK_SECRET=value (in env dumps / error strings)
    (_re.compile(r"GITHUB_WEBHOOK_SECRET=\S+", _re.IGNORECASE), "GITHUB_WEBHOOK_SECRET=[REDACTED]"),
]


def _scrub_sensitive(text: str) -> str:
    """W6: scrub secret-like tokens from strings before Sentry capture."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _sentry_warn(message: str, extras: dict | None = None) -> None:
    from core.sentry_via_gateway import capture_message_with_extras
    capture_message_with_extras(message, extras or {}, level="warning", requester="brain-f4-webhook")


def _sentry_breadcrumb(message: str, data: dict | None = None) -> None:
    from core.sentry_via_gateway import add_breadcrumb
    add_breadcrumb(category="skill_sync", message=message, level="info", data=data or {})
