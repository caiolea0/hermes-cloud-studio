# FRONTEND-GAP — Backend↔Frontend audit

- **last_updated**: 2026-06-23 17:30 UTC
- **phase_baseline**: post F.7
- **routes_total**: 250 (189 PC + 61 VM, 5 internal-only excluded)
- **consumed**: 142 (58.0% of public)
- **orphans**: 103
- **top_10_priority**: see §4

> Auditoria determinística cruzando AST routes FastAPI com consumo `dashboard/app.js + components/*.js`.
> Re-rodável: `python .claude/skills/hermes-frontend-gap/scripts/rank_gaps.py`.
> Re-execução ao fechar QUALQUER chapter F.2-F.9 é termômetro UX (GUARDRAILS §F.1).

## §1 Inventário routes (PC + VM)

- Total: **250** rotas FastAPI (189 PC, 61 VM)
- WS endpoints: 2
- Internal-only (loopback): 5 (excluídos do gap)

| Arquivo | Rotas |
|---|---|
| `vm_api/routes.py` | 46 |
| `api/linkedin.py` | 21 |
| `api/cobaia.py` | 19 |
| `api/pipeline_studio.py` | 13 |
| `api/skills.py` | 13 |
| `api/daemon.py` | 12 |
| `api/pipelines.py` | 9 |
| `api/prospects.py` | 9 |
| `api/brain.py` | 8 |
| `api/observability.py` | 8 |
| `api/hermes.py` | 7 |
| `api/sequences.py` | 7 |
| `api/templates.py` | 7 |
| `api/onboarding.py` | 5 |
| `api/lab.py` | 5 |
| `api/scraper.py` | 5 |
| `api/tasks.py` | 5 |
| `api/audit.py` | 4 |
| `api/server_ctrl.py` | 4 |
| `vm_api/vuecra.py` | 4 |
| `api/icp.py` | 3 |
| `api/internal.py` | 3 |
| `api/dashboard.py` | 2 |
| `api/activities.py` | 2 |
| `api/agent_zero.py` | 2 |
| `_health_ep.py` | 2 |
| `api/mcp_coverage.py` | 2 |
| `api/tunnel.py` | 2 |
| `api/user_prefs.py` | 2 |
| `hermes_api_v2.py` | 2 |
| `vm_api/broadcast.py` | 2 |
| `vm_api/geo.py` | 2 |
| `vm_api/market.py` | 2 |
| `vm_api/mcp_coverage.py` | 2 |
| `api/bootstrap.py` | 1 |
| `api/claude.py` | 1 |
| `api/config.py` | 1 |
| `api/outreach.py` | 1 |
| `api/photos.py` | 1 |
| `api/skills_webhook.py` | 1 |
| `api/stats.py` | 1 |
| `server.py` | 1 |
| `vm_api/mcp_jobs.py` | 1 |

## §2 Mapa consumo (app.js + 59 components)

- Endpoints únicos consumidos: **142**
- Total fetch/api calls: 170
- Fontes escaneadas: 60 arquivos (app.js + components/*.js + HTML inline)
- Hash routes (páginas SPA): audit, claude, cobaia, control, dashboard, lab, linkedin, mcp-gateway, memory, missions, observability, pipeline-studio, proposals, prospects, sequences, skill-proposals, skills, tasks

| Endpoint | Chamadas | Fontes |
|---|---|---|
| `/api/linkedin/cobaia/status` | 7 | cobaia_day_countdown.js, cobaia_operator.js, cobaia_status_card.js |
| `/api/prospects` | 7 | app.js, sequence_enroll_modal.js |
| `/api/dashboard` | 6 | app.js |
| `/api/linkedin/cobaia/metrics` | 6 | cobaia_operator.js, cobaia_studio.js |
| `/api/linkedin/cobaia/timeline` | 6 | cobaia_operator.js, cobaia_studio.js |
| `/api/skills/proposals` | 6 | skill_proposals_modal.js, skill_proposals_studio.js |
| `/api/pipelines` | 5 | app.js |
| `/api/templates` | 5 | app.js, sequence_canvas.js, template_editor.js |
| `/api/audit/prospect/{param}` | 3 | app.js |
| `/api/linkedin/cobaia/resume` | 3 | app.js, cobaia_emergency_stop.js, cobaia_status_card.js |
| `/api/observability/errors` | 3 | cobaia_sentry_banner.js, observability_errors.js, observability_resolve_modal.js |
| `/api/onboarding/state` | 3 | app.js, onboarding_wizard.js |
| `/api/pipelines/{param}` | 3 | app.js |
| `/api/prospects/{param}` | 3 | app.js |
| `/api/sequences` | 3 | sequence_canvas.js, sequence_enroll_modal.js |
| `/api/activities` | 2 | app.js |
| `/api/audit/status` | 2 | app.js |
| `/api/hermes/memory` | 2 | app.js |
| `/api/hermes/skills/{param}` | 2 | app.js |
| `/api/hermes/status` | 2 | app.js |

## §3 Órfãos — 103 endpoints sem UI

Backend expõe mas dashboard não consome. Owner depende de CLI/curl/SSH.

| Method | Path | Side | File | Auth |
|---|---|---|---|---|
| `POST` | `/api/daemon/broadcast` | pc | `api/daemon.py:256` | token |
| `POST` | `/api/daemon/broadcast` | vm | `vm_api/broadcast.py:15` | token |
| `POST` | `/api/daemon/pause` | pc | `api/daemon.py:73` | token |
| `POST` | `/api/daemon/resume` | pc | `api/daemon.py:84` | token |
| `GET` | `/api/daemon/ws_stats` | vm | `vm_api/broadcast.py:28` | token |
| `POST` | `/api/agent-zero/chat` | pc | `api/agent_zero.py:43` | token |
| `POST` | `/api/brain/confirm/{run_id}` | pc | `api/brain.py:242` | token |
| `POST` | `/api/brain/decide` | pc | `api/brain.py:189` | token |
| `POST` | `/api/brain/replay/{run_id}` | pc | `api/brain.py:229` | token |
| `POST` | `/api/prospects/{prospect_id}/resolve-conflict` | pc | `api/prospects.py:156` | token |
| `GET` | `/api/agent-zero/status` | pc | `api/agent_zero.py:15` | token |
| `GET` | `/api/brain/intents` | pc | `api/brain.py:353` | token |
| `GET` | `/api/brain/runs/{run_id}` | pc | `api/brain.py:218` | token |
| `GET` | `/api/linkedin/visited` | pc | `api/linkedin.py:445` | token |
| `GET` | `/api/linkedin/visited` | vm | `vm_api/routes.py:1554` | token |
| `POST` | `/api/audit/batch` | vm | `vm_api/routes.py:727` | token |
| `POST` | `/api/channels/configure` | pc | `api/onboarding.py:131` | token |
| `POST` | `/api/cobaia/autotune-trigger-manual` | pc | `api/cobaia.py:425` | token |
| `POST` | `/api/cobaia/verify-email` | pc | `api/cobaia.py:749` | token |
| `POST` | `/api/icp/profile` | pc | `api/icp.py:85` | token |
| `POST` | `/api/linkedin/campaigns/discover` | pc | `api/linkedin.py:411` | token |
| `POST` | `/api/linkedin/campaigns/discover` | vm | `vm_api/routes.py:1242` | token |
| `POST` | `/api/linkedin/campaigns/engage` | pc | `api/linkedin.py:399` | token |
| `POST` | `/api/linkedin/campaigns/engage` | vm | `vm_api/routes.py:1133` | token |
| `POST` | `/api/linkedin/cobaia/today-queue/{item_id}/skip` | pc | `api/cobaia.py:819` | token |
| `POST` | `/api/linkedin/connection/refresh` | pc | `api/linkedin.py:483` | token |
| `POST` | `/api/linkedin/connection/refresh` | vm | `vm_api/routes.py:1734` | token |
| `POST` | `/api/linkedin/detect-account-type` | pc | `api/linkedin.py:463` | token |
| `POST` | `/api/linkedin/detect-account-type` | vm | `vm_api/routes.py:1515` | token |
| `POST` | `/api/linkedin/health/clear` | pc | `_health_ep.py:15` | token |
| `POST` | `/api/linkedin/health/clear` | pc | `api/linkedin.py:478` | token |
| `POST` | `/api/linkedin/health/clear` | vm | `vm_api/routes.py:1542` | token |
| `POST` | `/api/mcp/coverage/publish` | vm | `vm_api/mcp_coverage.py:80` | token |
| `POST` | `/api/observability/errors/{error_id}/resolve` | pc | `api/observability.py:402` | token |
| `POST` | `/api/outreach/batch` | vm | `vm_api/routes.py:803` | token |
| `DELETE` | `/api/pipeline-studio/drafts/{draft_id}` | pc | `api/pipeline_studio.py:269` | token |
| `PUT` | `/api/pipeline-studio/drafts/{draft_id}` | pc | `api/pipeline_studio.py:219` | token |
| `POST` | `/api/pipeline-studio/drafts/{draft_id}/clone` | pc | `api/pipeline_studio.py:601` | token |
| `POST` | `/api/pipeline-studio/drafts/{draft_id}/execute` | pc | `api/pipeline_studio.py:459` | token |
| `POST` | `/api/pipeline-studio/runs/{run_id}/abort` | pc | `api/pipeline_studio.py:748` | token |
| `POST` | `/api/pipeline/execute` | vm | `vm_api/routes.py:850` | token |
| `POST` | `/api/prospects/{prospect_id}/outreach` | vm | `vm_api/routes.py:764` | token |
| `DELETE` | `/api/sequences/{seq_id}` | pc | `api/sequences.py:203` | token |
| `PUT` | `/api/sequences/{seq_id}` | pc | `api/sequences.py:173` | token |
| `POST` | `/api/sequences/{seq_id}/dry-run` | pc | `api/sequences.py:336` | token |
| `POST` | `/api/sequences/{seq_id}/enroll` | pc | `api/sequences.py:257` | token |
| `POST` | `/api/server/restart-all` | pc | `api/server_ctrl.py:80` | rate-limited |
| `POST` | `/api/server/restart-local` | pc | `api/server_ctrl.py:22` | rate-limited |
| `POST` | `/api/server/restart-vm` | pc | `api/server_ctrl.py:54` | rate-limited |
| `POST` | `/api/server/shutdown-local` | pc | `api/server_ctrl.py:36` | rate-limited |
| `POST` | `/api/skills/proposals/{proposal_id}/accept` | pc | `api/skills.py:181` | token |
| `POST` | `/api/skills/proposals/{proposal_id}/reject` | pc | `api/skills.py:241` | token |
| `POST` | `/api/skills/proposals/{proposal_id}/unverify` | pc | `api/skills.py:455` | token |
| `POST` | `/api/skills/proposals/{proposal_id}/verify` | pc | `api/skills.py:411` | token |
| `POST` | `/api/skills/webhook/pr-merged` | pc | `api/skills_webhook.py:186` | rate-limited |
| `POST` | `/api/skills/{skill_name}/unquarantine` | pc | `api/skills.py:501` | token |
| `POST` | `/api/tasks/bulk` | pc | `api/tasks.py:93` | token |
| `POST` | `/api/templates/render` | pc | `api/templates.py:259` | token |
| `DELETE` | `/api/templates/{template_id}` | pc | `api/templates.py:247` | token |
| `PUT` | `/api/templates/{template_id}` | pc | `api/templates.py:216` | token |
| `POST` | `/api/vuecra/{prospect_id}/claim` | vm | `vm_api/vuecra.py:138` | token |
| `POST` | `/api/vuecra/{prospect_id}/delivered` | vm | `vm_api/vuecra.py:219` | token |
| `POST` | `/api/vuecra/{prospect_id}/failed` | vm | `vm_api/vuecra.py:315` | token |
| `GET` | `/api/lab/runs/{run_id}/artifacts/{filename}` | pc | `api/lab.py:479` | token |
| `GET` | `/api/stats` | pc | `api/stats.py:11` | token |
| `GET` | `/api/stats` | vm | `vm_api/routes.py:356` | token |
| `GET` | `/` | pc | `api/dashboard.py:14` | token |
| `GET` | `/api/_ping` | vm | `hermes_api_v2.py:165` | token |
| `GET` | `/api/channels/{channel}/test` | pc | `api/onboarding.py:146` | token |
| `GET` | `/api/cobaia/autotune-history` | pc | `api/cobaia.py:367` | token |
| `GET` | `/api/cobaia/autotune-status` | pc | `api/cobaia.py:399` | token |
| `GET` | `/api/cobaia/bug-export` | pc | `api/cobaia.py:266` | token |
| `GET` | `/api/cobaia/f7-report` | pc | `api/cobaia.py:633` | token |
| `GET` | `/api/cobaia/health-score` | pc | `api/cobaia.py:294` | token |
| `GET` | `/api/cobaia/hunter-usage` | pc | `api/cobaia.py:775` | token |
| `GET` | `/api/cobaia/preflight` | pc | `api/cobaia.py:494` | token |
| `GET` | `/api/cobaia/sentry-env` | pc | `api/cobaia.py:351` | token |
| `GET` | `/api/geo/bairros` | vm | `vm_api/geo.py:119` | token |
| `GET` | `/api/geo/prospects` | vm | `vm_api/geo.py:36` | token |
| `GET` | `/api/icp/presets` | pc | `api/icp.py:92` | token |
| `GET` | `/api/icp/profile` | pc | `api/icp.py:78` | token |
| `GET` | `/api/linkedin/companies/lookup` | pc | `api/linkedin.py:457` | token |
| `GET` | `/api/linkedin/companies/lookup` | vm | `vm_api/routes.py:1612` | token |
| `GET` | `/api/linkedin/session-check` | vm | `vm_api/routes.py:1426` | token |
| `GET` | `/api/market/heatmap` | vm | `vm_api/market.py:113` | token |
| `GET` | `/api/market/signals` | vm | `vm_api/market.py:39` | token |
| `GET` | `/api/mcp/coverage/jobs/{job_id}` | vm | `vm_api/mcp_jobs.py:26` | token |
| `GET` | `/api/observability/_debug/explain_cost_plan` | pc | `api/observability.py:668` | token |
| `GET` | `/api/observability/credits` | pc | `api/observability.py:166` | token |
| `GET` | `/api/observability/mcp-coverage-history` | pc | `api/observability.py:621` | token |
| `GET` | `/api/photos/{photo_ref:path}` | pc | `api/photos.py:15` | token |
| `GET` | `/api/pipeline-studio/drafts/{draft_id}` | pc | `api/pipeline_studio.py:199` | token |
| `GET` | `/api/pipeline-studio/runs/{run_id}` | pc | `api/pipeline_studio.py:529` | token |
| `GET` | `/api/scraper/history` | pc | `api/scraper.py:123` | token |
| `GET` | `/api/scraper/history` | vm | `vm_api/routes.py:556` | token |
| `GET` | `/api/sequences/{seq_id}` | pc | `api/sequences.py:150` | token |
| `GET` | `/api/skills/health` | pc | `api/skills.py:335` | token |
| `GET` | `/api/skills/proposals-pending-verify` | pc | `api/skills.py:485` | token |
| `GET` | `/api/skills/proposals/{proposal_id}` | pc | `api/skills.py:137` | token |
| `GET` | `/api/skills/proposals/{proposal_id}/yaml-preview` | pc | `api/skills.py:150` | token |
| `GET` | `/api/skills/synthesis-runs/{run_id}` | pc | `api/skills.py:292` | token |
| `GET` | `/api/templates/{template_id}` | pc | `api/templates.py:203` | token |
| `GET` | `/api/vuecra/queue` | vm | `vm_api/vuecra.py:83` | token |

## §4 TOP 10 priorizado

Ranking: owner_pain_score (5=tail/decisions live) → method (write > read) → path.

| Rank | Endpoint | Método | Side | Chapter destino | WS needed | CLI hoje | Owner pain (1-5) |
|---|---|---|---|---|---|---|---|
| 1 | `/api/daemon/broadcast` | `POST` | pc | F.2 | — | `curl -X POST /api/daemon/broadcast` | 5 |
| 2 | `/api/daemon/broadcast` | `POST` | vm | F.2 | — | `curl -X POST /api/daemon/broadcast` | 5 |
| 3 | `/api/daemon/pause` | `POST` | pc | F.2 | — | `curl -X POST /api/daemon/pause` | 5 |
| 4 | `/api/daemon/resume` | `POST` | pc | F.2 | — | `curl -X POST /api/daemon/resume` | 5 |
| 5 | `/api/daemon/ws_stats` | `GET` | vm | F.2 | — | `curl /api/daemon/ws_stats` | 5 |
| 6 | `/api/agent-zero/chat` | `POST` | pc | F.6 | ✅ | `curl POST + parse stream manual` | 4 |
| 7 | `/api/brain/confirm/{run_id}` | `POST` | pc | F.6 | ✅ | `curl -X POST /api/brain/confirm/{run_id}` | 4 |
| 8 | `/api/brain/decide` | `POST` | pc | F.6 | ✅ | `curl -X POST /api/brain/decide` | 4 |
| 9 | `/api/brain/replay/{run_id}` | `POST` | pc | F.6 | ✅ | `curl -X POST /api/brain/replay/{run_id}` | 4 |
| 10 | `/api/prospects/{prospect_id}/resolve-conflict` | `POST` | pc | F.6 | — | `curl -X POST /api/prospects/{prospect_id}/resolve-conflict` | 4 |

**Justificativa por linha**:

1. **`POST /api/daemon/broadcast`** — Trigger broadcast WS arbitrário (devtool) — escondido pra owner, expose só em modo debug
2. **`POST /api/daemon/broadcast`** — Trigger broadcast WS arbitrário (devtool) — escondido pra owner, expose só em modo debug
3. **`POST /api/daemon/pause`** — Botão pause daemon (timeout N min) no header Mission Control
4. **`POST /api/daemon/resume`** — Botão resume daemon junto do pause
5. **`GET /api/daemon/ws_stats`** — /api/daemon/ws_stats
6. **`POST /api/agent-zero/chat`** — Chat AI no dashboard — substitui CLI Agent Zero
7. **`POST /api/brain/confirm/{run_id}`** — /api/brain/confirm/{run_id}
8. **`POST /api/brain/decide`** — /api/brain/decide
9. **`POST /api/brain/replay/{run_id}`** — /api/brain/replay/{run_id}
10. **`POST /api/prospects/{prospect_id}/resolve-conflict`** — Botão dismiss conflict no row de prospect

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

- Handlers no frontend: 17 (activity, alert, audit_done, channel_update, daemon_state, decision, error, final, linkedin_campaign_created, linkedin_campaign_done, linkedin_health, linkedin_progress, pipeline_progress, reply_received, scraper_update, sync, thought)
- Broadcasts no backend: 10 (activity, channel_update, daemon_state, decision, linkedin_account_type_updated, linkedin_campaign_created, linkedin_health, linkedin_progress, linkedin_session_rotated, sync)
- ✅ Matched (emitido + handler): activity, channel_update, daemon_state, decision, linkedin_campaign_created, linkedin_health, linkedin_progress, sync
- ⚠️ Orphan broadcasts (emitido sem handler): linkedin_account_type_updated, linkedin_session_rotated
- 🪦 Dead handlers (handler sem emitter local): alert, audit_done, error, final, linkedin_campaign_done, pipeline_progress, reply_received, scraper_update, thought

---

Gerado por `.claude/skills/hermes-frontend-gap/scripts/rank_gaps.py`.
Reproduzir: `python .claude/skills/hermes-frontend-gap/scripts/{parse_routes,grep_frontend,rank_gaps}.py`
