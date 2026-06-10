# MCP Enforcement Strategy — Hermes Cloud Studio

> **Status**: Proposta — pendente owner approval
> **Autor**: Audit estratégico cross-chapter F.5/F.6/F.7/F.4/F.8/F.9
> **Versão**: 1.0 (2026-06-09)
> **Escopo**: Garantir que MCPs declarados em F.5 sejam realmente usados em produção; prevenir "MCPs na gaveta"
> **Dependências**: F.5 (gateway + 9-12 MCPs) operacional, F.6 (Brain ToolRegistry) implementado, F.8 (observability shell) em curso

---

## 1. Context — Problema "MCPs na Gaveta"

F.5 entrega infraestrutura ambiciosa: **IBM ContextForge MCP Gateway + FastMCP 3.0 framework + 6 MCPs públicos firmes (GitHub, Sentry, Postgres Pro, Playwright MS, Omnisearch, Hunter.io) + 1 condicional (WhatsApp Business) + 3 custom (hermes-linkedin, hermes-prospects, hermes-skills)**. Total ≥9 MCPs ativos no gateway com auth+rate-limit+audit centralizado.

**Mas F.5 done_criteria é self-contained**: valida apenas que gateway responde, 30+ tools discoverable, 3 custom MCPs com OAuth 2.1 → **NÃO valida cross-chapter consumption**. Resultado previsível:

| Risco | Manifestação concreta |
|-------|----------------------|
| Owner Claude esquece e usa SDK direto | `import sentry_sdk`, `subprocess.run(['gh', 'pr', 'create'])`, `requests.get('api.hunter.io/v2/email-verifier')` |
| MCP declarado em F.5 ROI matrix nunca é integrado | Omnisearch citado pra "F.7 discovery PME Cuiabá" mas ZERO task F.7 referencia |
| Custom MCP custa 1+ sub-session implementar e fica órfão | `hermes-linkedin` MCP entregue, daemon F.7 dispara Patchright direto bypassando |
| Subscription paga (Apollo $50/mês, Hunter $49/mês se contratado) renova zombie | Ninguém detecta zero calls antes próximo billing cycle |
| Drift silencioso vendor MCP breaking change | GitHub MCP muda signature `create_pull_request`, Brain falha em prod sem alerta |
| Gateway = single point of failure sem rollback documentado | ContextForge cai → Brain perde acesso 9-12 MCPs simultâneo |

**Diagnóstico cruzado dos 3 fragments (F.5 deliverables + F.6 Brain registry + F.7/F.4/F.9 usage)**: existem **12 gaps de enforcement** + **11 gaps F.4/F.7/F.9 done_criteria silenciosos sobre MCP**. Sem mecanismo cross-chapter, F.5 vira teatro arquitetural — owner solo no-code paga overhead implementação e nunca colhe ROI.

**Industry pattern 2026 (Cursor Enterprise, LangSmith, MCP Gateways como Lunar/TrueFoundry, OTel GenAI semantic conventions)**: enforcement multi-camada com **hard limits (CI gates) + soft limits (dashboards pull-based) + deprecation passiva (npm `deprecate` flag, sem auto-removal)**. Nenhuma camada sozinha funciona; combinadas cobrem commit-time + runtime + reflexão mensal.

---

## 2. Sumário Executivo

**Primary combo recomendado**: **S2 (coverage tracker `mcp_calls` table + fail-closed audit F.6 middleware) + S1 (hard requirement done_criteria + validate_implementation.py phase F + runtime gate degradado) + S3 (audit mensal MCP-COVERAGE-{YYYY-MM}.md cron dia 15)**.

**Rationale 1-parágrafo**: Coverage MCP exige multi-camada porque 1 só estratégia deixa blindspot. **S2 é a coluna vertebral** — fornece dados runtime canônicos (Postgres mcp_calls + OTel GenAI spans) que S1 e S3 consomem; sem S2 ambas operam cegas. **S1 fecha o gap que S2 não cobre**: BYPASS gateway (owner importa `sentry_sdk` direto, usa `gh` CLI, `requests.get` Hunter) — S2 só registra o que passa pelo gateway, S1 detecta quem evita o gateway no momento do commit via grep-audit phase F. **S3 é a camada reflexiva pull-based** alinhada industry 2026 (Cursor Enterprise, npm deprecate pattern) — transforma dados S2 + violações S1 em narrativa owner-readable mensal com tier classification (active/warning/deprecated/quarantine/orphan/drift) e cross-ref `PLAN.md` done_criteria vs uso real. Combo cobre 3 dimensões temporais: **commit-time (S1 CI grep) → runtime (S2 fail-closed audit) → reflexão mensal (S3 markdown versionado git)**.

**Impact estimado**:
- **Effort**: ~6.5 sub-sessões total spread cross-chapter (F.5 +2.5, F.6 +0.5, F.8 +2.5, F.9 +1) — ZERO sessão standalone nova
- **ROI break-even**: detectar 1 subscription paga zombie em 6-8 meses ($49-99/mês) paga overhead implementação completo
- **Friction owner**: ~1.5h/mês intervenção real (30min triagem MD mensal + 1h investigação ad-hoc se drift > 3) — aceitável solo no-code
- **Observability**: industry-grade (OTel GenAI spans, Postgres analytics, npm deprecate pattern) sem novo SaaS pago — guardrail "zero API paga além Claude Max" preservado

---

## 3. Sete Estratégias Avaliadas (Rank Table)

| # | Strategy | Owner Friction | Observability | Cost/ROI | Maintenance | Verdict Score | Recomendação |
|---|----------|----------------|---------------|----------|-------------|---------------|--------------|
| **S2** | **mcp_calls Postgres table + F.6 fail-closed middleware + mat view mcp_coverage** | 3/10 ✓ | **9/10 ✓** | **9/10 ✓** | 3/10 ✓ | **4/4 valid** | **PRIMARY — coluna vertebral** |
| **S1** | **Hard requirement done_criteria + validate_implementation.py phase F grep-audit + runtime startup gate** | 3/10 ⚠ | 5→8/10 (com F.8) | 9/10 ✓ | 4/10 ⚠ | **3/4 valid** (rejeitada owner_friction → mitigar) | **PRIMARY — commit-time gate** |
| **S3** | **mcp-coverage-audit cron mensal → MCP-COVERAGE-{YYYY-MM}.md tier classification + Sentry weekly digest** | 4/10 ✓ | 8/10 ✓ | 8/10 ✓ | 4/10 ✓ | **4/4 valid** medium | **PRIMARY — camada reflexiva** |
| S4 | OTel GenAI spans only (instrument cada MCP + dashboard Sentry Performance) | 5/10 | 9/10 | 7/10 | 5/10 | partial | Complementar S2 (já incluído) |
| S5 | Gateway middleware rate-limit + cost cap por MCP (F.5 ContextForge config) | 4/10 | 6/10 | 7/10 | 5/10 | partial | Adiar F.8 cost tracking integrado |
| S6 | Manual quarterly review owner + sheet checklist | **2/10 best** | 3/10 | 6/10 | 2/10 | partial | Insuficiente solo (drift silencioso entre reviews) |
| S7 | Auto-removal MCP zumbi 60d (destrutivo) | 6/10 | 7/10 | 8/10 | 3/10 | **rejected** | Viola guardrail "NUNCA destrutivo sem owner confirm" |

**Convenções**: ✓ = aprovado lens, ⚠ = mitigável, **negrito** = primary combo. Verdict valid_count baseado em 4 lenses (owner_friction / observability / cost_roi / maintenance_burden).

---

## 4. Análise Detalhada Primary Combo (S2+S1+S3)

### 4.1 S2 — Coverage Tracker Postgres + Fail-Closed Audit F.6

**Componentes**:
- `mcp_registry` table (mcp_name PK, mcp_kind public|custom|infra, chapter_owner, deprecated_at, required_by_dc[])
- `mcp_calls` table (id, mcp_name FK, tool_name, caller_chapter, context_id, latency_ms, status, cost_usd, called_at) — PARTITION BY RANGE(called_at) mensal + retention 90d via pg_partman
- `mcp_coverage` materialized view (refresh 5min) — agrega calls_24h/7d/30d + last_used + p_avg_ms
- `ToolRegistry.invoke()` middleware fail-closed: INSERT `mcp_calls` row obrigatório por dispatch (try/except próprio — se INSERT falhar log.critical + sentry capture MAS NÃO propaga erro pro Brain caller)
- Cron 6h `detect_zombies()` — flagga `deprecated_at=NOW()` MCPs com `calls_30d=0` + Sentry warning (NUNCA remove)
- Endpoint `GET /api/observability/mcp-coverage` + `POST /api/mcp/registry/unflag` (owner unflag sazonal)

**Por que funciona solo no-code**: pull-based, owner inspeciona quando quer, npm deprecate pattern preserva guardrail "zero destrutivo". Reusa Postgres já deployado Hermes. Zero novo SaaS.

### 4.2 S1 — Hard Requirement + Phase F Grep-Audit + Degraded Gate

**Mitigações aplicadas após verdict owner_friction valid=false**:
1. **Reduzido pra UMA camada de enforcement ativa**: phase F validator em CI (sem PLAN.md literal triplicado, com runtime gate degradado-não-bloqueante)
2. **BANNED_PATTERNS movido pra `.claude/MCP-BANNED-PATTERNS.json`** declarativo (alinha checklist-driven existente `validate_implementation.py`)
3. **REQUIRED_PER_PHASE auto-derivado** via regex parse `PLAN.md` done_criteria seção "MCP HARD REQUIREMENTS (F.x)" — single source of truth, elimina drift hard-coded
4. **Runtime startup gate STRICT_MODE default=False** (env `HERMES_STRICT_MCP=1` só VM produção) — dev local não trava se gateway down, Brain entra modo `read_only_degraded`
5. **Hunter.io fallback documentado em GUARDRAILS.md ANTES virar hard requirement** (Task 6c F.7 NOVA): cache 30d verificações + degrade gracioso skip warmup se quota free 25/mês saturou OU rate-limit prospects 5/dia (=150/mês)

**Componentes**:
- `.claude/MCP-BANNED-PATTERNS.json` — patterns regex/AST (`import sentry_sdk`, `subprocess.*['gh'`, `requests.*api\.hunter\.io`, `from playwright`, `sqlite3\.connect.*cobaia`)
- `scripts/validate_implementation.py` phase F — NodeVisitor AST parse (mais robusto que regex puro) + coverage assertion auto-derivada
- `hermes_api_v2.py` lifespan startup gate — log warning + `app.state.brain_mode='read_only_degraded'` se MCPs required ausentes (NÃO `sys.exit(1)` por default)
- PLAN.md done_criteria patches F.4/F.7/F.9 (ver § 5)

### 4.3 S3 — Audit Mensal Reflexivo

**Cron**: `0 9 15 * *` (dia 15 9h BRT — evita janela cobaia F.7 deploy semana 1)
**Output**: `.claude/audits/mcp-coverage/MCP-COVERAGE-{YYYY-MM}.md` versionado git
**Componentes**:
- `scripts/mcp_coverage_audit.py` 7 fases: (1) fetch_gateway_inventory + AgentMemory MCPs PC/VM:3111 (fecha gap reconciliação F.5), (2) fetch_otel_usage(90d) Sentry Performance API, (3) fetch_chapter_expected regex parse PLAN.md, (4) classify_tools tier (active/warning 14d/deprecated 30d/quarantine 60d/orphan/drift), (5) render_markdown TL;DR + tables, (6) POST /api/mcp/coverage/publish surface F.8, (7) Sentry weekly digest agrupado (NÃO 1 alert por tool)
- Threshold sazonalidade: `seasonal_active_when TEXT[]` em mcp_registry (ex `['F.7.running']`) — cron SKIP MCPs sazonais quando chapter owner não ativo
- Audit complementar daily lightweight (drift-only sem MD render, ~30s execução) cobre breaking-change gap

**Owner intervenção real estimada**: 30min triagem MD/mês + 1h investigação se drift > 3 + 30min ad-hoc unflag sazonal = **~1.5h/mês total**

---

## 5. Fix per Chapter — PLAN.md Patches Específicos

### 5.1 F.4 Auto-Skill Loop

```markdown
### F.4 done_criteria (ADD)

MCP HARD REQUIREMENTS (F.4):
- Task 2 skill_proposals CRUD via mcp.hermes-skills.* (F.5 gateway)
- Task 3 PR-based deploy via mcp.github.create_pull_request
  (PROIBIDO: subprocess gh CLI, requests api.github.com direto)
- Task 7 auto-disable via mcp.sentry.list_issues
  (PROIBIDO: sentry-sdk Python direto, requests sentry.io)
- Primeira skill proposal invoca ≥2 MCPs distintos (prova orchestration)
- mcp_coverage.calls_7d > 0 para github+sentry+hermes-skills antes done
```

Phase F validate_implementation.py grep-audit bloqueia merge se detectar imports/subprocess banidos em `core/skill_proposals.py` + `core/auto_skill_*.py`. BANNED_PATTERNS em `.claude/MCP-BANNED-PATTERNS.json` (declarativo, owner edita JSON sem tocar Python).

### 5.2 F.5 MCP Foundation

**Task 5b NOVA** — Seed `mcp_registry` idempotente 9-12 rows:
```sql
INSERT INTO mcp_registry (mcp_name, mcp_kind, chapter_owner, required_by_dc) VALUES
  ('contextforge',     'infra',  'F.5', ARRAY['F.5.done']),
  ('github',           'public', 'F.4', ARRAY['F.4.done']),
  ('sentry',           'public', 'F.4', ARRAY['F.4.done','F.7.done']),
  ('postgres',         'public', 'F.6', ARRAY['F.6.done','F.7.done']),
  ('playwright',       'public', 'F.3', ARRAY['F.3.done']),
  ('omnisearch',       'public', 'F.7', ARRAY['F.7.done']),
  ('hunter',           'public', 'F.7', ARRAY['F.7.done']),
  ('whatsapp',         'public', 'F.7', ARRAY['F.7.done']),
  ('hermes-linkedin',  'custom', 'F.7', ARRAY['F.7.done','F.9.done']),
  ('hermes-prospects', 'custom', 'F.7', ARRAY['F.7.done','F.9.done']),
  ('hermes-skills',    'custom', 'F.4', ARRAY['F.4.done','F.9.done'])
ON CONFLICT (mcp_name) DO UPDATE SET chapter_owner=EXCLUDED.chapter_owner, required_by_dc=EXCLUDED.required_by_dc;
```

**Task 5c NOVA** — Editar PLAN.md done_criteria F.4/F.7/F.9 com cláusulas MCP HARD REQUIREMENTS literais + implementar `validate_implementation.py` phase F (AST parse banned patterns + coverage assertion auto-derivada regex parse PLAN.md, NÃO hardcoded).

**Task 7 NOVA** — Deploy `scripts/mcp_coverage_audit.py` + cron `mcp__scheduled-tasks__create_scheduled_task` (`0 9 15 * *`) + endpoints `GET /api/mcp/coverage/latest` + `POST /api/mcp/coverage/publish`.

**Done_criteria F.5 ADD**:
```markdown
- mcp_registry seeded ≥9 rows com chapter_owner + required_by_dc
- audit mensal gera MCP-COVERAGE-{YYYY-MM}.md tier classification 12/12 meses
- GET /api/mcp/gateway/tools expõe server+tool list consumível painel F.8 (schema {server, tool, version, registered_at})
- Runtime startup gate STRICT_MODE default=False (HERMES_STRICT_MCP=1 só VM prod)
```

### 5.3 F.6 Cérebro Hermes

```python
# core/tools.py — ToolRegistry.invoke() middleware fail-closed
async def invoke(self, tool_name: str, **kwargs) -> dict:
    mcp, tool = self._resolve(tool_name)
    chapter = ctx.get('caller_chapter', 'unknown')
    t0 = time.monotonic()
    trace_id = otel.start_span('gen_ai.tool.execute',
                                attrs={'gen_ai.tool.name': tool,
                                       'mcp.server.name': mcp})
    try:
        result = await self.gateway.call(mcp, tool, **kwargs)
        status = 'ok'
        return result
    except asyncio.TimeoutError:
        status = 'timeout'; raise
    except Exception:
        status = 'err'; raise
    finally:
        try:
            await db.execute("""INSERT INTO mcp_calls(mcp_name,tool_name,caller_chapter,
                context_id,latency_ms,status,cost_usd,otel_trace_id) VALUES($1,$2,$3,$4,$5,$6,$7,$8)""",
                mcp, tool, chapter, ctx.context_id,
                int((time.monotonic()-t0)*1000), status, ctx.cost_estimate, trace_id)
        except Exception as audit_err:
            log.critical(f"mcp_calls INSERT failed: {audit_err}")
            sentry_sdk.capture_exception(audit_err)
            # NÃO propaga — audit não pode quebrar Brain decision
```

**Done_criteria F.6 ADD**:
```markdown
- mcp_calls row gravada por invoke (fail-closed audit, INSERT erro NÃO propaga)
- OTel GenAI span emitido por tool dispatch (gen_ai.tool.execute schema canônico)
- Brain.decide() schema output {intent, tool_name, args, confidence} validado pydantic ANTES dispatch
- Confidence floor configurável via PrefPanel + pref_keys (default 0.7) — skip auto-execute, enfileira owner_confirm
- mcp.postgres.query read-only (já no done_criteria atual)
```

### 5.4 F.7 Cobaia Live Ops

```markdown
### F.7 done_criteria (ADD)

MCP HARD REQUIREMENTS (F.7):
- Task 6 OBRIGATÓRIA Hunter.io: mcp.hunter.verify_email via gateway antes warmup email
  (PROIBIDO: requests.get api.hunter.io)
- Task 6b NOVA Omnisearch: mcp.omnisearch.search discovery PMEs Cuiabá
- Task 6c NOVA Hunter fallback DOCUMENTADO em GUARDRAILS.md ANTES Task 6 hard:
    * Cache 30d verificações em mcp_hunter_cache table
    * Degrade gracioso skip warmup se quota free 25/mês saturou
    * Rate-limit prospects 5/dia (=150/mês) modo conservador
- Task 7 Sentry: mcp.sentry.capture_exception via gateway (NÃO sentry-sdk Python)
- Task 9 NOVA Postgres MCP Pro: cobaia_metrics_collector.py via mcp.postgres.query read-only
  (PROIBIDO: sqlite3.connect bare)
- Daemon F.7 dispara LinkedIn via mcp.hermes-linkedin.* (NÃO patchright direto)
- mcp_coverage.calls_7d > 0 para hunter+sentry+omnisearch+postgres+hermes-linkedin
- Widget cobaia-status mostra latest MCP-COVERAGE-{YYYY-MM}.md link
```

### 5.5 F.8 Observability

**Schema migration NOVA** (incluída em F.8 task_2 LLM cost middleware):
- `mcp_registry`, `mcp_calls` (PARTITION BY RANGE(called_at) mensal + retention 90d auto-drop pg_partman), `mcp_coverage` mat view

**Endpoints NOVOS**:
- `GET /api/observability/mcp-coverage` (rows + idle_30d + deprecated)
- `GET /api/observability/mcp-coverage/history?months=6` (sparkline tier transitions)
- `GET /api/observability/mcp-coverage/audits` (lista MCP-COVERAGE-{YYYY-MM}.md links versionados git)
- `POST /api/mcp/registry/unflag` (owner unflag sazonal)

**Task 5d NOVA**: TabMcpCoverage 5ª tab observability shell (ver § 7)

**WS namespace extension**: `obs.mcp_coverage_gap` event quando startup gate detecta MCPs faltando + phase F grep-audit bloqueia commit

**Integration ErrorInboxHandler**: phase F violations gravam `errors_inbox` category=`'mcp_bypass'` aparecem cross-tab Errors

**Sentry alert config**: weekly digest agrupado "MCPs zombie esta semana" (NÃO 1 capture_message por MCP — reduz noise inbox owner solo)

**Done_criteria F.8 ADD**:
```markdown
- Painel MCP coverage por chapter (5ª tab observability)
- Audit mensal histórico navegável via /api/observability/mcp-coverage/audits
- Drift count > 3 = Sentry warning weekly digest
- ZERO write bypass detectado phase F últimos 30d (errors_inbox category='mcp_bypass' count=0)
```

### 5.6 F.9 Pipeline Studio

**Task 1b NOVA**: tool registry source = F.5 gateway `/tools` endpoint (NÃO scan local `skills/`) + assert smoke test pipeline-studio expõe ≥6 MCPs distintos como first-class steps

**Done_criteria F.9 ADD**:
```markdown
- Step library JOIN mcp_registry exibe badge chapter_owner + last_used + tier
  (badge 'idle 60d+' WARN não bloqueia — industry passive flag)
- ZERO tool hardcoded local — todas source = F.5 gateway /tools endpoint
- Skill forge runner reject promotion se skill referencia tool tier=quarantine OR orphan
- Pipeline run grava mcp_calls.caller_chapter='F.9'
- Métrica orgânica (NÃO ≥6 hard): smoke test mede MCPs usados em pipelines REAIS owner cria
  primeiras 2 semanas, gate só se <3 (evita gaming step library com noise mcp.sentry decorativo)
```

---

## 6. Workflow Recurrent Design — `scripts/mcp_coverage_audit.py`

**Trigger**: `mcp__scheduled-tasks__create_scheduled_task` cron `0 9 15 * *` (dia 15 9h BRT)

**Por que dia 15 e não dia 1**: evita janela cobaia F.7 deploy semana 1 (alta volatilidade calls), pega ciclo médio mês após estabilização

**Fases (7)**:

1. **`fetch_gateway_inventory()`** — `GET /api/mcp/gateway/tools` lista TODAS tools registradas. **+ AgentMemory MCPs PC:3111 + VM:3111** incluídos via config explicit list `EXTRA_MCP_NAMES=['agentmemory-pc','agentmemory-vm']` (fecha gap reconciliação F.5)

2. **`fetch_otel_usage(90d)`** — query Sentry Performance API por `gen_ai.tool.execute` spans com aggregation `count + p95_latency + error_rate + last_seen` por `(mcp_name, tool_name)`. Fonte canônica RUNTIME complementa `mcp_calls` DB (cross-check S2 detecta drift entre OTel telemetry e DB audit)

3. **`fetch_chapter_expected()`** — regex parse `.claude/IMPLEMENTATION-PLAN.md` done_criteria seções `MCP HARD REQUIREMENTS (F.x)` extrai promessas formato canônico `mcp.<server>.<tool>` (single source of truth, REQUIRED_PER_PHASE NÃO hardcoded em Python)

4. **`classify_tools()`** — tier per `IDLE_THRESHOLDS` configurável `.claude/mcp-audit-config.json` (default warning=14d, deprecated=30d, quarantine=60d) + sazonalidade exception list (Hunter idle entre cobaias skip quarantine se `F.7.running=false`):
   - **active**: `calls_7d > 0`
   - **warning**: 14d idle
   - **deprecated**: 30d idle (mcp_registry.deprecated_at flagged)
   - **quarantine**: 60d idle
   - **orphan**: zero use + sem promessa chapter
   - **drift**: chapter promete + zero use (= violação cross-chapter mais importante)

5. **`render_markdown()`** — output `.claude/audits/mcp-coverage/MCP-COVERAGE-{YYYY-MM}.md` versionado git:
   - TL;DR topo: "X quarantine, Y drift, Z action required, $W/mês potential waste"
   - Summary stats table
   - Tables por tier com colunas: MCP | Tool | Days Idle | Promised By | Subscription Cost USD/mês | Recommended Action

6. **`publish_dashboard()`** — `POST /api/mcp/coverage/publish` surface no F.8 dashboard (pull-based, NUNCA push alert)

7. **`sentry_digest()`** — warning APENAS se `drift count >= 3` (threshold evita noise baseline imaturo). Weekly digest agrupado. Output secundário: notify Sentry tier=quarantine com `subscription_cost_usd_monthly > 0` (Apollo/Hunter) subject especial "PAID MCP zombie {name} 30d idle = ${X}/mês waste" — owner age ANTES próximo billing cycle

**Audit complementar daily lightweight** (`scripts/mcp_drift_quickcheck.py`): drift-only sem MD render, ~30s execução, custo $0 marginal. Cobre gap breaking-change detecção que mensal não captura.

**Owner intervenção real**: ~30min/mês triagem MD + ~1h/mês investigação se drift > 3 + 30min ad-hoc unflag sazonal = **~1.5h/mês total** (mensurável via session logs `hermes-status` skill)

---

## 7. Dashboard Widget Spec — `/observability/mcp-coverage`

**Localização**: 5ª tab observability shell F.8 ao lado Costs / Performance / Errors / Decisions

**Layout 4 seções vertical**:

### 7.1 TOP — SummaryRow (5 cards horizontais)
| Card | Valor | Visual | Refresh |
|------|-------|--------|---------|
| TotalMCPs | 9-12 | número grande | 5min |
| Active | sparkline `calls_7d` verde | mini Chart.js | 5min |
| Drift | count vermelho se >0 | badge alert + link investigation | 5min + WS push |
| Quarantine | count amarelo | badge warning | 5min |
| PaidIdle | $/mês desperdício potencial | $XX vermelho | 5min |

### 7.2 MEIO — MatrixCoveragePanel
Heatmap **Phase (F.4/F.5/F.6/F.7/F.8/F.9) × MCP (rows seed mcp_registry)**:
- Célula **verde** = `calls_7d > 0`
- Célula **vermelha** = `required_by_dc contém phase MAS calls_7d=0` (drift)
- Célula **cinza** = não required
- Hover célula → tooltip `last_used + calls_7d + p95_latency`
- Reusa pattern TabCosts grid Chart.js vendor local

### 7.3 BAIXO — MCP List Table
Colunas: `MCP Name | Kind (badge public/custom/infra) | Chapter Owner | Tier (color-coded) | calls_24h | calls_7d | calls_30d | Last Used (relative) | Subscription Cost $/mês | Actions`
- **Sortable** por `calls_7d desc` default
- **Filter tabs**: All | Active | Idle 30d | Deprecated | Drift | Paid
- **Actions**: botão "Unflag" se `deprecated_at not null` + link audit MD mensal mais recente

### 7.4 HISTORICO — SparklineHistory
6 meses tier transitions per MCP linha sparkline (active=verde, warning=amarelo, deprecated=laranja, quarantine=vermelho) — owner visualiza migration patterns sazonais Hunter ramp-up/down

### 7.5 Backend
- `GET /api/observability/mcp-coverage` (data principal, refresh 5min mat view)
- `GET /api/observability/mcp-coverage/history?months=6` (sparkline)
- `GET /api/observability/mcp-coverage/audits` (lista MD links versionados git, render inline via marked.js)
- WS namespace `obs.mcp_coverage_gap` event push REAL-TIME se startup gate detecta MCPs required faltando OU phase F grep-audit bloqueia commit
- Integration `ErrorInboxHandler`: phase F violations gravam `errors_inbox` category=`'mcp_bypass'` aparecem cross-tab Errors

### 7.6 Constraints
- Data source primary: `mcp_coverage` materialized view Postgres (S2)
- Refresh: mat view 5min + WS push event-driven
- Auth: loopback only (admin UI ContextForge pattern F.5)
- Tech reuse: Chart.js vendor local, SummaryWidget pattern F.8, TabsContainer extensibility (**validar refactor não previsto F.8 task_5a — possível blocker**)
- Friction owner: pull-based, abre quando quer, badge SummaryRow surface drift sem precisar entrar tab

---

## 8. Success Criteria Mensuráveis

1. **Coverage sustentada**: Cada MCP em `mcp_registry` com `required_by_dc` não-vazio tem `calls_7d > 0` sustentado por **3 audits mensais consecutivos** (≥3 meses produção F.7 cobaia). Sem isso = drift permanente, owner remove promessa do PLAN.md OU corrige integração

2. **Zero bypass detectado**: Phase F `validate_implementation.py` grep-audit ZERO bypass (`import sentry_sdk`, `subprocess gh`, `requests.get api.hunter.io|api.github.com|api.openai`) em commits F.4/F.7/F.9 **últimos 30 dias** — mede via CI logs + `errors_inbox category='mcp_bypass' count=0`

3. **Brain dispatcher coverage OTel 100%**: `Brain.tools.invoke()` emite `gen_ai.tool.execute` spans em 100% dos dispatches — assert via integration test obrigatório F.6 (sem isso S3 audit cego false-positive orphan)

4. **ROI subscription cancelada**: ≥1 subscription paga zombie detectada e cancelada por S3 audit mensal nos **primeiros 6 meses produção** (Hunter $49 OU Apollo $50 se contratado) — payback dev investment ~6.5 sub-sessões

5. **Diversidade MCP ativa**: `mcp_coverage` panel F.8 mostra **≥6 MCPs distintos categoria 'active'** (`calls_7d > 0`) sustentado: 3 custom (hermes-linkedin/prospects/skills) + 3 públicos (github/postgres/sentry) — prova F.5 gateway operacional + F.6 Brain consumindo realmente

6. **Audit mensal ininterrupto**: MCP-COVERAGE-{YYYY-MM}.md gerado e versionado git **12/12 meses ano calendário** — cron scheduled-tasks MCP zero falhas execução

7. **Owner friction ≤ budget**: Intervenção manual coverage tracker **≤2h/mês** (30min triagem + 1h investigação + 30min ad-hoc) — mede via session logs `hermes-status` skill

8. **Sentry digest baseline saudável**: Weekly digest "MCPs zombie" count médio **≤2 MCPs idle/semana** após 3 meses estabilização (baseline imaturo aceita >2 nas primeiras 6 semanas) — prova ecosystem MCP saudável não bloated

9. **Hunter quota não saturada**: Hunter.io quota free tier 25 verifs/mês NÃO saturada ANTES Plan B fallback ativar — mede via `Hunter.usage_count_mtd <22` sustentado 6 meses cobaia

---

## 9. Rollback Plan

Se enforcement causar fricção owner intolerável (**sinais**: >2h/mês intervenção manual sustentado 2 meses, ≥3 false-positives drift/mês exigindo investigação infrutífera, `hermes_api` recusa boot frequente dev local por startup gate, owner verbaliza burnout enforcement noise) — reverter em **CAMADAS reversíveis sem perder ganho observability core**:

### Tier 1 — Disable runtime startup gate (PRIMEIRO)
- `env HERMES_STRICT_MCP=0` ou remove gate completo de `hermes_api_v2.py` lifespan
- Brain inicia mesmo gateway down em `READ_ONLY` mode degraded
- Mantém: S2 + S3 + S1 camadas 1-2 (PLAN.md textual + phase F validator CI)
- **Loss: ZERO** — startup gate era cosmético

### Tier 2 — Phase F BLOCKING → WARNING (SEGUNDO)
- Se phase F grep-audit causar false-positives intoleráveis
- Editar `validate_implementation.py` phase F: `return True` sempre + log apenas violations
- PR comment + `errors_inbox` row, NÃO bloqueia merge
- Owner revisa weekly digest, ack manual
- Mantém: S2 (audit DB) + S3 (mensal MD) + S1 textual
- **Loss: parcial** — bypass detection vira opt-in owner

### Tier 3 — Pausar cron S3 audit mensal (TERCEIRO)
- Se MD ignorado 3 meses seguidos por owner (zero ack tier=quarantine)
- Pausar via `mcp__scheduled-tasks__update_scheduled_task disable`
- Remover painel F.8 TabMcpCoverage badge SummaryWidget alert
- Mantém: S2 `mcp_calls` table + endpoint `GET /api/observability/mcp-coverage` on-demand (owner consulta quando suspeita)
- **Loss: cadência reflexiva** — vira modo reativo

### Tier 4 — S2 fail-closed → fail-open (ÚLTIMO)
- Se middleware F.6 detectado quebrando Brain decisions em prod (`mcp_calls` INSERT erro propagando incorretamente apesar try/except)
- Trocar fail-closed por fail-open (`try/except` amplo + log warning + continue) em `core/tools.py invoke()`
- Perde garantia audit completo MAS preserva Brain reliability
- Mantém: schema + endpoints + S3 audit (com gaps)
- **Loss: audit pode ter holes ~1-5% calls em produção**

### Critério Reverso Re-ativar
Se rollback ativado, re-survey mensal `/hermes-mcp-survey` skill verifica se ecosystem MCP cresceu >15 MCPs OU bypass volume detectado via Sentry > 5 events/mês — re-ativar camada disabled mais recente primeiro (LIFO).

### Documentação obrigatória
Cada rollback em `.claude/audits/mcp-coverage/ROLLBACK-{YYYY-MM-DD}.md` com razão + métrica trigger + camadas afetadas + plano re-ativação — preserva memória institucional pra owner futuro.

---

## 10. Cross-References + Approval Checklist Owner

### 10.1 Cross-references

| Documento | Seção | Relação |
|-----------|-------|---------|
| `.claude/IMPLEMENTATION-PLAN.md` | F.4 / F.5 / F.6 / F.7 / F.8 / F.9 done_criteria | Patches § 5 deste doc |
| `.claude/GUARDRAILS.md` | NOVA seção "MCP-routing enforcement" | Adicionar regra "NUNCA import sentry_sdk/subprocess gh/requests.get api externa direto — sempre via ToolRegistry.invoke" |
| `.claude/MCP-LANDSCAPE.md` | Survey output skill `hermes-mcp-survey` | Re-survey trigger mensal cron, alimenta `mcp_registry` updates |
| `.claude/PHASE-F-STUDY-SYNTHESIS.md` | "NUNCA expor 15 MCPs ao agent. Compor atrás de 1 gateway" | Enforcement mecânico dessa diretiva |
| `scripts/validate_implementation.py` | phases A-E existentes | Adicionar phase F (esta proposta) |
| `.claude/MCP-BANNED-PATTERNS.json` | NOVO arquivo | Declarativo JSON, alinha checklist-driven |
| `.claude/mcp-audit-config.json` | NOVO arquivo | IDLE_THRESHOLDS + sazonalidade exceptions |
| `.claude/audits/mcp-coverage/` | NOVO diretório | Output MCP-COVERAGE-{YYYY-MM}.md versionados git |
| Skill `hermes-mcp-survey` | Existente | Trigger mensal automatizado via cron |
| Skill `hermes-status` | Existente | Adicionar MCP coverage snapshot |
| Skill `hermes-brain-test` | Existente | Adicionar phase G (OTel span assertion runtime Brain.decide) |

### 10.2 Approval Checklist Owner

Antes implementar primary combo (S2+S1+S3), owner Caio confirma:

- [ ] **Schema mcp_registry seed F.5**: lista 9-12 MCPs com `chapter_owner` + `required_by_dc[]` revisada e aprovada (§ 5.2)
- [ ] **Hunter.io fallback Plan B documentado** em GUARDRAILS.md ANTES Task 6 F.7 virar hard requirement (cache 30d + rate-limit 5/dia OU upgrade paid $49)
- [ ] **F.8 task_5d TabMcpCoverage** aprovada (+1 sub-session F.8 — 10-12 sessões já estouradas, owner aceita extensão)
- [ ] **Runtime startup gate STRICT_MODE default=False** confirmado (env `HERMES_STRICT_MCP=1` só VM prod, NÃO dev local)
- [ ] **BANNED_PATTERNS.json declarativo** confirmado (NÃO hardcoded em Python — alinha checklist-driven existente)
- [ ] **REQUIRED_PER_PHASE auto-derivado** via regex parse PLAN.md (NÃO hardcoded validator)
- [ ] **Cron audit dia 15** confirmado (NÃO dia 1 — evita janela cobaia F.7 semana 1)
- [ ] **Sentry weekly digest** confirmado (NÃO 1 alert por MCP — reduz noise inbox solo)
- [ ] **F.9 critério orgânico** (smoke test mede MCPs reais primeiras 2 semanas) confirmado, NÃO hard ≥6 (evita gaming)
- [ ] **AgentMemory MCPs PC+VM :3111** incluídos via config explicit list `EXTRA_MCP_NAMES` no `mcp_coverage_audit.py` (fecha gap reconciliação F.5)
- [ ] **Rollback plan tiered** revisado (§ 9) — owner confirma tem autonomia desativar camadas se fricção intolerável
- [ ] **Success criteria** (§ 8) revisados — owner concorda com 9 métricas mensuráveis (especialmente ROI ≥1 subscription cancelada em 6 meses)

### 10.3 Sequência de Execução Recomendada

1. **F.5** (Task 5b seed + 5c PLAN.md patches + 7 cron audit) — fundação
2. **F.6** (middleware fail-closed `ToolRegistry.invoke`) — coluna runtime
3. **F.8** (schema migration + endpoints + TabMcpCoverage) — observability surface
4. **F.4** (skill_proposals via mcp.hermes-skills, GitHub MCP, Sentry MCP) — primeiro chapter consumer real
5. **F.7** (Hunter + Omnisearch + Postgres MCP + hermes-linkedin via gateway) — maior consumer
6. **F.9** (step library JOIN mcp_registry + smoke test orgânico) — último consumer

**Total effort estimado**: ~6.5 sub-sessões spread cross-chapter, ZERO sessão standalone nova. **ROI break-even**: 6-8 meses (1 subscription paga zombie detectada).

---

**FIM DO DOCUMENTO**

> Owner Caio: revisar approval checklist § 10.2, marcar items confirmados, retornar para start F.5 Task 5b. Dúvidas → spawn task ou abrir discussão `discussion/mcp-enforcement`.
