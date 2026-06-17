#!/usr/bin/env bash
# Hermes P1 Hardening — instalar pre-commit hook de deteccao de credenciais
# Usage: bash scripts/install_precommit_hook.sh
# Idempotente: re-executar nao sobrescreve se hook identico ja instalado.
# Compativel: Git bash (Windows), Linux, macOS.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
HOOK_FILE="$HOOKS_DIR/pre-commit"

if [ ! -d "$HOOKS_DIR" ]; then
    echo "ERRO: .git/hooks nao encontrado em $HOOKS_DIR"
    echo "  Executar da raiz do repositorio git."
    exit 1
fi

# Conteudo do hook
HOOK_CONTENT='#!/usr/bin/env bash
# Hermes P1 Hardening — bloqueia commit com credenciais reais
# Instalado por: scripts/install_precommit_hook.sh

CRED_PATTERN="^(OPENROUTER_API_KEY|HERMES_NIM_API_KEY|GITHUB_PERSONAL_ACCESS_TOKEN|GITHUB_WEBHOOK_SECRET|HERMES_GATEWAY_OAUTH_SECRET|HERMES_TELEGRAM_BOT_TOKEN)=.+"

STAGED_FILES=$(git diff --cached --name-only 2>/dev/null)

if [ -z "$STAGED_FILES" ]; then
    exit 0
fi

FOUND=$(echo "$STAGED_FILES" | xargs grep -lE "$CRED_PATTERN" 2>/dev/null || true)

if [ -n "$FOUND" ]; then
    echo ""
    echo "=== PRE-COMMIT BLOQUEADO ==="
    echo "ERRO: credencial REAL detectada em arquivo staged:"
    echo "$FOUND" | sed '"'"'s/^/  /'"'"'
    echo ""
    echo "Arquivos .env sao gitignored — NUNCA commitar credenciais."
    echo "Se e falso positivo (ex: .env.example vazio), checar se o valor e real."
    echo ""
    exit 1
fi

exit 0
'

# Verificar se hook identico ja existe (idempotente)
if [ -f "$HOOK_FILE" ]; then
    if grep -q "Hermes P1 Hardening" "$HOOK_FILE" 2>/dev/null; then
        echo "Pre-commit hook ja instalado (idempotente). Nenhuma acao necessaria."
        echo "  $HOOK_FILE"
        exit 0
    else
        echo "AVISO: $HOOK_FILE existe mas nao e hook Hermes."
        echo "  Backup: ${HOOK_FILE}.backup-$(date +%Y%m%d%H%M%S)"
        cp "$HOOK_FILE" "${HOOK_FILE}.backup-$(date +%Y%m%d%H%M%S)"
    fi
fi

printf '%s' "$HOOK_CONTENT" > "$HOOK_FILE"
chmod +x "$HOOK_FILE"

echo "Pre-commit hook instalado:"
echo "  $HOOK_FILE"
echo ""
echo "Credenciais monitoradas:"
echo "  OPENROUTER_API_KEY"
echo "  HERMES_NIM_API_KEY"
echo "  GITHUB_PERSONAL_ACCESS_TOKEN"
echo "  GITHUB_WEBHOOK_SECRET"
echo "  HERMES_GATEWAY_OAUTH_SECRET"
echo "  HERMES_TELEGRAM_BOT_TOKEN"
echo ""
echo "Smoke test (deve BLOQUEAR commit):"
echo "  echo 'OPENROUTER_API_KEY=sk-or-v1-testvalue123456789012345678901234567890' > /tmp/fake_cred.txt"
echo "  git add /tmp/fake_cred.txt && git commit -m 'test' # deve falhar"
echo "  git reset HEAD /tmp/fake_cred.txt && rm /tmp/fake_cred.txt"
echo ""
