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

### F0.5 — Auto-deploy a cada push ✅ (2026-06-22, VALIDADO)
- `.github/workflows/deploy-hermes.yml`: push master (não-docs) → ssh root@207.180.240.208 (IP público:22, igual Geronimo — sem Tailscale no CI) → `scripts/deploy-hermes-vps.sh`. Guard `vars.HERMES_AUTODEPLOY=='true'`.
- Chave DEDICADA `hermes_deploy` (gerada + autorizada na VPS, revogável) → secret `HERMES_VPS_SSH_KEY`; var `HERMES_AUTODEPLOY=true`.
- **2 fixes**: healthcheck via Docker health nativo (curl localhost:8800 quebrou após bind Tailscale); rollback não-destrutivo (o `compose down` derrubou o Hermes num healthcheck falho → incidente; Hermes restaurado na hora).
- **Gate ✅**: run #27942489875 **success** (1m11s) → Hermes recriado + healthy, Geronimo intacto.

### F0.4-app + F0.6 — DIFERIDOS pro frontend v2 (decisão owner 2026-06-22)
- Descoberto (Explore): aposentar `server.py` = **3-5 dias** — a VM não tem `/ws` (WebSocket), `/api/_bootstrap` é loopback-only (distribui tokens), e daemon pause / server-control / túnel / lab são PC-only. E isso refatoraria o **dashboard 1.x que o frontend v2 (design aprovado) vai substituir** → retrabalho descartável.
- **Decisão**: o frontend v2 nasce VPS-direct (WebSocket na VM + bootstrap/tokens + sem server.py). F0.4-app (app aponta pra VPS) e F0.6 (aposentar server.py) são feitos LÁ, certo uma vez.
- Até lá: `server.py` local segue como está (não bloqueia nada; a fundação não depende dele).

## Decisões adotadas (default, ajustável)
- **SQLite-first**: H2-F0 sobe o Hermes com SQLite em volume (como hoje). Migração SQLite→Postgres compartilhado só em F1/F2 (quando o motor entra). Menor risco na fundação.
- **Build na VPS** (não no PC) — PC não precisa de Docker; espelha o Geronimo.

## Estado
- [x] Pré-flight
- [x] F0.1 · [x] F0.2 · [x] F0.3 (Hermes VIVO) · [x] F0.4-rede (app→v2) · [x] F0.5 auto-deploy ✅ · [→v2] F0.6

> **FUNDAÇÃO H2-F0 ESSENCIAL ✅ COMPLETA** (2026-06-22): Hermes 24/7 na Contabo + LinkedIn frozen + coabitação limpa + acesso Tailscale privado + auto-deploy validado. F0.4-app/F0.6 diferidos pro frontend v2. **Próximo: MOTOR — H2-F1 (Overpass discovery).**

---

## H2-F1 — Overpass Discovery (backbone $0) ✅ COMPLETO (2026-06-22)

### O que foi feito
- `hermes-overpass` container: `wiktorn/overpass-api`, extract Centro-Oeste (Geofabrik), `mem_limit: 8g`, port `127.0.0.1:12345:80` (nunca 0.0.0.0), volume `overpass_data`.
- `scripts/discovery_overpass.py`: Overpass QL query bbox Cuiabá, 6 tags (shop/amenity/office/craft, node+way), `out center tags`, retorna lista Prospect.
- Migração H2-F1 em `vm_core/state.py`: 5 cols novas em prospects (`source_type`, `osm_id`, `lat`, `lng`, `opening_hours`) + unique index `idx_prospects_osm_id`.
- `vm_api/routes.py`: `create_prospect()` aceita OSM fields.
- `core/pipeline.py`: `discovery_osm()` chama Overpass → POST /api/prospects.
- `daemon/orchestrator.py`: P4 chama `discovery_osm()`.

### Bugs resolvidos
1. `core/pipeline.py:85` — header era `Authorization: Bearer` → corrigido para `X-Hermes-Token` (VM API usa header custom).
2. `daemon/orchestrator.py:156` — daemon usava `HERMES_AUTH_TOKEN` (PC token) → corrigido para `HERMES_VM_AUTH_TOKEN` (com fallback).
3. `docker-compose.yml` — `OVERPASS_ALLOW_DUPLICATE_QUERIES: "yes"` resolveu 504s intermitentes (dispatcher rejeitava segunda query idêntica).
4. `/db/` permissions — `drwxr-xr-x 755` (nginx user precisa traversar; persiste no volume).

### Gate final ✅
- Overpass: `20 slots available`, status 200, `--allow-duplicate-queries=yes`
- `discover_cuiaba()`: 2396 POIs de Cuiabá (Burger King, Serra Restaurante, Arezzo, etc.)
- DB: **717 prospects** `source_type='osm'` com lat/lng/osm_id reais
- Daemon: 200 OK em todos os POSTs (auth corrigida)
- 22 non-Hermes containers intactos

> **H2-F1 ✅ COMPLETO** (2026-06-22): Overpass self-hosted como backbone discovery $0/24-7. Próximo: H2-F2 (audit pipeline OSM + scoring).

---

## H2-F2 — CNPJ Authority + Enrichment (2026-06-22)

### Objetivo
Camada de autoridade CNPJ Receita Federal sobre prospects OSM. PostgreSQL dedicado (hermes-postgres) com pg_trgm + unaccent para fuzzy name matching PT-BR. Pipeline: OSM name → RF CSV lookup → BrasilAPI validate → PATCH prospect.

### Arquitetura
```
hermes-postgres:16 (mem_limit 2g, bind 127.0.0.1:5433, geronimo-net)
  └─ schema cnpj.estabelecimentos (GIN trgm, ~50k+ rows Cuiabá MT subset)
scripts/load_cnpj_cuiaba.py  — stream RF CSV → upsert (cuiaba_code via Municipios.zip)
scripts/enrich_cnpj.py       — cnpj_lookup (SIM≥0.45) + cnpj_validate (BrasilAPI)
mcps/hermes-enrich/server.py — FastMCP 3.0, tools: cnpj_lookup + cnpj_validate
daemon/orchestrator.py P3    — _enrich_single usa asyncio.to_thread → PATCH VM API
```

### Mudanças (código PC — não commitado)
| Arquivo | Mudança |
|---|---|
| `config.py` | 5 HERMES_PG_* fields + `hermes_pg_dsn` property |
| `core/state.py` | Migration H2-F2: cnpj/razao_social/cnae/situacao_cadastral/cnpj_match_confidence + index |
| `vm_core/state.py` | Mesmo migration H2-F2 (VM side) |
| `vm_core/models.py` | 5 campos CNPJ em ProspectCreate + ProspectUpdate |
| `docker-compose.yml` | hermes-postgres service + hermes_pg_data volume + hermes-api/daemon depends_on |
| `docker/pg_init/01_ext.sql` | CREATE EXTENSION pg_trgm + unaccent (init container) |
| `scripts/load_cnpj_cuiaba.py` | Stream download RF CSV → filter Cuiabá → UPSERT postgres |
| `scripts/enrich_cnpj.py` | cnpj_lookup + cnpj_validate + enrich_prospect_cnpj |
| `mcps/hermes-enrich/server.py` | FastMCP 3.0 — 2 tools CNPJ |
| `mcps/gateway/config.yaml` | hermes-enrich upstream adicionado |
| `.mcp.json` | hermes-enrich stdio entry |
| `daemon/orchestrator.py` | _get_unenriched_prospects (VM API primary) + _enrich_single real |

### Gates (verificar na VPS após deploy)
1. `hermes-postgres` UP + healthy + `\dx` mostra pg_trgm + unaccent. Bind 127.0.0.1:5433. mem_limit 2g.
2. `SELECT COUNT(*) FROM cnpj.estabelecimentos WHERE municipio_rf=<cuiaba_code>` > 50k.
3. `PRAGMA table_info(prospects)` PC + VM: colunas cnpj/razao_social/cnae/situacao_cadastral presentes.
4. `enrich_cnpj.py`: ≥3 matches com sim score + ≥1 caso low-confidence sem sobrescrever.
5. BrasilAPI: validação de 1 CNPJ real retorna `situacao_cadastral: ATIVA`.
6. Daemon P3: log `enrich_batch` ≥5 min sem traceback.
7. MCP hermes-enrich: `cnpj_lookup` invocado 1x via gateway.
8. 22 non-Hermes containers intactos (Gate 8 H2-F1 preservado).
9. `validate_implementation.py --phase A` a `E`: 20/22 PASS (baseline pré-existente).

### Decisões de design
- **RF code trap**: Cuiabá RF code ≠ IBGE (9067 vs 5103403). load_cnpj_cuiaba.py resolve via Municipios.zip automaticamente.
- **Confidence 'low'**: só grava cnpj+confidence, NÃO sobrescreve razao_social/cnae (evita falso positivo).
- **Ambiguidade**: delta < 0.08 entre top1 e top2 = `low` mesmo se SIM ≥ 0.45. Corroboração bairro/phone eleva p/ `high`.
- **Container DSN**: hermes-postgres:5432 (docker net). Host VPS: 127.0.0.1:5433. Config default = container.
- **LGPD**: só empresa (razão social, CNAE, endereço). QSA/sócios (PII) = NÃO armazenar.

> **H2-F2 ⏳ AGUARDANDO DEPLOY** (2026-06-22): Código PC completo. Owner faz commit + push → auto-deploy → verificar gates na VPS. Próximo: H2-F3 (audit pipeline + score + outreach triggers).
