# FRONTEND-GAP — Backend↔Frontend audit

- **last_updated**: 2026-06-17 15:23 UTC
- **phase_baseline**: post F.7
- **routes_total**: 209 (159 PC + 50 VM, 5 internal-only excluded)
- **consumed**: 94 (46.1% of public)
- **orphans**: 110
- **top_10_priority**: see §4

> Auditoria determinística cruzando AST routes FastAPI com consumo `dashboard/app.js`.
> Re-rodável: `python .claude/skills/hermes-frontend-gap/scripts/rank_gaps.py`.
> Re-execução ao fechar QUALQUER chapter F.2-F.9 é termômetro UX (GUARDRAILS §F.1).

## §1 Inventário routes (PC + VM)

- Total: **209** rotas FastAPI (159 PC, 50 VM)
- WS endpoints: 1
- Internal-only (loopback): 5 (excluídos do gap)

| Arquivo | Rotas |
|---|---|
| `vm_api/routes.py` | 46 |
| `api/linkedin.py` | 21 |
| `api/cobaia.py` | 17 |
| `api/daemon.py` | 12 |
| `api/pipeline_studio.py` | 12 |
| `api/skills.py` | 10 |
| `api/pipelines.py` | 9 |
| `api/prospects.py` | 9 |
| `api/observability.py` | 8 |
| `api/hermes.py` | 7 |
| `api/brain.py` | 6 |
| `api/lab.py` | 5 |
| `api/scraper.py` | 5 |
| `api/tasks.py` | 5 |
| `api/audit.py` | 4 |
| `api/server_ctrl.py` | 4 |
| `api/internal.py` | 3 |
| `api/dashboard.py` | 2 |
| `api/activities.py` | 2 |
| `api/agent_zero.py` | 2 |
| `_health_ep.py` | 2 |
| `api/mcp_coverage.py` | 2 |
| `api/tunnel.py` | 2 |
| `api/user_prefs.py` | 2 |
| `vm_api/mcp_coverage.py` | 2 |
| `api/bootstrap.py` | 1 |
| `api/claude.py` | 1 |
| `api/config.py` | 1 |
| `api/outreach.py` | 1 |
| `api/photos.py` | 1 |
| `api/skills_webhook.py` | 1 |
| `api/stats.py` | 1 |
| `server.py` | 1 |
| `hermes_api_v2.py` | 1 |
| `vm_api/mcp_jobs.py` | 1 |

## §2 Mapa consumo `dashboard/app.js`

- Endpoints únicos consumidos: **94**
- Total fetch/api calls: 87
- Hash routes (páginas SPA): audit, claude, cobaia, control, dashboard, lab, linkedin, mcp-gateway, memory, missions, observability, pipeline-studio, proposals, prospects, skill-proposals, skills, tasks

| Endpoint | Chamadas | Locais (file:line) |
|---|---|---|
| `/api/dashboard` | 6 | app.js:188, app.js:270, app.js:279 |
| `/api/prospects` | 6 | app.js:785, app.js:821, app.js:1284 |
| `/api/pipelines` | 5 | app.js:1936, app.js:2135, app.js:2609 |
| `/api/audit/prospect/{param}` | 3 | app.js:1386, app.js:1906, app.js:2788 |
| `/api/pipelines/{param}` | 3 | app.js:2132, app.js:2149, app.js:2157 |
| `/api/prospects/{param}` | 3 | app.js:1400, app.js:1541, app.js:1613 |
| `/api/activities` | 2 | app.js:805, app.js:1494 |
| `/api/audit/status` | 2 | app.js:776, app.js:1758 |
| `/api/hermes/memory` | 2 | app.js:3256, app.js:3287 |
| `/api/hermes/status` | 2 | app.js:627, app.js:746 |
| `/api/linkedin/campaigns/{param}/stop` | 2 | app.js:5627, app.js:5761 |
| `/api/outreach/generate/{param}` | 2 | app.js:1569, app.js:2741 |
| `/api/pipeline-executions/active` | 2 | app.js:870, app.js:2214 |
| `/api/pipelines/{param}/executions` | 2 | app.js:2569, app.js:2612 |
| `/api/tasks` | 2 | app.js:835, app.js:2818 |
| `/api/_bootstrap` | 1 | app.js:236 |
| `/api/audit/start` | 1 | app.js:1835 |
| `/api/claude/execute` | 1 | app.js:2919 |
| `/api/daemon/channels` | 1 | app.js:3529 |
| `/api/daemon/decisions` | 1 | app.js:3607 |

## §3 Órfãos — 110 endpoints sem UI

Backend expõe mas dashboard não consome. Owner depende de CLI/curl/SSH.

| Method | Path | Side | File | Auth |
|---|---|---|---|---|
| `POST` | `/api/daemon/broadcast` | pc | `api/daemon.py:256` | token |
| `POST` | `/api/daemon/pause` | pc | `api/daemon.py:73` | token |
| `POST` | `/api/daemon/resume` | pc | `api/daemon.py:84` | token |
| `POST` | `/api/daemon/subsystems/all/pause` | pc | `api/daemon.py:393` | rate-limited |
| `POST` | `/api/daemon/subsystems/{name}/pause` | pc | `api/daemon.py:434` | rate-limited |
| `POST` | `/api/daemon/subsystems/{name}/resume` | pc | `api/daemon.py:443` | rate-limited |
| `GET` | `/api/linkedin/cobaia/timeline` | pc | `api/cobaia.py:223` | token |
| `POST` | `/api/agent-zero/chat` | pc | `api/agent_zero.py:43` | token |
| `POST` | `/api/brain/confirm/{run_id}` | pc | `api/brain.py:154` | token |
| `POST` | `/api/brain/decide` | pc | `api/brain.py:107` | token |
| `POST` | `/api/brain/replay/{run_id}` | pc | `api/brain.py:143` | token |
| `POST` | `/api/prospects/{prospect_id}/resolve-conflict` | pc | `api/prospects.py:156` | token |
| `GET` | `/api/agent-zero/status` | pc | `api/agent_zero.py:15` | token |
| `GET` | `/api/brain/intents` | pc | `api/brain.py:221` | token |
| `GET` | `/api/brain/runs` | pc | `api/brain.py:120` | token |
| `GET` | `/api/brain/runs/{run_id}` | pc | `api/brain.py:132` | token |
| `GET` | `/api/linkedin/visited` | pc | `api/linkedin.py:443` | token |
| `GET` | `/api/linkedin/visited` | vm | `vm_api/routes.py:1528` | token |
| `POST` | `/api/audit/batch` | vm | `vm_api/routes.py:701` | token |
| `POST` | `/api/cobaia/autotune-trigger-manual` | pc | `api/cobaia.py:429` | token |
| `POST` | `/api/cobaia/verify-email` | pc | `api/cobaia.py:753` | token |
| `POST` | `/api/lab/runs/{run_id}/abort` | pc | `api/lab.py:384` | token |
| `POST` | `/api/lab/start` | pc | `api/lab.py:333` | rate-limited |
| `POST` | `/api/linkedin/campaigns/discover` | pc | `api/linkedin.py:411` | token |
| `POST` | `/api/linkedin/campaigns/discover` | vm | `vm_api/routes.py:1216` | token |
| `POST` | `/api/linkedin/campaigns/engage` | pc | `api/linkedin.py:399` | token |
| `POST` | `/api/linkedin/campaigns/engage` | vm | `vm_api/routes.py:1107` | token |
| `POST` | `/api/linkedin/cobaia/emergency-stop` | pc | `api/cobaia.py:138` | token |
| `POST` | `/api/linkedin/cobaia/pause` | pc | `api/cobaia.py:100` | token |
| `POST` | `/api/linkedin/cobaia/resume` | pc | `api/cobaia.py:113` | token |
| `POST` | `/api/linkedin/cobaia/start-warmup` | pc | `api/cobaia.py:84` | token |
| `POST` | `/api/linkedin/connection/refresh` | pc | `api/linkedin.py:481` | token |
| `POST` | `/api/linkedin/connection/refresh` | vm | `vm_api/routes.py:1708` | token |
| `POST` | `/api/linkedin/detect-account-type` | pc | `api/linkedin.py:461` | token |
| `POST` | `/api/linkedin/detect-account-type` | vm | `vm_api/routes.py:1489` | token |
| `POST` | `/api/linkedin/health/clear` | pc | `_health_ep.py:15` | token |
| `POST` | `/api/linkedin/health/clear` | pc | `api/linkedin.py:476` | token |
| `POST` | `/api/linkedin/health/clear` | vm | `vm_api/routes.py:1516` | token |
| `POST` | `/api/mcp/coverage/publish` | vm | `vm_api/mcp_coverage.py:80` | token |
| `POST` | `/api/observability/errors/{error_id}/resolve` | pc | `api/observability.py:380` | token |
| `POST` | `/api/outreach/batch` | vm | `vm_api/routes.py:777` | token |
| `POST` | `/api/pipeline-studio/drafts` | pc | `api/pipeline_studio.py:165` | token |
| `DELETE` | `/api/pipeline-studio/drafts/{draft_id}` | pc | `api/pipeline_studio.py:262` | token |
| `PUT` | `/api/pipeline-studio/drafts/{draft_id}` | pc | `api/pipeline_studio.py:212` | token |
| `POST` | `/api/pipeline-studio/drafts/{draft_id}/clone` | pc | `api/pipeline_studio.py:594` | token |
| `POST` | `/api/pipeline-studio/drafts/{draft_id}/execute` | pc | `api/pipeline_studio.py:452` | token |
| `POST` | `/api/pipeline-studio/runs/{run_id}/abort` | pc | `api/pipeline_studio.py:741` | token |
| `POST` | `/api/pipeline/execute` | vm | `vm_api/routes.py:824` | token |
| `POST` | `/api/prospects/{prospect_id}/outreach` | vm | `vm_api/routes.py:738` | token |
| `POST` | `/api/server/restart-all` | pc | `api/server_ctrl.py:80` | rate-limited |
| `POST` | `/api/server/restart-local` | pc | `api/server_ctrl.py:22` | rate-limited |
| `POST` | `/api/server/restart-vm` | pc | `api/server_ctrl.py:54` | rate-limited |
| `POST` | `/api/server/shutdown-local` | pc | `api/server_ctrl.py:36` | rate-limited |
| `POST` | `/api/skills/proposals` | pc | `api/skills.py:115` | token |
| `POST` | `/api/skills/proposals/generate` | pc | `api/skills.py:312` | token |
| `POST` | `/api/skills/proposals/{proposal_id}/accept` | pc | `api/skills.py:178` | token |
| `POST` | `/api/skills/proposals/{proposal_id}/reject` | pc | `api/skills.py:238` | token |
| `POST` | `/api/skills/webhook/pr-merged` | pc | `api/skills_webhook.py:186` | rate-limited |
| `POST` | `/api/skills/{skill_name}/unquarantine` | pc | `api/skills.py:406` | token |
| `POST` | `/api/tasks/bulk` | pc | `api/tasks.py:93` | token |
| `PUT` | `/api/user-prefs` | pc | `api/user_prefs.py:76` | rate-limited |
| `GET` | `/api/lab/runs` | pc | `api/lab.py:424` | token |
| `GET` | `/api/lab/runs/{run_id}` | pc | `api/lab.py:431` | token |
| `GET` | `/api/lab/runs/{run_id}/artifacts/{filename}` | pc | `api/lab.py:479` | token |
| `GET` | `/api/stats` | pc | `api/stats.py:11` | token |
| `GET` | `/api/stats` | vm | `vm_api/routes.py:330` | token |
| `GET` | `/` | pc | `api/dashboard.py:14` | token |
| `GET` | `/api/_ping` | vm | `hermes_api_v2.py:157` | token |
| `GET` | `/api/cobaia/autotune-history` | pc | `api/cobaia.py:371` | token |
| `GET` | `/api/cobaia/autotune-status` | pc | `api/cobaia.py:403` | token |
| `GET` | `/api/cobaia/bug-export` | pc | `api/cobaia.py:270` | token |
| `GET` | `/api/cobaia/f7-report` | pc | `api/cobaia.py:637` | token |
| `GET` | `/api/cobaia/health-score` | pc | `api/cobaia.py:298` | token |
| `GET` | `/api/cobaia/hunter-usage` | pc | `api/cobaia.py:779` | token |
| `GET` | `/api/cobaia/preflight` | pc | `api/cobaia.py:498` | token |
| `GET` | `/api/cobaia/sentry-env` | pc | `api/cobaia.py:355` | token |
| `GET` | `/api/config` | pc | `api/config.py:27` | token |
| `GET` | `/api/linkedin/cobaia/metrics` | pc | `api/cobaia.py:153` | token |
| `GET` | `/api/linkedin/cobaia/status` | pc | `api/cobaia.py:128` | token |
| `GET` | `/api/linkedin/companies/lookup` | pc | `api/linkedin.py:455` | token |
| `GET` | `/api/linkedin/companies/lookup` | vm | `vm_api/routes.py:1586` | token |
| `GET` | `/api/linkedin/rate-limits` | pc | `api/linkedin.py:29` | token |
| `GET` | `/api/linkedin/rate-limits` | vm | `vm_api/routes.py:1387` | token |
| `GET` | `/api/linkedin/session-check` | vm | `vm_api/routes.py:1400` | token |
| `GET` | `/api/mcp/coverage/jobs/{job_id}` | vm | `vm_api/mcp_jobs.py:26` | token |
| `GET` | `/api/mcp/coverage/latest` | pc | `api/mcp_coverage.py:78` | token |
| `GET` | `/api/mcp/coverage/latest` | vm | `vm_api/mcp_coverage.py:26` | token |
| `GET` | `/api/mcp/gateway/health` | pc | `api/mcp_coverage.py:100` | token |
| `GET` | `/api/observability/_debug/explain_cost_plan` | pc | `api/observability.py:646` | token |
| `GET` | `/api/observability/costs` | pc | `api/observability.py:55` | token |
| `GET` | `/api/observability/credits` | pc | `api/observability.py:162` | token |
| `GET` | `/api/observability/decisions` | pc | `api/observability.py:474` | token |
| `GET` | `/api/observability/errors` | pc | `api/observability.py:313` | token |
| `GET` | `/api/observability/mcp-coverage-history` | pc | `api/observability.py:599` | token |
| `GET` | `/api/observability/perf` | pc | `api/observability.py:98` | token |
| `GET` | `/api/photos/{photo_ref:path}` | pc | `api/photos.py:15` | token |
| `GET` | `/api/pipeline-studio/drafts` | pc | `api/pipeline_studio.py:117` | token |
| `GET` | `/api/pipeline-studio/drafts/{draft_id}` | pc | `api/pipeline_studio.py:192` | token |
| `GET` | `/api/pipeline-studio/runs` | pc | `api/pipeline_studio.py:647` | token |
| `GET` | `/api/pipeline-studio/runs/{run_id}` | pc | `api/pipeline_studio.py:522` | token |
| `GET` | `/api/pipeline-studio/steps` | pc | `api/pipeline_studio.py:341` | token |
| `GET` | `/api/pipeline-studio/templates` | pc | `api/pipeline_studio.py:390` | token |
| `GET` | `/api/scraper/history` | pc | `api/scraper.py:123` | token |
| `GET` | `/api/scraper/history` | vm | `vm_api/routes.py:530` | token |
| `GET` | `/api/skills/health` | pc | `api/skills.py:335` | token |
| `GET` | `/api/skills/proposals` | pc | `api/skills.py:94` | token |
| `GET` | `/api/skills/proposals/{proposal_id}` | pc | `api/skills.py:134` | token |
| `GET` | `/api/skills/proposals/{proposal_id}/yaml-preview` | pc | `api/skills.py:147` | token |
| `GET` | `/api/skills/synthesis-runs/{run_id}` | pc | `api/skills.py:292` | token |
| `GET` | `/api/user-prefs` | pc | `api/user_prefs.py:70` | token |

## §4 TOP 10 priorizado

Ranking: owner_pain_score (5=tail/decisions live) → method (write > read) → path.

| Rank | Endpoint | Método | Side | Chapter destino | WS needed | CLI hoje | Owner pain (1-5) |
|---|---|---|---|---|---|---|---|
| 1 | `/api/daemon/broadcast` | `POST` | pc | F.2 | — | `curl -X POST /api/daemon/broadcast` | 5 |
| 2 | `/api/daemon/pause` | `POST` | pc | F.2 | — | `curl -X POST /api/daemon/pause` | 5 |
| 3 | `/api/daemon/resume` | `POST` | pc | F.2 | — | `curl -X POST /api/daemon/resume` | 5 |
| 4 | `/api/daemon/subsystems/all/pause` | `POST` | pc | F.2 | — | `curl -X POST /api/daemon/subsystems/all/pause` | 5 |
| 5 | `/api/daemon/subsystems/{name}/pause` | `POST` | pc | F.2 | — | `curl -X POST /api/daemon/subsystems/{name}/pause` | 5 |
| 6 | `/api/daemon/subsystems/{name}/resume` | `POST` | pc | F.2 | — | `curl -X POST /api/daemon/subsystems/{name}/resume` | 5 |
| 7 | `/api/linkedin/cobaia/timeline` | `GET` | pc | F.3 | — | `curl /api/linkedin/cobaia/timeline` | 5 |
| 8 | `/api/agent-zero/chat` | `POST` | pc | F.6 | ✅ | `curl POST + parse stream manual` | 4 |
| 9 | `/api/brain/confirm/{run_id}` | `POST` | pc | F.6 | ✅ | `curl -X POST /api/brain/confirm/{run_id}` | 4 |
| 10 | `/api/brain/decide` | `POST` | pc | F.6 | ✅ | `curl -X POST /api/brain/decide` | 4 |

**Justificativa por linha**:

1. **`POST /api/daemon/broadcast`** — Trigger broadcast WS arbitrário (devtool) — escondido pra owner, expose só em modo debug
2. **`POST /api/daemon/pause`** — Botão pause daemon (timeout N min) no header Mission Control
3. **`POST /api/daemon/resume`** — Botão resume daemon junto do pause
4. **`POST /api/daemon/subsystems/all/pause`** — /api/daemon/subsystems/all/pause
5. **`POST /api/daemon/subsystems/{name}/pause`** — /api/daemon/subsystems/{name}/pause
6. **`POST /api/daemon/subsystems/{name}/resume`** — /api/daemon/subsystems/{name}/resume
7. **`GET /api/linkedin/cobaia/timeline`** — /api/linkedin/cobaia/timeline
8. **`POST /api/agent-zero/chat`** — Chat AI no dashboard — substitui CLI Agent Zero
9. **`POST /api/brain/confirm/{run_id}`** — /api/brain/confirm/{run_id}
10. **`POST /api/brain/decide`** — /api/brain/decide

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

- Handlers em `app.js`: 15 (activity, alert, audit_done, channel_update, daemon_state, decision, linkedin_campaign_created, linkedin_campaign_done, linkedin_health, linkedin_progress, pipeline_progress, reply_received, scraper_update, string, sync)
- Broadcasts no backend: 10 (activity, channel_update, daemon_state, decision, linkedin_account_type_updated, linkedin_campaign_created, linkedin_health, linkedin_progress, linkedin_session_rotated, sync)
- ✅ Matched (emitido + handler): activity, channel_update, daemon_state, decision, linkedin_campaign_created, linkedin_health, linkedin_progress, sync
- ⚠️ Orphan broadcasts (emitido sem handler): linkedin_account_type_updated, linkedin_session_rotated
- 🪦 Dead handlers (handler sem emitter local): alert, audit_done, linkedin_campaign_done, pipeline_progress, reply_received, scraper_update, string

---

Gerado por `.claude/skills/hermes-frontend-gap/scripts/rank_gaps.py`.
Reproduzir: `python .claude/skills/hermes-frontend-gap/scripts/{parse_routes,grep_frontend,rank_gaps}.py`
