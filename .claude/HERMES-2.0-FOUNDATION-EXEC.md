# Hermes 2.0 — Plano de Execução da Fundação (H2-F0)
**Criado**: 2026-06-21 · **Status**: pré-flight ✅ · executando

> Como subir a fundação do Hermes 2.0 na VPS Contabo, coabitando com Geronimo + Bolseye, sem quebrar nada. Faseado, com gate e rollback por etapa.

## Pré-flight (FATOS confirmados)
- **Contabo**: `root@207.180.240.208`, key `~/.ssh/geronimo_ed25519` (mesma do Geronimo), Geronimo em `/opt/geronimo`.
- **Rede**: `geronimo-net` (docker bridge) JÁ existe → Hermes pluga como **external network**.
- **Postgres**: container `postgres` (pg16, user `geronimo`, db `events_audit`), interno (não exposto). Hermes cria DB próprio nele quando precisar.
- **Tailscale PC↔VPS JÁ ativo**: Geronimo consome Ollama do PC via `100.99.116.28:11434`. A malha que o app desktop precisa já está de pé.
- **Deploy Geronimo (padrão a espelhar)**: rsync local→VPS + `docker compose up -d --build` + cloudflared + healthcheck (`scripts/deploy-2a-vps.sh`).
- **Hermes repo**: GitHub `caiolea0/hermes-cloud-studio` (branch master) + `gh` logado → auto-deploy via Actions viável.
- **Portas livres p/ Hermes**: 8800–8810 (Geronimo usa 8700/3000/8222/18080/8080).

## REGRAS DE OURO (coabitação — INVIOLÁVEL)
1. Hermes usa **compose próprio** (`/opt/hermes/docker-compose.yml`) + `geronimo-net` como `external: true`. **NUNCA** `docker compose down` no `/opt/geronimo`.
2. **Nunca** tocar containers/volumes do Geronimo (postgres_data, etc). Hermes cria DB `hermes` separado no mesmo Postgres (CREATE DATABASE idempotente) — só quando o motor (F1+) precisar; H2-F0 usa SQLite em volume próprio.
3. Hermes em `/opt/hermes` (separado de `/opt/geronimo`). Volume de dados próprio.
4. Verificar headroom (RAM/disco) ANTES de subir. H2-F0 = só a API+daemon (leve, ~300-500MB).
5. Todo deploy: healthcheck + rollback. Falhou → reverte, Geronimo intacto.

## Sub-fases (cada uma com GATE)

### F0.1 — Artefatos de containerização (LOCAL, não toca VPS) ✅
- `Dockerfile` (python:3.12-slim; remove pystray/pywebview/pytest; NÃO instala patchright→LinkedIn frozen; healthcheck `/api/_ping`; CMD uvicorn `hermes_api_v2:app` :8420).
- `docker-compose.yml`: 2 serviços **hermes-api** (:8800→8420) + **hermes-daemon** (`python -m daemon.orchestrator`), `geronimo-net` external, volume `hermes_data`, `restart: unless-stopped`, `FEATURE_LINKEDIN=off`, `HERMES_STRICT_MCP=0`.
- `.dockerignore` (sem .git/.claude/*.db/linkedin_data/segredos) + `.env.hermes.example` (template; `.env` real só na VPS, gitignored).
- Validado contra runtime real (Explore): server.py FORA (PC-only), tokens fail-closed documentados, SQLite em volume.
- **Gate**: ✅ artefatos revisados. Build roda na VPS (padrão Geronimo).

### F0.2 — Freeze LinkedIn (código, LOCAL) ✅
- `config.py`: flag `feature_linkedin` (env `FEATURE_LINKEDIN`; default True preserva 1.x; VPS=off).
- `daemon/orchestrator.py`: import `settings`; P0 `_get_cobaia_action`→None quando off; P2 OUTREACH/sequence gateado pela flag. Zero deleção (aditivo).
- patchright/playwright nunca importados top-level → container boota sem eles (provado).
- Dashboard cobaia hiding diferido pro frontend (server.py não roda no container).
- **Gate ✅** (smoke no PC, sem patchright = espelha container): off→False / default→True · DAEMON_IMPORT_OK + API_IMPORT_OK · `_get_cobaia_action(off)`→None. validate_implementation.py completo roda no gate de deploy.

### F0.3 — Primeiro deploy à VPS (🔴 TOCA PRODUÇÃO) ✅ (2026-06-22, GO total do owner)
- Pré-flight read-only confirmou: 21Gi RAM / 355G disco livres · geronimo-net OK · porta 8800 livre · Geronimo+Bolseye healthy.
- `/opt/hermes` criado + `.env` (tokens gerados na VPS via openssl, chmod 600) · código via tar+ssh (9.4M, sem git/claude/dados/segredos; `.env` preservado).
- `docker compose up -d --build`: imagem `hermes:latest` + `hermes-api` (8800→8420, healthy) + `hermes-daemon`.
- **2 fixes aplicados**: (a) daemon chamava `runtime_state` sem a tabela → adicionado `core.state.init_db()` no `main()` do daemon; (b) healthcheck do daemon desabilitado (worker não escuta porta). Re-deploy → daemon boota limpo ("24/7 operation"), logs sem erro.
- `scripts/deploy-hermes-vps.sh` consolida o processo (pré-flight+rsync+build+healthcheck+rollback) p/ F0.5.
- **Gate ✅**: `/api/_ping`→`{"ok":true}` · daemon estável sem erros · **Geronimo (13) + Bolseye (8) = 21 intactos** (Hermes só somou 2). Regra de ouro respeitada.

### F0.4 — Acesso via Tailscale 🟡 (rede ✅ provada / app config pendente)
- **VPS Tailscale IP = `100.74.227.37`**. Bind do Hermes mudado p/ `${HERMES_BIND_IP:-127.0.0.1}:8800:8420` (HERMES_BIND_IP=100.74.227.37 no .env) → escuta SÓ na interface Tailscale. **Fechou a exposição pública** (docker-proxy em 0.0.0.0 furava o ufw; Geronimo usa 127.0.0.1 pelo mesmo motivo).
- **PROVADO do PC (tailnet)**: `curl http://100.74.227.37:8800/api/_ping` → `{"ok":true}`. Caminho app→cérebro funciona e é privado.
- **Falta**: app Tauri (`app/`) apontar `HERMES_BASE_URL=http://100.74.227.37:8800` (REST+WS) + abrir/testar. Config no PC (owner-facing).
- **Gate parcial ✅**: rede PC→VPS via Tailscale OK e segura.

### F0.5 — Auto-deploy a cada push ⏳
- GitHub Actions: push `master` → `tailscale/github-action` entra na tailnet → ssh VPS → pull/rsync + compose up + healthcheck + rollback + alerta Telegram.
- **Gate**: um push de teste publica sozinho e passa o healthcheck.

### F0.6 — Aposentar `server.py` local ⏳
- App fala direto com a VPS; remover o proxy local (D2). 
- **Gate**: app 100% funcional sem o server.py local.

## Decisões adotadas (default, ajustável)
- **SQLite-first**: H2-F0 sobe o Hermes com SQLite em volume (como hoje). Migração SQLite→Postgres compartilhado só em F1/F2 (quando o motor entra). Menor risco na fundação.
- **Build na VPS** (não no PC) — PC não precisa de Docker; espelha o Geronimo.

## Estado
- [x] Pré-flight
- [x] F0.1 artefatos · [x] F0.2 freeze · [x] F0.3 deploy (Hermes VIVO na VPS) · [~] F0.4 tailscale (rede ✅ provada PC→VPS + segura; app Tauri config pendente) · [ ] F0.5 auto-deploy CI · [ ] F0.6 aposentar server.py
