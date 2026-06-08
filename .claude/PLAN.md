--- a/.claude/PLAN.md
+++ b/.claude/PLAN.md
@@ -593,99 +593,442 @@
 ---
 
-## Fase F — Hermes Operacional + Self-Evolving (4-6 semanas) — INICIADA 2026-06-08
+## FASE F — Owner solo no-code (4-6 semanas) — INICIADA 2026-06-08, RE-FORMALIZADA 2026-06-08
 
 **Diagnóstico re-auditoria 2026-06-08** (ver `.claude/AUDIT-2026-06-08-FASE-F.md` + `.claude/PHASE-F-STUDY-SYNTHESIS.md`):
 - Backend solidificado (Fases A-D + E.1+E.2 XSS = 20/22 findings PASS)
 - Gap real: backend↔frontend (owner CLI-dependent), cobaia ociosa, sem cérebro orquestrador, MCPs subutilizados
-- Foco Fase F: tirar Hermes do "engine pronta sem volante" pra "operador no-code orquestrando frota"
+- Foco FASE F: tirar Hermes de "engine pronta sem volante" pra "owner solo no-code orquestrando frota"
+- North star: owner abre `dashboard/control`, vê tudo, comanda tudo, NUNCA precisa de terminal/SSH/curl
+
+### Visão consolidada FASE F
+
+| Chapter | Título                                              | Class.        | UI score | Sessões | Status      | Dep.        |
+|---------|-----------------------------------------------------|---------------|----------|---------|-------------|-------------|
+| F.1     | Backend↔Frontend Gap Audit                          | research+ui   | 3        | 1       | EM ANDAMENTO| —           |
+| F.2     | Mission Control Real-Time + Design System Polish    | ui+backend    | 9        | 5       | PLANEJADO   | F.1         |
+| F.3     | Lab Cockpit + Stealth UX                            | ui+backend    | 8        | 4       | PLANEJADO   | F.1         |
+| F.4     | Auto-Skill Loop W3 + GitHub PR-based deploy         | backend+ui    | 7        | 5       | PLANEJADO   | F.1, F.5    |
+| F.5     | MCP Gateway + Discovery + Custom MCPs               | backend+infra | 4        | 4       | PLANEJADO   | F.1         |
+| F.6     | Cérebro Hermes (Brain orchestrator)                 | backend+ui    | 9        | 6       | PLANEJADO   | F.1, F.5    |
+| F.7     | Cobaia Live Ops + Warmup 14d automatizado           | backend+ui    | 8        | 5       | PLANEJADO   | F.2, F.5    |
+| F.8     | Cost & Performance Observability                    | backend+ui    | 7        | 3       | PLANEJADO   | F.2, F.6    |
+| F.9     | Pipeline Studio Visual (form-driven)                | ui+backend    | 9        | 5       | PLANEJADO   | F.1, F.6    |
+
+**Total estimado**: 38 sessões (1 + 5 + 4 + 5 + 4 + 6 + 5 + 3 + 5). Banda histórica 50-150k tokens/sessão = 4-6 semanas calendário owner solo, ritmo 1-2 sessões/dia.
+
+**Gate inegociável cross-chapter**: `validate_implementation.py --phase A B C D E` deve continuar 20/22 PASS antes E depois de cada chapter que toca código MADURO. Falha = REVERT.
 
 ### Chapter F.1 — Backend↔Frontend Gap Audit
-- [ ] Skill `hermes-frontend-gap`: parser `api/*.py` + `vm_api/routes.py` → 144 rotas
-- [ ] Grep `dashboard/app.js` → mapa rotas consumidas vs órfãs
-- [ ] Output `.claude/FRONTEND-GAP.md` ranking impacto UX
-- [ ] Owner decide top 10 features pra expor
-
-### Chapter F.2 — Mission Control Real-Time Upgrade
-- [ ] Polir `dashboard/control` (Mission Control)
-- [ ] Activity Orbit expandida: tile por subsistema com status WS live
-- [ ] Botão pause/resume por subsistema
-- [ ] Live tail logs (WS rolling buffer)
-- [ ] Indicadores visuais saudável/warning/erro
-- [ ] Persistir user prefs
-
-### Chapter F.3 — Lab Cockpit
-- [ ] Página `dashboard/lab` nova
-- [ ] UI rodar `lab_runner.py` sem CLI (botões fingerprint/login/viewer)
-- [ ] Live screenshot polling
-- [ ] Compliance score + delta vs baseline
-- [ ] Runs históricos com diff fingerprint
-- [ ] API `/api/lab/{runs,start,artifacts}`
-
-### Chapter F.4 — Auto-Skill Loop W3
-- [ ] Workflow `.claude/workflows/hermes-skill-forge.js`
-- [ ] Pipeline: activity 30d → classify intents Ollama → propõe skills YAML → lab-test → submete dashboard
-- [ ] Nova tabela `skill_proposals` PC
-- [ ] UI `/skills/proposals` com YAML preview + accept/reject
-- [ ] Accept sync VM `~/.hermes/skills/` auto
-- [ ] Reject log feedback
-
-### Chapter F.5 — MCP Discovery + Integration
-- [ ] Workflow `mcp-discovery-survey` — research MCPs 2026 com ROI
-- [ ] Integrar 2-3 MCPs públicos prioritários (candidatos: github, sqlite, playwright Anthropic, firecrawl, exa)
-- [ ] Desenvolver `linkedin-lab` MCP custom (test_flow, capture_trace, fingerprint_compare)
-- [ ] Decisão go/no-go: `prospect-enricher`, `ollama-router-mcp`, `hermes-brain-mcp`
-
-### Chapter F.6 — Cérebro Hermes: Orchestration Layer
-- [ ] Decisão arquitetural: classifier intent qwen2.5:3b → tool router → execute
-- [ ] Módulo `core/brain.py`: chat → classify → dispatch → stream
-- [ ] Tools registry: skills+pipelines+MCPs+endpoints sob namespace único
-- [ ] UI chat dashboard com cards de ações executadas
-- [ ] Multi-turn `_brain_context_id`
-- [ ] WS stream tokens + action events
-- [ ] Tabela `brain_sessions`
-
-### Chapter F.7 — Cobaia Live Ops
-- [ ] Documentar plano warmup 14d com gates diários
-- [ ] Daemon auto-exec: d0-6 lurking, d7-13 ramp connects, d14+ outreach
-- [ ] Métricas: acceptance_rate (já), reply_rate, ban_probability
-- [ ] Stop gates: burned_flag, compliance<70, acceptance<40%
-- [ ] Daily Telegram report
-- [ ] Dashboard `/cobaia` timeline + métricas
-
-### Chapter F.8 — Cost & Performance Observability (NOVO)
-- [ ] Cost tracking LLM calls (Claude+OpenRouter+Ollama) — tokens + USD agg
-- [ ] Performance dashboard p50/p95/p99 endpoints PC+VM, throughput loops, slow queries
-- [ ] Error inbox visual: agrega 24h, triage, permalink trace (substitui SSH logs)
-- [ ] Audit trail Brain.decide() acoplado F.6
-- [ ] API `/api/observability/{costs,perf,errors,decisions}`
-- [ ] Dashboard `/observability` 4 tabs
-
-### Chapter F.9 — Pipeline Studio Visual (NOVO)
-- [ ] Pipeline builder form-driven (decisão design: NÃO canvas drag-drop, owner solo)
-- [ ] Step library: skills + pipelines + MCP tools + endpoints como steps
-- [ ] Live execution monitor por step (status/output/timing/error inline)
-- [ ] Template gallery clone-and-modify
-- [ ] A/B test pipelines paralelas
-- [ ] API `/api/pipeline-studio/{steps,templates,execute,monitor}`
-- [ ] Tabela `pipeline_drafts` + `pipeline_runs` granular
-- [ ] Dashboard `/pipeline-studio` substitui parcialmente `/pipeline` legado
-
-### Regra inviolável Fase F — Regression-test gate
+
+**Classification**: research+ui · **UI score**: 3 · **Estimated sessions**: 1 · **Status**: EM ANDAMENTO · **Dependencies**: nenhuma
+
+**Deliverable**: `.claude/FRONTEND-GAP.md` + skill `hermes-frontend-gap/` + slash command `/hermes-frontend-gap`. Mapa autoritativo dos 144+ endpoints PC+VM cruzado com consumo `dashboard/app.js` (5429 linhas, 271 fetch calls), top-10 priorizado por impacto UX/owner-pain alimentando F.2-F.9.
+
+- [ ] Task 1: Parser AST routes PC+VM — `parse_routes.py` (api/*.py + vm_api/routes.py + server.py + hermes_api_v2.py); output `.claude/frontend-gap/routes.json`; sanity hard ≥140 rotas
+- [ ] Task 2: Grep consumo dashboard/app.js — `grep_frontend.py`; cobre fetch + WS subscriptions + path params dinâmicos + channels/*.py emitters cruzados com socket.on()
+- [ ] Task 3: Diff + ranking — `rank_gaps.py` → `.claude/FRONTEND-GAP.md` 6 seções (Inventário, Mapa consumo, Órfãos, TOP 10, Quick Wins UX, Mission Control endpoints); assert hard contém 11 fantasmas conhecidos (§2 PHASE-F-STUDY-SYNTHESIS); colunas top-10: rank, endpoint, método, side, chapter_destino, ws_event_needed, cli_command_replaced, owner_pain_score (1-5)
+- [ ] Task 4: Empacotar skill `hermes-frontend-gap/SKILL.md` + `/hermes-frontend-gap` slash + permissions escopadas em settings.local.json (não wildcard `python *`)
+- [ ] Task 5: Validação regressão + persistência 6-camadas — pre/post `validate_implementation.py --phase A B C D E` (20/22 PASS gate); PLAN.md F.1 ✅; GUARDRAILS.md regra ✅ SEMPRE 'Backend novo SEM consumo frontend = débito imediato'; memory_save `hermes F.1 complete`; mark_chapter; commit `docs(audit): F.1 — FRONTEND-GAP.md + skill hermes-frontend-gap`
+
+**11 endpoints fantasma esperados no TOP 10** (sanity check):
+`/api/prospects/{id}/resolve-conflict`, `/api/tasks/bulk`, `/api/stats`, `/api/daemon/state`, `/api/daemon/log`, `/api/daemon/decisions`, `/api/daemon/channels`, `/api/daemon/timeline`, `/api/linkedin/visited`, `/api/linkedin/comment/{edit|delete}`, `/api/agent-zero/{status|chat}`.
+
+**Done criteria F.1**: skill re-rodável <90s end-to-end · FRONTEND-GAP.md tem `last_updated` + `phase_baseline` (vira termômetro de progresso UX) · diff-vs-known.md gerado em re-execuções pra detectar drift · 20/22 PASS preservado.
+
+### Chapter F.2 — Mission Control Real-Time + Design System Polish
+
+**Classification**: ui+backend · **UI score**: 9 · **Estimated sessions**: 5 · **Status**: PLANEJADO · **Dependencies**: F.1 (top-10 daemon/* fantasmas)
+
+**Deliverable**: `dashboard/control` real-time completo. Owner vê todos os 6 subsistemas (linkedin/email/scraper/audit/daemon/tunnel) com status WS live, pause/resume individual, live tail logs (rolling buffer WS), timeline de decisões últimas 24h, indicadores semafóricos saudável/warning/erro. Design system polido (CSS tokens + dark mode + toast component reutilizável).
+
+**APIs a expor (F.1 → consumir aqui)**:
+- `GET /api/daemon/state` · `GET /api/daemon/log` · `GET /api/daemon/decisions` · `GET /api/daemon/channels` · `GET /api/daemon/timeline`
+- `POST /api/daemon/pause` · `POST /api/daemon/resume`
+
+**APIs novas**:
+- `GET /api/daemon/subsystems` — snapshot agregado healthy/warning/error + última ação + próxima agendada por subsistema (lê runtime_state + daemon_state + channels stats)
+- `POST /api/daemon/subsystems/{name}/pause` + `/resume` — pausa subsistema individual por N min
+- `WS /ws/daemon/subsystems` — broadcast status delta em mudança
+
+**Tasks**:
+- [ ] Task 1: Backend `/api/daemon/subsystems` GET — agrega state.json + daemon_state + channels; cobertura testes 6 subsistemas
+- [ ] Task 2: Backend POST pause/resume por subsistema — escreve `subsystem_pause` no daemon_state; loops checam flag a cada tick (não interrompe execução atual)
+- [ ] Task 3: WS broadcast — `ws_manager.broadcast('subsystem_state', ...)` em loops/sync.py via spawn() pattern (MERGED-001); pre_test loops resilience phase D
+- [ ] Task 4: Live tail logs WS — `/ws/daemon/log-tail` com rolling buffer 500 linhas em memória; backend SSE alternativa fallback
+- [ ] Task 5: UI Activity Orbit redesign — tile por subsistema em grid 3x2; cores semafóricas (verde/amarelo/vermelho); contagem ações 24h; botão pause/resume inline com confirmação
+- [ ] Task 6: UI Timeline component — list virtualizada decisões/eventos últimas 24h; filtros subsistema + tipo (decision/action/error); permalink por evento
+- [ ] Task 7: UI Live tail panel — collapsible drawer bottom; auto-scroll; pause-on-hover; clear button; filter por subsistema/severity
+- [ ] Task 8: Design system polish — CSS tokens (`dashboard/styles/tokens.css`: colors, spacing, radius, shadows); dark mode toggle persistido localStorage; toast component reutilizável (`dashboard/components/toast.js`); migrar 5 alerts inline existentes pra toast
+- [ ] Task 9: User prefs persistence — `GET/PUT /api/user/prefs` (theme, panel layout, filters); tabela `user_prefs` PC (1 row owner solo)
+- [ ] Task 10: Validação regressão + persistência — pre/post phase A B D (toca loops/sync.py + api/daemon.py MADUROS); 20/22 PASS preservado; PLAN.md F.2 ✅; mark_chapter; commit `feat(mission-control): F.2 — real-time subsystems + design polish`
+
+**Done criteria F.2**: owner abre `/control` e nunca mais precisa SSH pra ver state daemon · pause/resume linkedin individual sem matar email/scraper · live tail substitui `ssh vm 'tail -f /var/hermes/log'` · dark mode persistido entre sessões · 20/22 PASS preservado.
+
+### Chapter F.3 — Lab Cockpit + Stealth UX
+
+**Classification**: ui+backend · **UI score**: 8 · **Estimated sessions**: 4 · **Status**: PLANEJADO · **Dependencies**: F.1
+
+**Deliverable**: Página `dashboard/lab` nova. Owner roda `lab_runner.py` sem CLI: botões "test fingerprint", "test login", "test viewer flow"; live screenshot polling 2s; compliance score + delta vs baseline; runs históricos com diff fingerprint; cobaia descartável workflow integrado.
+
+**APIs novas**:
+- `GET /api/lab/runs` · `POST /api/lab/runs/start` · `GET /api/lab/runs/{id}/artifacts` · `GET /api/lab/runs/{id}/screenshot` · `GET /api/lab/baselines`
+- `WS /ws/lab/run/{id}` — stream progress + screenshot delta
+
+**MCP integração**: Microsoft Playwright MCP (fallback QA descartável, NUNCA conta Caio) + custom `linkedin-lab` MCP (decisão F.5).
+
+**Tasks**:
+- [ ] Task 1: Backend `lab_runner.py` HTTP wrapper — POST start enfileira run, retorna run_id; subprocess.Popen com timeout 5min; PID tracking
+- [ ] Task 2: Backend WS progress — broadcast steps (fingerprint_init, login_attempt, viewer_navigate, ...) + screenshot path por step
+- [ ] Task 3: Backend compliance scorer — compara fingerprint atual vs baseline (`linkedin/stealth_compliance.py` extensão); output JSON score 0-100 + breakdown 8 dimensões
+- [ ] Task 4: UI página `/lab` — 3 botões action, painel live screenshot, sidebar histórico runs, modal compare 2 runs
+- [ ] Task 5: UI compliance dashboard — gauge score atual + sparkline 30d + breakdown 8 dimensões em radar chart
+- [ ] Task 6: Validação regressão + persistência — phase A B C D E (toca linkedin/stealth_compliance.py MADURO); 20/22 PASS; PLAN.md F.3 ✅; commit `feat(lab): F.3 — Lab Cockpit + compliance scorer`
+
+**Done criteria F.3**: owner valida stealth de cobaia nova sem terminar · compliance regression visível antes de toque produção · screenshot history pra debug DOM LinkedIn mudou · 20/22 PASS preservado.
+
+### Chapter F.4 — Auto-Skill Loop W3 + GitHub PR-based deploy
+
+**Classification**: backend+ui · **UI score**: 7 · **Estimated sessions**: 5 · **Status**: PLANEJADO · **Dependencies**: F.1, F.5 (GitHub MCP + Sentry MCP)
+
+**Deliverable**: Hermes propõe próprias skills observando activity 30d, classifica via Ollama qwen2.5:3b, gera YAML, testa em lab, abre PR no repo via GitHub MCP. Owner aprova/rejeita via `dashboard/skills/proposals`. Accept = merge PR + sync VM auto. Auto-disable skill se Sentry MCP reporta 5+ erros em 24h.
+
+**APIs novas**:
+- `GET /api/skills/proposals` · `POST /api/skills/proposals/{id}/{accept|reject}` · `GET /api/skills/proposals/{id}/yaml-preview`
+- `POST /api/skills/proposals/generate` — trigger manual loop
+- `GET /api/skills/health` — agrega Sentry + execution stats
+
+**DB migrations**: tabela `skill_proposals` PC (id, created_at, source_pattern, yaml_blob, lab_test_result, pr_url, status, owner_decision_at, owner_decision_reason)
+
+**Tasks**:
+- [ ] Task 1: Workflow `.claude/workflows/hermes-skill-forge.js` — pipeline activity 30d → classify intents → 3 candidatos YAML
+- [ ] Task 2: Backend `skill_proposals` CRUD + tabela; integração com hermes-skill-forge.js via API trigger
+- [ ] Task 3: GitHub MCP integração — `create_pull_request` em branch `skill/proposal-{id}`; owner aprovação UI = merge via API
+- [ ] Task 4: Lab test auto — antes de criar PR, roda skill em sandbox VM cobaia; fail = não cria PR, marca proposal como `lab_failed`
+- [ ] Task 5: UI `/skills/proposals` — list cards com YAML preview (Monaco editor read-only), diff vs skills existentes, botões accept/reject com modal reason
+- [ ] Task 6: Sync VM auto on accept — webhook GitHub merge → trigger `scp` skills/ + restart hermes_api_v2 via systemd
+- [ ] Task 7: Sentry MCP auto-disable — task scheduled 6h check skills com 5+ erros 24h → toggle off + notify owner Telegram
+- [ ] Task 8: Validação regressão + persistência — phase A B C D E (toca daemon/orchestrator.py se loop integrar); 20/22 PASS; PLAN.md F.4 ✅; commit `feat(skills): F.4 — auto-skill loop + GitHub PR deploy`
+
+**Done criteria F.4**: Hermes propõe ≥1 skill útil/semana sem owner pedir · PR-based deploy substitui scp+restart manual · auto-disable previne skill bugada queimar cobaia · 20/22 PASS preservado.
+
+### Chapter F.5 — MCP Gateway + Discovery + Custom MCPs
+
+**Classification**: backend+infra · **UI score**: 4 · **Estimated sessions**: 4 · **Status**: PLANEJADO · **Dependencies**: F.1
+
+**Deliverable**: IBM ContextForge MCP Gateway na VM como single endpoint multiplex. Brain (F.6) consulta APENAS gateway, NUNCA 15 MCPs direto. Auth + rate limit + audit trail + OpenTelemetry centralizado. 3 MCPs custom (hermes-linkedin, hermes-prospects, hermes-skills) sobre framework FastMCP 3.0 com OAuth 2.1 + JWT. Integração MCPs públicos prioritários selecionados via ROI matrix.
+
+**APIs novas**:
+- `GET /api/mcp/gateway/status` · `GET /api/mcp/gateway/tools` · `GET /api/mcp/gateway/audit-log`
+
+**MCP landscape priorizado (ROI alto, custo baixo, sem API paga adicional)**:
+
+| MCP                              | Tipo       | ROI Hermes                                                       | Effort | Phase |
+|----------------------------------|------------|------------------------------------------------------------------|--------|-------|
+| IBM ContextForge MCP Gateway     | Infra      | Multiplex+auth+audit 1 endpoint, A2A futuro                      | medium | F.5   |
+| FastMCP 3.0                      | Framework  | OAuth 2.1+JWT pros 3 MCPs custom, OpenTelemetry tracing          | low    | F.5   |
+| GitHub MCP (oficial)             | Público    | F.4 PR-based deploy, projects toolset task tracking F.6          | medium | F.5   |
+| Sentry MCP (oficial)             | Público    | F.4 auto-disable skill (5+ erros), F.7 monitoring live ops       | low    | F.5   |
+| Postgres MCP Pro (CrystalDBA)    | Público    | F.6 Brain.decide() read-only DB, index tuning, vacuum_health     | low    | F.5   |
+| Microsoft Playwright MCP         | Público    | F.3 fallback QA descartável (NUNCA conta Caio)                   | low    | F.5   |
+| MCP Omnisearch (spences10)       | Público    | F.7 discovery PME Cuiabá 7 providers em 1 MCP                    | low    | F.5   |
+| Firecrawl MCP (oficial)          | Público    | F.7 ICP enrichment site PME (alternativa a Apollo Brasil)        | low    | F.5   |
+| Hunter.io MCP (oficial)          | Público    | F.7 email verifier antes warmup (preserva reputação domínio)     | low    | F.5   |
+| WhatsApp Business MCP            | Público    | F.7 channel Brasil-first (vs Slack — Brasil PME = WhatsApp)      | medium | F.5   |
+| hermes-linkedin (custom)         | Custom     | Lab flow, capture trace, fingerprint compare, stealth probes     | medium | F.5   |
+| hermes-prospects (custom)        | Custom     | CRUD prospects + scoring + bulk ops (substitui curl owner)       | low    | F.5   |
+| hermes-skills (custom)           | Custom     | Skill registry + toggle + lab-test trigger                       | low    | F.5   |
+
+**Deferidos** (custo SaaS / cobertura Brasil duvidosa):
+- Apollo.io MCP — validar coverage PME Cuiabá antes investir
+- AgentMail MCP — SaaS pricing pode violar restrição "zero API paga além Claude Max"
+- Notion MCP — só se owner usar Notion (verificar)
+- Slack MCP — Brasil PME = WhatsApp, dar prioridade
+- Exa MCP standalone — redundante via Omnisearch
+
+**Tasks**:
+- [ ] Task 1: Deploy ContextForge Gateway na VM via Docker; config Redis cache + OpenTelemetry → Sentry; admin UI loopback-only
+- [ ] Task 2: Scaffold 3 MCPs custom em `mcps/hermes-{linkedin,prospects,skills}/` com FastMCP 3.0; OAuth 2.1 + JWT audience validation
+- [ ] Task 3: Integrar 6 MCPs públicos prioritários (GitHub, Sentry, Postgres Pro, Playwright, Omnisearch, Hunter.io) via gateway; testar tool discovery
+- [ ] Task 4: Decisão go/no-go WhatsApp Business MCP (validar Meta Cloud API credentials owner) + Firecrawl (se Omnisearch já cobrir)
+- [ ] Task 5: UI `/mcp/gateway` minimal — status gateway, lista 9-12 MCPs ativos, audit log últimas 24h (read-only)
+- [ ] Task 6: Validação regressão + persistência — phase A B C D E; 20/22 PASS; PLAN.md F.5 ✅; mark_chapter; commit `feat(mcp): F.5 — gateway + 6 públicos + 3 custom`
+
+**Done criteria F.5**: Brain F.6 chama 1 endpoint gateway, recebe 30+ tools agregadas · auth+rate-limit+audit centralizado · 3 MCPs custom respondem com OAuth 2.1 · 20/22 PASS preservado.
+
+### Chapter F.6 — Cérebro Hermes (Brain orchestrator)
+
+**Classification**: backend+ui · **UI score**: 9 · **Estimated sessions**: 6 · **Status**: PLANEJADO · **Dependencies**: F.1, F.5 (gateway operacional)
+
+**Deliverable**: `core/brain.py` — chat owner em PT-BR caveman vira ação executada. Classifier intent qwen2.5:3b → tool router (skills + pipelines + MCPs gateway + endpoints) → execute → stream resultado. UI chat em `dashboard/control` com cards de ações executadas em real-time. Multi-turn com context_id. Substitui CLI/curl completamente pra 80% das operações owner.
+
+**APIs novas**:
+- `POST /api/brain/chat` (multi-turn com context_id) · `GET /api/brain/sessions` · `GET /api/brain/sessions/{id}` · `DELETE /api/brain/sessions/{id}`
+- `WS /ws/brain/{context_id}` — stream tokens + action events + tool results
+- `GET /api/brain/tools` — registry tools disponíveis
+
+**DB migrations**: `brain_sessions` (id, owner, started_at, turns_count, context_summary) + `brain_turns` (session_id, idx, role, content, tool_calls JSON, latency_ms, cost_usd)
+
+**Tasks**:
+- [ ] Task 1: Backend `core/brain.py` — classifier intent qwen2.5:3b via ollama_router; output schema {intent, tool_name, args, confidence}
+- [ ] Task 2: Tools registry — namespace único (`skills.*`, `pipelines.*`, `mcp.<server>.<tool>`, `api.<endpoint>`); auto-discovery via FastMCP gateway + skills/pipelines diretórios
+- [ ] Task 3: Dispatcher — executa tool com timeout 60s; captura output; tratamento erro com retry exponencial 1x; log decision em `brain_audit` tabela (acopla F.8)
+- [ ] Task 4: WS streaming — tokens LLM + action_start + action_done + action_error events; client subscribe via context_id
+- [ ] Task 5: UI chat panel em `/control` — Composer bottom; histórico messages; cards inline pra cada tool_call (collapsed JSON output, expand on click); resume sessions sidebar
+- [ ] Task 6: Multi-turn context — sliding window 8 últimas turns + summary auto-gerado a cada 10 turns; `_brain_context_id` cookie
+- [ ] Task 7: Postgres MCP integration — Brain.decide() consulta `mcp.postgres.query` (read-only) pra "quantos prospects qualificados hoje?", "qual deal won última semana?"
+- [ ] Task 8: Validação regressão + persistência — phase A B C D E (toca core/ai.py + ollama_router.py MADUROS); 20/22 PASS; PLAN.md F.6 ✅; commit `feat(brain): F.6 — Cérebro Hermes orchestrator + chat UI`
+
+**Done criteria F.6**: owner digita "pause linkedin 2h" e Hermes executa via tool router · "quantos prospects warm Cuiabá?" retorna número via Postgres MCP · 80% operações CLI eliminadas · 20/22 PASS preservado.
+
+### Chapter F.7 — Cobaia Live Ops + Warmup 14d automatizado
+
+**Classification**: backend+ui · **UI score**: 8 · **Estimated sessions**: 5 · **Status**: PLANEJADO · **Dependencies**: F.2 (Mission Control), F.5 (MCPs Sentry/Hunter/Omnisearch)
+
+**Deliverable**: Cobaia LinkedIn opera 24/7 sem owner intervir. Warmup 14d com gates diários auto: d0-6 lurking + connects soft, d7-13 ramp connects + replies, d14+ outreach. Métricas live: acceptance_rate, reply_rate, ban_probability, burned_flag. Stop gates auto: compliance<70, acceptance<40%, ban detected. Daily Telegram report. Dashboard `/cobaia` timeline + métricas.
+
+**APIs novas**:
+- `GET /api/cobaia/state` · `GET /api/cobaia/metrics?range=24h|7d|14d` · `GET /api/cobaia/timeline`
+- `POST /api/cobaia/gate-override` (owner manual) · `POST /api/cobaia/burn-and-rotate`
+
+**DB migrations**: `cobaia_daily_metrics` (date, account, connects_sent, accepted, replied, viewed, ban_signals JSON, compliance_score, daemon_actions_count)
+
+**Tasks**:
+- [ ] Task 1: Daemon auto-exec warmup — `daemon/cobaia_orchestrator.py`: lê dia atual, dispara skill apropriada (lurking/connect_ramp/outreach); idempotente
+- [ ] Task 2: Métricas coletor — task scheduled 1h agrega LinkedIn API resp + `linkedin/visited` + replies daemon → escreve `cobaia_daily_metrics`
+- [ ] Task 3: Stop gates auto — check 30min: compliance<70 → pause subsystem linkedin + alert; acceptance<40% rolling 7d → notify owner; burned_flag → burn-and-rotate
+- [ ] Task 4: Daily Telegram report — task scheduled 19h (Cuiabá): markdown report últimas 24h + comparação 7d + alertas; via existing Telegram bot
+- [ ] Task 5: UI `/cobaia` dashboard — timeline events 14d com markers (login, connect, reply, ban_signal); 4 gauges (acceptance, reply, compliance, ban_prob); botão override gate manual
+- [ ] Task 6: Hunter.io email verifier integration — antes warmup email channel (E.2), verifier prospect emails; bounce>2% pausa channel
+- [ ] Task 7: Sentry MCP — todos erros warmup → Sentry tag account_id; UI link Sentry issue por evento timeline
+- [ ] Task 8: Validação regressão + persistência — phase A B C D E (toca daemon/orchestrator.py + linkedin/limiter.py MADUROS); 20/22 PASS; PLAN.md F.7 ✅; commit `feat(cobaia): F.7 — warmup 14d auto + live ops`
+
+**Done criteria F.7**: cobaia opera 14d completos sem owner ssh · daily report Telegram 19h sem falha · stop gates previnem ban antes humano notar · 20/22 PASS preservado.
+
+### Chapter F.8 — Cost & Performance Observability
+
+**Classification**: backend+ui · **UI score**: 7 · **Estimated sessions**: 3 · **Status**: PLANEJADO · **Dependencies**: F.2 (Mission Control base), F.6 (Brain audit trail)
+
+**Deliverable**: Observabilidade 4 dimensões em `dashboard/observability`. Cost tracking LLM calls (Claude + OpenRouter + Ollama local = $0) com agg tokens + USD por dia/skill/loop. Performance p50/p95/p99 endpoints PC+VM, throughput loops, slow queries Postgres MCP. Error inbox visual agrega 24h, triage, permalink Sentry. Audit trail Brain.decide() acoplado F.6.
+
+**APIs novas**:
+- `GET /api/observability/costs?range=24h|7d|30d&group_by=skill|loop|model`
+- `GET /api/observability/perf?endpoint=&range=`
+- `GET /api/observability/errors?status=open|resolved` · `POST /api/observability/errors/{id}/resolve`
+- `GET /api/observability/decisions?context_id=` (F.6 brain audit)
+
+**DB migrations**: `llm_calls` (timestamp, source, model, prompt_tokens, completion_tokens, cost_usd, latency_ms, skill_id, loop_name) — partição mensal
+
+**Tasks**:
+- [ ] Task 1: Backend LLM cost middleware — wrapper único em core/ai.py + ollama_router.py + Brain dispatcher; grava `llm_calls`; tabela preço USD por model
+- [ ] Task 2: Performance metrics middleware — FastAPI middleware p50/p95/p99 percentis rolling 1h por endpoint; expose `/metrics` Prometheus-compatible
+- [ ] Task 3: Error inbox via Sentry MCP — query issues open last 24h, agrupa por fingerprint, expose com permalink Sentry; mark resolve via Sentry API
+- [ ] Task 4: UI `/observability` 4 tabs (Costs, Performance, Errors, Decisions) — Recharts pra séries temporais; tabela ordenável por coluna; export CSV
+- [ ] Task 5: Validação regressão + persistência — phase A B C D E (toca core/ai.py + ollama_router.py MADUROS); 20/22 PASS; PLAN.md F.8 ✅; commit `feat(observability): F.8 — cost+perf+errors+decisions`
+
+**Done criteria F.8**: owner vê custo Claude Max consumido por skill/dia · slow queries identificadas auto · error inbox substitui `ssh vm 'tail -f' | grep ERROR` · audit Brain decisions navegável · 20/22 PASS preservado.
+
+### Chapter F.9 — Pipeline Studio Visual (form-driven)
+
+**Classification**: ui+backend · **UI score**: 9 · **Estimated sessions**: 5 · **Status**: PLANEJADO · **Dependencies**: F.1, F.6 (Brain + tools registry)
+
+**Deliverable**: Pipeline builder form-driven (NÃO canvas drag-drop — owner solo dispensa). Step library reusa registry F.6 (skills + pipelines + MCPs + endpoints como steps). Live execution monitor por step (status/output/timing/error inline). Template gallery clone-and-modify. A/B test pipelines paralelas.
+
+**APIs novas**:
+- `GET /api/pipeline-studio/steps` (delega tools registry F.6) · `GET /api/pipeline-studio/templates`
+- `POST /api/pipeline-studio/drafts` · `PUT /api/pipeline-studio/drafts/{id}` · `POST /api/pipeline-studio/drafts/{id}/execute`
+- `GET /api/pipeline-studio/runs/{id}/monitor` · `WS /ws/pipeline-studio/run/{id}`
+
+**DB migrations**: `pipeline_drafts` (id, name, yaml_blob, version, owner, created_at, ab_group) + `pipeline_runs_granular` (run_id, draft_id, step_idx, step_name, status, output_json, started_at, ended_at, error)
+
+**Tasks**:
+- [ ] Task 1: Backend CRUD `pipeline_drafts` + integração tools registry F.6 como step library; validação YAML schema
+- [ ] Task 2: Backend execution engine — interpreta YAML drafts, chama tools via Brain dispatcher (F.6), grava granular per-step em `pipeline_runs_granular`
+- [ ] Task 3: WS monitor — broadcast step_start/step_done/step_error events; client renderiza progress live
+- [ ] Task 4: UI `/pipeline-studio` — form builder vertical (add step → modal step picker do registry → params form auto-gerado do tool schema); preview YAML lateral; botões save/execute/clone
+- [ ] Task 5: Template gallery — 5-8 templates seed (prospect → audit → proposta → site → entrega; lead enrichment; warmup cobaia; ...); clone-and-modify workflow
+- [ ] Task 6: A/B test — execute draft em 2 grupos paralelo (50/50 rotation); UI compara métricas (latency, cost, success_rate) lado-a-lado
+- [ ] Task 7: Substituição parcial `/pipeline` legado — flag feature-toggle no UI; legacy permanece read-only durante migração
+- [ ] Task 8: Validação regressão + persistência — phase A B C D E (toca core/pipeline.py MADURO); 20/22 PASS; PLAN.md F.9 ✅; commit `feat(pipeline-studio): F.9 — visual builder + A/B + templates`
+
+**Done criteria F.9**: owner cria pipeline nova sem editar YAML manual · live monitor mostra step travado em real-time · A/B compara duas estratégias outreach lado-a-lado · 20/22 PASS preservado.
+
+---
+
+### Regra inviolável FASE F — Regression-test gate
 - [ ] Toda task que toca MADURO exige pre_test + post_test
 - [ ] `validate_implementation.py --phase A B C D E` antes E depois de cada chapter
 - [ ] 20/22 PASS preservado é gate de merge inegociável
 - [ ] Falha = REVERT, não "cosmético deixa quieto"
+- [ ] Toda task fora de .claude/ exige `git diff --stat` no post_test (defesa contra drift acidental)
 
 **Áreas MADURAS** (toque exige gate):
 core/{state,models,ai,pipeline,limiter}.py + loops/* + api/* + vm_api/routes.py + linkedin/{stealth,human,limiter,account_profile,preflight,stealth_compliance,ollama_router}.py + channels/email/* + daemon/orchestrator.py
 
-### Pendências cross-Fase F
+### Dependências cruzadas FASE F (DAG)
+
+```
+F.1 (gap audit) ──┬──> F.2 (mission control)  ──┬──> F.7 (cobaia live ops)
+                  ├──> F.3 (lab cockpit)         │
+                  ├──> F.4 (auto-skill) ──┐      │
+                  ├──> F.5 (MCP gateway) ─┴──┬──> F.6 (Brain) ──┬──> F.8 (observability)
+                  └──> F.9 (pipeline studio) <──┘                └──> F.9
+```
+
+**Ordem ótima execução**: F.1 → (F.2 ∥ F.5) → F.3 → (F.6 ∥ F.4) → (F.7 ∥ F.9) → F.8
+
+**Paralelizáveis** (sem conflito MADURO): F.2+F.5, F.6+F.4, F.7+F.9
+
+### Pendências cross-FASE F
 - [ ] Channels WhatsApp + Instagram (E.2/E.3 — deferido 30d após Email operacional)
 - [ ] VM-GPU migration (aguarda decisão financeira)
 - [ ] Fix `_extract_profile_data` selectors LinkedIn DOM atual
 - [ ] Tech-debt: 11 sqlite3.connect bare daemon + 4 linkedin/* → usar db_utils._connect
 - [ ] Deletar `hermes_desktop.py` deprecated + subfolder `Hermes Cloud Studio/`
+- [ ] Validar Meta Cloud API credentials owner pra WhatsApp Business MCP (F.5)
+- [ ] Validar Apollo.io coverage PME Cuiabá antes investir SaaS (F.7 alternativa Firecrawl)
+- [ ] Verificar owner workflow usa Notion (skip MCP se não)
 
 ### Sessão re-auditoria 2026-06-08 — Chapter atual
 - [x] Ler GUARDRAILS + AUDIT + PLAN existentes
 - [x] Inventário (CLAUDE.md, .mcp.json, git log, artifacts .claude/)
 - [x] Entrevista 4 perguntas (foco próximas 4-6 semanas)
 - [x] AUDIT-2026-06-08-FASE-F.md criado (delta v1)
-- [x] PLAN.md atualizado com 7 chapters Fase F
-- [ ] TaskCreate 7 chapters
-- [ ] memory_save re-auditoria
+- [x] PHASE-F-STUDY-SYNTHESIS.md criado (11 fantasmas + MCP landscape)
+- [x] PLAN.md atualizado com 9 chapters FASE F + dependencies + estimated_sessions
+- [ ] TaskCreate 9 chapters
+- [ ] memory_save re-auditoria FASE F final
 - [ ] Atualizar MEMORY.md global