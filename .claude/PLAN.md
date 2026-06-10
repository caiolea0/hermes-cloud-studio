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