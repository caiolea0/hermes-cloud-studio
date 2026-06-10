# PLAN.md MCP Enforcement Patch (F.4/F.5/F.6/F.7/F.8/F.9)

Patch instructions pra .claude/PLAN.md substituir done_criteria vagos por MCP HARD REQUIREMENTS literais alinhados combo S2+S1+S3 (mcp_calls audit + phase F validator + mensal MCP-COVERAGE MD).

Combo strategy: S2 coluna vertebral (runtime), S1 commit-time gate (CI), S3 reflexao mensal pull-based. 3 dimensoes temporais cobertas.

Aplicar em ordem: F.5 PRIMEIRO (gateway+seed+validator), depois F.6 (middleware audit), F.4/F.7/F.9 (consumidores), F.8 (painel).

---

## F.5 — MCP Gateway & Registry

ANTES (approx):
- ContextForge gateway operacional VM
- 3 MCP custom registrados (hermes-linkedin/prospects/skills)
- Endpoint /tools lista server+tool

DEPOIS:
- ContextForge gateway operacional VM (loopback only)
- Task 5b: mcp_registry seeded idempotente 9-12 rows com chapter_owner + required_by_dc[] (ContextForge=infra, GitHub=F.4, Sentry=F.4+F.7, Postgres MCP Pro=F.6+F.7, Playwright=F.3, Omnisearch=F.7, Hunter=F.7, WhatsApp=F.7, hermes-linkedin=F.7+F.9, hermes-prospects=F.7+F.9, hermes-skills=F.4+F.9)
- Task 5c: PLAN.md done_criteria F.4/F.6/F.7/F.8/F.9 editado com clausulas "MCP HARD REQUIREMENTS (F.x)" literais formato canonico mcp.<server>.<tool>
- Task 5c: scripts/validate_implementation.py phase F implementado — grep banned patterns + coverage assertion auto-derivada regex parse PLAN.md (NAO hardcoded, single source of truth)
- Task 5c: .claude/MCP-BANNED-PATTERNS.json declarativo criado
- Task 7: scripts/mcp_coverage_audit.py deployado + cron scheduled-tasks "0 9 15 * *" (dia 15 09h BRT evita janela cobaia semana 1)
- Task 7: endpoints GET /api/mcp/coverage/latest + POST /api/mcp/coverage/publish
- Endpoint GET /api/mcp/gateway/tools (consumido F.8 + F.9)
- Runtime startup gate hermes_api_v2.py lifespan: STRICT_MODE default=False, ativa apenas se HERMES_STRICT_MCP=1 (VM prod) — dev local nao trava
- audit mensal gera .claude/audits/mcp-coverage/MCP-COVERAGE-{YYYY-MM}.md versionado git com tier classification

---

## F.6 — Brain & Tool Dispatch

ANTES (approx):
- Brain.decide() retorna intent + tool
- Postgres MCP read-only via mcp.postgres.query
- Audit log brain_decisions table

DEPOIS — MCP HARD REQUIREMENTS:
- core/tools.py ToolRegistry.invoke() wrap middleware FAIL-CLOSED INSERT mcp_calls(server, tool, args_hash, latency_ms, error, context_id, turn_idx, caller_chapter) try/except proprio — se INSERT falhar: log.critical + sentry_sdk.capture_exception MAS NAO propaga erro caller
- Decorator @instrumented obrigatorio em todo dispatch emite OTel GenAI spans (gen_ai.tool.execute, gen_ai.tool.name, mcp.server.name) — assert via integration test obrigatorio
- Schema brain_decisions ganha coluna otel_trace_id cross-ref mcp_calls.context_id+turn_idx
- Brain.decide() schema output validado pydantic ANTES dispatch: {intent, tool_name, args, confidence}
- Confidence floor configuravel PrefPanel + DB pref_keys (default 0.7) — < threshold skip auto-execute enfileira owner_confirm
- Postgres MCP read-only via mcp.postgres.query (PROIBIDO sqlite3.connect bare)
- Phase F validator pass: ZERO bypass core/ (sentry_sdk import, subprocess gh, requests api.*)

---

## F.4 — Auto-Skill Loop

ANTES (approx):
- skill_proposals table CRUD
- PR-based deploy skill
- Auto-disable via Sentry

DEPOIS — MCP HARD REQUIREMENTS:
- Task 2 skill_proposals CRUD via mcp.hermes-skills.* (F.5 gateway)
- Task 3 PR-based deploy via mcp.github.create_pull_request (PROIBIDO subprocess gh CLI + requests api.github.com)
- Task 7 auto-disable via mcp.sentry.list_issues (PROIBIDO sentry-sdk Python direto em core/auto_skill_*.py)
- Primeira skill proposal ponta-a-ponta invoca >=2 MCPs distintos (prova orchestration real)
- mcp_coverage.calls_7d > 0 para github + sentry + hermes-skills ANTES marcar done
- scripts/validate_implementation.py phase F grep-audit bloqueia merge se detectar imports/subprocess banidos em: core/skill_proposals.py, core/auto_skill_runner.py, core/auto_skill_promoter.py
- BANNED_PATTERNS declarativo em .claude/MCP-BANNED-PATTERNS.json

---

## F.7 — Cobaia Live Ops

ANTES (approx):
- Pipeline cobaia 14d warmup
- LinkedIn outreach 5/dia rate-limited
- Sentry capturando erros
- Coletor metricas cobaia

DEPOIS — MCP HARD REQUIREMENTS:
- Task 6 Hunter.io: mcp.hunter.verify_email via gateway ANTES warmup email (PROIBIDO requests.get api.hunter.io)
- Task 6b NOVA Omnisearch: mcp.omnisearch.search discovery PMEs Cuiaba
- Task 6c NOVA Plan B Hunter (documentar GUARDRAILS.md ANTES Task 6 hard): cache 30d verificacoes + degrade gracioso skip warmup se quota free 25/mes saturou OU rate-limit prospects 5/dia (=150/mes)
- Task 7 Sentry: mcp.sentry.capture_exception via gateway (NAO sentry-sdk direto)
- Task 9 NOVA Postgres MCP Pro: cobaia_metrics_collector.py via mcp.postgres.query read-only (PROIBIDO sqlite3.connect bare)
- Daemon F.7 dispara LinkedIn via mcp.hermes-linkedin.* (NAO patchright direto)
- mcp_coverage.calls_7d > 0 para: hunter + sentry + omnisearch + postgres + hermes-linkedin
- Phase F grep-audit pass (errors_inbox category='mcp_bypass' count = 0)
- Widget cobaia-status mostra link latest MCP-COVERAGE-{YYYY-MM}.md
- Hunter quota MTD < 22/25 sustentado 6 meses (gate Plan B fallback)

---

## F.8 — Observability Dashboard

ANTES (approx):
- Tabs Costs/Performance/Errors/Decisions
- SummaryWidget KPIs
- WS obs.* namespace push real-time

DEPOIS — MCP HARD REQUIREMENTS:
- Schema migration: tabelas mcp_registry + mcp_calls + mat view mcp_coverage (refresh 5min) + PARTITION BY RANGE(called_at) mensal + retention 90d auto-drop (pg_partman)
- Cron 6h detect_zombies AUTO-flagga deprecated_at (NUNCA remove — npm deprecate pattern)
- Endpoints: GET /api/observability/mcp-coverage, GET /api/observability/mcp-coverage/history?months=6, GET /api/observability/mcp-coverage/audits, POST /api/mcp/registry/unflag
- Task 5d NOVA: TabMcpCoverage 5a tab observability shell — SummaryRow 5 cards (TotalMCPs/Active/Drift/Quarantine/PaidIdle$), MatrixCoveragePanel heatmap Phase × MCP (verde/vermelho/cinza), MCP List Table sortable/filterable (All/Active/Idle30d/Deprecated/Drift/Paid), SparklineHistory 6 meses. Reusa Chart.js vendor local + SummaryWidget pattern + TabCosts grid
- Estender WS obs.* namespace: obs.mcp_coverage_gap event (startup gate detecta MCPs faltando OU phase F bloqueia commit)
- Phase F violations gravar errors_inbox category='mcp_bypass' (reusa ErrorInboxHandler cross-tab Errors)
- SummaryWidget badge mcp_required_missing
- Sentry alert WEEKLY DIGEST (NAO 1 capture por MCP — reduz noise)
- Add literal: "painel MCP coverage por chapter · audit mensal historico navegavel · drift count > 3 = Sentry warning · ZERO write bypass detectado phase F ultimos 30d"

---

## F.9 — Pipeline Studio

ANTES (approx):
- Step library exibe >=6 tools
- Pipeline DAG editor visual
- Skill forge promotion criteria

DEPOIS — MCP HARD REQUIREMENTS:
- Task 1b NOVA: tool registry SOURCE = F.5 gateway audit-log GET /api/mcp/gateway/tools (NAO scan local skills/ dir)
- Step library JOIN mcp_registry exibir MCPs como steps com badge chapter_owner + last_used + tier (badge "idle 60d+" WARN — NAO bloqueia, industry passive flag)
- Substituir criterio numerico ">=6 hard" por metrica organica: smoke test mede MCPs usados em pipelines REAIS owner cria primeiras 2 semanas, gate fail apenas se < 3 (evita gaming step library com noise tipo mcp.sentry decorativo)
- Smoke test pipeline-studio: pipeline owner-built expoe >=6 MCPs como first-class steps (3 custom hermes-linkedin/prospects/skills + 3 publicos github/postgres/sentry)
- Skill forge runner REJECT promotion se skill referencia tool tier=quarantine OR tier=orphan
- Pipeline run grava mcp_calls.caller_chapter='F.9' (rastreabilidade)
- Add literal: "ZERO tool hardcoded local — todas source = F.5 gateway /tools"

---

## Git Command Sequence (manual)

```powershell
cd D:\dev-projects\main\hermes-cloud-studio
git checkout -b plan/mcp-enforcement-patch

# Editar PLAN.md aplicando blocos DEPOIS, manter ANTES como <!-- comentario -->
# Criar arquivos suporte:
#   .claude/MCP-BANNED-PATTERNS.json
#   .claude/mcp-audit-config.json (IDLE_THRESHOLDS configuraveis)
#   .claude/audits/mcp-coverage/.gitkeep

git add .claude/PLAN.md .claude/IMPLEMENTATION-PLAN-FASE-F.md `
        .claude/MCP-BANNED-PATTERNS.json `
        .claude/mcp-audit-config.json `
        .claude/audits/mcp-coverage/.gitkeep `
        .claude/PLAN-MCP-ENFORCEMENT-PATCH.md
git commit -m "plan(mcp): enforce MCP HARD REQUIREMENTS F.4-F.9 done_criteria"

git push -u origin plan/mcp-enforcement-patch
gh pr create --title "PLAN: MCP enforcement F.4-F.9" --body "@see .claude/PLAN-MCP-ENFORCEMENT-PATCH.md"
```

---

## Approval Checklist (owner antes merge)

- [ ] Li blocos DEPOIS de TODOS chapters F.4/F.5/F.6/F.7/F.8/F.9
- [ ] Confirmo combo S2+S1+S3 (audit DB + CI validator + mensal MD)
- [ ] Startup gate default OFF (HERMES_STRICT_MCP=0 dev) — nao trava local
- [ ] Phase F validator BLOCKING merge em F.4/F.7/F.9 (nao warning)
- [ ] Cron audit mensal dia 15 09h BRT (evita janela cobaia semana 1)
- [ ] Hunter.io Plan B (cache 30d + rate-limit 5/dia) documentado GUARDRAILS.md ANTES Task 6 virar hard
- [ ] Orcamento ~6.5 sub-sessoes dev (S2 ~2.5 + S1 ~2 + S3 ~2)
- [ ] Payback ~6-8 meses via cancelamento subscription paga zombie
- [ ] Rollback plan 4 camadas LIFO documentado
- [ ] Single source of truth = PLAN.md (validator parse, NAO hardcoded)
- [ ] Criterio organico F.9 (>=3 MCPs uso real owner-built, NAO >=6 gaming-friendly)

---

## Sucesso (metricas 6 meses cobaia)

1. mcp_registry required_by_dc nao-vazio → calls_7d > 0 sustentado 3 audits consecutivos
2. Phase F validator: ZERO bypass F.4/F.7/F.9 ultimos 30d
3. Brain.tools.invoke() 100% OTel GenAI spans coverage
4. >=1 subscription paga zombie cancelada via S3 (Hunter $49 OU Apollo $50)
5. mcp_coverage panel F.8 mostra >=6 MCPs active sustentado
6. Audit mensal 12/12 meses cron sem falhas
7. Owner intervencao <=2h/mes
8. Sentry weekly digest zombies <=2 MCPs/semana apos 3 meses
9. Hunter quota MTD < 22/25 sustentado

---

## Rollback (4 camadas LIFO)

1. Camada 3 OFF: HERMES_STRICT_MCP=0 — startup gate disabled, Brain boota gateway down (READ_ONLY). Loss: zero
2. Camada 1 WARNING: phase F validator vira PR comment + errors_inbox (nao bloqueia). Loss: parcial
3. Camada 3 PAUSE: cron S3 audit disabled via mcp__scheduled-tasks__update_scheduled_task + remove painel badge. Loss: cadencia reflexiva
4. S2 fail-open: core/tools.py invoke() try/except amplo + continue. Loss: audit holes ~1-5%

Re-ativar LIFO se /hermes-mcp-survey detecta ecosystem >15 MCPs OR bypass Sentry > 5 events/mes. Documentar em .claude/audits/mcp-coverage/ROLLBACK-{YYYY-MM-DD}.md.
