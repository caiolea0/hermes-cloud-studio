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
+| F.1     | Backend↔Frontend Gap Audit                          | research+ui   | 3        | 1       | CONCLUÍDO 2026-06-08 | —    |
+| F.2     | Mission Control Real-Time + Design System Polish    | ui+backend    | 9        | 7       | **CONCLUÍDO 2026-06-08** | F.1         |
+| F.3     | Lab Cockpit + Stealth UX                            | ui+backend    | 8        | 4       | **CONCLUÍDO 2026-06-10** (4 sub-sessões ☒) | F.1         |
+| F.4     | Auto-Skill Loop W3 + GitHub PR-based deploy         | backend+ui    | 7        | 5       | **UNBLOCKED 2026-06-10** | F.1, F.5    |
+| F.5     | MCP Gateway + Discovery + Custom MCPs               | backend+infra | 4        | 4       | PLANEJADO   | F.1         |
+| F.6     | Cérebro Hermes (Brain orchestrator)                 | backend+ui    | 9        | 6       | PLANEJADO   | F.1, F.5    |
+| F.7     | Cobaia Live Ops + Warmup 14d automatizado           | backend+ui    | 8        | 5       | PLANEJADO   | F.2, F.5    |
+| F.8     | Cost & Performance Observability                    | backend+ui    | 7        | 3       | PLANEJADO   | F.2, F.6    |
+| F.9     | Pipeline Studio Visual (form-driven)                | ui+backend    | 9        | 5       | PLANEJADO   | F.1, F.6    |
+
+**Total estimado**: 38 sessões (1 + 5 + 4 + 5 + 4 + 6 + 5 + 3 + 5). Banda histórica 50-150k tokens/sessão = 4-6 semanas calendário owner solo, ritmo 1-2 sessões/dia.
+
+**Gate inegociável cross-chapter**: `validate_implementation.py --phase A B C D E` deve continuar 20/22 PASS antes E depois de cada chapter que toca código MADURO. Falha = REVERT.
+
+## 🔢 ORDEM EXECUÇÃO FASE F — REGRA INVIOLÁVEL (cristalizada 2026-06-10)
+
+**Sequência ÚNICA aprovada owner**: **F.1 → F.2 → F.3 → F.5 → F.6 → F.8 → F.9 → F.4 → F.7**
+
+**Status atual pós F.3.4** (F.1+F.2+F.3 ✅ done): próximas 6 chapters em ordem **F.5 → F.6 → F.8 → F.9 → F.4 → F.7**.
+
+### Justificativa objetiva por position (NÃO subjetiva — critérios documentados)
+
+| Position | Chapter | Sessões | Justificativa (critérios objetivos) |
+|---|---|---|---|
+| **4** (próximo) | **F.5** MCP Gateway + Custom MCPs | 4 | UNBLOCKED (deps F.1 ✓). **Destrava cascata**: F.6 (tool registry source) + F.4 (GitHub MCP deploy) + F.7 (Hunter/Apollo/Omnisearch MCPs cobaia). Fundação ecosystem. |
+| **5** | **F.6** Cérebro Brain.py | 6 | Depende F.5 tool registry. **Core feature transformador** — Brain orquestra TODAS chapters seguintes via ToolRegistry.invoke(). |
+| **6** | **F.8** Observability | 3 | Depende F.2+F.6. **Instrumenta cedo** F.4/F.7/F.9 — sem F.8 medir cobaia warmup vira cego, F.4 skill performance cego, F.9 pipeline cost cego. F.8 ANTES F.4/F.7/F.9 = alavanca observability todas chapters seguintes. |
+| **7** | **F.9** Pipeline Studio | 5 | Depende F.5 (MCP tools step library) + F.6 (Brain tools.invoke). **Reusa F.6 brain + F.5 tools + F.8 observability** — não pode entrar antes. |
+| **8** | **F.4** Auto-Skill Loop W3 | 5 | Depende F.1+F.5+F.6+F.3+F.8. **Mais arriscado** (meta-recursivo: Hermes propõe próprias skills). Exige F.5/F.6 maduros pra Brain decidir skill quality + F.8 pra medir skill performance pós-deploy + F.3 lab sandbox testar. F.4 ANTES F.7 porque skill loop pode beneficiar cobaia warmup tuning. |
+| **9** (último) | **F.7** Cobaia Live Ops | 6 | Depende F.2+F.5+ DECISION.md APScheduler. **Operacionalização final** — merece TUDO maduro (Brain + MCPs + Observability + Pipeline Studio + Auto-Skill) pra monitor 14d sem CLI. F.7 SEM F.6 Brain = warmup decisões manuais owner = não autônomo. F.7 SEM F.8 = cego pra performance gates. F.7 SEM F.4 = sem auto-tune skills cobaia. |
+
+### 5 critérios objetivos (NÃO subjetivos)
+
+1. **Dependencies graph**: respeitar `blockedBy` declarado em cada chapter PLAN.md (F.6 blocked F.5, F.8 blocked F.2+F.6, F.4 blocked F.5+F.6+F.3+F.8 implícito, F.7 blocked F.2+F.5)
+2. **Foundation-first**: chapters que destravam mais cascata vão primeiro (F.5 destrava 4 chapters; F.6 destrava 3 chapters)
+3. **Risk-last**: chapters meta-recursivos OR cobaia-real vão por último com tudo maduro (F.4 + F.7)
+4. **Observability-early**: F.8 antes consumers (F.4/F.7/F.9) — alavanca cross-chapter
+5. **DECISION.md compliance**: F.7 já tem decisão arquitetural cristalizada (commit a0d3eb0) — última posição respeitando pre-req
+
+### Sequências REJEITADAS (documentadas pra evitar reconsidera)
+
+- ❌ `F.1 → F.8 → F.2 → F.5 → F.6 → F.9 → F.4 → F.3 → F.7` (HOW-TO velha pré-2026-06-10) — VIOLA dependency F.8 blocked F.6
+- ❌ `F.1 → (F.2 ∥ F.5) → F.3 → (F.6 ∥ F.4) → (F.7 ∥ F.9) → F.8` (PLAN velha) — VIOLA dependency F.4 blocked F.5+F.6, paralelismo impossível
+- ❌ Revenue-first `F.5 → F.7` skip Brain — gera retrabalho F.7 quando F.6 entrar, cobaia sem auto-decisor
+
+### Quando essa ordem PODE mudar
+
+APENAS se uma destas condições for satisfeita (NÃO opinião subjetiva):
+1. Owner descobre nova dependency crítica não-mapeada (cross-ref obrigatória em PLAN.md + memory)
+2. Workflow dedicado análise (igual `f7-schedule-arch-analysis.js`) propõe ordem alternativa com recommendation PASS adversarial verify
+3. Bloqueador externo impede chapter atual (ex: API externa down) — pular pra próxima UNBLOCKED + tracker explícito
+
+**Mudança ordem requer**: commit PLAN.md + GUARDRAILS.md + HOW-TO-START-PHASE.md + memory_save + cross-ref aqui (não silencioso ad-hoc).
+
+### Esta sessão Claude (PC orquestrador) — responsabilidade
+
+Claude no PC (cwd `C:\Users\cleao`) é o **orquestrador cross-session** — audita sessões dedicadas + prepara prompts. **DEVE** confirmar ordem antes entregar próximo prompt:
+1. Read PLAN.md tabela "Visão consolidada FASE F" + "Sequência ÚNICA aprovada"
+2. memory_smart_search "hermes ordem execução fase F" → mem persistido
+3. TaskList — próxima task pending NÃO blocked
+4. Se owner pedir chapter fora ordem → exigir justificativa (3 condições acima) + atualizar docs antes entregar prompt
+
+**Cross-refs**: HOW-TO-START-PHASE.md F.X cuidados + GUARDRAILS.md § Ordem execução + memory mem_<próximo SHA>.
 
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
+- [x] Task 1: Parser AST routes PC+VM — `parse_routes.py` → 138 rotas (91 PC + 47 VM, 5 internal-only), sanity ≥130 PASS
+- [x] Task 2: Grep consumo dashboard/app.js — `grep_frontend.py` → 57 endpoints únicos, 86 chamadas, WS handlers 14 / broadcasts 10 / matched 8
+- [x] Task 3: Diff + ranking — `rank_gaps.py` → `.claude/FRONTEND-GAP.md` 6 seções, 40 órfãos, top 10 priorizado por owner_pain_score (5=daemon broadcast/pause/resume), 6 phantoms já consumidos (vitória F.2 parcial)
+- [x] Task 4: Empacotar skill — `hermes-frontend-gap/SKILL.md` (preexistente) + `.claude/commands/hermes-frontend-gap.md` slash + `settings.local.json` 3 permissions específicos (NÃO wildcard)
+- [x] Task 5: Validação + persistência — post `validate_implementation.py --phase A/B/C/D/E` MANTÉM 20/22 PASS (E.2/E.3 stubs intencionais); PLAN.md F.1 ✅; GUARDRAILS.md regra nova; memory_save; mark_chapter; commit `docs(audit): F.1 — FRONTEND-GAP.md + skill hermes-frontend-gap`
+
+**11 endpoints fantasma esperados no TOP 10** (sanity check):
+`/api/prospects/{id}/resolve-conflict`, `/api/tasks/bulk`, `/api/stats`, `/api/daemon/state`, `/api/daemon/log`, `/api/daemon/decisions`, `/api/daemon/channels`, `/api/daemon/timeline`, `/api/linkedin/visited`, `/api/linkedin/comment/{edit|delete}`, `/api/agent-zero/{status|chat}`.
+
+**Done criteria F.1**: skill re-rodável <90s end-to-end · FRONTEND-GAP.md tem `last_updated` + `phase_baseline` (vira termômetro de progresso UX) · diff-vs-known.md gerado em re-execuções pra detectar drift · 20/22 PASS preservado.
+
+### Chapter F.2 — Mission Control Real-Time + Design System Polish ✅
+
+**Classification**: ui+backend · **UI score**: 9 · **Real sessions**: 7 (planned 5, +40% expansão por bug catches + axe tech-debt mapeado + reviewer gate overhead + fatiamento qualidade) · **Status**: **CONCLUÍDO 2026-06-08** · **Dependencies**: F.1 (top-10 daemon/* fantasmas)
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
+- [x] Task 1 (F.2.1): Backend `/api/daemon/subsystems` GET — agrega daemon_state row + tunnel_supervisor_state.json; 6 subsistemas (daemon/linkedin/email/scraper/audit/tunnel) com status normalizado paused|healthy|warning|error|offline
+- [x] Task 2 (F.2.1): Backend POST pause/resume por subsistema — persiste em `runtime_state.subsystem_pauses` (JSON map name→until_ts) via set_runtime_state (NÃO ALTER TABLE); rate-limit 30/min; minutes bounded 1-720; WS broadcast `daemon.subsystem_status`
+- [x] Task 2.5 (F.2.2): Gate `subsystem_pauses` em 4 loops maduros — helper `core.state.is_subsystem_paused()`; `loops/sync.py` (daemon), `loops/linkedin_sync.py` + `loops/linkedin_scheduler.py` (linkedin), `channels/email/sender.py` (email) raise EmailRateLimited('subsystem_paused') ANTES de qualquer write em email_rate.db; logger.info extra category=subsystem_pause; try/except logger.exception/warning preservado (MERGED-007)
+- [x] Task 3 (F.2.3): WS broadcast canonical dot-notation 2026-06-08 — `daemon.subsystem_status` transition-only em loops/sync.py + loops/linkedin_sync.py (canonical emitter pro subsystem='linkedin'); linkedin_scheduler log-only anti-dup; `daemon.log_event` paralelo em daemon/orchestrator.py + loops/linkedin_health.py; `daemon.decision` (com field decision_event) paralelo em orchestrator.log_decision; 3 handlers no dashboard/app.js (hooks window._missionControl, render fica em legacy até cleanup); scripts/ws_test_subscriber.py CLI smoke; frontend-ux-reviewer PASS-WITH-NOTES 0 BLOCKERS; smoke E2E ≥3 distinct via WS pipe; validate 20/22 PASS preservado em 5 commits separados; sem asyncio.create_task bare (MERGED-015)
+- [ ] **F.2.future cleanup** — remover broadcasts legacy `activity`/`decision` de daemon/orchestrator.py após handlers dashboard migrarem 100% pra `daemon.log_event`/`daemon.decision` (executar pós-F.2 inteira, antes F.6 Brain integration). Tech-debt registrado em commit 7acd0b7.
+- [ ] Task 4: Live tail logs WS — `/ws/daemon/log-tail` com rolling buffer 500 linhas em memória; backend SSE alternativa fallback
+- [ ] Task 5: UI Activity Orbit redesign — tile por subsistema em grid 3x2; cores semafóricas (verde/amarelo/vermelho); contagem ações 24h; botão pause/resume inline com confirmação
+- [ ] Task 6: UI Timeline component — list virtualizada decisões/eventos últimas 24h; filtros subsistema + tipo (decision/action/error); permalink por evento
+- [ ] Task 7: UI Live tail panel — collapsible drawer bottom; auto-scroll; pause-on-hover; clear button; filter por subsistema/severity
+- [x] Task 8 (F.2.4) 2026-06-08 — Design system scaffolding completo: tokens.css 38 vars DARK default + light.css overrides + README convenção; axe-core 4.10.3 vendor LOCAL; toast.js (window.hermesToast, DOMPurify, aria-live, hover-pause) + skeleton.js (shimmer + prefers-reduced-motion); index.html FOUC inline script + scripts defer; app.js toast() wrapper compat + reverte hotfix F.2.3 'info'→'warn'; coexistência styles.css legacy (2949 linhas) sem colisão de namespace. frontend-ux-reviewer PASS-WITH-NOTES 0 BLOCKERS. validate 20/22 PASS preservado em 5 commits (13aa8c8→6922190).
+- [ ] **Task 8.5 (F.2.4 owner action)**: smoke browser pós-restart server: (a) abrir 3 páginas em light+dark = 6 axe runs DevTools `await axe.run().then(r => console.log(r.violations.filter(v => v.id==='color-contrast')))` zero violations; (b) capturar 6 screenshots 1440x900 em `.claude/screenshots/baseline/`; (c) testar `window.hermesToast.warn('test')` renderiza amarelo + FOUC zero flash.
+- [ ] **F.2.future tech-debt** — (1) migrar styles.css legacy progressivamente pra tokens canonical `--color-*/--space-*`, componente-por-componente, NÃO bulk rewrite; (2) remover `function toast()` wrapper compat após callers migrarem pra `window.hermesToast.*` direto; (3) reviewer notes deferidos — light theme warn `#9a6700` contraste fino (considerar `#8a5a00` ~5.3) + axe-core lazy load (540KB carregado em toda page); (4) **F.2.5a orphan cleanup** — `.channel-card`/`.ch-*` selectors em styles.css legacy (declarados ~427-441) sem HTML consumer após F.2.5a; remover em sessão cleanup junto com `loadDaemonChannels()`/`updateChannelCard()` em app.js (no-op silent após channel-cards removal).
+- [x] **Task 9 (F.2.5a)** 2026-06-08 commit 7e862d9 — SubsystemTileGrid 6 tiles (linkedin/email/scraper/audit/daemon/tunnel) substitui channel-cards section. dashboard/components/subsystem_tile.js NOVO (window.SubsystemTileGrid.{init,update,destroy} + adapter window._missionControl.* bridge F.2.3 handlers). dashboard/app.js MATURE: _wsAlive + _subsystemsPollingTimer + start/stopSubsystemsPollingFallback + fetchAndRenderSubsystems + hooks ws.onopen/close/error + loadMissionControl init. dashboard/styles.css MATURE append-only F.2.5a section (zero hex literal, 100% var(--color-*/space-*/radius-*/motion-*/font-*) tokens F.2.4). dashboard/index.html MATURE: script defer + channel-cards REMOVIDA. Polling fallback ≥30s gated por _wsAlive + currentPage==='control', idempotent. Pause optimistic + countdown MM:SS aria-live + toast.warn. State merge defensivo (ignora keys undefined) preserva paused_until_ts contra WS broadcast parcial. axe contrast nodes /control dark: 22→18 (-4 canais removidos). validate phase A 3/3 + phase E 2/4 preservado. sanitize count 3→3. frontend-ux-reviewer PASS zero BLOCKERS zero critical warnings. Panic button + LiveLogTail + PrefPanel DEFERIDO F.2.5b.
+- [x] **Task 10 (F.2.5b)** 2026-06-08 commits e62a2ea + 5f398c4 + 98b7770 + 87c13d7 — Panic button + PrefPanel + /api/user-prefs. Step 0 (e62a2ea): dashboard/components/_utils.js NOVO (window.hermesUtils.safeMerge — filtra undefined ANTES Object.assign, falsy 0/False preservados; reusado F.2.5c LiveLogTail + F.6 Brain). Step 1 (5f398c4): POST /api/daemon/subsystems/all/pause panic backend — _pause_subsystem_core helper extraído de F.2.1 (DRY individual + panic), best-effort sequential 6 subsistemas, response {ok, minutes, paused_until_ts, paused[], failed[{name, error}]}, idempotente REPLACE (re-panic substitui paused_until_ts, não estende), @limiter.limit('5/minute') anti-abuse, route ordering /all/pause ANTES /{name}/pause (FastAPI literal match first). Step 2 (98b7770): GET/PUT /api/user-prefs com Pydantic UserPrefs strict (theme=Literal[light|dark|auto], refresh_rate=Literal[10|30|60], tile_order/tile_visibility/sound_notifications/badge_counter_unread_errors, extra='ignore' forward-compat), storage embedded runtime_state.user_prefs={version:N, data:{...}} atomic 1 write, last-wins concurrency (frontend NÃO envia version), helper _safe_merge_dict inline Python equivalente, @limiter.limit('30/minute') PUT, GET sem limit, legacy raw dict migration → {version:1, data:raw}. Step 3 (87c13d7): panic_button.js NOVO (window.HermesPanicButton, confirm modal 2s anti-acidente CSS+timer, role=alertdialog + aria-modal + aria-labelledby + aria-describedby, focus trap Tab cycle, ESC + overlay click fecham, minutes selector dropdown 1/5/15/30/60/120/240/720 default last-used via getUserPref, best-effort failed[] inline render, total fail keep modal open), pref_panel.js NOVO (window.HermesPrefPanel, slide-in right 5 sections theme/MC/notif/order/visibility, auto-save debounced 500ms zero Save btn, status aria-live 'Salvo às HH:MM:SS', drag HTML5 + keyboard alt Alt+↑/↓ WCAG accessible, tile visibility revert se ≥1 obrigatório), app.js MATURE +184 (getUserPref/setUserPref sync localStorage + best-effort PUT, Web Audio API beep 660Hz/150ms/0.3vol/ADSR envelope SUBSTITUI notification.mp3 vendor — strictly cleaner zero binary repo + sub-ms latency + customizável runtime, AudioContext lazy init pós-gesture, SOMENTE toast.error toca beep anti-fadiga, _hermesErrorsUnread O(1) + updateBadgeTitle text-safe document.title + clearHermesErrorBadge() reset ORIGINAL_DOC_TITLE, _installErrorHook __f25b_hooked guard anti double-hook, _mountMissionControlHeaderActions idempotent panic+⚙ no metrics-bar). styles.css MATURE +421 append-only L3082+ (.panic-* + .pref-* + animations, 100% var(--color-*/space-*/radius-*/motion-*) tokens, zero hex literal F.2.5b, @media prefers-reduced-motion respeitado, focus-visible em todos buttons). Smoke browser 13 assertions PASS (components mount, theme switch debounce, panic modal a11y, panic POST→6/6 paused verified, badge title (1)→(2)→clear, zero console err/warn). axe-core zero F.2.5b violations (4 legacy preserved). frontend-ux-reviewer PASS-WITH-NOTES 0 BLOCKERS + 6 notes (documentadas seção F.2.5b reviewer notes abaixo). validate phase A 3/3 + B 5/5 + C 6/6 + D 4/4 + E 2/4 stubs = 20/22 PASS preservado. sanitize count 3→3.
+- [ ] **F.2.5b reviewer notes (PASS-WITH-NOTES commit 87c13d7, frontend-ux-reviewer)** — 6 tech-debt itens rastreáveis:
+    1. **Token consolidação `--color-overlay`** — 13 ocorrências `rgba(0,0,0,0.xx)` em styles.css (11 legacy + 2 F.2.5b backdrops). Criar `--color-overlay-strong: rgba(0,0,0,0.55)` (panic modal) + `--color-overlay-soft: rgba(0,0,0,0.4)` (pref panel) em tokens.css; migrar legacy linhas 260/558/642/663/717/950/1017/1095/1480/2399/2588 em refactor F.future.
+    2. **PrefPanel `aria-modal="false"` intencional** (pref_panel.js:323) — slide-in lateral não bloqueia viewport, screen reader navega fora ainda. Se F.future quiser strict modal: mudar para `true` + focus trap completo (atualmente só ESC fecha, sem Tab cycle).
+    3. **Dead code `_pageTitle`** (pref_panel.js:45) declared mas nunca usado. Remover em próximo passe.
+    4. **Hook fallback `setInterval` 50×100ms** (app.js `_hookWhenReady`) — alternativa mais limpa: `requestIdleCallback` ou listener `DOMContentLoaded` explicit. Funcional atual, refactor F.future.
+    5. **Dead code `_modal`** (panic_button.js:28) declared mas só `_overlay` referenciado runtime. Minimal cleanup.
+    6. **PrefPanel `onChange` listener API** exposto (pref_panel.js:495) sem consumer atual — F.future hook para SubsystemTileGrid reagir a `tile_order`/`tile_visibility` deltas em real-time (atualmente requer reload `/control`).
+- [x] **Task 11 (F.2.5c)** 2026-06-08 commits 99aafb5 + 10d9d34 + c9e8881 — LiveLogTail standalone virtualizada. dashboard/components/live_log_tail.js NOVO (window.HermesLiveLogTail.{init,append,clear,exportCsv,toggle,destroy,_ringBuffer debug getter}). Ring buffer FIFO 200 cap (append→shift quando >MAX), virtual list render VIRTUAL_WINDOW=20 nodes via DocumentFragment+replaceChildren batch (zero reflow loop). Auto-scroll bottom + pause-on-hover (mouseenter _paused=true; mouseleave catch-up render). Filtros chips multi-select AND combine: levels (info/warn/error/debug) + emitters (daemon/loops/api/scheduler), keyboard accessible (Enter/Space + aria-pressed sync). Click entry com payload → expand JSON inline textContent JSON.stringify; _expandedPayloadIds Set preserva estado cross-render. Botão Limpar drena buffer + clear DOM; Botão Exportar CSV download Blob+URL.createObjectURL com filename ISO Windows-safe (.replace(/[:/\\*?\"<>|]/g,'-')) + escape \"\" CSV correto. Toggle collapse chevron header (aria-expanded sync) persiste via setUserPref('live_log_tail_collapsed', false default expanded). Empty state UX skeleton + placeholder PT-BR. dashboard/app.js MATURE: handlers daemon.log_event + daemon.decision real (consume HermesLiveLogTail.append paralelo aos hooks legacy _missionControl preserved); init em loadMissionControl idempotente após HermesPrefPanel.init. dashboard/index.html MATURE: script defer após pref_panel.js + mount point <section class="mc-bottom-section"><div data-component="live-log-tail"> abaixo .control-grid. dashboard/styles.css MATURE APPEND-ONLY linhas 3503-3725 (.live-log-* + .mc-bottom-section + .log-* + .filter-chip), 100% var(--color-*/space-*/radius-*/motion-*/font-*) tokens F.2.4, zero hex literal, @media (prefers-reduced-motion: reduce) cobre 5 transições. XSS hygiene: TODO content runtime textContent (ts/emitter/message/payload); innerHTML APENAS _buildShell literal template. Reuses window.hermesUtils.safeMerge (F.2.5b Step 0) + getUserPref/setUserPref + hermesToast.error. frontend-ux-reviewer verdict: PASS-WITH-NOTES, ZERO BLOCKERS. WARN #1 (debug opacity 0.7 → contraste composite 3.45/2.78 < WCAG AA 4.5) PATCHED pré-commit (1-line removal, agora 5.62 DARK / 4.93 LIGHT AA passa). WARN #2/#3/#4/#5 documentados em F.2.5c reviewer notes abaixo. validate phase A 3/3 + B 5/5 + C 6/6 + D 4/4 + E 2/4 stubs = 20/22 PASS preservado em 3 commits. sanitize count 3 → 3 (textContent-only).
+- [ ] **F.2.5c reviewer notes (PASS-WITH-NOTES, frontend-ux-reviewer agentId acdb8377d01fbcac8)** — 4 tech-debt itens rastreáveis (WARN #1 patched pré-commit):
+    1. ~~WARN #1 debug opacity contraste~~ — PATCHED pré-commit (live_log_tail Step 3 styles.css: opacity 0.7 removido em .log-entry-debug; ratio composite 3.45→5.62 DARK / 2.78→4.93 LIGHT, AA passa).
+    2. **WARN #2 init order pref defer** (live_log_tail.js:96) — _getPref('live_log_tail_collapsed') chamado no _buildShell durante init(); se script defer ordem corromper e setUserPref infra (F.2.5b app.js) não estiver disponível em time, pref nunca persiste mas degrada silenciosamente (fallback expanded). OK por design D5; documentado pra F.future se debugging persist issue.
+    3. **WARN #3 ring buffer shift O(n)** (live_log_tail.js:367) — `_ringBuffer.shift()` é O(n) re-allocation; aceitável n=200 (microsegundos) mas circular buffer com index móvel seria O(1) puro. Refactor F.future se profiler apontar hot path.
+    4. **WARN #4 chip keydown handler redundante** (live_log_tail.js:165-171) — `<button>` nativos disparam click em Enter/Space; handler `_onFilterKey` em `.live-log-filters` é redundante mas tem preventDefault, então não double-toggle (verificado manualmente reviewer). Pode remover em refactor cleanup pra reduzir noise.
+    5. **WARN #5 re-mount idempotency** (live_log_tail.js:309-326) — init() early-return em _initialized=true; safe enquanto app.js NÃO faz swap innerHTML do <div data-component=live-log-tail>. Anotar se F.future outra page mexer no mount point.
+- [ ] ~~Task 9: User prefs persistence~~ — SUPERSEDIDO por **F.2.5b** (commit 98b7770 entrega `/api/user-prefs` + Pydantic strict + runtime_state.user_prefs embedded).
+- [x] **Task 12 (F.2 closeout)** 2026-06-08 commits 8305c4c + (PLAN_SHA) — Closeout autônomo docs-only. G6.2 6 screenshots baseline 1440x900 capturados via Edge headless + dashboard/dev-bootstrap.html helper LOCAL (gitignored, deletado pós-uso): control_dark/light, dashboard_dark/light, prospects_dark/light. Tamanhos 78-180KB. Mission Control renderiza com auth OK (sidebar + KPIs + Subsistemas + Activity Orbit + Live Feed). `.gitignore` adaptado: `.claude/screenshots/*` + negação `!.claude/screenshots/baseline/` (mantém ephemeral ignore + permite baseline commit). PLAN.md atualizado Task #1 [x] + retrospective 7 sessões + F.3 unblock explicit. memory_save workflow F.2 complete. mark_chapter "Phase F.2 COMPLETE". Push master 2 commits (8305c4c screenshots + PLAN_SHA docs). validate phase A B C D E SKIPPED (zero touch backend/frontend código — puro docs+screenshots).
+
+**Done criteria F.2**: owner abre `/control` e nunca mais precisa SSH pra ver state daemon · pause/resume linkedin individual sem matar email/scraper · live tail substitui `ssh vm 'tail -f /var/hermes/log'` · dark mode persistido entre sessões · 20/22 PASS preservado. ✅ ATINGIDO.
+
+**F.2 Closeout retrospective 2026-06-08** (7 sessões reais, planned 5, +40%, ~24 commits push master):
+- F.2.1 backend pause/resume (e125681)
+- F.2.2 loops gate (d0a8cc2)
+- F.2.3 WS broadcasts canonical daemon.* 5 commits (7acd0b7 + b086501 + 17508c5 + 367e6af + 41188fa + 905395b)
+- F.2.4 design system 6 commits (13aa8c8..032b3dc)
+- F.2.5a SubsystemTileGrid + WS handlers + polling fallback (7e862d9 + 717ffff)
+- F.2.5b _utils + panic + PrefPanel + Web Audio + badge counter 6 commits (e62a2ea + 5f398c4 + 98b7770 + 87c13d7 + 1eb5bfa + 1999a25)
+- F.2.5c LiveLogTail virtualizada + filters + CSV + ring buffer 200 4 commits (99aafb5 + 10d9d34 + c9e8881 + 8622185)
+- F.2 closeout 2 commits (8305c4c screenshots + PLAN_SHA docs)
+
+Validate phase A B C D E: **20/22 PASS preservado em TODOS commits maduros** (E.2/E.3 stubs WhatsApp/Instagram intencionais).
+Axe contrast nodes /control: 22 → 18 (-4 canais removidos F.2.5a confirmed sub-effect). Zero novas violations F.2.5b/F.2.5c (WARN #1 contraste debug PATCHED pré-commit).
+G6 smoke E2E F.2.5c: **27/27 assertions PASS** (memory mem_mq62e015). Pause-on-hover funciona REAL.
+G6.2 screenshots baseline 1440x900: **6 capturados** via Edge headless automatizado (zero owner manual capture).
+frontend-ux-reviewer agent: PASS/PASS-WITH-NOTES em F.2.4 + F.2.5a + F.2.5b + F.2.5c — **zero BLOCKERS, 11 notes documentadas F.2.future**.
+
+**Deliverables visíveis owner Mission Control real-time** (zero CLI necessário):
+- 6 SubsystemTiles status badges (healthy/paused/warn/error) + última ação timestamp + Pause/Resume individual com countdown MM:SS aria-live
+- Panic button header + confirmation modal 2s anti-acidente + ESC + focus trap + minutes selector 1/5/15/30/60/120/240/720
+- PrefPanel ⚙ header + 5 sections (Theme/Mission Control/Notificações/Tiles/Advanced) + auto-save debounced 500ms + status "Salvo às HH:MM:SS"
+- LiveLogTail bottom section live daemon events + filters chips levels+emitters AND combine + JSON payload expand inline + CSV export ISO filename + ring buffer 200 cap FIFO + pause-on-hover
+- Badge counter document.title `(N) Hermes` quando errors unread (clear on PrefPanel toggle OR error tile click)
+- Sound notification Web Audio synthesized beep em toast.error (NÃO mp3 vendor — strictly cleaner zero binary repo)
+- Dark/Light theme toggle + FOUC prevention inline head script
+
+**Decisões arquiteturais validadas pra F.6+**:
+- `core/brain.py` NOVO pra F.6 (NÃO estender daemon)
+- Web Audio synthesized > .mp3 vendor (strictly cleaner, reviewer validated)
+- Wrapper compat `showToast()` pre F.future migration
+- Append-only `styles.css` (zero refactor legacy 2949 linhas — chapter próprio)
+- Subagent project-local `frontend-ux-reviewer` direto (sem workaround pós-F.2.4)
+- Edge headless + bootstrap helper local pra screenshots automatizados (G6.2 zero owner action)
+
+**Tech-debt F.2.future tracked** (NÃO bloqueia F.3+, rastreado em PLAN.md):
+- [ ] Channels legacy CSS `.ch-*` selectors orphan (F.2.5a removeu HTML, CSS órfão)
+- [ ] `styles.css` legacy 2949 linhas migração progressiva pra `var(--color-*)` tokens (chapter próprio)
+- [ ] 18 axe contrast nodes restantes /control (daemon-badge + metric-label x4 + energy-label + timeline-labels x4+) — bulk migration F.future
+- [ ] NOTE 1 reviewer: overlay tokens consolidação 13 rgba 9 valores diferentes (chapter próprio, 30-45min)
+- [ ] NOTE 2 reviewer F.2.5b: aria-modal=false intentional (slide-in pattern, doc fix only)
+- [ ] NOTE 4 reviewer F.2.5b: setInterval → requestIdleCallback micro-optim
+- [ ] NOTE 6 reviewer F.2.5b: PrefPanel onChange consumer ausente (F.6 Brain integrate)
+- [ ] WARN #2 reviewer F.2.5c: init order live_log_tail depende app.js loadMissionControl
+- [ ] WARN #3 reviewer F.2.5c: ring buffer .shift() O(n) acceptable até 200 (F.future deque se scale)
+- [ ] WARN #4 reviewer F.2.5c: filter chip keydown redundante (Enter/Space)
+- [ ] WARN #5 reviewer F.2.5c: re-mount idempotency edge case
+- [ ] `showToast()` wrapper compat remover após callers migrarem 100% pra `window.hermesToast.*`
+
+### Chapter F.3 — Lab Cockpit + Stealth UX
+
+**Classification**: ui+backend · **UI score**: 8 · **Estimated sessions**: 4 · **Status**: **CONCLUÍDO 2026-06-10** (F.3.1 + F.3.2 + F.3.3 + F.3.4 ☒ — 4 sub-sessões dedicadas, ~10 commits master, smoke E2E real validado) · **Dependencies**: F.1
+
+**Deliverable**: Página `dashboard/lab` nova. Owner roda `lab_runner.py` sem CLI: botões "test fingerprint", "test login", "test viewer flow"; live screenshot polling 2s; compliance score + delta vs baseline; runs históricos com diff fingerprint; cobaia descartável workflow integrado.
+
+**APIs novas**:
+- `GET /api/lab/runs` · `POST /api/lab/runs/start` · `GET /api/lab/runs/{id}/artifacts` · `GET /api/lab/runs/{id}/screenshot` · `GET /api/lab/baselines`
+- `WS /ws/lab/run/{id}` — stream progress + screenshot delta
+
+**MCP integração**: Microsoft Playwright MCP (fallback QA descartável, NUNCA conta Caio) + custom `linkedin-lab` MCP (decisão F.5).
+
+**Sub-sessões dedicadas (4)**:
+
+**F.3.1 — Backend Lab API + DB schema + SSH async** (2026-06-08 ☒ commits a8e4a08 + 406c239)
+- [x] core/state.py: lab_runs table migration + helpers (lab_run_create/update/get/list/is_running)
+- [x] api/lab.py NOVO: POST /start (SSH async via asyncio.create_subprocess_exec + xvfb-run python3 -m linkedin.lab.lab_runner), POST /runs/{id}/abort (terminate+kill 3s), GET /runs paginated, GET /runs/{id} detail+artifacts, GET /runs/{id}/artifacts/{filename} FileResponse path-sanitized
+- [x] server.py include_router(lab_router)
+- [x] WS broadcasts namespace lab.* (run_started, step_progress, compliance_score, fingerprint, run_completed, run_failed, run_aborted)
+- [x] Concurrent gate 409 (cobaia single profile) + rate-limit 3/min POST start
+- [x] Smoke: empty list 200, invalid flow 400, 404, path traversal sanitized, no token 401, validate phases A-E 20/22 preserved
+
+**F.3.2 — VM-side lab_runner.py emit JSON events** (2026-06-09 ☒ commits 1d1de24 + 930d09f + 881ff58)
+- [x] linkedin/lab/_event_emit.py NOVO — sanitizer recursivo SENSITIVE_KEYS (li_at/token/cookie/password/auth/jsessionid/csrf/api_key/secret/bearer/li_rm/lidc/bcookie/bscookie/x-li-track) + ALLOWED_EVENTS whitelist 7 types + mask_email + emit() try/except BrokenPipe+generic
+- [x] linkedin/lab/lab_runner.py MATURE — emit run_started (flow + account_email_masked + profile_name + run_id) / run_completed (duration_ms + summary[:200]) / run_failed (error[:500]). Prints [lab] legacy preservados pra debug humano SSH stdout.
+- [x] linkedin/lab/flows/{fingerprint_baseline,login,viewer_test}.py MATURE — emit step_progress (started/success/failed) + screenshot_captured (filename/site/step) + fingerprint_dump (signals + sha256[:16] hash). Lógica stealth.launch_stealth_browser / human.type_human / profile.record_* / _is_authwall INTACTA.
+- [x] BLACKLIST R2 validado: zero touch em stealth.py/human.py/limiter.py/preflight.py/stealth_compliance.py/account_profile.py/config.py/cooldown.py/db_utils.py/ollama_router.py (git diff --name-only blacklist regex zero matches)
+- [x] Smoke VM fingerprint flow CreepJS (xvfb-run python3 -m linkedin.lab.lab_runner --flow fingerprint --sites creepjs): 6 events emit, 5 distinct types (run_started + step_progress + screenshot_captured + fingerprint_dump + run_completed), schema strict PASS, zero SENSITIVE_KEYS leak in JSON payload
+- [x] code-reviewer agent: PASS-WITH-NOTES (zero BLOCKERS). Notes follow-up F.3.2-future (não bloqueia F.3.3): (a) expandir SENSITIVE_KEYS pra cobrir liap/usermatchhistory/analyticssynchistory defense-in-depth; (b) sanitize key check adicionar .strip() pra blindar trailing whitespace tricks
+- [x] Deploy VM via scp seletivo (5 files: _event_emit.py + lab_runner.py + 3 flows). VM imports OK pós cada commit.
+- [x] validate phases A-E 20/22 PASS preservado em TODOS 3 commits MATURE
+
+**F.3.3 — Frontend Lab Cockpit page + components** (2026-06-09 ☒ commits 8601d3c + 38bcdd5 + 51865a0)
+- [x] dashboard/components/lab_cockpit.js NOVO — window.HermesLabCockpit.{init,destroy,refreshRuns,startRun,abortRun,openRunDetails,closeDrawer,appendEvent}
+- [x] dashboard/components/lab_gauge.js NOVO — SVG semicircular 0-100 animated tween + threshold 70 + cor tokens --color-success/warn/error
+- [x] dashboard/components/lab_fingerprint_diff.js NOVO — table side-by-side 18 signals + match/mismatch/missing status tokens
+- [x] dashboard/app.js MATURE — page routing #lab + 8 WS handlers lab.* (sanitize delta 3→3, zero new innerHTML +=)
+- [x] dashboard/index.html MATURE — sidebar nav item Lab (i-eye icon) + 3 script imports + mount point #page-lab
+- [x] dashboard/styles.css MATURE APPEND — .lab-* selectors var(--color-*) tokens F.2.4 (ZERO hex literal validated grep)
+- [x] Smoke browser Claude Preview: 6 mock events injected → gauge animou 0→78, 3 status rows (success/failed/aborted), drawer slide-in role=complementary aria-hidden toggle, fp diff empty state correto
+- [x] frontend-ux-reviewer agent: PASS-WITH-NOTES (zero BLOCKERS). 4 WARNs follow-up F.3.future (NÃO bloqueia F.3.4):
+  - AUTH-IMG-TOKEN: middleware auth não aceita ?token= query, screenshots <img src> com token query falham 401. Fix: extender middleware accept query token APENAS pra /api/lab/runs/*/artifacts/* paths.
+  - A11Y-NATIVE-CONFIRM: window.confirm() em login/viewer pre-start. Upgrade pra custom alertdialog modal (consistência abort pattern).
+  - RESP-NO-MOBILE-MEDIA: grid .lab-main + .lab-footer sem @media <768px stack fallback (Phase F target desktop owner-solo).
+  - PERF-FP-DIFF-N1: _refreshFingerprintDiff Promise.all top-2 fetches (N=2 baixo risco, document constraint).
+- [x] validate phases A-E 20/22 PASS preservado em TODOS 3 commits MATURE
+
+**F.3.4 — Auto-cleanup + smoke E2E + closeout** (2026-06-10 ☒ commits 6bcdece + 1f406c4 + SHA-final)
+- [x] scripts/lab_cleanup.py NOVO — dual-mode (DB-driven PC + FS-driven VM com sentinel `.pinned`). 5 smoke tests PASS (missing DB graceful + missing table graceful + real DB dry-run + path traversal rejected + FS mode 3 dirs com old/recent/pinned)
+- [x] Decisão arquitetural: APScheduler defer F.future. Linux crontab VM standalone preferred (`0 3 * * * cd ~ && python3 scripts/lab_cleanup.py >> ~/logs/lab_cleanup.log 2>&1`). Razão: daemon/orchestrator.py SEM APScheduler atual, crontab simpler + zero nova dependency Python. Idempotency PASS (count=1 após re-run setup).
+- [x] Smoke E2E real fingerprint flow CreepJS+6 sites (run_id aeb103e9c2e94d13, duration 84649ms ~85s, 22 artifact files VM disk 5.6MB)
+- [x] TRIPLE evidence: DB row status=success + artifacts disk persisted + WS events broadcasted (parcial — 2 distinct types capturados de 6 esperados, 4 followups tracked)
+- [x] PLAN.md F.3 ☒ + memory_save workflow + mark_chapter "F.3 COMPLETE"
+- [x] validate phases A-E 20/22 PASS preservado em TODOS commits F.3.4
+
+**Done criteria F.3**: owner valida stealth de cobaia nova sem terminar · compliance regression visível antes de toque produção · screenshot history pra debug DOM LinkedIn mudou · 20/22 PASS preservado · 4 sub-sessões ☒.
+
+**Retrospective F.3 completo (2026-06-08 → 2026-06-10)**:
+- 4 sub-sessões dedicadas (planeadas 4, real 4) — alinhamento perfeito estimativa
+- ~10 commits master: F.3.1 (a8e4a08 + 406c239 + 9c098f1), F.3.2 (1d1de24 + 930d09f + 881ff58 + acc950f), F.3.3 (8601d3c + 38bcdd5 + 51865a0 + 797342c), F.3.4 (6bcdece + 1f406c4 + SHA-final)
+- 27 assertions PASS: 10 backend F.3.1 + 5 emit JSON F.3.2 + 6 smoke browser mock F.3.3 + 6 smoke E2E real F.3.4
+- frontend-ux-reviewer PASS-WITH-NOTES em F.3.3 (zero BLOCKERS, 4 WARNs F.future)
+- code-reviewer agent PASS-WITH-NOTES em F.3.2 (zero BLOCKERS, 2 notes defense-in-depth)
+- BLACKLIST R2 INTACTOS verified TODA F.3 inteira (zero touch stealth+human+limiter+preflight+stealth_compliance+account_profile+config+cooldown+db_utils+ollama_router)
+- Validate phase A B C D E: 20/22 PASS preservado TODOS commits maduros
+- Sanitize count app.js: 3 → 3 (textContent-strict pattern preservado)
+- Decisão arquitetural F.3.4: Linux crontab VM > APScheduler daemon (defer mature pattern change F.future)
+- Decisão arquitetural F.7 schedule infra: PENDENTE (descoberta F.3.4 documentada acima — owner decide quando ativar F.7)
+- F.3.followup F.future tracked (NÃO bloqueia F.3 closeout):
+  - F.3.3 WARNs: AUTH-IMG-TOKEN + A11Y-NATIVE-CONFIRM + RESP-NO-MOBILE-MEDIA + PERF-FP-DIFF-N1
+  - F.3.4 FOLLOWUPs: ~~event parsing extension (4 types missing)~~ **RESOLVED F.3.5 hotfix 2026-06-10 commits c407b4a + 2045e1f (api/lab.py _stream_run switch case ALLOWED_EVENT_TYPES whitelist + BUG #1 fingerprint_dump handler rename + BUG #3 payload spread conflict run_id key — smoke E2E real CreepJS 5/5 distinct types capturados, fingerprint_hash=ecd146eae16f3f9d DB populated)** · artifacts_path mismatch reconciliation (PENDENTE F.future) · compliance_score extraction (PENDENTE — flow fingerprint NÃO emite compliance_score, design choice) · fingerprint_hash computation (RESOLVED via mesmo hotfix)
+  - F.3.2 notes: expandir SENSITIVE_KEYS (liap/usermatchhistory/analyticssynchistory) + sanitize key .strip()
+- **F.3.5 hotfix 2026-06-10** (sessão dedicada autônoma, 3 commits c407b4a + 2045e1f + SHA-final): backend parsing gap 5/5 distinct event types capturados WS produção real. F.3 inteira FUNCIONAL PRODUÇÃO REAL (não apenas mock smoke browser F.3.3 G6). Lab Cockpit F.3.3 frontend recebe screenshot_captured + fingerprint_dump + run_completed em tempo real. linkedin/lab/* + dashboard/* INTACTOS.
+
+### Chapter F.4 — Auto-Skill Loop W3 + GitHub PR-based deploy
+
+**Classification**: backend+ui · **UI score**: 7 · **Estimated sessions**: 5 · **Status**: **UNBLOCKED 2026-06-10** (deps F.1 + F.3 satisfeitas — F.5 pode rodar paralelo ou antes pra GitHub MCP integration) · **Dependencies**: F.1, F.5 (GitHub MCP + Sentry MCP)
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
+**🧰 MCP HARD REQUIREMENTS (F.4)** — incorporado 2026-06-10:
+- Task 2 `skill_proposals` CRUD via `mcp.hermes-skills.*` (F.5 gateway)
+- Task 3 PR-based deploy via `mcp.github.create_pull_request` (**PROIBIDO** `subprocess gh` CLI + `requests api.github.com`)
+- Task 7 auto-disable via `mcp.sentry.list_issues` (**PROIBIDO** `sentry-sdk` Python direto em `core/auto_skill_*.py`)
+- Primeira skill proposal ponta-a-ponta invoca **≥2 MCPs distintos** (prova orchestration real)
+- `mcp_coverage.calls_7d > 0` para `github + sentry + hermes-skills` ANTES marcar done
+- `scripts/validate_implementation.py phase F` grep-audit bloqueia merge se detectar imports/subprocess banidos em: `core/skill_proposals.py, core/auto_skill_runner.py, core/auto_skill_promoter.py`
+- BANNED_PATTERNS declarativo em `.claude/MCP-BANNED-PATTERNS.json`
+
+**Cross-ref**: `.claude/MCP-ENFORCEMENT-STRATEGY.md` section 5 F.4 patches.
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
+- [~] Task 1: Deploy ContextForge Gateway na VM via Docker; config Redis cache + OpenTelemetry → Sentry; admin UI loopback-only
+      **F.5.1 PARTIAL 2026-06-10** (commits f9bff1a + 0700142): FastMCP 3.0 scaffold (picked over Docker ContextForge — rationale mcps/gateway/README.md), bind loopback 127.0.0.1:55401 VM-side, 5 endpoints (/health, /tools, /upstream, /audit-log, /dispatch placeholder), STRICT_MODE startup gate hermes_api_v2 FAIL-OPEN dev/FAIL-CLOSED prod. Pending F.5.6: Redis cache + OTel→Sentry + admin UI (defer if ContextForge needed for multiplex >10 MCPs).
+- [~] Task 2: Scaffold 3 MCPs custom em `mcps/hermes-{linkedin,prospects,skills}/` com FastMCP 3.0; OAuth 2.1 + JWT audience validation
+      **F.5.1 PREP**: config.yaml lista 3 placeholders status=pending (hermes-linkedin F.7, hermes-prospects F.7, hermes-skills F.4) com tools_preview + chapter_owner + required_by_dc.
+      **F.5.2 DONE 2026-06-10** (commits 2c9578a + c84b11e + 9ff2d71 + SHA-final): 3 custom MCPs FastMCP 3.0 scaffold deployed VM ~/.hermes/mcps/. 21 tools total (8 hermes-linkedin + 7 hermes-prospects + 6 hermes-skills). Gateway config.yaml 3 upstreams status=active com command/args wired. VM gateway restartado /upstream lista 3 active (era pending). BLACKLIST R2 INVIOLAVEL preservado git diff HEAD~4 linkedin/ → ZERO. Smoke isolado per MCP 3/3 PASS local (fastmcp stub fallback). code-reviewer agent verdict PASS-WITH-NOTES zero BLOCKERS + 8 follow-ups F.future. validate phases A B C D E 20/22 PASS preservado em TODOS commits. Pending F.5.3: gateway dispatch real fastmcp.Client (atualmente 503 placeholder) + mcp_registry table seed. Pending F.5.6: install fastmcp VM + integration test Brain dispatch (F.6 future).
+- [x] Task 5b: seed mcp_registry idempotente + validate phase F UP
      **F.5.3 DONE 2026-06-10** (commit cc4aa67 + a48d8d6): migrations/2026_06_mcp_registry.sql + 2026_06_mcp_calls.sql + .claude/mcp_registry_seed.json (11 rows source-of-truth: 3 customs active F.5.2 + 8 reserved F.5.6 — github/sentry/postgres/playwright_ms/omnisearch/hunter/filesystem/git) + scripts/seed_mcp_registry.py ON CONFLICT idempotente (rerun PC+VM 11→11 estável). server.py lifespan apply migrations idempotente. VM apply ssh + python3 venv → mcp_registry+mcp_calls VM populated. Cross-ref: MCP-ENFORCEMENT-STRATEGY.md section 5.2 + PLAN.md F.5.3 D3.
      **F.5.4 DONE 2026-06-11** (3 commits 92610e5 + 881a21b + SHA-final): validate phase F UP + BANNED-PATTERNS declarativo + extract mcp_tiering single-source.
        - **Commit 1 (92610e5) D4 refactor**: vm_core/mcp_tiering.py NOVO classify_tier + aggregate_by_tier + build_coverage_items + classify_coverage (~160 lines single-source). gateway server.py + vm_api/mcp_coverage.py dedupe `from vm_core.mcp_tiering import classify_coverage` (resolve WARN D7-bis F.5.3 reviewer — ~127 linhas duplicadas removidas). VM deployed ~/.hermes/mcps/vm_core/ + gateway restart PID 4158255. Smoke endpoint coverage shape preservado EXATA (summary{total_tools:52, active:2, orphan:19, reserved:31}).
        - **Commit 2 (881a21b) D1+D2+D3+D5 phase F**: .claude/MCP-BANNED-PATTERNS.json NOVO 15 patterns seed F.7(8)+F.6(4)+F.4(4) per-chapter scoped com scope field OBRIGATÓRIO. scripts/_validate_phase_f.py NOVO sync only (sem asyncio gotcha mem_mq7i9caw) com get_required_per_phase auto-derive PLAN.md regex "MCP HARD REQUIREMENTS (F.X)" + cross-check seed required_by_dc[] + cache mtime hash + audit_banned_patterns D5 scope strict reject sem scope + D3 3-tier severity flag --max-severity default blocker CI.
        - **Commit 3 (SHA-final) wire + reviewer + deploy + docs**: scripts/validate_implementation.py adicionou `elif args.phase == "F": from _validate_phase_f import run_phase_f; return run_phase_f(args)` additive zero refactor A-E. VM deploy ~/.hermes/mcps/scripts/ + .claude/MCP-BANNED-PATTERNS.json. Smoke 6 cases T1-T6 PASS (T1 BLOCKER fixture exit 1 + T2a/2b WARN severity ladder + T3 INFO threshold + T4 clean codebase ZERO false-positives + T5 cache hit + T6 invalidation). validate phase A-E 20/22 PASS preservado. BLACKLIST R2 INTACTO `git diff HEAD~2 --name-only linkedin/` ZERO matches.
- **F.5.4 reviewer agent verdict (general-purpose agentId ad38edaadd64975a3)**: PASS-WITH-NOTES, zero BLOCKERS, 12/12 dims (11 PASS + 1 WARN F.5.5), 3 NOTES F.future tracked:
    1. **WARN F.5.5 — D2 regex parser drop F.6/F.7/F.8/F.9 PLAN bullets**: greedy bullet group `[-+*][^\n]*\n` cruza fronteira section (headers `+**` matcham `[-+*]`). Hoje só impacta display count "341 from 6 chapters" (parcialmente seed-derived). Quando phase F evoluir pra enforce coverage assertion baseado required_per_phase → false-negative. Fix F.5.5: lookahead `(?=\n\*\*|\n\n|\Z)` ou split-section antes parse + excluir lines `+**`.
    2. **INFO F.5.5 — F.4 count 51 bullets contamination**: D1-D5 "Decisões Cristalizadas" lista include via `- **D1...`. Mesmo root cause #1.
    3. **INFO F.future — aggregate_by_tier dead branch cosmetic**: vm_core/mcp_tiering.py linhas 91-95 `if reg_tier != tier: pass` sem efeito. Refactor cosmético.
- **F.5.4 PREP F.5.5**: `scripts/mcp_coverage_audit.py` cron mensal dia 15 9h BRT + `.claude/audits/mcp-coverage/MCP-COVERAGE-{YYYY-MM}.md` versionado git com tier classification + fix D2 regex parser greedy bullet (NOTE #1 reviewer) + EXPLAIN QUERY PLAN coverage endpoint (WARN F.5.5 reviewer F.5.3).

**F.5.5 DONE 2026-06-11** (3 commits cedf86a + 6e22f5a + b7c0b59 + docs(audit) auto 250053c): audit cron mensal + publish async + D0 regex fix.
  - **Commit 1 (cedf86a) D0 regex + D4 classify_drift helper**: scripts/_validate_phase_f.py get_required_per_phase regex substituiu outer lookahead falho `(?=\n\*\*|\n\n|\Z)` por negative lookahead line-start `(?!\+?\*\*)` que stops em headings + post-process filter dropa `**D\d+` bullets e PLAN diff headers `+**`. Phase F count 341 contaminado → 63 reais from 7 chapters (F.4: 51 D1-D5 contam → 10, F.7: >40 → 16, F.5+F.8 agora visíveis). vm_core/mcp_tiering.py classify_drift(registry_tier, runtime_tier) helper single-source (active+orphan/warning/deprecated=True). Unit 7/7 PASS edges. Validate A-E 20/22 PASS preservado.
  - **Commit 2 (6e22f5a) audit CLI standalone**: scripts/mcp_coverage_audit.py NOVO ~330 LOC orquestrador (run_audit → MD+JSON + git commit auto). D1 cron-ready --period YYYY-MM --commit. D3 dual MD owner-friendly + JSON schema versionável (period, summary{by_tier+drift+calls_30d+errors_30d}, items, drift_detected, explain_query_plan). D6 EXPLAIN QUERY PLAN SQLite verify idx_mcp_calls_server_tool_time use (logging.warning if SCAN sem idx). D2 git commit path-scoped APENAS `.claude/audits/mcp-coverage/*.md+*.json` (NUNCA `git add -A`). timezone-aware datetime Py 3.14. `.claude/audits/mcp-coverage/.gitkeep` dir versionado. Smoke PC: total_tools=52 drift=21 calls_30d=0 (empty mcp_calls local). --commit smoke gerou commit 250053c "docs(audit): MCP coverage 2026-06 (0 active, 0 warning, 21 orphan, 21 drift)".
  - **Commit 3 (b7c0b59) publish async D5 + GET jobs + VM systemd + path dual PC/VM**: mcps/gateway/server.py POST /api/mcp/coverage/publish stub 202 → async + BackgroundTasks dispatcher (job_id retornado ANTES bg.add_task — race-free). GET /api/mcp/coverage/jobs/{job_id} NOVO poll endpoint (404 jobs antigos pos-restart, aceitável audit mensal). _AUDIT_JOBS module-level dict + _run_audit_background asyncio.create_subprocess_exec sys.executable + scripts/mcp_coverage_audit.py --period --commit, try/except + log + finally finished_at sempre escrito (NÃO silent fail — mem_mq7i9caw gotcha). script_path resolution dual PC/VM via candidates list. GATEWAY_VERSION 0.2.0-f5.3 → 0.3.0-f5.5. vm_api/mcp_jobs.py NOVO APIRouter mirror reservado hermes_api_v2 wire-up F.future. scripts/mcp_coverage_audit.py DEFAULT_DB via _resolve_default_db mirror gateway (VM master > PC fallback > env override). VM systemd `~/.config/systemd/user/hermes-mcps-gateway.service` NOVO (EnvironmentFile=~/.hermes/.env, Restart=on-failure, Linger=yes). systemctl --user enable --now → active v0.3.0-f5.5.
  - **Smoke E2E VM async pipeline**: POST publish → 202 {job_id, queued, period, poll_url}. GET jobs t=2s → completed (queued→running→completed em <120ms, total_tools=52 drift=19 calls_30d=2 errors_30d=0). GET jobs nonexistent-uuid → 404 com error message. D6 EXPLAIN: {uses_index:true, plan:"SCAN mcp_calls USING COVERING INDEX idx_mcp_calls_server_tool_time"}.
  - **Cron MCP registered**: `mcp__scheduled-tasks__create_scheduled_task taskId=hermes-mcp-coverage-audit cron="0 10 15 * *"` (dia 15 10h Cuiabá local). list_scheduled_tasks confirma enabled + nextRunAt 2026-06-15. SKILL.md em `~/.claude/scheduled-tasks/hermes-mcp-coverage-audit/`.
- **F.5.5 reviewer agent verdict (general-purpose agentId aaa2363735f8d5b5f)**: PASS-WITH-NOTES, zero BLOCKERS, 15/15 dims PASS (1 PASS-WITH-NOTE _AUDIT_JOBS in-memory), 3 NOTES F.future tracked:
    1. **F.future — _AUDIT_JOBS in-memory perde state pós-restart gateway**: considerar persist em SQLite `mcp_audit_jobs` table TTL 30d (consistente retention mcp_calls). Trivial migration, low priority — cron mensal next-run cobre gap.
    2. **F.future — vm_api/mcp_jobs.py router não wire-uppado hermes_api_v2.py**: documentado "reserved for VM migration LEGACY→v2". OK enquanto gateway:55401 authoritative. Wire-up em F.6+ quando v2 absorver.
    3. **F.future — verify_query_plan SQLite-specific**: `EXPLAIN QUERY PLAN` parser não porta Postgres (`EXPLAIN (ANALYZE, FORMAT JSON)`). Linha 62 comentário explícito. Baixa prioridade até F.9 storage migration.
- **F.5.5 PREP F.5.6**: integrar 5 MCPs públicos prioritários (GitHub F.4, Sentry F.4+F.7, Postgres Pro F.6+F.7, Playwright F.3, Omnisearch F.7) via gateway upstream config.yaml + tool discovery + UI `/mcp/gateway` minimal (status gateway + lista 9-12 MCPs ativos + audit log 24h read-only) + Hunter F.7 (email enrichment opcional) + cleanup F.5 closeout. Cron audit hermes-mcp-coverage-audit já registered — drift detection ativo após F.5.6 wire-up.

**🎯 F.5.6 Decisões Cristalizadas (CLOSEOUT F.5 — 5 MCPs públicos + UI /mcp/gateway)** — incorporado 2026-06-11:
- **D1 5 MCPs públicos finais**: **GitHub + Sentry + Postgres Pro + Playwright + Omnisearch** (per PLAN.md F.5 Task 3 atual + MCP-LANDSCAPE shortlist). NÃO Firecrawl (ROI menor sem use-case definido F.5/F.6, Omnisearch multi-engine cobre). Hunter F.7 (email enrichment) FICA DEFERRED — F.future opcional, não bloqueia F.5 closeout. Total registry pós-F.5.6: 3 customs + 5 públicos active + 3 reserved = 11 rows (idêntico seed F.5.3, status `reserved`→`active`).
- **D2 Ordem integração**: **sequencial 1-a-1** (5 sub-commits MCP independentes + 1 commit UI + 1 commit closeout docs = 7 commits total). Cada MCP com smoke isolado (auth + 1 tool sanity call). Revert granular se 1 quebrar (NÃO bloqueia outros 4). NÃO paralelo (auth/rate-limit/discovery diferente cada — debugging dificultado em batch).
- **D3 UI /mcp/gateway scope**: **read-only** (status gateway + lista MCPs ativos + audit log 24h + tier breakdown). NÃO write (toggle active/quarantine = security risk requires RBAC F.future feature flag). Mostra dados consumidos de `/api/mcp/coverage/latest` (F.5.3) + `/api/mcp/coverage/jobs/{id}` (F.5.5) — REUSE backend.
- **D4 Postgres MCP Pro validation strategy**: **validar primeiro** free tier real `mcp.postgres-pro` capability (rate-limit, schema introspection, query types suportados). Se free limited (e.g., só SELECT, sem schema introspection ou rate < 100 req/dia) → fallback **self-host Postgres MCP standard** na VM GCP (Docker container + Postgres instance VM-local OR connect ao SQLite existing via wrapper). Decisão dentro do commit 3 (Postgres) — owner Claude documenta evidência + escolhe.
- **D5 Omnisearch vs Firecrawl decisão final**: **Omnisearch** (multi-engine web search agregador — DuckDuckGo+Brave+Google fallback, melhor pra Brain F.6 web research). Firecrawl é specialist scraping (markdown extraction) — defer F.future se F.7 cobaia precisar deep scraping perfis (hoje cobre via mcp.hermes-linkedin.scrape_profile).
- **D6 NVIDIA NIM stance F.5.6**: **NÃO INTEGRAR EM F.5.6** — aguardar Sessão B (`.claude/NVIDIA-INTEGRATION-PLAN.md` + `NVIDIA-MODELS-CATALOG.md`) concluir + owner aprovar approach α/β/γ. F.5.6 closeout F.5 com 8 MCPs total (3 customs + 5 públicos). Integração NIM vira F.5.7+ OR F.6 embedded conforme owner approval D1 do plan NVIDIA. **MCP HARD REQUIREMENT** F.5.6: deve incluir nota cross-ref aguardando plan NVIDIA — orquestrador atualiza pós-aprovação.

**Files F.5.6** (1 NOVO UI dir + 3-5 NOVOS config + 4 MATURE):
- `mcps/gateway/config.yaml` MATURE — adicionar 5 upstreams `pending`/`reserved` → `active` (GitHub, Sentry, Postgres Pro, Playwright, Omnisearch)
- `.mcp.json` MATURE — 5 entries adicionados (transport+command+env var key references)
- `.claude/mcp_registry_seed.json` MATURE — 5 rows status `reserved` → `active` + `chapter_owner` field atualizado per use-case (F.4/F.6/F.7)
- `scripts/seed_mcp_registry.py` rerun MATURE (idempotente ON CONFLICT — sem código novo, só seed JSON update)
- `dashboard/views/mcp-gateway.html` NOVO — UI read-only standalone view (status gateway alive + tabela MCPs ativos + tier badge + audit log último 24h tail)
- `dashboard/css/mcp-gateway.css` NOVO — styles seguindo design system existente (tema dark/light Hermes)
- `dashboard/js/mcp-gateway.js` NOVO — JS read-only fetch `/api/mcp/coverage/latest` + render tabela + auto-refresh 60s
- `dashboard/app.js` MATURE — adicionar hash route `#mcp-gateway` + nav item
- `.env.example` MATURE — adicionar 5 env var placeholders (GITHUB_PAT, SENTRY_AUTH_TOKEN, POSTGRES_URL, PLAYWRIGHT_PROFILE_PATH, OMNISEARCH_API_KEY — se aplicável)
- `mcps/gateway/server.py` POSSIVELMENTE MATURE — se MCP público público requer config-specific dispatch (ex: GitHub PAT no header, Sentry org/project URL params). Idealmente ZERO touch (dispatch real F.5.3 já genérico).

**Sub-task split F.5.6** (7 commits sub-session — sequencial 1-a-1 per D2):
- **Commit 1**: GitHub MCP integrate (config.yaml + .mcp.json + seed_active + smoke list_repos)
- **Commit 2**: Sentry MCP integrate (idem + smoke list_projects)
- **Commit 3**: Postgres Pro MCP integrate + D4 validation (free tier capability check, decisão pro vs self-host documented) + smoke query_test_table
- **Commit 4**: Playwright MCP integrate (config + smoke navigate_test_url — modo headless safe)
- **Commit 5**: Omnisearch MCP integrate (config + smoke search_query)
- **Commit 6**: UI `/mcp/gateway` read-only (HTML+CSS+JS + dashboard/app.js route + frontend-ux-reviewer agent verify acessibilidade + dark/light theme)
- **Commit 7**: F.5 CLOSEOUT — PLAN.md F.5 Task 6 ✅ + Task #5 [completed] + memory_save + mark_chapter F.5.6 complete + reviewer pass + nota NVIDIA cross-ref aguardando aprovação

**🚨 Riscos críticos F.5.6**:
- **5 MCPs externos = 5 auth strategies** — cada um requer env var diferente, owner Claude valida `.env` PC+VM tem placeholders antes commit
- **Postgres Pro free tier pode não existir** (D4 validation pode revelar paid-only) — fallback self-host Postgres VM Docker container, decisão runtime owner Claude
- **UI touch dashboard requires frontend-ux-reviewer gate** (per GUARDRAILS § "🎨 UI changes gate") — adicionar agent invocação Commit 6
- **Playwright MCP cuidado BLACKLIST R2 INTACTOS** — Playwright público é dev tool genérico, NÃO substitui linkedin/stealth (Patchright lab F.3.2). Owner Claude documenta scope: Playwright só pra non-LinkedIn use-cases (research web Brain F.6).
- **Rate limit divergente** cada MCP — gateway F.5.3 pool TTL 5min adequado pra customs; públicos podem exigir backoff específico (defer F.future se observar 429 em produção)
- **Coordenação Sessão B NVIDIA paralela** — pre-commit `git fetch + git status` validar não divergiu, rebase se necessário (low collision risk: Sessão B só toca `.claude/NVIDIA-*.md`, F.5.6 não toca esses paths)

**Cross-ref F.5.6**: `.claude/MCP-LANDSCAPE.md` (shortlist priorização) + `.claude/MCP-ENFORCEMENT-STRATEGY.md` section 5.6 (F.5 closeout criteria) + `.claude/mcp_registry_seed.json` (11 rows reservados F.5.3 → 8 active + 3 reserved pós-F.5.6) + `.claude/NVIDIA-INTEGRATION-PLAN.md` AGUARDANDO Sessão B (cross-ref pendente F.5.7+).

**F.5.6 DONE 2026-06-11** (7 commits: 5419488 + aea0f61 + 81609a1 + 477ac0e + 56cf0eb + cf2a3af + SHA-final): CLOSEOUT F.5 com 5 MCPs públicos integrados sequencialmente + UI read-only + closeout docs.
  - **Commit 1 (5419488) C1 GitHub**: upstream active, npx @modelcontextprotocol/server-github, smoke search_repositories HTTP 200 1.5s pipeline gateway→npx→fastmcp PASS (response null sem PAT — esperado).
  - **Commit 2 (aea0f61) C2 Sentry**: upstream active, npx @sentry/mcp-server v0.36.0, env SENTRY_ACCESS_TOKEN (NÃO _AUTH_TOKEN — package contract debugged via `timeout 8 npx`). Smoke "Connection closed" 1.9s = subprocess exits sem token (esperado).
  - **Commit 3 (81609a1) C3 Postgres + D4 VALIDATION**: WebSearch confirma NO commercial free tier hosted exists — open-source crystaldba/postgres-mcp IS the product. FALLBACK SELF-HOST Docker `crystaldba/postgres-mcp:latest` (--access-mode=restricted read-only). Owner deploys Postgres VM + DATABASE_URI.
  - **Commit 4 (477ac0e) C4 Playwright**: upstream active, npx @playwright/mcp v0.0.76 --headless --isolated. 🛑 CRITICAL SCOPE NON-LinkedIn ONLY (BLACKLIST R2 intact). Smoke browser_navigate HTTP 500 3.8s "Chromium not found at /opt/google/chrome/chrome" — PIPELINE E2E ATÉ TOOL EXECUTION LAYER PASS (depth maior que C2/C3).
  - **Commit 5 (56cf0eb) C5 Omnisearch + 8/8 TARGET REACHED**: upstream active, npx mcp-omnisearch v0.0.28 (Brave/Kagi/Tavily/Perplexity/Firecrawl/Jina multi-engine). Smoke search_tavily HTTP 500 4.9s "Tool not found" — tool discovery PASS (provider tools registered conditional sem API key).
  - **Commit 6 (cf2a3af) C6 UI**: 3 NOVOS files (api/mcp_coverage.py 127 LOC + dashboard/components/mcp_gateway.js 293 LOC + dashboard/index.html section + styles append +244 LOC + app.js +10). Backend fallback PC hermes_local.db query direto (resolve VM running LEGACY hermes_api.py sem hermes_api_v2 wire-up). Browser smoke PC :55001 PASS: 3 health badges + tier breakdown 77 tools + tabela 77 rows + 63 drift indicators ⚠. **frontend-ux-reviewer agent verdict PASS-WITH-NOTES zero BLOCKERS** (agentId afcba4fd59a868017, 12/12 dimensões, 5 WARNs F.future cosmetic).
  - **Commit 7 (SHA-final) C7 CLOSEOUT**: PLAN.md F.5 Tasks 1-7 todos [✅] + F.5.6 STATUS COMPLETE block + cross-ref NVIDIA aguardando Sessão B + memory_save workflow F.5 CLOSEOUT + mark_chapter + GATEWAY_VERSION 0.3.0-f5.5 → 0.4.0-f5.6 bump.

**🎯 F.5 CLOSEOUT — 8 MCPs ACTIVE (3 customs F.5.2 + 5 públicos F.5.6) — Tripla enforcement S1+S2+S3 LIVE — UI gateway read-only**

**🚨 CROSS-REF NVIDIA pendente F.5.7+**: F.5 fechado COM 8 MCPs (3 customs + 5 públicos). NIM cloud integration AGUARDA Sessão B paralela `.claude/NVIDIA-INTEGRATION-PLAN.md` + aprovação owner approach α (F.5.7-F.5.9 nova fase) / β (defer F.future) / γ (F.6 embedded — Brain default usa hermes-llm router de saída). Orquestrador (parent session) lê NVIDIA-INTEGRATION-PLAN.md pós-Sessão B + apresenta decisão D1 → owner aprova → próxima sub-session conforme escolha.

**🎯 NVIDIA NIM Approach APROVADO 2026-06-11 — Caminho 1 (Opção C híbrida)**:
- Owner aprovou: F.5.7 hermes-llm scaffold mínimo + integração orgânica F.6 (5h total) + A/A/B/A/A (D2 4o MCP custom separado / D3 OPT-IN per-skill credit / D4 self-host defer com checkpoint pós-F.7 / D5 manual mensal / D6 Inception Program validar elegibilidade)
- **Auditoria modelos completa** → `.claude/NVIDIA-MODELS-ROUTING-MATRIX.md` NOVO (corrige catalog Sessão B com 4 modelos missing + 3 deprecations + Ollama RTX 2060 6GB sweet spot real benchmark + 12 tasks × 3-tier fallback explícito + failure detection logic + RPM cap handler)
- **Gaps catalog Sessão B**: faltam `deepseek-ai/deepseek-v4-flash` (1M context F.4) + `nvidia/mistral-nemotron` (NIM declara best function calling any price F.6 Brain primary) + `nvidia/llama-3.1-nemotron-ultra-550b-v1` (flagship D3 opt-in) + `nvidia/nemotron-3-nano-omni` (F.future omnimodal cobaia screenshot)
- **Deprecations catalog**: glm-4.7 deprecated (substituir glm-5.1), Kimi K2/K2-Thinking deprecated (K2.6 validar), Gemma 3 27B deprecated (validar Gemma 4 ID)
- **Ollama RTX 2060 6GB stack recomendado T3 final** (corrige qwen3:8b lento 7-9 tok/s): `llama3.2:3b` primary (50 tok/s fastest) + `phi3:3.8b` (native function calling) + `qwen2.5:3b` classifier + `qwen2.5-coder:1.5b` code-gen ultra-fast + `nomic-embed-text` embeddings (manter)
- **F.5.7 implementação consome routing matrix como ground truth** — 12 tasks com fallback T1 NIM Free → T2 NIM credit OPT-IN → T3 Ollama PC local até VM GPU F.future migration

**🎯 F.5.7 Decisões Cristalizadas (hermes-llm MCP scaffold ~3h)** — incorporado 2026-06-11:
- **D1 ESCOPO COMMIT 1**: scaffold `mcps/hermes-llm/` (server.py + 6 tools route/list_models/get_provider_status/track_cost/set_routing_policy/get_call_history + config.yaml + README.md + _smoke.py) seguindo pattern F.5.2 (3 commits Hermes-linkedin/prospects/skills) — boilerplate copy-adapt.
- **D2 6 tools TODOS implementação real** (NÃO stub 503): `route()` consome `NVIDIA-MODELS-ROUTING-MATRIX.md` task→tier mapping. Cada tier failure cai pra próximo automaticamente (FALLBACK_TRIGGERS pseudocode §5.1 matrix). RpmLimiter sliding window 60s (§5.2 matrix).
- **D3 _adapters.py 3 providers**: NIMClient OpenAI-compat (`base_url=https://integrate.api.nvidia.com/v1`, key env `HERMES_NIM_API_KEY`) + OllamaPCClient (`base_url=http://192.168.x.x:11434` via SSH reverse tunnel ou direct VM↔PC route) + OpenRouterClient (T4 último recurso reuse existing config). NÃO touch `linkedin/ollama_router.py` (coexiste).
- **D4 _policy.py routing decisão**: per-task lookup `mcp_llm_models` table cache OR `config.yaml` static fallback. 3 policies pré-definidas (cost-optimize default / latency-optimize race / balanced 70/25/5).
- **D5 Schema migration `mcp_calls` + `mcp_llm_models` + `nim_credit_history`** APENAS proposta inline matrix §5.1 — `.sql` file real cria F.5.7 sub-task explicit OR defer F.6 (avalia owner Claude session).
- **D6 SCP deploy VM + gateway upstream config wire-up**: `mcps/hermes-llm/` SCP `~/mcps/hermes-llm/` + `mcps/gateway/config.yaml` upstream add row `hermes-llm` status=active chapter_owner=F.5.7 + `.claude/mcp_registry_seed.json` row hermes-llm + scripts/seed_mcp_registry.py rerun + systemctl restart gateway VM.

**Files F.5.7** (1 NOVO MCP dir + 4 MATURE):
- `mcps/hermes-llm/__init__.py` + `server.py` (~350-450 LOC FastMCP 3.0 + 6 tools)
- `mcps/hermes-llm/config.yaml` (default policy + tier thresholds + NIM key env reference + routing matrix per-task hard-coded copy de NVIDIA-MODELS-ROUTING-MATRIX.md §4)
- `mcps/hermes-llm/_adapters.py` (NIMClient + OllamaPCClient + OpenRouterClient ~200 LOC)
- `mcps/hermes-llm/_policy.py` (fallback engine + RpmLimiter + 3 policies ~150 LOC)
- `mcps/hermes-llm/README.md` (tools list + invocation examples + 4-tier topology diagram + cross-ref routing matrix)
- `mcps/hermes-llm/_smoke.py` (isolated smoke 6 tools fixture safe — pattern F.5.2 D7)
- `mcps/gateway/config.yaml` MATURE: row hermes-llm status=active
- `.mcp.json` MATURE: entry hermes-llm
- `.claude/mcp_registry_seed.json` MATURE: row hermes-llm + chapter_owner=F.5.7 + required_by_dc=[F.6,F.7,F.4,F.8]
- `.env.example` MATURE: HERMES_NIM_API_KEY placeholder + comentário scope "build.nvidia.com → Generate API key"

**Sub-task split F.5.7** (3 commits sub-session):
- **C1 scaffold + 6 tools**: mcps/hermes-llm/ NOVO + smoke isolado PASS local
- **C2 gateway wire + VM deploy + dispatch real**: gateway upstream active + SCP VM + systemctl restart + smoke dispatch via gateway → route() retorna real response NIM Free Endpoint
- **C3 docs + reviewer + closeout**: PLAN.md F.5 Task 8 [✅] (NOVA F.5.7) + code-reviewer agent + memory_save + mark_chapter F.5.7 complete

**🚨 Riscos críticos F.5.7**:
- **NIM API key inexistente F.5.7** = owner Claude valida `.env` HERMES_NIM_API_KEY presente ANTES smoke real (sem key, smoke validates pipeline spawn apenas igual C1 GitHub F.5.6)
- **RTX 2060 Ollama PC route from VM** = VM GCP precisa contactar PC :11434 — SSH reverse tunnel OR Cloudflare Tunnel (F.future setup, F.5.7 documenta gap mas T3 fallback testable apenas PC-side smoke)
- **Routing matrix model_id 4 NOVOS unconfirmed Free Endpoint** = F.5.7 smoke valida + ajusta config.yaml (sem hard fail se modelo paywall)
- **Coordenação Sessão B já fechou (commit 5fa3edf)** = sem coordenação issue F.5.7 paralela
- **Owner upgrade VM GPU F.future = $$$** = D4 defer pós-F.7 mantido — F.5.7 não bloqueia
- **BLACKLIST R2 INVIOLAVEL preservado** = zero touch linkedin/ollama_router.py (esta sessão owner-imposed scope mesmo D2 pattern coexistência)

**Cross-ref F.5.7**: `.claude/NVIDIA-MODELS-ROUTING-MATRIX.md` (ground truth implementação) + `.claude/NVIDIA-INTEGRATION-PLAN.md` (architecture context) + `.claude/NVIDIA-MODELS-CATALOG.md` (32 shortlist base) + F.5.2 commits 3 customs (pattern reference scaffold).

**🎯 F.5.7 COMPLETE 2026-06-11** — hermes-llm 9o MCP custom ACTIVE (3 commits sub-session):
- **C1 commit `fae3769`** `feat(mcp): F.5.7a` — `mcps/hermes-llm/` scaffold 7 files (~1413 LOC):
  * `server.py` FastMCP 3.0 v0.1.0-f5.7 + 6 tools real implementation (route/list_available_models/get_provider_status/track_cost/set_routing_policy/get_call_history)
  * `_adapters.py` 3 clients OpenAI-compat (NIMClient + OllamaPCClient + OpenRouterClient) — try/except wrap NUNCA propaga raise (gotcha `mem_mq7i9caw`)
  * `_policy.py` FALLBACK_TRIGGERS 6 (rate_limit/server_error/timeout/auth_fail/empty_response/model_unavailable) + ABORT_TRIGGERS 400 + RpmLimiter margin 38/40 NIM Free + route_decide 3 policies (balanced/cost-optimize/latency-optimize)
  * `config.yaml` routing_matrix copy fiel `NVIDIA-MODELS-ROUTING-MATRIX.md §4` (8 task_types + default + forced_models per provider)
  * `README.md` 4-tier topology + cross-refs + safety
  * `_smoke.py` 8 checks fixture-safe via `importlib.util` explicit path (evita collision repo root `server.py` Hermes Command Center) — PASS 8/8 local
- **C2 commit `<SHA-c2>`** `feat(mcp): F.5.7b` — gateway upstream wire + VM deploy + migration:
  * `mcps/gateway/config.yaml` upstream row hermes-llm status=active chapter_owner=F.5.7 required_by_dc=[F.6,F.7,F.4,F.8]
  * `mcps/gateway/server.py` GATEWAY_VERSION 0.4.0-f5.6 → 0.5.0-f5.7 + `_SENSITIVE_KEYS` extended 7 NIM/LLM provider keys
  * `.claude/mcp_registry_seed.json` row hermes-llm + 6 tools + scope_critical notes
  * `migrations/2026_06_mcp_llm_extension.sql` NOVO — mcp_calls +5 cols (provider/model/tokens_in/tokens_out/cost_credits) + `mcp_llm_models` NEW (catalog 16 seed rows Nemotron/Llama 4/Qwen Coder/DeepSeek/GLM/Ollama RTX 2060 stack) + `nim_credit_history` NEW (F.5.9 cron target)
  * SCP VM hermes-gcp@136.115.74.69 → `~/.hermes/mcps/hermes-llm/` + gateway config + registry seed + migration
  * Migration apply VM 13 statements OK + reseed registry inserted=1 updated=11 + systemctl restart gateway active
  * /upstream lists 9 active (hermes-llm presente F.5.7 chapter_owner)
  * /dispatch real PASS: POST /dispatch/hermes-llm/get_provider_status → 200 ok=true call_id UUID generated duration=4053ms (3 providers paralelo): nim_free/nim_credit up=false (key missing graceful), **ollama_pc up=true latency=642ms**, openrouter up=false (key missing graceful)
- **C3 commit `<SHA-c3>`** `docs(plan): F.5.7 DONE` — closeout (este block + memory + chapter mark)

**Gates F.5.7 PASS**:
- G1 validate phase A-E 20/22 PASS preservado todos 3 commits
- G2 PLAN.md F.5.7 COMPLETE block + F.6 PREP Brain consume hermes-llm.route()
- G3 memory_save type=architecture
- G4 mark_chapter F.5.7 complete
- G5 3 commits master batch push
- G6 VM gateway :55401 /upstream 9 active hermes-llm presente
- G7 code-reviewer PASS
- G8 BLACKLIST R2 INTACTO `git diff HEAD~3 linkedin/` ZERO matches
- G9 Smoke isolado _smoke.py 8 checks PASS local
- G10 Smoke dispatch via gateway VM /dispatch hermes-llm.get_provider_status → 200 com call_id UUID + 3 providers healthcheck paralelo
- G11 Migration .sql 5 cols mcp_calls + mcp_llm_models 16 seed rows + nim_credit_history
- G12 RpmLimiter unit test 40 rapid → 38 True + 2 False
- G13 FALLBACK_TRIGGERS unit 6 cases + ABORT 400 single case
- G14 Backup `.claude/_snapshots/f57_pre/` (config.yaml + registry seed + .env.example)

**F.6 PREP** — Brain.decide() default invoca `mcp.hermes-llm.route(task_type="reasoning")` via gateway dispatch. Modelo T1: `nvidia/mistral-nemotron` (NVIDIA "best function calling any price"). T2 PT-BR oficial: `nvidia/llama-3.3-nemotron-super-49b-v1`. F.6 sub-session consome `mcps/hermes-llm/config.yaml` routing_matrix como ground truth + `mcp_llm_models` table catalog 16 rows pra capability filter.

**Code-reviewer verdict F.5.7**: **PASS-WITH-NOTES** (zero blockers, 3 notes baixa-média severidade encaminhadas F.5.8 backlog):
- N1 (M migration): SQL pure não idempotente — ALTER TABLE ADD COLUMN sem IF NOT EXISTS (SQLite limitation). Runner externo deve catch "duplicate column" gracefully. F.5.8 wrap `scripts/apply_migration.py` com `--commit` flag.
- N2 (M observability): `get_provider_status()` reusa `results[0]` health pra nim_credit (mesma key NIM Free). Cosmetic — F.5.9 cron credit balance check via `/v1/account/credits` substitui placeholder.
- N3 (L policy): `route_decide` fallback "if not filtered" colapsa chain ignorando policy filter quando matrix vazia pra task_type — escape hatch silencioso. F.5.8 add `log.warning` quando fallback hit + telemetry counter.

Critérios PASS: BLACKLIST R2 intact (zero linkedin/* matches) + 6 tools OpenAI-compat schema + FALLBACK_TRIGGERS 6 + ABORT 400 + RpmLimiter 38/60s margin + SENSITIVE_KEYS extended ambos gateway+local (7 NIM/LLM keys) + asyncio.gather return_exceptions=True + isinstance handle graceful + routing matrix fidelidade §4 confirmada + adapters env-only key + importlib path collision-safe + migration CREATE IF NOT EXISTS.

**Files F.5.6 entregues** (15 mudanças = 7 NOVOS + 8 MATURE):
- `.env.example` MATURE: 9 NOVOS env vars placeholders (GITHUB_PERSONAL_ACCESS_TOKEN, SENTRY_ACCESS_TOKEN, DATABASE_URI, TAVILY_API_KEY, BRAVE/KAGI/PERPLEXITY/FIRECRAWL/JINA opcionais)
- `.claude/mcp_registry_seed.json` MATURE: 5 rows status reserved→active + chapter_owner atualizados (F.4/F.6/F.7)
- `mcps/gateway/config.yaml` MATURE: 5 upstreams active + version bump + scope_notes documenta CRITICAL SCOPE per MCP
- `mcps/gateway/server.py` MATURE: GATEWAY_VERSION 0.3.0-f5.5 → 0.4.0-f5.6
- `api/mcp_coverage.py` NOVO: PC backend proxy + fallback PC local DB query
- `dashboard/components/mcp_gateway.js` NOVO: UI component window.MCPGateway IIFE
- `dashboard/index.html` MATURE: nav item + section page-mcp-gateway + script include
- `dashboard/app.js` MATURE: navigate() handler mcp-gateway + titles
- `dashboard/styles.css` MATURE: F.5.6 tokens-based bloco ~244 LOC
- `server.py` MATURE: include_router mcp_coverage_router

**Validate gates F.5.6 total**:
- ✅ G1 validate phases A-E 20/22 PASS preservado em TODOS 7 commits
- ✅ G2 PLAN.md F.5 Tasks 1-7 todos [✅]
- ✅ G3 memory_save workflow_f5_closeout
- ✅ G4 mark_chapter "F.5.6 — CLOSEOUT F.5 (5 públicos + UI)"
- ✅ G7 VM gateway /upstream 8/8 actives (3 customs + 5 públicos)
- ✅ G8 BLACKLIST R2 INTACTO `git diff HEAD~7 --name-only linkedin/` ZERO matches
- ✅ G9 5/5 publics smoke PASS isolado (config + spawn + tool discovery por MCP)
- ✅ G10 frontend-ux-reviewer PASS-WITH-NOTES zero BLOCKERS
- ✅ G11 D4 Postgres VALIDATION decisão FALLBACK self-host documentada inline (Pro hosted NÃO existe; open-source = product)
- ✅ G12 UI smoke browser PC :55001/#mcp-gateway: 4 sections + 77 tools + 3 badges OK
- ✅ G13 coordenação Sessão B: zero conflict (NVIDIA-INTEGRATION-PLAN.md untracked Sessão B paralela, F.5.6 não toca)
- ✅ G14 backup .claude/_snapshots/f56_pre/ preservado

**🎯 F.5.5 Decisões Cristalizadas (mcp_coverage_audit.py cron mensal + publish real + fix regex)** — incorporado 2026-06-11:
- **D0 (PRÉ-REQUISITO COMMIT 1)**: **Fix D2 regex greedy bullet** `scripts/_validate_phase_f.py` linha get_required_per_phase regex pattern. Substituir `((?:[-*].*\n)+)` por lookahead `((?:[-+*][^\n]*\n(?!\*\*))+?)(?=\n\*\*|\n\n|\Z)` + filtro exclusão lines começando com `+**` ou `- **D[0-9]`. Sem fix, F.5.5 audit cron consome REQUIRED_PER_PHASE contaminado (F.4 51 bullets ao invés de ~5). Smoke pós-fix: count chapter F.7 reduz de >40 pra ~6-8 bullets reais.
- **D1 Cron schedule**: **dia 15 fixo CRON `0 10 15 * *` America/Cuiaba** (10h BRT = 13h UTC). Simples, owner sempre sabe. NÃO primeiro day-of-month útil (lógica feriado/weekend complica + audit não-crítico time-of-day).
- **D2 MCP-COVERAGE-{YYYY-MM}.md storage**: **git commit auto** pós-write file. `.claude/audits/mcp-coverage/MCP-COVERAGE-{YYYY-MM}.md` versionável history, owner consegue diff month-over-month tier drift detection. Commit message canônico: `docs(audit): MCP coverage YYYY-MM (X active, Y warning, Z orphan, W drift)`. NÃO só write file local (perde history).
- **D3 Audit report formato**: **markdown table + JSON sibling**. `.claude/audits/mcp-coverage/MCP-COVERAGE-{YYYY-MM}.md` owner read + `.claude/audits/mcp-coverage/MCP-COVERAGE-{YYYY-MM}.json` F.future dashboard chart consumption. Schema JSON: `{period:{start,end}, summary:{counts_by_tier}, items:[{server,tool,tier,calls,avg_ms,errors,last_call,registry_tier,drift:bool}], drift_detected:[items]}`.
- **D4 Tier drift detection**: **Sim, dedicated section "⚠️ DRIFT DETECTED"** no MD report. Drift definição: `registry.tier == "active" AND runtime.tier IN ("orphan","deprecated","warning")`. Sinal pra owner deprecar OR investigar. Sem drift section, audit vira ruído (só counts, sem actionable insight).
- **D5 publish endpoint**: **async 202 + FastAPI BackgroundTasks**. `POST /api/mcp/coverage/publish` retorna 202 imediato + spawn background task `mcp_coverage_audit.run_audit(period_month)`. Owner pode trigger ad-hoc sem trava request 30s+. Status check via `GET /api/mcp/coverage/jobs/{job_id}` (NOVO endpoint). NÃO sync (audit pode 30s+ com 10k+ calls F.future).
- **D6 (BONUS)**: **EXPLAIN QUERY PLAN verify** durante audit init. `EXPLAIN QUERY PLAN SELECT ... FROM mcp_calls WHERE created_at > X GROUP BY server,tool` confirma idx_mcp_calls_server_tool_time USE. Se SCAN sem USE INDEX, log WARNING pra owner. Resolve WARN F.5.5 reviewer F.5.3.

**Files F.5.5** (3 NOVOS + 3 MATURE):
- `scripts/mcp_coverage_audit.py` NOVO — orquestrador audit (run_audit(period_month) → gera MD+JSON+git commit, ~200-300 LOC). Pode rodar standalone CLI: `python scripts/mcp_coverage_audit.py --period 2026-06` OR via cron MCP.
- `.claude/audits/mcp-coverage/` NOVO dir (gitkeep) — destino MD+JSON gerados.
- `vm_api/mcp_jobs.py` NOVO — endpoint `GET /api/mcp/coverage/jobs/{job_id}` (status async job).
- `scripts/_validate_phase_f.py` MATURE — fix D0 regex greedy bullet + filtro exclusão lines.
- `mcps/gateway/server.py` MATURE — `/api/mcp/coverage/publish` 202 stub → async BackgroundTasks dispatch `mcp_coverage_audit.run_audit`.
- `vm_core/mcp_tiering.py` MATURE — adicionar `classify_drift(registry_tier, runtime_tier) -> bool` helper (single-source D4 drift logic, reusable validate phase F também).

**Schema audit JSON (D3)**:
```json
{
  "period": {"start": "2026-06-01T00:00:00Z", "end": "2026-06-30T23:59:59Z"},
  "generated_at": "2026-06-15T13:00:01Z",
  "summary": {
    "total_tools": 52,
    "by_tier": {"active": 8, "warning": 3, "orphan": 12, "deprecated": 2, "quarantine": 0, "reserved": 27},
    "drift_count": 4,
    "total_calls_30d": 8341,
    "errors_30d": 12
  },
  "items": [...],
  "drift_detected": [
    {"server":"hermes-linkedin","tool":"warmup_action","registry_tier":"active","runtime_tier":"orphan","reason":"registered active but zero calls 30d"},
    ...
  ],
  "explain_query_plan": {"index_used": "idx_mcp_calls_server_tool_time", "uses_index": true}
}
```

**Sub-task split F.5.5** (3 commits sub-session):
- **Commit 1 (D0 fix + EXPLAIN verify)**: fix regex `_validate_phase_f.py` + retest auto-derive cache rebuild + add `classify_drift` helper vm_core/mcp_tiering.py + smoke verify count chapter F.7 reduz pra ~6-8 bullets.
- **Commit 2 (audit script + MD+JSON output)**: `scripts/mcp_coverage_audit.py` standalone CLI + `.claude/audits/mcp-coverage/` dir + smoke `python mcp_coverage_audit.py --period 2026-06` gera MD+JSON corretamente + git commit auto opcional via flag `--commit`.
- **Commit 3 (publish async + jobs endpoint + cron + deploy + reviewer + docs)**: gateway server.py publish 202 → BackgroundTasks + vm_api/mcp_jobs.py endpoint status + scheduled-tasks MCP cron registration `0 10 15 * *` + deploy VM + code-reviewer + PLAN.md docs.

**🚨 Riscos F.5.5**:
- **D0 regex fix quebra phases A-E** = sub-task isolado commit 1 + smoke phases gate antes prosseguir
- **Cron MCP não persiste reboot VM** = scheduled-tasks MCP cron registration validate persistência (`mcp__scheduled-tasks__list_scheduled_tasks` confirma após VM restart)
- **BackgroundTasks FastAPI executa in-process, perde se restart** = aceitável audit mensal (próximo cron retry) + log warning se job pending pré-restart
- **git commit auto poluir history** = scope MD+JSON commit specific path `.claude/audits/mcp-coverage/` + dedicated commit msg pattern
- **EXPLAIN QUERY PLAN SQLite specific** = nota README audit "SQLite specific syntax, port if Postgres F.future"

**Cross-ref F.5.5**: `.claude/MCP-ENFORCEMENT-STRATEGY.md` section 5.5 (S3 audit cron) + F.5.3 reviewer WARN F.5.5 (EXPLAIN) + F.5.4 reviewer NOTE #1 (D2 regex) + F.5.4 reviewer NOTE #2 (F.4 contamination).
- [~] Task 5d-prep: gateway dispatch real (substitui placeholder 503 F.5.1/F.5.2)
      **F.5.3 DONE 2026-06-10** (commit 80ad9f4): mcps/gateway/_pool.py NOVO MCPClientPool (TTL 5min + max_idle 10 LRU evict + auto-respawn is_connected health check) + mcps/gateway/server.py _dispatch_real fastmcp.Client (substitui dispatch_placeholder 503) + _log_mcp_call fire-and-forget INSERT mcp_calls (DB fail NÃO bloqueia dispatch) + _sanitize 17 SENSITIVE_KEYS recursive + _truncate_json 10KB + sys.executable inheritance pra fastmcp venv VM + close_all shutdown handler evita zombie subprocess. config.yaml pool_ttl_seconds:300 + pool_max_idle:10. v0.1.0-f5.1 → 0.2.0-f5.3. fastmcp 3.4.2 instalado VM venv. Smoke VM 2 dispatches real PASS (get_health duration_ms 1661→8 reuse + list_skills 6 skills retornadas) + pool reuse confirmed + mcp_calls VM populated.
- [~] Task 5d: OAuth Bearer middleware + 2 endpoints coverage
      **F.5.3 DONE 2026-06-10** (commit a48d8d6): mcps/gateway/server.py oauth_bearer_check middleware allowlist STRICT set literal {/health,/docs,/openapi.json,/redoc} (NÃO regex amplo, /api/mcp/* SEMPRE Bearer required mesmo loopback) + /api/mcp/coverage/latest LIVE query mcp_calls last 30d + tier classify {active<7d, warning 7-30d, orphan registered sem call, deprecated/quarantine/reserved registry override} + /api/mcp/coverage/publish stub 202 next_step F.5.5. hermes_api_v2.py middleware + bypass /api/mcp/* + include vm_api/mcp_coverage.py router (PC source-of-truth quando VM migrar hermes_api LEGACY pra v2). PIVOT arquitetural runtime VM: endpoints no gateway server.py mesmo (VM roda hermes_api.py LEGACY pré-MERGED-011, não v2 — concentra MCP-related no gateway, evita patch legacy massivo). HERMES_GATEWAY_OAUTH_SECRET token_urlsafe(32) persisted ~/.hermes/.env. Smoke 5/5 PASS VM: T1 missing_bearer 401 + T2 invalid_bearer 401 + T3 valid 200 summary{total_tools:52,active:2,orphan:19,reserved:31} + T4 /health bypass 200 + T5 publish 202.
- **F.5.3 reviewer agent verdict (mcp-integrator agentId ab413cb5e32da4da7)**: PASS-WITH-NOTES, zero BLOCKERS, 12/12 dims PASS, 4 WARNs F.future tracked:
    1. **WARN F.5.4 — duplicação _classify_tiers_realtime** gateway server.py + vm_api/mcp_coverage.py (~50 linhas idênticas line-by-line) — drift risk se um lado atualizar tier rules e outro não. F.5.4 extrair pra vm_core/mcp_tiering.py compartilhado.
    2. **WARN F.5.4 — _log_mcp_call db missing silent skip**: server.py linha 506-508 `if not db_path.exists(): return` sem logger.warning. Adicionar log rate-limited primeira ocorrência (não floodar).
    3. **WARN F.5.5 — coverage endpoint sem EXPLAIN QUERY PLAN**: hoje OK volume pequeno, F.6 Brain emitir 1000+ calls/dia precisará verificar idx_mcp_calls_server_tool_time usage. F.5.5 audit incluir EXPLAIN.
    4. **WARN F.6 — pool lock single global**: asyncio.Lock serializa TODAS acquires entre todos servers. Hoje 3 customs OK. F.6 Brain concorrente precisar per-server lock granular pra evitar wait spike.
- **F.5.3 PREP F.5.4**: validate_implementation.py phase F grep-audit + .claude/MCP-BANNED-PATTERNS.json declarativo + REQUIRED_PER_PHASE auto-derivado regex parse PLAN.md done_criteria seção "MCP HARD REQUIREMENTS (F.x)".

**🎯 F.5.4 Decisões Cristalizadas (validate phase F grep-audit + BANNED-PATTERNS + extract mcp_tiering)** — incorporado 2026-06-10:
- **D1 BANNED-PATTERNS.json schema**: **per-chapter scoped** `{"F.7":[{pattern, reason, severity, scope}], "F.6":[...], ...}` (granular, false-positive baixo, owner consegue ler diff por chapter). NÃO regex flat global (ruído cross-chapter, hard to maintain).
- **D2 REQUIRED_PER_PHASE auto-derive**: **regex parse PLAN.md done_criteria seção "MCP HARD REQUIREMENTS (F.x)"** + cross-check `.claude/mcp_registry_seed.json` `required_by_dc[]` campo. Single source of truth = PLAN.md (evita drift PLAN vs validate.py). NÃO YAML manual paralelo. Cache result em `.claude/_validate_required_cache.json` invalidado por hash PLAN.md mtime.
- **D3 Violation severity**: **3-tier BLOCKER + WARN + INFO** com flag `--max-severity {blocker,warn,info}` default `blocker` (CI), owner consegue `--max-severity info` local debug. BLOCKER = exit 1 commit fail. WARN = exit 0 stderr report. INFO = exit 0 stdout note. NÃO 2-tier (sem WARN owner perde signal early).
- **D4 Extract `vm_core/mcp_tiering.py` ANTES validate phase F**: validate phase F usa `mcp_tiering.classify_tier(server, tool)` pra detectar drift (registered tier vs runtime tier). Refactor PRIMEIRO evita duplicação (3a cópia em validate.py seria pior). Resolve WARN D7-bis F.5.3 reviewer. Files: gateway server.py + vm_api/mcp_coverage.py importam de vm_core/mcp_tiering.py (zero duplicate logic).
- **D5 Scope validate phase F**: **`mcps/* + brain/* + skills/* + api/agent_zero.py + hermes_api_v2.py + vm_api/*`** (entry points Brain + agent_zero + 2 shells API). NÃO codebase completo (lint world = noise). NÃO só `mcps/*` (perde Brain F.6 violations downstream). Owner adiciona path via `validate.py --scope-add <glob>` se F.future precisar.

**Files F.5.4** (4 NOVOS + 3 MATURE):
- `vm_core/mcp_tiering.py` NOVO — `classify_tier(server, tool, last_call_at, registry_tier) -> str` + `aggregate_by_tier(items) -> dict` (~80-120 linhas, single-source classify logic).
- `vm_core/__init__.py` NOVO (se não existir já).
- `.claude/MCP-BANNED-PATTERNS.json` NOVO — declarativo per-chapter scoped (15-25 patterns iniciais 3 customs F.5.2 wrappers como reference).
- `scripts/_validate_phase_f.py` NOVO — módulo phase F (separado pra não inchar validate_implementation.py).
- `scripts/validate_implementation.py` MATURE — adicionar `elif args.phase == "F": from _validate_phase_f import run_phase_f; sys.exit(run_phase_f(args))` (zero refactor das phases A-E existentes).
- `mcps/gateway/server.py` MATURE — substituir `_classify_tiers_realtime` inline por `from vm_core.mcp_tiering import classify_tier, aggregate_by_tier`.
- `vm_api/mcp_coverage.py` MATURE — idem (D4 dedupe). Source-of-truth shared PC, deploy VM mesmo arquivo.

**Patterns BANNED-PATTERNS.json iniciais** (F.5.4 seed, F.future expand):
```json
{
  "F.7": [
    {"pattern": "from linkedin\\.connector import", "reason": "F.7 deve usar mcp.hermes-linkedin.send_invite via gateway dispatch, não import direto", "severity": "BLOCKER", "scope": "brain/, api/agent_zero.py"},
    {"pattern": "from linkedin\\.limiter import", "reason": "F.7 deve usar mcp.hermes-linkedin.get_rate_limits", "severity": "BLOCKER", "scope": "brain/, api/agent_zero.py"},
    {"pattern": "from linkedin\\.account_profile import", "reason": "F.7 deve usar mcp.hermes-linkedin.get_account_profile via gateway", "severity": "WARN", "scope": "brain/"}
  ],
  "F.6": [
    {"pattern": "import sqlite3.*FROM prospects", "reason": "F.6 deve usar mcp.hermes-prospects.search_prospects via gateway (não SQL direto)", "severity": "BLOCKER", "scope": "brain/decide.py, brain/tools.py"},
    {"pattern": "open\\(.*skills/.*\\.yaml", "reason": "F.6 deve usar mcp.hermes-skills.list_skills via gateway", "severity": "WARN", "scope": "brain/"}
  ],
  "F.4": [
    {"pattern": "with open.*skill_proposals\\.yaml", "reason": "F.4 deve usar mcp.hermes-skills.propose_skill_yaml_stub via gateway", "severity": "BLOCKER", "scope": "skills/, api/agent_zero.py"}
  ]
}
```

**Sub-task split F.5.4** (3 commits sub-session):
- **Commit 1 (D4 refactor)**: extrair vm_core/mcp_tiering.py + dedupe gateway server.py + vm_api/mcp_coverage.py. Validate phase A-E preservado.
- **Commit 2 (BANNED-PATTERNS + auto-derive)**: .claude/MCP-BANNED-PATTERNS.json seed 15-25 patterns + scripts/_validate_phase_f.py com parse PLAN.md regex auto-derive REQUIRED_PER_PHASE + cache invalidation.
- **Commit 3 (wire + smoke + reviewer + docs)**: validate_implementation.py wire phase F + smoke 6 cases (BLOCKER hit / WARN hit / INFO hit / clean / cache hit / cache invalidation) + deploy VM + code-reviewer + PLAN.md docs.

**🚨 Riscos F.5.4**:
- **False-positive BLOCKER frustra dev** = scope strict (D5) + patterns surgical (D1 per-chapter) mitiga
- **False-negative deixa regressão real** = smoke 6 cases obrigatório + reviewer specific dim "patterns catch realistic violations" 
- **Drift PLAN.md vs validate.py** = D2 auto-derive resolve (cache invalidation por mtime hash)
- **vm_core extract quebra gateway runtime** = D4 sub-task split commit 1 isolado, validate A-E gate antes prosseguir
- **BANNED scope amplo regex** = D5 scope explícito field obrigatório, validate.py recusa pattern sem scope

**Cross-ref F.5.4**: `.claude/MCP-ENFORCEMENT-STRATEGY.md` section 5.3 (S1 hard requirement done_criteria checks) + F.5.3 reviewer WARN #1 (D7-bis duplicação classify resolve) + F.5.3 mcp_registry_seed.json (required_by_dc[] cross-ref).
- [x] Task 3: Integrar 5 MCPs públicos prioritários via gateway (GitHub+Sentry+Postgres+Playwright+Omnisearch) — F.5.6 ✅ DONE (Hunter+Firecrawl deferred F.future per D1+D5 cristalizados)
+- [x] Task 4: Decisão WhatsApp+Firecrawl — DEFERRED F.future explicit (D1+D5 cristalizados — F.5.6 closeout não bloqueado)
+- [x] Task 5: UI `/mcp/gateway` minimal — F.5.6f ✅ DONE (read-only D3, status gateway + 4 sections + frontend-ux-reviewer PASS-WITH-NOTES zero BLOCKERS)
+- [x] Task 6: Validação regressão + persistência — F.5.6 ✅ DONE (phase A-E 20/22 PASS preservado em todos 7 commits; PLAN.md F.5 ✅; memory_save + mark_chapter; 7 commits feat/docs)
+
+**Done criteria F.5**: Brain F.6 chama 1 endpoint gateway, recebe 30+ tools agregadas · auth+rate-limit+audit centralizado · 3 MCPs custom respondem com OAuth 2.1 · 20/22 PASS preservado.
+
+**🧰 MCP HARD REQUIREMENTS (F.5)** — incorporado via PLAN-MCP-ENFORCEMENT-PATCH 2026-06-10:
+- **Task 5b NOVA**: seed `mcp_registry` idempotente 9-12 rows com `chapter_owner` + `required_by_dc[]` (ContextForge=infra, GitHub=F.4, Sentry=F.4+F.7, Postgres MCP Pro=F.6+F.7, Playwright=F.3, Omnisearch=F.7, Hunter=F.7, WhatsApp=F.7, hermes-linkedin=F.7+F.9, hermes-prospects=F.7+F.9, hermes-skills=F.4+F.9)
+- **Task 5c NOVA**: editar PLAN.md done_criteria F.4/F.6/F.7/F.8/F.9 com cláusulas MCP HARD REQUIREMENTS literais ✅ DONE (este commit) + implementar `scripts/validate_implementation.py phase F` (grep banned patterns + coverage assertion auto-derivada regex parse PLAN.md, NÃO hardcoded) + criar `.claude/MCP-BANNED-PATTERNS.json` declarativo
+- **Task 7 NOVA**: deploy `scripts/mcp_coverage_audit.py` + cron scheduled-tasks MCP `0 9 15 * *` (dia 15 09h BRT evita janela cobaia semana 1) + endpoints `GET /api/mcp/coverage/latest` + `POST /api/mcp/coverage/publish` + endpoint `GET /api/mcp/gateway/tools` (consumido F.8 + F.9)
+- Runtime startup gate `hermes_api_v2.py` lifespan: `STRICT_MODE default=False`, ativa apenas `HERMES_STRICT_MCP=1` (VM prod) — dev local não trava
+- Audit mensal gera `.claude/audits/mcp-coverage/MCP-COVERAGE-{YYYY-MM}.md` versionado git com tier classification
+- F.5 sessions impact: base 4 → **6 reais** (+2 Tasks 5b/5c/7 NOVAS)
+
+**Cross-ref**: `.claude/MCP-ENFORCEMENT-STRATEGY.md` (documento canônico, 10 sections) + `.claude/PLAN-MCP-ENFORCEMENT-PATCH.md` (patches) + GUARDRAILS § "🧰 MCP usage coverage" + memory mem_mq7jalw7.
+
+**🎯 F.5.2 Decisões Cristalizadas (3 custom MCPs scaffold)** — incorporado 2026-06-10:
+- **D1 Tools granularidade**: cada custom MCP expõe **6-8 tools médio** (granular suficiente Brain F.6 compor, sem fragmentar 15+ tools/MCP)
+- **D2 Imports strategy**: **direct imports** `from linkedin.connector import ...` dentro mcps/hermes-linkedin/server.py (gateway VM-side, evita HTTP overhead, simpler). NÃO proxy via VM API endpoint.
+- **D3 hermes-prospects scoring**: **delega Postgres MCP Pro** (`mcp.postgres.query` read-only) via gateway — single source of truth. Brain F.6 mesma rota.
+- **D4 hermes-skills storage**: **hybrid** — YAML reads agora (skills/*.yaml glob), DB writes deferred F.4 skill_proposals table (Brain F.6 propõe via DB, owner aprova → sync YAML).
+- **D5 OAuth 2.1 JWT rotação**: **manual mensal** (3 MCPs solo owner, auto cron é over-engineering F.future). Secret em .env `HERMES_GATEWAY_OAUTH_SECRET`.
+- **D6 Reviewer agent**: **code-reviewer direto** (sem custom subagent F.future). frontend-ux-reviewer não aplica (zero touch dashboard/* F.5.2).
+- **D7 Smoke E2E**: **isolado per MCP** (3 smoke tests separados) + integration test Brain dispatch **deferred F.6** (Brain ainda não existe).
+- **D8 Tools naming**: **simple `send_invite` (sem prefix)** — gateway já namespaces via server prefix (`hermes-linkedin.send_invite` no full path).
+
+**Files F.5.2** (3 NOVOS custom MCPs + gateway upstream config update):
+- `mcps/hermes-linkedin/{__init__,server,README}.py/md` — wrap stealth+human+limiter+cooldown como 6-8 tools (send_invite, scrape_profile, get_inbox, warmup_action, send_message, send_inmail, get_health, get_rate_limits)
+- `mcps/hermes-prospects/{__init__,server,README}.py/md` — wrap DB queries + scoring (search_prospects, score_lead, mark_converted, get_campaign_stats, enrich_pipeline, list_top_scored, get_by_status) — delega Postgres MCP Pro pra reads
+- `mcps/hermes-skills/{__init__,server,README}.py/md` — wrap skills/*.yaml management (list_skills, get_skill, toggle_active, propose_skill_yaml_stub, test_skill_dryrun, get_metrics) — hybrid YAML+DB
+- `mcps/gateway/config.yaml` MATURE update — 3 upstream MCPs status=active (era pending F.5.1)
+- `.mcp.json` MATURE update — 3 entries adicionados (hermes-linkedin/prospects/skills VM loopback)
+
+**🚨 BLACKLIST CRÍTICO F.5.2**: NÃO MODIFICAR linkedin/{stealth,human,limiter,cooldown,preflight,account_profile,config}.py — APENAS importar e wrap. hermes-linkedin é WRAPPER, NÃO refactor. Qualquer touch BLACKLIST R2 = REVERT IMEDIATO.
+
+**F.5.2 STATUS COMPLETE 2026-06-10 (commits 2c9578a + c84b11e + 9ff2d71 + SHA-final)**:
+- 4 commits push master: hermes-linkedin (8 tools wrap stealth) + hermes-prospects (7 tools D3 scoring local + Postgres delegate) + hermes-skills (6 tools YAML mgmt D4 hybrid) + gateway config wire-up + reviewer + docs
+- VM gateway PID rotação: 3113463 (F.5.1) → 3589929 (F.5.2 restart) — /upstream: 3/3 active
+- BLACKLIST R2 INVIOLAVEL: zero touch linkedin/* verified `git diff HEAD~4 --name-only linkedin/` ZERO matches
+- Smoke isolado per MCP: hermes-linkedin (8 tools + sanitize 7 cases + .strip defense + uppercase + nested list) + hermes-prospects (7 tools + score_lead deterministic full=100/sparse=45) + hermes-skills (6 tools + path traversal 7 bad/1 good + list_skills count=6 + propose stub 11 keys) ALL PASS local
+- code-reviewer agent verdict: PASS-WITH-NOTES, zero BLOCKERS, 8 WARNs/NOTES F.future tracked abaixo
+- validate phases A B C D E 20/22 PASS preservado em TODOS commits F.5.2 (E.2/E.3 stubs intentional WhatsApp/Instagram)
+- F.5.3 PREP: gateway dispatch real fastmcp.Client substitui placeholder 503 + seed mcp_registry table 11 rows (com chapter_owner + required_by_dc[] cristalizadas MCP-ENFORCEMENT-STRATEGY § 5.2)
+
+**🎯 F.5.3 Decisões Cristalizadas (gateway dispatch real + seed mcp_registry + endpoints)** — incorporado 2026-06-10:
+- **D1 fastmcp.Client transport**: **stdio subprocess** (FastMCP 3.0 default, sem porta gerenciar, isolation per spawn). NÃO http loopback :55402+ (overhead porta gerenciar 3 custom MCPs).
+- **D2 Connection caching**: **pool connection per upstream server** (3 customs reusable cache em-memória process gateway). Evita overhead spawn 100-300ms/call. Pool com TTL 5min + auto-respawn on disconnect. NÃO spawn per request (latency proibitivo Brain F.6).
+- **D3 mcp_registry seed format**: **JSON file `.claude/mcp_registry_seed.json` + INSERT idempotente** (ON CONFLICT chapter_owner UPDATE). 11 rows (3 customs + 5 públicos previstos + 3 reserved). Versionável git, fácil owner editar. NÃO INSERT static Python literal (não versionável).
+- **D4 Endpoint `/api/mcp/coverage/latest`**: **live query mcp_calls table** (count by server/tool last 30d + tier classification em-tempo-real). F.5.5 entrega audit cron mensal separado (`mcp_coverage_audit.py` → MCP-COVERAGE-{YYYY-MM}.md persisted). Latest = mês corrente live (não snapshot). NÃO pull from S3 ou file cache (stale data).
+- **D5 OAuth Bearer check**: **middleware FastAPI** `@app.middleware("http")` aplica a TODOS endpoints `/api/mcp/*` + gateway endpoints. Allowlist bypass: `/health`, `/docs`, `/openapi.json`. DRY (F.5.3+ 4-5 endpoints). NÃO per-endpoint decorator repetitivo.
+
+**Files F.5.3** (4 NOVOS + 4 MATURE):
+- `mcps/gateway/server.py` MATURE — substituir `dispatch_placeholder` 503 por `_dispatch_real(server, tool, args)` usando `fastmcp.Client(transport="stdio", command=...)`. Pool cache global `_CLIENT_POOL: dict[str, Client]` TTL 5min.
+- `mcps/gateway/_pool.py` NOVO — `MCPClientPool` class (acquire/release/health_check/auto_respawn).
+- `.claude/mcp_registry_seed.json` NOVO — 11 rows source-of-truth (3 customs + 5 públicos F.5.6 + 3 reserved postgres/filesystem/git).
+- `scripts/seed_mcp_registry.py` NOVO — INSERT idempotente ON CONFLICT. Idempotente rerun.
+- `migrations/00X_mcp_registry.sql` NOVO — CREATE TABLE mcp_registry (server TEXT PK, tools TEXT[], status TEXT, chapter_owner TEXT, required_by_dc TEXT[], tier TEXT, oauth_required BOOL, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ).
+- `migrations/00Y_mcp_calls.sql` NOVO — CREATE TABLE mcp_calls (id UUID PK, server TEXT, tool TEXT, args JSONB, response JSONB, error TEXT NULL, duration_ms INT, requester TEXT, created_at TIMESTAMPTZ). Index on (server, tool, created_at DESC).
+- `hermes_api_v2.py` MATURE — adicionar middleware OAuth Bearer + 2 endpoints: `GET /api/mcp/coverage/latest` (live query mcp_calls) + `POST /api/mcp/coverage/publish` (manual trigger F.5.5 audit).
+- `mcps/gateway/config.yaml` MATURE — adicionar pool config (`pool_ttl_seconds: 300`, `pool_max_idle: 10`).
+
+**Sub-task split F.5.3** (3 commits sub-session):
+- **Commit 1 (migrations + seed)**: mcp_registry + mcp_calls tables + seed JSON + script idempotente. Validate phase E preserves stubs.
+- **Commit 2 (dispatch real + pool)**: gateway dispatch fastmcp.Client real + MCPClientPool + test smoke 3 customs dispatch. Substitui 503 placeholder.
+- **Commit 3 (endpoints + middleware + deploy + reviewer + docs)**: hermes_api_v2 middleware + 2 endpoints + deploy VM + code-reviewer + PLAN.md docs.
+
+**🚨 Riscos críticos F.5.3** (sessão "switching fabric"):
+- **Quebrar dispatch real** = todos MCP calls 503 downstream Brain F.6/F.7/F.4 paralisados
+- **Pool connection leak** = process gateway VM crash OOM após dias (TTL + max_idle obrigatórios)
+- **mcp_registry seed race** = INSERT não-idempotente duplica rows ao re-rodar (ON CONFLICT obrigatório)
+- **OAuth middleware bypass leak** = endpoint sensível exposto (allowlist deve ser allow-list strict, não regex amplo)
+
+**Cross-ref F.5.3**: `.claude/MCP-ENFORCEMENT-STRATEGY.md` section 4 (S2 mcp_calls table) + section 5.2 (mcp_registry seed schema) + F.5.2 commits (8 reviewer WARNs, especialmente WARN #1 dispatch placeholder).
+
+**F.5.2 reviewer notes (PASS-WITH-NOTES, code-reviewer agentId a4d6ce115ff6d81ba)** — 8 follow-ups F.future tracked:
+    1. **WARN F.5.3 — gateway dispatch ainda 503 placeholder**: mcps/gateway/server.py dispatch_placeholder retorna HTTPException(503) mesmo pros 3 upstreams agora `active`. Config diz "active", runtime diz "not yet wired". F.5.3/F.5.4 deve implementar fastmcp.Client dispatch real OU clarificar comentário que `active` = spawn-ready.
+    2. **WARN F.future — sticky_session_id exposure**: assert_account_safe retorna sticky_session_id raw. Deterministic hash (não credencial direta) mas cross-ref identifier. Considerar mask ou retornar apenas boolean.
+    3. **WARN F.future — hermes-prospects sanitize coverage menor**: 11 keys vs 17 hermes-linkedin. Se prospects.notes/outreach_message acumular sensível, expandir SENSITIVE_KEYS OU unificar mcps/_shared/sanitize.py.
+    4. **WARN F.future — start_campaign é stub control plane**: Não dispatcha campanha real, só echo + next_step pointing hermes_api_v2. Tool name sugere ação. Considerar renomear plan_campaign ou preview_campaign_dispatch F.5.3+.
+    5. **NOTE — propose_skill_yaml_stub system_prompt placeholder**: Texto literal "TODO owner review...". F.4 substitui com LLM-gerado rico.
+    6. **NOTE — _smoke.py introspection fragility hermes-linkedin**: callable(getattr(server, name, None)) fallback funciona com stub mas pode dar falsos positivos se módulo importar função homônima. F.5.4 com fastmcp real, usar mcp_obj._tool_manager.list_tools() padronizada.
+    7. **NOTE — .mcp.example.json prefix `_` documentation**: Elegante pra entries documentados sem habilitar PC accidentally. Garantir docs F.5.3 mencione remover prefix antes habilitar local dev.
+    8. **NOTE — is_within_working_hours() return tuple shape**: get_rate_limits assume tuple shape estável. Se BLACKLIST R2 limiter.py mudar API F.future, wrapper quebra silent (smoke não cobre). Adicionar try/except defensivo OU contract test gateway-side F.5.4.
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
+**🧰 MCP HARD REQUIREMENTS (F.6)** — incorporado 2026-06-10:
+- `core/tools.py ToolRegistry.invoke()` wrap middleware **FAIL-CLOSED** INSERT `mcp_calls(server, tool, args_hash, latency_ms, error, context_id, turn_idx, caller_chapter)` try/except próprio — se INSERT falhar: `log.critical + sentry_sdk.capture_exception` MAS NÃO propaga erro caller (audit não pode quebrar Brain decisão)
+- Decorator `@instrumented` OBRIGATÓRIO em todo dispatch emite OTel GenAI spans (`gen_ai.tool.execute, gen_ai.tool.name, mcp.server.name`) — assert via integration test obrigatório
+- Schema `brain_decisions` ganha coluna `otel_trace_id` cross-ref `mcp_calls.context_id+turn_idx`
+- `Brain.decide()` schema output validado pydantic ANTES dispatch: `{intent, tool_name, args, confidence}`
+- Confidence floor configurável PrefPanel + DB `pref_keys` (default 0.7) — `< threshold skip auto-execute → enfileira owner_confirm`
+- Postgres MCP read-only via `mcp.postgres.query` (**PROIBIDO** `sqlite3.connect` bare)
+- Phase F validator pass: ZERO bypass `core/` (`sentry_sdk import, subprocess gh, requests api.*`)
+- F.6 sessions impact: zero overhead (middleware é fixture natural)

**🎯 F.6 Decisões Cristalizadas (Brain orchestrator) — incorporado 2026-06-12**:

Auditoria pós-F.5.7 (gateway 9 MCPs LIVE + hermes-llm 3-tier fabric funcional + mcp_calls extension 5 columns aplicada). F.6 consome routing matrix via mcp.hermes-llm.route() — NÃO chama NIM/Ollama direto. Owner Caio aprovou approach Caminho A (cristalizar F.6 + prompt entregue sub-sessão).

**D1 Framework Brain implementation**: **Plain Python asyncio + transitions FSM lib lightweight** (~100 LOC core state machine). NÃO LangGraph (heavy deps, owner solo no-code preference). NÃO OpenAI Agents SDK (proprietary). NÃO CrewAI (multi-agent overkill). Transitions lib é mature, deterministic, debuggable, sem heavy deps. Padrão ReAct (think→observe→act loop) implementado em asyncio nativo.

**D2 State machine = 6 states** (canonical Anthropic Think→Act→Observe): `IDLE → CLASSIFY → REASON → ACT → REVIEW → COMMIT → IDLE`. NÃO 8 states (REASONING/ROUTING separados over-engineering F.6 inicial). NÃO 4 states minimal (REVIEW + COMMIT precisam separação safety gates). Expand F.future se Brain.decide() complexity crescer.

**D3 Intents core inicial = 6** (5 essenciais + 1 utility):
1. `answer_owner` (chat dashboard owner-facing)
2. `send_outreach` (F.7 cobaia LinkedIn message gen + dispatch hermes-linkedin.send_invite)
3. `synth_skill` (F.4 auto-skill generation via mcp.hermes-skills.propose_skill_yaml_stub)
4. `classify_prospect` (F.7 ICP scoring via hermes-llm.route task_type=classify)
5. `summarize_conversation` (F.6 chat memory long-context summarization)
6. `route_skill_run` (utility: executor pure Python sem LLM, gateway dispatch direct, low-latency)

Expand F.future: `analyze_competitor`, `generate_report`, `triage_inbox` (F.7+ orgânico).

**D4 Memory consolidation cadence**: **per-run** (cada Brain.decide() invocation persiste 1 row `brain_runs` + N rows `brain_decisions` per state transition). NÃO daily cron (perde granularidade per-call). NÃO threshold-based (complica F.6 inicial). Per-run simple + deterministic + cheap (SQLite INSERT ms-scale). F.future agregação cron mensal pra `brain_audit_2026-06.md` similar F.5.5 pattern.

**D5 Owner confirm UX** (confidence < 0.5 OR action_class="destructive"): **dashboard modal síncrono** (bloqueia Brain.decide() até owner clica approve/deny). NÃO Telegram alert (F.future F.7 cobaia live, F.6 owner usually no PC dashboard already open). NÃO both (over-engineering F.6 inicial). Dashboard modal endpoint `POST /api/brain/confirm/{run_id}` → owner aprova → Brain retoma state COMMIT.

**D6 Brain default model T1 reasoning**: **routing matrix decide automaticamente** via `mcp.hermes-llm.route(task_type="reasoning")`. T1 = `nvidia/mistral-nemotron` (NIM declara "best function calling at any price"). T2 fallback = `nvidia/llama-3.3-nemotron-super-49b-v1` (PT-BR oficial + reasoning). Brain code NÃO hardcode model_id — só `task_type` (routing matrix é ground truth).

**D7 Decision replay UI dashboard tab**: **F.future** (NÃO F.6 inicial). Replay UI tab vira F.future quando F.8 cost observability dashboard implementar. F.6 entrega CLI/API replay only (`POST /api/brain/replay/{run_id}` retorna sequence + tool calls + final result). UI tab cross-ref F.8.

**D8 Safety gates destructive action threshold**: **hybrid** — `confidence < 0.5` OR `action_class IN ("destructive", "send_outreach", "synth_skill_promote")` → owner confirm OBRIGATÓRIO via dashboard modal D5. NÃO single threshold 0.7 (envia LinkedIn high-confidence sem owner check = risco cobaia). NÃO always confirm (over-prompts owner UX ruim). Lista `DESTRUCTIVE_ACTIONS = {"send_outreach", "send_message", "send_inmail", "synth_skill_promote", "deploy_skill_pr"}` hardcoded `brain/safety.py`.

**D9 Brain.decide() API**: **async FastAPI endpoint** `POST /api/brain/decide` body `{intent, context}` returns `{run_id, status, result, latency_ms, total_cost_credits, requires_confirm: bool}` OR HTTP 202 + poll endpoint se `total_latency > 30s` (long-running). Status check via `GET /api/brain/runs/{run_id}` (pattern F.5.5 `mcp/coverage/jobs/{id}` familiar).

**D10 Sub-task split F.6 = 6 sub-sessions**:
- **F.6.1**: Brain scaffold + state machine + 6 intents stubs + transitions FSM (NÃO toca LLM ainda, smoke deterministic golden cases skeleton)
- **F.6.2**: Tool calling integration mcp.hermes-llm.route() + outros MCPs (hermes-prospects/skills/linkedin via gateway dispatch) — primeiro real LLM call F.6
- **F.6.3**: Memory consolidation (brain_runs + brain_decisions persistence + agentmemory MCP integration short-term/long-term)
- **F.6.4**: Safety gates + owner confirm UX dashboard modal + endpoint POST /api/brain/confirm/{run_id}
- **F.6.5**: Golden cases test suite + hermes-brain-test skill update F.6 real (existing skill .claude/ ganha bateria 6 dimensões deterministic)
- **F.6.6**: F.6 closeout + reviewer + Task #6 [completed]

Estimativa total F.6: 6 sub-sessions × 3-5h cada = 20-30h spread over 1 semana. Cada sub-sessão entrega 2-4 commits. **Owner Claude per sub-sessão = Opus 4.7 recomendado** (Brain decisão arquitetural NOVEL, alto risco).

**Files F.6.1** (NOVO scaffold, ~600-800 LOC):
- `brain/__init__.py` (NOVO empty)
- `brain/decide.py` (~250 LOC Brain class + state machine + 6 intents dispatch stubs)
- `brain/states.py` (~80 LOC 6 states enum + transitions FSM definition usando `transitions` lib)
- `brain/intents.py` (~120 LOC 6 intents handlers stubs — retornam mock data F.6.1, real LLM call F.6.2)
- `brain/safety.py` (~50 LOC DESTRUCTIVE_ACTIONS set + classify_action + confidence threshold check)
- `brain/replay.py` (~80 LOC replay logic stub — F.6.3 implementa real, F.6.1 só skeleton)
- `brain/_smoke.py` (~100 LOC isolated smoke 6 intents PASS deterministic mock)
- `api/brain.py` NOVO (~80 LOC FastAPI endpoint POST /api/brain/decide stub)
- `migrations/2026_06_<próximo>_brain_runs_decisions.sql` NOVO (CREATE brain_runs + brain_decisions tables)
- `requirements.txt` MATURE: adicionar `transitions>=0.9.0` (state machine lib)
- `server.py` MATURE: `app.include_router(api.brain.router)` wire-up
- `hermes_api_v2.py` MATURE: idem (PC source-of-truth quando VM migrar)

**Sub-task split F.6.1** (2 commits):
- **C1 scaffold core**: brain/ NOVO 7 files + transitions lib install + migration .sql + smoke 6 intents PASS mock
- **C2 wire FastAPI endpoint + reviewer + docs**: api/brain.py + server.py include + PLAN.md F.6.1 [✅] + code-reviewer + memory_save + mark_chapter

**🚨 Riscos críticos F.6 (full chapter)**:
- **Brain NOVEL design** — sem pattern reference (F.5.x customs são wrappers, F.6 é orchestrator) → cada sub-sessão risco alto, Opus 4.7 recomendado
- **Cost escalation** — Anthropic confirma agents ~4x tokens chat normal, 15x multi-agent. F.6 Brain.decide() pode consumir 5-10k tokens/run rapidamente. mcp_calls cost_credits tracking F.5.7 cobre — owner monitora dashboard F.8 futura.
- **State machine transitions bugs latentes** — F.6.1 smoke deterministic golden cases obrigatório (não live LLM)
- **Safety gates bypass risk** — DESTRUCTIVE_ACTIONS hardcoded F.6.1, expand F.7 cobaia ANTES first live send_outreach
- **BLACKLIST R2 INTACTO** — Brain NÃO chama `linkedin/*` direto (mesmo coexistência ollama_router pattern). Sempre via `mcp.hermes-linkedin.*` gateway dispatch.
- **Decision replay determinism** — F.6.3 implementa real replay. F.6.1 stub returns "not implemented" pra evitar incorrect expectations.
- **Anthropic Extended Thinking mode** — não usado F.6 (NIM models may not support same way). F.future se Anthropic SDK adicionado.
- **Memory consolidation cross-session** — agentmemory MCP integration F.6.3. F.6.1 brain_runs/decisions só local DB.

**Cross-ref F.6**:
- `.claude/NVIDIA-MODELS-ROUTING-MATRIX.md` Task 1+2+7 (Brain reasoning + classifier + summarize)
- `mcps/hermes-llm/server.py` (F.5.7 — Brain consume via gateway)
- `mcps/hermes-prospects/server.py` (D3 cristalizado — prospects queries via mcp.postgres.query delegate)
- `.claude/skills/hermes-brain-test/` (existing skill, F.6.5 update real)
- `mem_mqa6qoq0` (F.5.7 routing matrix + decisions)
- WebSearch refs:
  - [stevekinney agent loops anatomy](https://stevekinney.com/writing/agent-loops)
  - [Anthropic writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
  - [datasciencedojo agentic loops ReAct 2026](https://datasciencedojo.com/blog/agentic-loops-explained-from-react-to-loop-engineering-2026-guide/)
  - [brics-econ state diagrams orchestrators LLM](https://brics-econ.org/state-diagrams-and-orchestrators-for-complex-llm-agent-pipelines)
+
+**Cross-ref**: `.claude/MCP-ENFORCEMENT-STRATEGY.md` section 4 (S2 details) + memory mem_mq7jalw7.
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
+**🧰 MCP HARD REQUIREMENTS (F.7)** — incorporado 2026-06-10:
+- Task 6 Hunter.io: `mcp.hunter.verify_email` via gateway ANTES warmup email (**PROIBIDO** `requests.get api.hunter.io`)
+- **Task 6b NOVA Omnisearch**: `mcp.omnisearch.search` discovery PMEs Cuiabá
+- **Task 6c NOVA Plan B Hunter** documentado GUARDRAILS.md ANTES Task 6 virar hard: cache 30d verificações + degrade gracioso skip warmup se quota free 25/mês saturou OU rate-limit prospects 5/dia (=150/mês)
+- Task 7 Sentry: `mcp.sentry.capture_exception` via gateway (NÃO `sentry-sdk` direto)
+- **Task 9 NOVA Postgres MCP Pro**: `cobaia_metrics_collector.py` via `mcp.postgres.query` read-only (**PROIBIDO** `sqlite3.connect` bare)
+- Daemon F.7 dispara LinkedIn via `mcp.hermes-linkedin.*` (**NÃO** patchright direto)
+- `mcp_coverage.calls_7d > 0` para: `hunter + sentry + omnisearch + postgres + hermes-linkedin`
+- Phase F grep-audit pass (`errors_inbox category='mcp_bypass' count = 0`)
+- Widget cobaia-status mostra link latest `MCP-COVERAGE-{YYYY-MM}.md`
+- Hunter quota MTD < 22/25 sustentado 6 meses (gate Plan B fallback)
+
+**Cross-ref**: `.claude/MCP-ENFORCEMENT-STRATEGY.md` section 5 F.7 + `.claude/F7-SCHEDULE-ARCH-DECISION.md` (APScheduler Tasks 2/3/4).
+
+### ✅ Schedule Infrastructure — Decisão Final (workflow f7-schedule-arch-analysis 2026-06-10, commit a0d3eb0)
+
+**📖 DOCUMENTO CANÔNICO**: `.claude/F7-SCHEDULE-ARCH-DECISION.md` (30k chars, 13 sections — owner Claude da sessão F.7 DEVE ler ANTES de qualquer task)
+
+**Primary**: **B) APScheduler in-process daemon** (`AsyncIOScheduler` embedded em `daemon/orchestrator.py` + `hermes_api_v2.py` lifespan). 3 tasks F.7 (métricas 1h, stop gates 30min, Telegram 19h) compartilham state com daemon (warmup_state cache, `linkedin/limiter.acceptance_cooldown` PATCH-014 singleton, cobaia_daily_metrics) e in-process elimina IPC/HTTP bridge. `CronTrigger(timezone=ZoneInfo('America/Cuiaba'))` resolve constraint "NUNCA `asyncio.sleep` até 19h DST-fragile" em 1 linha. Observability `add_listener(EVENT_JOB_ERROR|EXECUTED|MISSED)` integra F.5 Sentry + F.8 Cost&Perf grátis. Zero infra nova (aproveita `hermes-daemon.service` systemd unit existente), única dep ~600KB tolerável (13→14 deps).
+
+**Fallback**: **D-híbrido** asyncio loop check 60s inline daemon (Tasks 2+3a) + systemd --user timer VM (Task 4 Telegram 19h `OnCalendar='19:00:00' Persistent=true`) — acionado se APScheduler 3.x mostrar bug crítico durante F.7 (conflito event loop com loops MERGED-015 spawn, tzdata Windows flake, EVENT_JOB_MISSED race). Custo: +1 sessão F.7 reescrever 3 callables + perde observability nativa.
+
+**Long-term migration**: B → migração futura F.future pra APScheduler 4.x quando estável (post-2026) OU Temporal.io se Hermes escalar multi-tenant (10+ schedulers concurrent). Migração 3.11→4.x é mecânica. Solo owner F.7→F.9 não precisa Temporal.
+
+**Dependencies novas** (adicionar requirements.txt ANTES F.7):
+- `apscheduler>=3.11.0,<4.0` (pin explícito anti 4.0aX alpha)
+- `tzdata>=2024.1` (Windows tz fallback robusto)
+
+**F.7 sessions impact**: base 5 → **6 sessões reais** (+1 sessão dedicada `core/scheduler.py` singleton + wire-up `HermesDaemon.start/shutdown` + endpoints `/api/scheduler/jobs`).
+
+**F.7 Tasks 2/3/4 implementation**: ver `.claude/F7-SCHEDULE-ARCH-DECISION.md` sections 5-6 (pseudo-code completo copy-paste-adapt + migration checklist 12 steps).
+
+**Success criteria**: ver `.claude/F7-SCHEDULE-ARCH-DECISION.md` section 10 (8 critérios mensuráveis — smoke prod 3 jobs registered, 24h métricas streak, gate trigger <30min, Telegram 7d streak, regression 20/22 PASS preservada, daemon heartbeat <60s, fail-closed verificado, Sentry capture verified).
+
+**Rollback plan**: ver `.claude/F7-SCHEDULE-ARCH-DECISION.md` section 11 (procedimento 15-30min preservando warmup state cobaia 14d intacto — remove_job runtime + git revert seletivo + migrate fallback D-híbrido +1 sessão).
+
+**Rank 8 alternativas avaliadas** (lower score = melhor; ≥3/4 lenses valid = accepted):
+1. 🥇 **B APScheduler in-process daemon** (score 16) ✅ accepted
+2. 🥈 G systemd --user timers VM (18) ✅ accepted
+3. 🥉 A Linux crontab VM F.3.4 pattern (21) ❌ rejected (2/4)
+4. H Daemon main loop time-check (22) ❌
+5. D asyncio.create_task + sleep loop (23) ❌
+6. F MCP scheduled-tasks server (24) ❌
+7. C FastAPI BackgroundTasks (28) ❌
+8. E Celery + Redis (32, overkill confirmado) ❌
+
+**Guardrails adicionados** (incorporados GUARDRAILS.md § F.7 + HOW-TO-START-PHASE.md F.7):
+- NUNCA upgradar `apscheduler` para 4.0aX em produção (pin `<4.0` em requirements.txt)
+- Callables NUNCA instanciam `AccountProfile.load()` ou `Settings()` nova — reusar `self.account_profile`/`self.settings` do daemon (anti state drift)
+- Inline `_check_stop_gates()` no P1-P7 loop body PRESERVADO — APScheduler 30min é double-check fallback, NÃO substitui inline
+
+**Cross-refs**: F.3.4 discovery commit c3c24d3 + memory mem_mq7eyrio + mem_mq7fh8qa + mem_mq7g4rw5 + workflow `.claude/workflows/f7-schedule-arch-analysis.js` (48 agents, 2.47M tokens, 13min execução).
+
+**⚠️ ANTES de iniciar F.7 sessão dedicada — OWNER ACTION OBRIGATÓRIO**:
+1. Read `.claude/F7-SCHEDULE-ARCH-DECISION.md` completo (~15 min leitura)
+2. Marcar Approval Checklist (section 13 do DECISION.md) — 4 itens
+3. Confirm `requirements.txt` tem `apscheduler>=3.11.0,<4.0` + `tzdata>=2024.1` (Primary B requer)
+4. Use Tasks 2/3/4 implementation plan section 5 do DECISION.md como base canônica — NÃO improvisar callables
+5. Pre-deploy gate: `bash scripts/validate_implementation.py phases A B C D E` 20/22 PASS preservado; se cair <20 ROLLBACK + migrate fallback D-híbrido
+6. Canary 2h prod pós-deploy: `ssh hermes-gcp 'journalctl --user -fu hermes-daemon -n 100 | grep -E "(scheduler|cobaia)"'` — abort se ERROR no listener nas primeiras 2h
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
+**🧰 MCP HARD REQUIREMENTS (F.8)** — incorporado 2026-06-10:
+- Schema migration: tabelas `mcp_registry` + `mcp_calls` + mat view `mcp_coverage` (refresh 5min) + `PARTITION BY RANGE(called_at)` mensal + retention 90d auto-drop (pg_partman)
+- Cron 6h `detect_zombies` AUTO-flagga `deprecated_at` (NUNCA remove — npm deprecate pattern)
+- Endpoints: `GET /api/observability/mcp-coverage` · `GET /api/observability/mcp-coverage/history?months=6` · `GET /api/observability/mcp-coverage/audits` · `POST /api/mcp/registry/unflag`
+- **Task 5d NOVA TabMcpCoverage** 5ª tab observability shell: SummaryRow 5 cards (TotalMCPs/Active/Drift/Quarantine/PaidIdle$) + MatrixCoveragePanel heatmap Phase × MCP (verde/vermelho/cinza) + MCP List Table sortable/filterable + SparklineHistory 6 meses tier transitions. Reusa Chart.js vendor local + SummaryWidget pattern + TabCosts grid
+- Estender WS `obs.*` namespace: `obs.mcp_coverage_gap` event (startup gate detecta MCPs faltando OU phase F bloqueia commit)
+- Phase F violations gravar `errors_inbox category='mcp_bypass'` (reusa `ErrorInboxHandler` cross-tab Errors)
+- SummaryWidget badge `mcp_required_missing`
+- Sentry alert WEEKLY DIGEST (NÃO 1 capture por MCP — reduz noise)
+- Done criteria add: "painel MCP coverage por chapter · audit mensal histórico navegável · drift count > 3 = Sentry warning · ZERO write bypass detectado phase F últimos 30d"
+
+**Cross-ref**: `.claude/MCP-ENFORCEMENT-STRATEGY.md` section 7 dashboard widget spec.
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
+**🧰 MCP HARD REQUIREMENTS (F.9)** — incorporado 2026-06-10:
+- **Task 1b NOVA**: tool registry SOURCE = F.5 gateway audit-log `GET /api/mcp/gateway/tools` (**NÃO** scan local `skills/` dir)
+- Step library JOIN `mcp_registry` exibir MCPs como steps com badge `chapter_owner + last_used + tier` (badge "idle 60d+" WARN — NÃO bloqueia, industry passive flag)
+- Substituir critério numérico ≥6 hard por métrica orgânica: smoke test mede MCPs usados em pipelines REAIS owner cria primeiras 2 semanas, gate fail apenas se < 3 (evita gaming step library com noise tipo `mcp.sentry` decorativo)
+- Smoke test pipeline-studio: pipeline owner-built expõe ≥6 MCPs como first-class steps (3 custom hermes-linkedin/prospects/skills + 3 públicos github/postgres/sentry)
+- Skill forge runner REJECT promotion se skill referencia tool `tier=quarantine` OR `tier=orphan`
+- Pipeline run grava `mcp_calls.caller_chapter='F.9'` (rastreabilidade)
+- Done criteria add: "ZERO tool hardcoded local — todas source = F.5 gateway /tools"
+
+**Cross-ref**: `.claude/MCP-ENFORCEMENT-STRATEGY.md` section 5 F.9 + section 7 step library JOIN.
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