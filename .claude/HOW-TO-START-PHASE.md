# Como começar cada fase em sessão dedicada

> Procedimento canônico **idêntico** para A, B, C, D, E, F. Persistência embutida.
> Use ESTE arquivo como roteiro. Não improvise — desvios = bugs invisíveis.

---

## Prompt universal (copiar-colar no início de QUALQUER fase)

Abre Claude Code em `D:\dev-projects\main\hermes-cloud-studio` e cola:

```
Vamos começar a Fase {A|B|C|D|E|F} do IMPLEMENTATION-PLAN do Hermes Cloud Studio.

PRÉ-REQUISITOS OBRIGATÓRIOS (executar nesta ordem, NÃO PULAR):

1. Read .claude/GUARDRAILS.md  — internalizar 🚫 NUNCA + ✅ SEMPRE
2. Read .claude/PLAN.md         — estado atual do projeto
3. Read .claude/IMPLEMENTATION-PLAN.md (seção da Fase {X})  — escopo da fase
4. Read .claude/VALIDATION-CHECKLIST.md (findings dessa fase) — asserts a satisfazer
5. memory_smart_search "hermes phase {X} implementation"
6. Verificar tunnel: `python scripts/tunnel_supervisor.py --status` deve retornar egress_residential=true
7. Baseline check: `python scripts/validate_implementation.py --phase {X}` — confirma quais findings ainda em FAIL

EXTRA PRA FASE F (executar adicionalmente ANTES de qualquer código):
F1. Read .claude/AUDIT-2026-06-08-FASE-F.md            — diagnóstico delta + 9 chapters F.1-F.9
F2. Read .claude/IMPLEMENTATION-PLAN-FASE-F.md         — plano detalhado por chapter
F3. Read .claude/PHASE-F-STUDY-SYNTHESIS.md            — síntese dos 5 agents Explore (frontend, backend, brain, MCP, skills)
F4. Validar baseline maduro: `python scripts/validate_implementation.py --phase A B C D E` MUST = 20/22 PASS
    Se < 20/22: PARAR. Investigar regressão A-E antes de tocar F.

EXECUÇÃO:

Pra cada finding da fase (em ordem do IMPLEMENTATION-PLAN):
  a. mark_chapter "Phase {X}.{N} — MERGED-XXX" (ou "Phase F.{N} — <titulo>")
  b. TaskCreate com descrição do finding
  c. Implementar conforme análise + solução documentadas
  d. Smoke test conforme plano de teste do finding
  e. `python scripts/validate_implementation.py --finding MERGED-XXX` deve PASS
  f. git add + git commit "fix(escope): MERGED-XXX — descrição curta"
  g. memory_save tipo bug/architecture com fix + arquivos tocados
  h. Update .claude/PLAN.md (marcar checkbox)
  i. Update .claude/GUARDRAILS.md se regra arquitetural nova
  j. TaskUpdate completed

EXTRA PRA FASE F — Regression-test gate INVIOLÁVEL em CADA task que toca código MADURO:
  • pre_test BEFORE: smoke concreto (não grep) do comportamento atual + captura output
  • aplica mudança
  • post_test AFTER: re-run smoke + diff esperado
  • `python scripts/validate_implementation.py --phase A B C D E` DEPOIS DA MUDANÇA
    MUST PRESERVAR 20/22 PASS. Falha = REVERT imediato, nada de "cosmético deixa quieto"
  • Áreas MADURAS (qualquer toque = gate): core/{state,models,ai,pipeline,limiter}.py,
    loops/*, api/*, vm_api/routes.py, linkedin/{stealth,human,limiter,account_profile,
    preflight,stealth_compliance,ollama_router}.py, channels/email/*, daemon/orchestrator.py

Ao final da fase:
  - `python scripts/validate_implementation.py --phase {X}` MUST be 100% PASS
  - Pra Fase F: ADICIONAL `--phase A B C D E` MUST seguir 20/22 PASS (sem regressão)
  - Se FAIL: NÃO fechar fase. Re-abrir findings + iterar.
  - git push
  - memory_save tipo workflow: resumo da fase, próximo movimento
  - Comunicar fim ao owner

Anti-padrões PROIBIDOS:
  ❌ Pular validação porque "óbvio que funciona"
  ❌ Commit que mexe em arquivo fora do escopo do finding atual
  ❌ Marcar finding completed sem PASS no script
  ❌ Implementar 2 findings no mesmo commit (exceto se tecnicamente acoplados)
  ❌ Pular memory_save / chapter mark / PLAN update
  ❌ [Fase F] Tocar código maduro sem pre+post test + validate --phase A B C D E
  ❌ [Fase F] Expor MCPs direto ao agent sem gateway (allowlist + rate-limit + auth)
  ❌ [Fase F] Misturar lógica de decisão (brain.py) com infra (daemon/orchestrator.py)
  ❌ [Fase F] Manter polling onde WS resolve (meta zero-stale na UI)

Comece executando os 7 pré-requisitos em paralelo (são todos read-only), reporte estado, depois aguarde minha confirmação antes de mexer em código.
```

Substituir `{X}` por `A`, `B`, `C`, `D`, `E`, ou `F`.

---

## Por fase — particularidades

### Fase A — Security Critical

**Tempo estimado**: 4-6h em 1 sessão dedicada
**Tokens**: ~50k
**Sequência**: A.1 (MERGED-002) → A.2 (MERGED-001) → A.3 (MERGED-003)

**Por quê essa ordem**: MERGED-002 (fail-closed AUTH_TOKEN) é prerequisito de A.2 e A.3 — sem auth funcional, WS auth e internal token são incompletos.

**Cuidados específicos**:
- Tauri precisa injetar HERMES_AUTH_TOKEN no env do subprocess server.py. Verificar `app/src-tauri/src/lib.rs` antes de commitar A.1
- WS auth no dashboard precisa também atualizar `linkedin_data/sessions/*.json` se houver cookie/token cacheado
- INTERNAL_TOKEN no .env requer **regenerar** os mesmos tokens no extension Chrome (recarregar)

**Risco principal**: dev local sem env var → server não sobe. Documentar no PLAN regenerar token com `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

### Fase B — State & Robustness

**Tempo estimado**: 3-5 dias em 2-3 sessões
**Tokens**: ~150k
**Sequência sugerida**:
1. B.1 MERGED-005 (busy_timeout) — quick win, melhora confiabilidade geral
2. B.3 MERGED-015 (asyncio spawn helper) — prerequisito de B.2
3. B.2 MERGED-004 (globals persistence) — depende de B.3
4. B.5 MERGED-016 (dispatch error preservation)
5. B.4 MERGED-007 (except: pass) — pode dividir em sub-sessões por arquivo

**Cuidados**:
- B.2 inclui SCHEMA migration (campaign_runs table) — deploy VM ou rodar migration manualmente
- B.4 NÃO fazer em 1 commit gigante. Por arquivo ou bloco lógico.

### Fase C — Architecture Consistency

**Tempo estimado**: 1-2 semanas em 3-5 sessões
**Tokens**: ~400k
**Sequência OBRIGATÓRIA** (cada um habilita o próximo):
1. C.1 MERGED-013 (Settings central pydantic-settings) — **TODO O RESTO depende**
2. C.2 MERGED-009 (IP VM via env) — refactor trivial após C.1
3. C.3 MERGED-008 (topologia enforce) — depende de C.1
4. C.4 MERGED-014 (Ollama router) — decisão estratégica do owner
5. C.6 MERGED-012 (pipeline dedupe) — extrai core/pipeline.py
6. C.5 MERGED-011 (split monolitos) — **iterativo, vários sub-commits**, por último

**Cuidados**:
- C.5 split: NÃO mover lógica num só commit. Mover APIRouter por domínio, smoke test cada.
- C.1 quebra deploy se .env não atualizado. Rodar antes em dev.
- C.4 depende da decisão estratégica VM-GPU migration (pode adiar)

### Fase D — Infra & Supervision

**Tempo estimado**: 3-5 dias em 1-2 sessões
**Tokens**: ~80k
**Sequência**:
1. D.1 MERGED-017 (subprocess scraper) — quick win
2. D.2 MERGED-018 (session monitor consecutive) — quick win
3. D.3 MERGED-020 (rate-limit restart) — quick win
4. D.4 MERGED-006 (sync versioning) — schema migration, requer mais cuidado

**Cuidados**:
- D.4 envolve coluna nova em tabela existente. Migration script obrigatório.

### Fase E — Features & Hardening

**Tempo estimado**: 1 sprint completo (~2-3 semanas)
**Tokens**: ~200k
**Estratégia**: implementar 1 channel por vez, testar 30 dias, próximo.

**Sequência**:
1. E.1.1 MERGED-010 Email (SMTP, simples, alto ROI)
2. E.1.2 MERGED-010 WhatsApp (Business API ou wppconnect — escolher antes)
3. E.1.3 MERGED-010 Instagram (Graph API — risco ban)
4. E.2 MERGED-019 XSS sanitization

**Cuidados**:
- Cada channel = mini-sprint. NÃO emparelhar.
- Skills YAML novas precisam ser sincronizadas pra VM (~/.hermes/skills/).
- Email: setup Gmail App Password antes (não senha conta).
- WhatsApp: decisão Business API (paga) vs wppconnect (free, risco ban) é estratégica owner.

### Fase F — Operacional + Self-Evolving

**Tempo estimado**: **47 sessões** distribuídas em 6-8 semanas (ritmo owner solo)
**Tokens estimados (síntese 9 chapters)**: ~1.5M-2.0M total
  - F.1: ~50k (1 sessão, parse + ranking)
  - F.8: ~180k (2 sessões, observability foundation)
  - F.2: ~280k (3 sessões, Mission Control WS upgrade)
  - F.5: ~250k (1 research + 2-3 integração)
  - F.6: ~400k (3-4 sessões, core/brain.py + tools registry)
  - F.9: ~380k (3-4 sessões, Pipeline Studio visual)
  - F.4: ~300k (2-3 sessões, auto-skill loop meta-recursivo)
  - F.3: ~200k (2 sessões, Lab Cockpit)
  - F.7: ~80k (1 sessão setup + monitor contínuo daily ~20-40k)

**Sequência OBRIGATÓRIA dos chapters** (vem de `coherence.execution_order_recommended` — cada um habilita o próximo):

```
F.1 → F.8 → F.2 → F.5 → F.6 → F.9 → F.4 → F.3 → F.7
```

**Justificativa do encadeamento**:
- **F.1 primeiro**: gap audit gera inventário 11 endpoints fantasma + ranking UX. Sem isso, F.2/F.9 ficam cegos pra prioridade
- **F.8 logo após**: observability é fundação pra MEDIR impacto das mudanças seguintes (custo, latência, decisões). Sem F.8, F.6/F.4 voam às cegas
- **F.2 depois de F.8**: Mission Control real-time usa endpoints fantasma (F.1) + integra error inbox/perf cards (F.8). WS broadcast pattern reusado em F.6/F.9
- **F.5 antes de F.6**: MCP gateway + tool registry pattern são pré-requisito do brain.py. Sem MCPs maduros, brain só orquestra skills atuais
- **F.6 antes de F.9 + F.4**: `core/brain.py` + `core/tools.py` são fundação que F.9 (Pipeline Studio steps = tools) e F.4 (auto-skill loop usa Brain.classify) consomem
- **F.9 antes de F.4**: Pipeline Studio + tabela `pipeline_drafts` é palco onde auto-skill loop F.4 publica propostas testadas
- **F.4 meta-recursivo**: precisa F.6 (Brain.evaluate_result) + F.8 (métricas A/B) + F.9 (visualização diff YAML) maduros
- **F.3 paralelo possível**: Lab Cockpit é ortogonal — pode entrar mais cedo se prioridade owner mudar, mas depende de WS de F.2 pra screenshot polling clean
- **F.7 último**: warmup cobaia é OPERACIONAL — só faz sentido com cockpit (F.2), brain (F.6) e observability (F.8) maduros pra monitor 14d sem CLI

**Cuidados específicos Fase F (TRANSVERSAIS aos 9 chapters)**:

🚫 **Regression-test gate INVIOLÁVEL** (pre+post em maduro):
  - Toda task que toca `core/*`, `loops/*`, `api/*`, `vm_api/routes.py`, `linkedin/{stealth,human,limiter,account_profile,preflight,stealth_compliance,ollama_router}.py`, `channels/email/*`, `daemon/orchestrator.py` exige:
    1. pre_test BEFORE: smoke concreto + captura output
    2. aplica mudança
    3. post_test AFTER: re-run + diff esperado
    4. `validate_implementation.py --phase A B C D E` PRESERVA 20/22 PASS
  - Falha = REVERT imediato. Sem exceção "cosmético".

🚫 **UI MUITO MAIS CAPAZ — meta zero-CLI**:
  - Toda ação que owner faz via terminal hoje precisa virar botão/form na dashboard
  - Polling 30s+ stale é REGRESSÃO — substituir por WS real-time
  - Persistir prefs UI (collapsed sections, refresh rate, filtros URL deep-link)
  - Loading states + feedback de ação (polling status pós-trigger)

🚫 **WS real-time prioridade vs polling**:
  - Mission Control timeline/decisions: HOJE polling-only stale → F.2 obriga WS broadcast
  - Pattern: cada subsistema (LinkedIn/Email/Scraper/Audit/Daemon/Tunnel) tem WS channel próprio
  - Polling só fallback se WS indisponível, NUNCA primário em painel "ao vivo"

🚫 **MCP gateway pattern (não expor direto)**:
  - NUNCA conectar 15 MCPs direto ao agent — compor atrás de `hermes-mcp-gateway` na VM
  - Gateway responsabilidades: multiplex + auth + rate-limit + allowlist + audit log
  - Streamable HTTP + OAuth 2.1 (abandona stdio puro pra produção)
  - Validator tool descriptions obrigatório (30 CVEs em 60d em 2026)

🚫 **Brain.py vs daemon — manter separação infra/decisão**:
  - `core/brain.py` (NOVO): decisão pura, classifier, action selector, reward — TESTÁVEL ISOLADO
  - `daemon/orchestrator.py` (ESTÁVEL): state machine, sleep, error recovery — INFRA
  - decide_next_action() vira `Brain.decide(context)` consumido pelo daemon
  - `core/tools.py`: registry unificado (skills + MCPs + pipelines + endpoints)
  - Agent Zero entra como decision maker (não fallback)

🚫 **Sem mocks/stubs** em testes (GUARDRAILS) — lab usa fixtures reais com IDs anonimizados

#### F.1 — Backend↔Frontend Gap Audit
- **Tempo**: 1 sessão (4-6h)
- **Tokens**: ~50k
- **Sequência tasks**:
  1. Parser AST `api/*.py` + `vm_api/routes.py` → JSON de 144 rotas (path, method, handler, schema)
  2. Grep `dashboard/app.js` (276KB, 271 fetch calls) → mapa rotas consumidas
  3. Diff órfãs = endpoints fantasma (target ≥11 incluindo `/api/daemon/*` 5 endpoints)
  4. Ranking impacto UX (alto = ação freq via CLI hoje)
  5. Output `.claude/FRONTEND-GAP.md` + lista top 10 features expor
  6. memory_save type=architecture com lista órfãs
- **Cuidados**: parsing AST tem que respeitar `APIRouter` prefix; grep precisa pegar fetch() E `_apiCall()` wrapper
- **Risco**: falsos positivos (rotas internas que NÃO deveriam ter UI). Marcar `internal_only=true` no JSON

#### F.8 — Cost & Performance Observability
- **Tempo**: 2 sessões (~2-3 dias)
- **Tokens**: ~180k
- **Sequência tasks**:
  1. Schema `llm_calls` (timestamp, provider, model, prompt_tokens, completion_tokens, usd_estimated, chapter_id) + middleware Ollama/OpenRouter/Claude
  2. Schema `endpoint_metrics` (latência p50/p95/p99 rolling 24h por route) + middleware FastAPI
  3. Schema `errors_inbox` (timestamp, subsystem, severity, trace, status: new|seen|resolved) + log aggregator
  4. Schema `brain_decisions` (acoplado a F.6, criar tabela já — populada depois)
  5. Endpoints `/api/observability/{costs,perf,errors,decisions}`
  6. Dashboard `/observability` com 4 tabs + WS push pra novos erros
  7. Pre+post test em middlewares (cuidado: NÃO inflar latência > 5ms overhead)
- **Cuidados**: middleware NÃO pode bloquear request. Async fire-and-forget pra escrita métrica
- **Risco**: SQLite contention (tabelas crescem rápido). Usar busy_timeout (MERGED-005) + rotação 30d

#### F.2 — Mission Control Real-Time Upgrade
- **Tempo**: 2-3 sessões (~3-5 dias)
- **Tokens**: ~280k
- **Sequência tasks**:
  1. WS broadcast pra timeline + decisions (substitui polling-only stale)
  2. Activity Orbit expandida: tile por subsistema (LinkedIn / Email / Scraper / Audit / Daemon / Tunnel) com status WS
  3. Live tail logs (SSE ou WS rolling buffer 500 lines)
  4. Botões pause/resume daemon + channel toggle + clear decisions + archive activity
  5. Indicadores visuais saudável/warning/erro com cores claras
  6. Persist user prefs (collapsed sections, refresh rate) em localStorage + backend mirror
  7. Integrar cards F.8 (custo, perf, errors) no cockpit
- **Cuidados**: WS broadcast precisa NÃO regressar daemon_state (10s poll funcionando). Reusar pattern WS channel_update existente
- **Risco**: WS reconnect storm se daemon reinicia. Backoff exponencial client-side

#### F.5 — MCP Discovery + Integration
- **Tempo**: 1 research + 2-3 integração (~1 semana)
- **Tokens**: ~250k
- **Sequência tasks**:
  1. Workflow `mcp-discovery-survey` → research MCPs 2026 públicos + estima ROI
  2. Decisão owner: 2-3 públicos integrar primeiro (top candidatos: Playwright MS, Postgres MCP Pro, GitHub MCP oficial, Exa, Firecrawl)
  3. **Setup `hermes-mcp-gateway` VM** (FastMCP 3.0 Python) — multiplex + auth + rate-limit + allowlist
  4. Integrar MCPs públicos via gateway (NUNCA direto)
  5. Desenvolver 1º MCP custom: `hermes-linkedin-mcp` (moat técnico — wrap Patchright+stealth+limiter+cooldown)
  6. Testar via MCP Inspector + smoke pipeline real
  7. Documentar allowlist tools por agent + audit log gateway
- **Cuidados**: NÃO usar `mcp-server-sqlite` oficial (Anthropic marca como reference/educational) — usar Postgres MCP Pro. Avisar do `LinkedIn-Posts-Hunter-MCP` (Playwright sem stealth, ban risk)
- **Risco**: tool description injection (30 CVEs em 60d 2026). Validator obrigatório no gateway

#### F.6 — Cérebro Hermes: Orchestration Layer
- **Tempo**: 3-4 sessões (~1-2 semanas)
- **Tokens**: ~400k
- **Sequência tasks**:
  1. Criar `core/brain.py` NOVO (Brain.decide / Brain.classify / Brain.evaluate_result) — isolated, testável
  2. Criar `core/tools.py` (ToolRegistry: skills + mcps + pipelines + endpoints) — namespace único
  3. Refactor `_classify_reply_intent()` → `Brain.classify(text, categories, context)` (generalizado)
  4. Encapsular `daemon/orchestrator.py::decide_next_action()` em `Brain.decide()` — daemon vira state machine pura
  5. `execute_task()` consome `ToolRegistry.invoke(tool_name, **kwargs)` (dinâmico)
  6. UI chat na dashboard: stream tokens WS + cards de ações executadas (link log/artifact)
  7. Multi-turn com `_brain_context_id`
  8. Persistir conversas `brain_sessions` table
  9. Skill `hermes-brain-test` + workflow `brain-intent-coverage` (50 prompts típicos)
  10. Audit trail decisões em `brain_decisions` (popula tabela F.8)
- **Cuidados**: separar RIGOROSAMENTE infra (daemon) vs decisão (brain). Brain NUNCA tem `while True: await sleep`. Daemon NUNCA tem `if priority == P1: ...`
- **Risco principal**: regressão dos 7 níveis prioridade hardcoded (P1-P7) durante migração. Pre_test = snapshot decisões 24h pré-brain, post_test = mesmas decisões pós-brain (acerto ≥90%)

#### F.9 — Pipeline Studio Visual
- **Tempo**: 3-4 sessões (~1-2 semanas)
- **Tokens**: ~380k
- **Sequência tasks**:
  1. Decisão design: form-driven structured (cards de step) > canvas drag-drop (owner solo + 11 páginas vanilla)
  2. Schema `pipeline_drafts` (rascunhos sem publicar) + `pipeline_runs` (histórico granular por step)
  3. Step library: cada skill + pipeline existente + MCP tool (via gateway F.5) + endpoint vira step
  4. UI `/pipeline-studio` — form builder cards + step library sidebar
  5. Live execution monitor — cada step status/output/timing/error inline (WS)
  6. Template gallery — clone-and-modify pipelines existentes
  7. A/B test pipelines — 2 variantes paralelas mesma fonte, comparar métricas (consome F.8)
  8. API `/api/pipeline-studio/{steps,templates,execute,monitor}`
  9. Substitui parcialmente `/pipeline` legado (NÃO deletar até migration 100%)
- **Cuidados**: consome `core/tools.py` (F.6) — não criar registry paralelo. WS execution monitor reusa pattern de F.2
- **Risco**: drift entre pipelines YAML (`pipelines/*.yaml`) e drafts visuais. Source-of-truth claro: visual draft → publica → vira YAML versionado

#### F.4 — Auto-Skill Loop W3 (meta-recursivo)
- **Tempo**: 2-3 sessões (~1 semana)
- **Tokens**: ~300k
- **Sequência tasks**:
  1. Schema `skill_proposals` (status: draft|lab_pending|lab_pass|lab_fail|approved|rejected|active|disabled, metrics JSON, owner_notes)
  2. Workflow `hermes-skill-forge.js` — lê activity DB 30d → `Brain.classify` intents recorrentes (F.6) → propõe N skills YAML
  3. Lab test executor SANDBOX: 10+ fixture inputs incluindo injection tests
  4. UI `/skills/proposals` — YAML preview com VISUAL DIFF highlight deltas (obriga owner ler)
  5. Accept → POST `/api/skill-proposals/{id}/deploy` → scp staged + ssh validate + PATCH active (reusa `/hermes-deploy`)
  6. 10s polling confirma + rollback se erro
  7. 7 dias A/B test: sucesso_rate / latência_p99 / custo (consome F.8)
  8. Auto-disable após 5+ erros + Telegram notify (cooldown 1x/dia máximo proposta)
  9. cost_budget_per_day no schema YAML (campo NOVO) — rejeita se excede
- **Cuidados**: skill bugada que passa lab (3 runs lucky). Mitigação: 10+ fixtures parametrizadas + injection tests + snapshot DB prod wipe IDs (fixture realista)
- **Risco principal**: skill rouge ativa em prod degrada warmup cobaia. Auto-disable strict + Telegram alert obrigatório

#### F.3 — Lab Cockpit
- **Tempo**: 2 sessões (~2-3 dias)
- **Tokens**: ~200k
- **Sequência tasks**:
  1. Página `dashboard/lab` nova
  2. UI rodar `linkedin/lab/lab_runner.py` sem CLI: botões fingerprint baseline / login fresh / viewer test
  3. Live screenshot polling (`artifacts/*/screenshots/`) — WS push quando novo screenshot
  4. Visualizar compliance score + delta vs baseline
  5. Lista runs históricos + diff fingerprint
  6. API `/api/lab/runs`, `/api/lab/start`, `/api/lab/{run_id}/artifacts`
  7. Integrar MCP `linkedin-lab` (test_flow, fingerprint_compare, capture_trace) — opcional se F.5 maduro
- **Cuidados**: lab roda PATCHRIGHT na VM (NUNCA PC — GUARDRAILS). UI PC só dispara via API. Reusar pattern WS de F.2 pra live screenshots
- **Risco**: lab run trava sem timeout — gate `--timeout 600s` obrigatório no lab_runner.py

#### F.7 — Cobaia Live Ops
- **Tempo**: 6 sessões reais (+1 vs base 5 pra `core/scheduler.py` singleton APScheduler — ver DECISION.md)
- **Tokens**: ~80k/sessão + ~20-40k/dia monitor pós-setup
- **🚨 PRÉ-REQUISITO INVIOLÁVEL ANTES de qualquer task**:
  1. **Read** `.claude/F7-SCHEDULE-ARCH-DECISION.md` completo (30k chars, 13 sections — decisão arquitetural canônica workflow f7-schedule-arch-analysis 2026-06-10 commit a0d3eb0)
  2. **Marcar** Approval Checklist section 13 do DECISION.md (4 itens)
  3. **Confirmar** PLAN.md F.7 bloco "Schedule Infrastructure — Decisão Final" reflete decisão real (Primary B APScheduler — NÃO placeholder antigo "DECISÃO PENDENTE")
  4. **Confirmar** `requirements.txt` contém `apscheduler>=3.11.0,<4.0` + `tzdata>=2024.1` (Primary B requer); se ausente: adicionar como Step 1 da sessão
  5. **Use** Tasks 2/3/4 implementation plan section 5 do DECISION.md como base canônica — NÃO improvisar callables, NÃO recalcular `acceptance_cooldown` (PATCH-014 fonte canônica), NÃO remover inline `_check_stop_gates()` do P1-P7 loop body
- **Sequência tasks** (6 sessões):
  0. **Sessão setup APScheduler**: `core/scheduler.py` singleton + wire-up `HermesDaemon.start/shutdown` + endpoints `/api/scheduler/jobs` (ver DECISION.md section 5)
  1. Plano warmup 14d documentado com gates diários
  2. Daemon auto-executa via APScheduler CronTrigger Cuiabá tz: dia 0-6 só lurking (views), dia 7-13 ramp connects, dia 14+ outreach
  3. Métricas job (1h interval): acceptance_rate (PATCH-014 já implementado), reply_rate, ban_probability → escreve `cobaia_daily_metrics`
  4. Stop gates job (30min interval, double-check fallback): burned_flag / compliance<70 / acceptance<40% — inline P1-P7 preservado
  5. Daily Telegram report job (CronTrigger 19h Cuiabá tz, Persistent=true) via skill `hermes-cobaia-status`
  6. Dashboard `/cobaia` com timeline + métricas (consome F.8 + WS F.2) + dashboard `/scheduler/jobs` (next_run + last_error realtime)
  7. Subagent `warmup-coach` (conhece PATCH-007/008/014 + janelas operacionais)
- **Cuidados**: conta `milgrauz.exe@gmail.com` é COBAIA — pode queimar. Conta Caio NUNCA tocada até cobaia 30d clean. Stop gates auto-disparam, NUNCA owner manual
- **Risco principal**: warmup pulado / acelerado por ansiedade owner. Gate técnico obriga dias mínimos no schema
- **Pre-deploy gate**: `bash scripts/validate_implementation.py phases A B C D E` 20/22 PASS preservado; se cair <20 ROLLBACK + migrate fallback D-híbrido (DECISION.md section 11)
- **Canary 2h prod pós-deploy**: `ssh hermes-gcp 'journalctl --user -fu hermes-daemon -n 100 | grep -E "(scheduler|cobaia)"'` — abort se ERROR no listener primeiras 2h

---

## Quando atacar tudo em sessões consecutivas vs espaçadas

| Estratégia | Quando faz sentido |
|---|---|
| **Tudo em 1-2 semanas sprint-like** | Owner tem ~6h/dia dedicado |
| **1 fase por semana espaçada** | Owner trabalha part-time + cliente paralelo |
| **Só Fase A agora, resto adiar** | Outras prioridades estratégicas (ex: cliente novo, deadline) |
| **Fase F em 6-8 semanas distribuídas** | 47 sessões — owner solo, ritmo sustentável, gate regressão pesado |

**Recomendação**: Fase A imediatamente (segurança não espera) + Fase B em até 2 semanas. Fases C/D/E podem espaçar conforme contexto. **Fase F**: começar SÓ depois de A-E todos PASS (20/22 baseline) — sem isso, regression-gate falha logo na 1ª task F.

---

## Validação cross-projeto

A skill `/audit-project` global (em `~/.claude/skills/audit-project/`) replica esse framework. Quando rodar `/audit-project` em outro projeto:
- Cria .claude/GUARDRAILS.md (Fase 0 obrigatória)
- Coleta findings
- **Não cria IMPLEMENTATION-PLAN automaticamente** — esse é manual por projeto (deep-audit workflow é opcional, custo alto)

Pra ter IMPLEMENTATION-PLAN em outro projeto, peça explicitamente: "rodar deep-audit no projeto X" depois.

---

## Atalho para sessões futuras

Salve este prompt como `.claude/commands/start-phase.md`:

```markdown
---
description: Inicia fase do IMPLEMENTATION-PLAN com pré-requisitos automatizados
argument-hint: "<A|B|C|D|E|F>"
---

Leia HOW-TO-START-PHASE.md no .claude/. Execute os 7 pré-requisitos em paralelo
(+ 4 extras se fase=F: AUDIT-2026-06-08-FASE-F.md + IMPLEMENTATION-PLAN-FASE-F.md
+ PHASE-F-STUDY-SYNTHESIS.md + baseline --phase A B C D E = 20/22 PASS),
reporte baseline da validation `--phase $1`, aguarde confirmação owner antes de
mexer em código.
```

Daí basta digitar `/start-phase A` (ou `B`, `C`, `D`, `E`, `F`) no Claude Code aberto no projeto.
