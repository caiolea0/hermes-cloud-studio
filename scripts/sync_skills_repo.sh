#!/bin/bash
# F.4.4 — VM-local skills/ sync script (runs on VM, NOT via SSH from PC).
#
# Called by hermes_api.py POST /api/skills/webhook/pr-merged:
#   bash ~/hermes-cloud-studio/scripts/sync_skills_repo.sh <run_id>
# OR (if repo not yet cloned at ~/hermes-cloud-studio):
#   bash ~/.hermes/scripts/sync_skills_repo.sh <run_id>
#
# Logic:
#   1. flock(1) prevents concurrent syncs (D8 VM-side).
#   2. First run: git clone hermes-cloud-studio to ~/hermes-cloud-studio/.
#   3. Subsequent runs: git pull origin master -- skills/.
#   4. Copy changed skills/*.yaml to HERMES_HOME/skills/ (where hermes_api reads).
#
# Exit codes:
#   0  completed
#   1  conflict / stash error (conflict_manual)
#   2  fatal error (pull fail / lock busy / no PAT)
#
# stdout: JSON {"status": "...", "affected_skills": [...]}
# stderr: human-readable log messages

set -euo pipefail

RUN_ID="${1:-unknown}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
REPO_DIR="$HOME/hermes-cloud-studio"
SKILLS_SRC="$REPO_DIR/skills"
SKILLS_DST="$HERMES_HOME/skills"
LOCK_FILE="/tmp/hermes-sync.lock"
BRANCH="master"
GITHUB_REPO="caiolea0/hermes-cloud-studio"

log() { echo "[sync_skills $RUN_ID] $*" >&2; }

# ---------------------------------------------------------------------------
# Acquire exclusive lock — flock LOCK_EX non-blocking (D8 VM-side guard)
# ---------------------------------------------------------------------------
exec 9>"$LOCK_FILE"
if ! flock -xn 9; then
    log "LOCK BUSY — concurrent sync in progress"
    echo '{"status":"busy","affected_skills":[]}'
    exit 2
fi

# ---------------------------------------------------------------------------
# Clone if first run
# ---------------------------------------------------------------------------
if [ ! -d "$REPO_DIR/.git" ]; then
    PAT="${GITHUB_PERSONAL_ACCESS_TOKEN:-}"
    if [ -z "$PAT" ]; then
        log "ERRO: GITHUB_PERSONAL_ACCESS_TOKEN not set — cannot clone"
        echo '{"status":"failed","affected_skills":[]}'
        exit 2
    fi
    log "First run: cloning $GITHUB_REPO → $REPO_DIR ..."
    if ! git clone --depth=20 "https://oauth2:$PAT@github.com/$GITHUB_REPO.git" "$REPO_DIR" 2>&1; then
        log "ERRO: git clone failed"
        echo '{"status":"failed","affected_skills":[]}'
        exit 2
    fi
    log "Clone OK"
fi

cd "$REPO_DIR"

# Configure PAT for future pulls (URL-based credential, no password prompt)
PAT="${GITHUB_PERSONAL_ACCESS_TOKEN:-}"
if [ -n "$PAT" ]; then
    git remote set-url origin "https://oauth2:$PAT@github.com/$GITHUB_REPO.git" 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# Snapshot skills/ before pull
# ---------------------------------------------------------------------------
BEFORE_HASH="$(git ls-files -s skills/ 2>/dev/null | sha256sum | cut -d' ' -f1)"

# ---------------------------------------------------------------------------
# git pull — only skills/ subtree
# ---------------------------------------------------------------------------
log "git pull origin $BRANCH -- skills/ ..."
if ! git pull origin "$BRANCH" -- skills/ 2>&1; then
    log "ERRO: git pull failed"
    echo '{"status":"failed","affected_skills":[]}'
    exit 2
fi

# ---------------------------------------------------------------------------
# Snapshot after pull
# ---------------------------------------------------------------------------
AFTER_HASH="$(git ls-files -s skills/ 2>/dev/null | sha256sum | cut -d' ' -f1)"

# ---------------------------------------------------------------------------
# Copy changed skills to HERMES_HOME/skills/
# ---------------------------------------------------------------------------
AFFECTED_NAMES=""
if [ "$BEFORE_HASH" != "$AFTER_HASH" ]; then
    mkdir -p "$SKILLS_DST"
    COUNT=0
    for f in skills/*.yaml skills/*.yml; do
        [ -f "$f" ] || continue
        cp "$f" "$SKILLS_DST/"
        BNAME="$(basename "$f" .yaml)"
        BNAME="$(basename "$BNAME" .yml)"
        AFFECTED_NAMES="${AFFECTED_NAMES:+$AFFECTED_NAMES,}\"$BNAME\""
        COUNT=$((COUNT + 1))
    done
    log "Synced $COUNT skills → $SKILLS_DST"
else
    log "No changes in skills/"
fi

echo "{\"status\":\"completed\",\"affected_skills\":[$AFFECTED_NAMES]}"
exit 0
