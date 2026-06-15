#!/bin/bash
# F.4.4 C1 — VM-side skills/ sync script (D2: git stash + pull + pop).
#
# Called by api/skills_webhook.py via SSH:
#   ssh hermes-gcp@VM 'bash ~/hermes-cloud-studio/scripts/sync_skills_repo.sh <run_id>'
#
# Exit codes:
#   0  — completed (JSON to stdout with affected_skills)
#   1  — conflict during stash pop (conflict_manual)
#   2  — git pull failure
#
# Lock: flock(1) on LOCK_FILE prevents concurrent runs (D8 VM-side guard).
#   cf. fcntl.LOCK_EX pattern — same semantics, POSIX shell equivalent.

set -euo pipefail

RUN_ID="${1:-unknown}"
REPO_DIR="${HERMES_HOME:-$HOME/.hermes}/../hermes-cloud-studio"
REPO_DIR="$(realpath "$HOME/hermes-cloud-studio" 2>/dev/null || echo "$HOME/hermes-cloud-studio")"
LOCK_FILE="/tmp/hermes-sync.lock"
BRANCH="master"

log() { echo "[sync_skills] $*" >&2; }

# ---------------------------------------------------------------------------
# Acquire exclusive lock (non-blocking). Exit 2 if already locked.
# flock -xn: exclusive + non-blocking (cf. fcntl.LOCK_EX | LOCK_NB)
# ---------------------------------------------------------------------------
exec 9>"$LOCK_FILE"
if ! flock -xn 9; then
    log "LOCK BUSY — another sync in progress (run_id=$RUN_ID)"
    echo '{"status":"busy","affected_skills":[]}'
    exit 2
fi

cd "$REPO_DIR" || { log "ERRO: repo_dir nao encontrado: $REPO_DIR"; exit 2; }

# ---------------------------------------------------------------------------
# Snapshot skills/ before pull to compute diff later
# ---------------------------------------------------------------------------
BEFORE_HASH="$(git ls-files -s skills/ | git hash-object --stdin 2>/dev/null || echo 'none')"

# ---------------------------------------------------------------------------
# git stash (only if skills/ is dirty)
# ---------------------------------------------------------------------------
STASH_APPLIED=0
if ! git diff --quiet -- skills/ 2>/dev/null || ! git diff --cached --quiet -- skills/ 2>/dev/null; then
    STASH_MSG="auto-pull-stash-$(date +%s)-${RUN_ID}"
    log "skills/ dirty — stashing: $STASH_MSG"
    git stash push -m "$STASH_MSG" -- skills/ || true
    STASH_APPLIED=1
fi

# ---------------------------------------------------------------------------
# git pull
# ---------------------------------------------------------------------------
log "pulling origin/$BRANCH skills/ ..."
if ! git pull origin "$BRANCH" -- skills/ 2>&1; then
    log "ERRO: git pull falhou"
    # Restore stash if we pushed one
    if [ "$STASH_APPLIED" -eq 1 ]; then
        git stash pop --index 2>/dev/null || true
    fi
    exit 2
fi

# ---------------------------------------------------------------------------
# git stash pop
# ---------------------------------------------------------------------------
CONFLICT=0
if [ "$STASH_APPLIED" -eq 1 ]; then
    log "restoring stash ..."
    if ! git stash pop --index 2>/dev/null; then
        log "CONFLITO: stash pop falhou — intervenção manual necessária"
        CONFLICT=1
    fi
fi

# ---------------------------------------------------------------------------
# Compute affected skills (files changed between before/after)
# ---------------------------------------------------------------------------
AFTER_HASH="$(git ls-files -s skills/ | git hash-object --stdin 2>/dev/null || echo 'none')"

AFFECTED_SKILLS="[]"
if [ "$BEFORE_HASH" != "$AFTER_HASH" ]; then
    # List YAML files changed in skills/
    CHANGED="$(git diff HEAD~1 --name-only -- 'skills/*.yaml' 'skills/*.yml' 2>/dev/null || true)"
    if [ -n "$CHANGED" ]; then
        # Build JSON array of basenames without extension
        NAMES=""
        while IFS= read -r f; do
            [ -z "$f" ] && continue
            BASE="$(basename "$f" .yaml)"
            BASE="$(basename "$BASE" .yml)"
            NAMES="${NAMES:+$NAMES,}\"$BASE\""
        done <<< "$CHANGED"
        AFFECTED_SKILLS="[$NAMES]"
    fi
fi

# ---------------------------------------------------------------------------
# Reload skills service (idempotent — ignore failure if service not running)
# ---------------------------------------------------------------------------
systemctl --user reload hermes-mcps-skills.service 2>/dev/null \
    || systemctl --user restart hermes-mcps-skills.service 2>/dev/null \
    || true

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
if [ "$CONFLICT" -eq 1 ]; then
    echo "{\"status\":\"conflict_manual\",\"affected_skills\":$AFFECTED_SKILLS}"
    exit 1
fi

echo "{\"status\":\"completed\",\"affected_skills\":$AFFECTED_SKILLS}"
exit 0
