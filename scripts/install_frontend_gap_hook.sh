#!/usr/bin/env bash
# Hermes P4 Hardening — install frontend-gap auto-refresh block in pre-commit hook.
# Usage: bash scripts/install_frontend_gap_hook.sh
# Idempotent: re-running does nothing if P4 block already present.
# Compatible: Git Bash (Windows), Linux, macOS.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
HOOK_FILE="$HOOKS_DIR/pre-commit"

if [ ! -d "$HOOKS_DIR" ]; then
    echo "ERROR: .git/hooks not found at $HOOKS_DIR"
    echo "  Run from repository root."
    exit 1
fi

# Idempotent guard
if [ -f "$HOOK_FILE" ] && grep -q "P4 Hardening: frontend-gap" "$HOOK_FILE" 2>/dev/null; then
    echo "[install_frontend_gap_hook] Already installed (idempotent). No action needed."
    echo "  $HOOK_FILE"
    exit 0
fi

P4_BLOCK='
# --- P4 Hardening: frontend-gap auto-refresh ---
# Re-run skill if routes or frontend files change; auto-stage FRONTEND-GAP.md update.
ROUTE_CHANGED=$(git diff --cached --name-only 2>/dev/null | grep -E '"'"'^(api/|vm_api/|server\.py|hermes_api_v2\.py|dashboard/app\.js)'"'"' || true)

if [ -n "$ROUTE_CHANGED" ]; then
    REPO_ROOT="$(git rev-parse --show-toplevel)"
    SKILL_DIR="$REPO_ROOT/.claude/skills/hermes-frontend-gap/scripts"
    echo "[frontend-gap] Route/frontend change detected -- refreshing FRONTEND-GAP.md..."
    if python "$SKILL_DIR/parse_routes.py" 2>/dev/null \
       && python "$SKILL_DIR/grep_frontend.py" 2>/dev/null \
       && python "$SKILL_DIR/rank_gaps.py" 2>/dev/null; then
        git add "$REPO_ROOT/.claude/FRONTEND-GAP.md" \
                "$REPO_ROOT/.claude/frontend-gap/routes.json" \
                "$REPO_ROOT/.claude/frontend-gap/frontend-consumption.json" \
                "$REPO_ROOT/.claude/frontend-gap/ws-events.json" \
                "$REPO_ROOT/.claude/frontend-gap/diff-vs-known.md" 2>/dev/null || true
        echo "[frontend-gap] FRONTEND-GAP.md refreshed and staged."
    else
        echo "[frontend-gap] WARN: skill refresh failed -- FRONTEND-GAP.md may be stale."
        echo "  Re-run manually: python .claude/skills/hermes-frontend-gap/scripts/rank_gaps.py"
    fi
fi
'

if [ -f "$HOOK_FILE" ]; then
    # Append P4 block before final `exit 0`
    if grep -q "^exit 0" "$HOOK_FILE"; then
        # Insert P4 block before last `exit 0`
        TMP=$(mktemp)
        awk '/^exit 0/{if(!found){print p; found=1} p=""} {p=$0} END{if(!found)print p}' \
            p="$P4_BLOCK" "$HOOK_FILE" > "$TMP" 2>/dev/null || true
        # Fallback: simple append before exit 0
        python3 -c "
import re, sys
content = open('$HOOK_FILE').read()
block = open('/dev/stdin').read()
# Insert before last 'exit 0'
content = re.sub(r'\nexit 0\s*$', '\n' + block.strip() + '\n\nexit 0\n', content, flags=re.DOTALL)
open('$HOOK_FILE', 'w').write(content)
" <<< "$P4_BLOCK" 2>/dev/null || {
            # Simplest fallback: remove last exit 0 and append
            head -n -1 "$HOOK_FILE" > "$TMP"
            echo "$P4_BLOCK" >> "$TMP"
            echo "exit 0" >> "$TMP"
            cp "$TMP" "$HOOK_FILE"
        }
        rm -f "$TMP"
    else
        echo "$P4_BLOCK" >> "$HOOK_FILE"
        echo "exit 0" >> "$HOOK_FILE"
    fi
else
    # Create hook from scratch with P4 block
    cat > "$HOOK_FILE" << 'HOOKEOF'
#!/usr/bin/env bash
# Hermes pre-commit hook
HOOKEOF
    echo "$P4_BLOCK" >> "$HOOK_FILE"
    echo "exit 0" >> "$HOOK_FILE"
fi

chmod +x "$HOOK_FILE"

echo "[install_frontend_gap_hook] P4 frontend-gap block installed:"
echo "  $HOOK_FILE"
echo ""
echo "Smoke test:"
echo "  touch api/_test.py && git add api/_test.py"
echo "  bash .git/hooks/pre-commit  # should print [frontend-gap] and refresh"
echo "  git reset HEAD api/_test.py && rm api/_test.py"
echo ""
