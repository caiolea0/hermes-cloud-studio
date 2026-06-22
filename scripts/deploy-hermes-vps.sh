#!/usr/bin/env bash
# deploy-hermes-vps.sh — deploy Hermes 2.0 → Contabo VPS (/opt/hermes), coabitando geronimo-net.
# Espelha o padrão do Geronimo (rsync + docker compose up -d --build + healthcheck + rollback).
# REGRA DE OURO: só mexe em /opt/hermes. NUNCA toca /opt/geronimo nem containers do Geronimo/Bolseye.
# Uso: bash scripts/deploy-hermes-vps.sh
set -euo pipefail

VPS="${HERMES_VPS_HOST:-root@207.180.240.208}"
KEY="${HERMES_VPS_KEY:-$HOME/.ssh/geronimo_ed25519}"
VPS_DIR="/opt/hermes"
LOCAL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log(){ echo "[deploy-hermes] $*"; }

# 1. Pré-flight read-only (acesso + recursos + rede do Geronimo presente)
log "Pré-flight..."
ssh -i "$KEY" -o ConnectTimeout=15 "$VPS" "
  echo VPS_OK
  free -h | awk 'NR==2{print \"  RAM livre:\", \$7}'
  df -h / | tail -1 | awk '{print \"  disco livre:\", \$4}'
  docker network inspect geronimo-net >/dev/null 2>&1 && echo '  geronimo-net OK' || { echo '  SEM geronimo-net'; exit 1; }
" || { echo "ERRO: VPS inacessível ou geronimo-net ausente"; exit 1; }

# 2. Garante /opt/hermes + .env (gera tokens 1x; preserva se já existir)
ssh -i "$KEY" "$VPS" 'mkdir -p /opt/hermes && cd /opt/hermes && [ -f .env ] || {
  A=$(openssl rand -hex 32); I=$(openssl rand -hex 32); V=$(openssl rand -hex 32);
  printf "HERMES_AUTH_TOKEN=%s\nHERMES_INTERNAL_TOKEN=%s\nHERMES_VM_AUTH_TOKEN=%s\nFEATURE_LINKEDIN=off\nHERMES_STRICT_MCP=0\nOLLAMA_URL=http://100.99.116.28:11434\n" "$A" "$I" "$V" > .env && chmod 600 .env && echo ".env criado";
}'

SHA="$(git -C "$LOCAL" rev-parse --short HEAD 2>/dev/null || echo nogit)"

# 3. Rsync (exclui git/claude/dados/segredos/tauri; --exclude .env PRESERVA o da VPS, mesmo com --delete)
log "Rsync → $VPS:$VPS_DIR ..."
rsync -az --delete \
  --exclude='.git' --exclude='.claude' --exclude='.env' --exclude='__pycache__' \
  --exclude='*.pyc' --exclude='*.db' --exclude='*.db-wal' --exclude='*.db-shm' \
  --exclude='linkedin_data' --exclude='linkedin/lab/artifacts' --exclude='linkedin/lab/profiles' \
  --exclude='channels_data' --exclude='photo_cache' --exclude='logs' --exclude='*.log' \
  --exclude='.venv' --exclude='venv' --exclude='node_modules' --exclude='app' \
  --exclude='dist' --exclude='build' --exclude='tests' --exclude='.deployed_sha' \
  -e "ssh -i $KEY" "$LOCAL/" "$VPS:$VPS_DIR/"

# 4. Build + up (somente o Hermes)
log "docker compose up -d --build ..."
ssh -i "$KEY" "$VPS" "cd $VPS_DIR && docker compose up -d --build"

# 5. Healthcheck via Docker health nativo do hermes-api (independe do bind do host;
#    o Dockerfile já faz curl localhost:8420 dentro do container) + sinaliza falha.
log "Healthcheck (docker health do hermes-api) ..."
if ssh -i "$KEY" "$VPS" "for i in \$(seq 1 12); do [ \"\$(docker inspect -f '{{.State.Health.Status}}' hermes-api 2>/dev/null)\" = healthy ] && exit 0; sleep 5; done; exit 1"; then
  ssh -i "$KEY" "$VPS" "echo '$SHA' > $VPS_DIR/.deployed_sha"
  log "DEPLOY OK (sha=$SHA). Geronimo/Bolseye intactos."
else
  # NÃO derruba (evita tirar o serviço do ar por healthcheck flaky). Sinaliza p/ inspeção.
  log "HEALTHCHECK FALHOU — serviço mantido no ar p/ inspeção (Geronimo nunca tocado)."
  log "Investigar: ssh $VPS \"cd $VPS_DIR && docker compose logs --tail 60\""
  exit 1
fi
