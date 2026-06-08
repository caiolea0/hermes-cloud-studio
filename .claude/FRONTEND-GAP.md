# FRONTEND-GAP — Backend↔Frontend audit

- **last_updated**: 2026-06-08 23:13 UTC
- **phase_baseline**: F.1
- **routes_total**: 138 (91 PC + 47 VM, 5 internal-only excluded)
- **consumed**: 93 (69.9% of public)
- **orphans**: 40
- **top_10_priority**: see §4

> Auditoria determinística cruzando AST routes FastAPI com consumo `dashboard/app.js`.
> Re-rodável: `python .claude/skills/hermes-frontend-gap/scripts/rank_gaps.py`.
> Re-execução ao fechar QUALQUER chapter F.2-F.9 é termômetro UX (GUARDRAILS §F.1).

## §1 Inventário routes (PC + VM)

- Total: **138** rotas FastAPI (91 PC, 47 VM)
- WS endpoints: 1
- Internal-only (loopback): 5 (excluídos do gap)

| Arquivo | Rotas |
|---|---|
| `vm_api/routes.py` | 46 |
| `api/linkedin.py` | 21 |
| `api/pipelines.py` | 9 |
| `api/prospects.py` | 9 |
| `api/daemon.py` | 8 |
| `api/hermes.py` | 7 |
| `api/scraper.py` | 5 |
| `api/tasks.py` | 5 |
| `api/audit.py` | 4 |
| `api/server_ctrl.py` | 4 |
| `api/internal.py` | 3 |
| `api/dashboard.py` | 2 |
| `api/activities.py` | 2 |
| `api/agent_zero.py` | 2 |
| `_health_ep.py` | 2 |
| `api/tunnel.py` | 2 |
| `api/bootstrap.py` | 1 |
| `api/claude.py` | 1 |
| `api/outreach.py` | 1 |
| `api/photos.py` | 1 |
| `api/stats.py` | 1 |
| `server.py` | 1 |
| `hermes_api_v2.py` | 1 |

## §2 Mapa consumo `dashboard/app.js`

- Endpoints únicos consumidos: **93**
- Total fetch/api calls: 86
- Hash routes (páginas SPA): audit, claude, control, dashboard, linkedin, memory, missions, pipeline, proposals, prospects, skills, tasks

| Endpoint | Chamadas | Locais (file:line) |
|---|---|---|
| `/api/dashboard` | 6 | app.js:188, app.js:270, app.js:279 |
| `/api/prospects` | 6 | app.js:582, app.js:618, app.js:1081 |
| `/api/pipelines` | 5 | app.js:1733, app.js:1932, app.js:2406 |
| `/api/audit/prospect/{param}` | 3 | app.js:1183, app.js:1703, app.js:2585 |
| `/api/pipelines/{param}` | 3 | app.js:1929, app.js:1946, app.js:1954 |
| `/api/prospects/{param}` | 3 | app.js:1197, app.js:1338, app.js:1410 |
| `/api/activities` | 2 | app.js:602, app.js:1291 |
| `/api/audit/status` | 2 | app.js:573, app.js:1555 |
| `/api/hermes/memory` | 2 | app.js:2916, app.js:2947 |
| `/api/hermes/status` | 2 | app.js:424, app.js:543 |
| `/api/linkedin/campaigns/{param}/stop` | 2 | app.js:5240, app.js:5374 |
| `/api/outreach/generate/{param}` | 2 | app.js:1366, app.js:2538 |
| `/api/pipeline-executions/active` | 2 | app.js:667, app.js:2011 |
| `/api/pipelines/{param}/executions` | 2 | app.js:2366, app.js:2409 |
| `/api/tasks` | 2 | app.js:632, app.js:2615 |
| `/api/_bootstrap` | 1 | app.js:236 |
| `/api/audit/start` | 1 | app.js:1632 |
| `/api/claude/execute` | 1 | app.js:2716 |
| `/api/daemon/channels` | 1 | app.js:3142 |
| `/api/daemon/decisions` | 1 | app.js:3220 |

## §3 Órfãos — 40 endpoints sem UI

Backend expõe mas dashboard não consome. Owner depende de CLI/curl/SSH.

| Method | Path | Side | File | Auth |
|---|---|---|---|---|
| `POST` | `/api/daemon/broadcast` | pc | `api/daemon.py:145` | token |
| `POST` | `/api/daemon/pause` | pc | `api/daemon.py:33` | token |
| `POST` | `/api/daemon/resume` | pc | `api/daemon.py:44` | token |
| `POST` | `/api/agent-zero/chat` | pc | `api/agent_zero.py:43` | token |
| `POST` | `/api/prospects/{prospect_id}/resolve-conflict` | pc | `api/prospects.py:156` | token |
| `GET` | `/api/agent-zero/status` | pc | `api/agent_zero.py:15` | token |
| `GET` | `/api/linkedin/visited` | pc | `api/linkedin.py:443` | token |
| `GET` | `/api/linkedin/visited` | vm | `vm_api/routes.py:1509` | token |
| `POST` | `/api/audit/batch` | vm | `vm_api/routes.py:701` | token |
| `POST` | `/api/linkedin/campaigns/discover` | pc | `api/linkedin.py:411` | token |
| `POST` | `/api/linkedin/campaigns/discover` | vm | `vm_api/routes.py:1216` | token |
| `POST` | `/api/linkedin/campaigns/engage` | pc | `api/linkedin.py:399` | token |
| `POST` | `/api/linkedin/campaigns/engage` | vm | `vm_api/routes.py:1107` | token |
| `POST` | `/api/linkedin/connection/refresh` | pc | `api/linkedin.py:481` | token |
| `POST` | `/api/linkedin/connection/refresh` | vm | `vm_api/routes.py:1689` | token |
| `POST` | `/api/linkedin/detect-account-type` | pc | `api/linkedin.py:461` | token |
| `POST` | `/api/linkedin/detect-account-type` | vm | `vm_api/routes.py:1470` | token |
| `POST` | `/api/linkedin/health/clear` | pc | `_health_ep.py:15` | token |
| `POST` | `/api/linkedin/health/clear` | pc | `api/linkedin.py:476` | token |
| `POST` | `/api/linkedin/health/clear` | vm | `vm_api/routes.py:1497` | token |
| `POST` | `/api/outreach/batch` | vm | `vm_api/routes.py:777` | token |
| `POST` | `/api/pipeline/execute` | vm | `vm_api/routes.py:824` | token |
| `POST` | `/api/prospects/{prospect_id}/outreach` | vm | `vm_api/routes.py:738` | token |
| `POST` | `/api/server/restart-all` | pc | `api/server_ctrl.py:80` | rate-limited |
| `POST` | `/api/server/restart-local` | pc | `api/server_ctrl.py:22` | rate-limited |
| `POST` | `/api/server/restart-vm` | pc | `api/server_ctrl.py:54` | rate-limited |
| `POST` | `/api/server/shutdown-local` | pc | `api/server_ctrl.py:36` | rate-limited |
| `POST` | `/api/tasks/bulk` | pc | `api/tasks.py:93` | token |
| `GET` | `/api/stats` | pc | `api/stats.py:11` | token |
| `GET` | `/api/stats` | vm | `vm_api/routes.py:330` | token |
| `GET` | `/` | pc | `api/dashboard.py:14` | token |
| `GET` | `/api/_ping` | vm | `hermes_api_v2.py:88` | token |
| `GET` | `/api/linkedin/companies/lookup` | pc | `api/linkedin.py:455` | token |
| `GET` | `/api/linkedin/companies/lookup` | vm | `vm_api/routes.py:1567` | token |
| `GET` | `/api/linkedin/rate-limits` | pc | `api/linkedin.py:29` | token |
| `GET` | `/api/linkedin/rate-limits` | vm | `vm_api/routes.py:1368` | token |
| `GET` | `/api/linkedin/session-check` | vm | `vm_api/routes.py:1381` | token |
| `GET` | `/api/photos/{photo_ref:path}` | pc | `api/photos.py:15` | token |
| `GET` | `/api/scraper/history` | pc | `api/scraper.py:121` | token |
| `GET` | `/api/scraper/history` | vm | `vm_api/routes.py:530` | token |

## §4 TOP 10 priorizado

Ranking: owner_pain_score (5=tail/decisions live) → method (write > read) → path.

| Rank | Endpoint | Método | Side | Chapter destino | WS needed | CLI hoje | Owner pain (1-5) |
|---|---|---|---|---|---|---|---|
| 1 | `/api/daemon/broadcast` | `POST` | pc | F.2 | — | `curl -X POST /api/daemon/broadcast` | 5 |
| 2 | `/api/daemon/pause` | `POST` | pc | F.2 | — | `curl -X POST /api/daemon/pause` | 5 |
| 3 | `/api/daemon/resume` | `POST` | pc | F.2 | — | `curl -X POST /api/daemon/resume` | 5 |
| 4 | `/api/agent-zero/chat` | `POST` | pc | F.6 | ✅ | `curl POST + parse stream manual` | 4 |
| 5 | `/api/prospects/{prospect_id}/resolve-conflict` | `POST` | pc | F.6 | — | `curl -X POST /api/prospects/{prospect_id}/resolve-conflict` | 4 |
| 6 | `/api/agent-zero/status` | `GET` | pc | F.6 | — | `curl + parse JSON em PowerShell` | 4 |
| 7 | `/api/linkedin/visited` | `GET` | pc | F.7 | — | `ssh vm 'sqlite3 linkedin_data/rate_limits.db "SELECT * FROM ` | 4 |
| 8 | `/api/linkedin/visited` | `GET` | vm | F.7 | — | `ssh vm 'sqlite3 linkedin_data/rate_limits.db "SELECT * FROM ` | 4 |
| 9 | `/api/audit/batch` | `POST` | vm | F.6 | — | `curl -X POST /api/audit/batch` | 3 |
| 10 | `/api/linkedin/campaigns/discover` | `POST` | pc | F.3 | — | `curl -X POST /api/linkedin/campaigns/discover` | 3 |

**Justificativa por linha**:

1. **`POST /api/daemon/broadcast`** — Trigger broadcast WS arbitrário (devtool) — escondido pra owner, expose só em modo debug
2. **`POST /api/daemon/pause`** — Botão pause daemon (timeout N min) no header Mission Control
3. **`POST /api/daemon/resume`** — Botão resume daemon junto do pause
4. **`POST /api/agent-zero/chat`** — Chat AI no dashboard — substitui CLI Agent Zero
5. **`POST /api/prospects/{prospect_id}/resolve-conflict`** — Botão dismiss conflict no row de prospect
6. **`GET /api/agent-zero/status`** — Status Agent Zero (model, context_id, last_invoked)
7. **`GET /api/linkedin/visited`** — Lista de perfis já visitados (cooldown debug)
8. **`GET /api/linkedin/visited`** — Lista de perfis já visitados (cooldown debug)
9. **`POST /api/audit/batch`** — Botão 'rodar auditoria em lote' na lista de prospects qualificados
10. **`POST /api/linkedin/campaigns/discover`** — /api/linkedin/campaigns/discover

## §5 Quick Wins UX (1 fetch + 1 toast / 1 botão)

Implementação <1h cada — alta razão impacto/esforço:

- `POST /api/prospects/{id}/resolve-conflict` — Botão 'resolver conflito' no row do prospect quando `conflict_at IS NOT NULL`
- `GET /api/stats` — Card de KPIs no topo do dashboard (prospects total, deals won, replies 24h)
- `POST /api/tasks/bulk` — Toolbar com 'priorize selecionados' / 'cancelar selecionados' em /tasks
- `GET /api/agent-zero/status` — Badge no header com modelo/context_id ativo

## §6 Mission Control endpoints (WS broadcasts + streaming)

Endpoints que F.2 deve consumir com canais WS dedicados:

| Endpoint | WS event sugerido | Comentário |
|---|---|---|
| `/api/daemon/state` | `daemon_state` | Já emitido (sync.py + daemon/orchestrator.py) (✅ ativo) |
| `/api/daemon/timeline` | `daemon_timeline_update` | Broadcast inexistente — criar em loops/sync.py (🔨 a criar) |
| `/api/daemon/decisions` | `decision` | Já emitido (daemon orchestrator log_decision) (✅ ativo) |
| `/api/daemon/channels` | `channel_update` | Já emitido (daemon orchestrator) (✅ ativo) |
| `/api/daemon/log` | `daemon_log_line` | Broadcast inexistente — rolling buffer 500 lines F.2 (🔨 a criar) |
| `/api/lab/runs/{id}/screenshot` | `lab_screenshot_new` | Polling 2s ou WS push (F.3) (🔨 a criar) |
| `/api/brain/chat` | `brain_token / brain_action` | Stream tokens + tool events (F.6) (🔨 a criar) |

### WS events backend vs handlers `dashboard/app.js`

- Handlers em `app.js`: 14 (activity, alert, audit_done, channel_update, daemon_state, decision, linkedin_campaign_created, linkedin_campaign_done, linkedin_health, linkedin_progress, pipeline_progress, reply_received, scraper_update, sync)
- Broadcasts no backend: 10 (activity, channel_update, daemon_state, decision, linkedin_account_type_updated, linkedin_campaign_created, linkedin_health, linkedin_progress, linkedin_session_rotated, sync)
- ✅ Matched (emitido + handler): activity, channel_update, daemon_state, decision, linkedin_campaign_created, linkedin_health, linkedin_progress, sync
- ⚠️ Orphan broadcasts (emitido sem handler): linkedin_account_type_updated, linkedin_session_rotated
- 🪦 Dead handlers (handler sem emitter local): alert, audit_done, linkedin_campaign_done, pipeline_progress, reply_received, scraper_update

---

Gerado por `.claude/skills/hermes-frontend-gap/scripts/rank_gaps.py`.
Reproduzir: `python .claude/skills/hermes-frontend-gap/scripts/{parse_routes,grep_frontend,rank_gaps}.py`
