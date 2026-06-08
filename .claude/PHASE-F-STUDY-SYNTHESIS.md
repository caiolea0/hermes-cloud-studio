# Síntese do Estudo Profundo Fase F (2026-06-08)

> Input destilado dos 5 agents Explore executados antes do workflow phase-orchestrator.
> Agents do workflow devem LER este arquivo em vez de re-investigar do zero.

---

## 1. FRONTEND REAL (dashboard/app.js 276KB, 271 fetch calls)

### Páginas × Status
| Página | Status | Real-time |
|---|---|---|
| control (Mission) | Funcional | 70% real-time (atividade+canais WS); **timeline+decisions são polling-only stale** |
| dashboard | Funcional | Auto-refresh 30s; sem WS pra stats principais |
| prospects | Funcional | Paginação manual; filtros não persistem em URL |
| proposals | **Parcial** | "Marcar Enviado" é toggle local-only sem persist backend |
| audit | Funcional | Polling 3s rodando; sem auto-trigger pós-import |
| pipeline | Funcional | Watcher ativo; SEM botão Stop/Cancel |
| tasks | Funcional | Ações disparam mas sem polling feedback de status |
| skills | Funcional | Toggle local; sem WS skill_toggled |
| memory | Funcional CRUD | Sem busca, sem tags |
| missions | Funcional | Calendário estático, sem live updates |
| **linkedin** | **Parcial** | Comment edit/delete são STUBS (UI placeholder) |
| claude | Funcional | Terminal sem contexto outras páginas |

### TOP 10 GAPS UX (priorizado por impacto)
1. **[ALTO]** Mission Control Timeline/Decisions stale (polling-only, sem WS)
2. **[ALTO]** Proposals "Sent" state local-only (sem POST persist)
3. **[MÉDIO]** LinkedIn comment edit/delete stubbed (UI sem backend)
4. **[MÉDIO]** Audit sem auto-trigger pós-import
5. **[MÉDIO]** Tasks queue sem polling feedback ação
6. **[MÉDIO]** Prospects sem deep-link state (URL filtros)
7. **[BAIXO]** LinkedIn cooldown countdown local + 30s polling
8. **[BAIXO]** Pipeline execution sem Stop/Cancel button
9. **[BAIXO]** Memory facts sem busca/tags
10. **[BAIXO]** Skills sem loading state + WS

### Mission Control real-time hoje
- ✅ WS: daemon_state (10s poll), channel_update, activity, reply_received
- ❌ HTTP-only static: timeline, decisions, log
- ❌ Sem botão: Play/Pause daemon, channel toggle, clear decisions, archive activity
- **Crítica**: cockpit ao vivo quebra quando narrativas (timeline/decisions) ficam stale até reload

---

## 2. BACKEND MATURIDADE (140+ rotas PC + VM)

### 11 ENDPOINTS FANTASMA (sem UI — ouro a expor F.1)
1. `/api/prospects/{id}/resolve-conflict` — MERGED-006 conflict sync
2. `/api/tasks/bulk` — bulk update pronto, não exposto
3. `/api/stats` — pipeline_stats histórico 7 dias
4. `/api/daemon/state` — energy + current_task
5. `/api/daemon/log` — live feed (WS-ready)
6. `/api/daemon/decisions` — IA reasoning audit
7. `/api/daemon/channels` — health cards quota
8. `/api/daemon/timeline` — 24h activity heatmap
9. `/api/linkedin/visited` — profile history
10. `/api/linkedin/comment/{edit|delete}` — comment management
11. `/api/agent-zero/{status|chat}` — wrapper Agent Zero inativo

**OURO: api/daemon/* (5 endpoints) = framework Mission Control oculto**, fundação pra F.2.

### Validações fracas detectadas
- prospects.py bulk_action não valida IDs contra DB
- scraper.py parse-prompt fallback sem JSON strict
- linkedin.py `_compute_schedule_state` sem timeout recovery se VM lenta

### Auth gaps
- bootstrap.py loopback OK mas HTTP sem cert pinning
- internal.py auth só por IP (127.0.0.1) — SSH tunnel = spoof risk teórico

---

## 3. CÉREBRO HERMES HOJE (decisão arquitetural F.6)

### Modelo atual
**Rule-based priority queue HARD-CODED por hora** em `daemon/orchestrator.py::decide_next_action()`:
- P1 07-20h: pending replies → _classify_reply_intent (Ollama qwen2.5:3b)
- P2 08-18h dia útil: sequence steps
- P3 06-22h: enrichment batch
- P4 00-06h ou pipeline vazia: discovery scrape
- P5 00-07h/20-23h: batch audit
- P6 22-23h: score recalc
- P7 Dom 19-21h: weekly report

### Gaps pra cérebro real-time
| Aspecto | Hoje | F.6 Necessário |
|---|---|---|
| Decisão | P1-P7 hardcoded | Classifier dinâmico: "o que fazer AGORA?" |
| Feedback loop | Log descartado, energia 1.0→0 linear | Task result → score → next_action |
| Agent Zero | Isolado no chat dashboard | Daemon consulta Agent Zero pra tasks complexas |
| Tool registry | Skills YAML scattered | core/tools.py namespace único |
| Multi-agent | Daemon solo | Orquestrador chama sub-agents |

### REUSO vs REESCRITA por componente
- **decide_next_action()**: ESTENDER — encapsula em `Brain.decide()` + classifier Ollama
- **execute_task()**: ESTENDER — adiciona tool_registry + execute_tool dinâmico
- **_classify_reply_intent()**: REFACTOR — generaliza pra `Brain.classify(text, categories)`
- **PipelineRunner**: REUSE TOTAL (ouro nuclear)
- **OllamaRouter**: ESTENDER — bridge MCP + skill invocation
- **WS broadcast**: ESTENDER — enriquece com decision_rationale + tool_calls

### Decisão arquitetural F.6
**Criar `core/brain.py` NOVO** (decisão pura, classifier, action selector, reward — testável isolado).
**Manter `daemon/orchestrator.py`** (state machine, sleep, error recovery — infra estável).
**Adicionar `core/tools.py`** — registry unificado: skills + MCPs + pipelines + endpoints.
Integrar Agent Zero como **decision maker** (não fallback).

```python
class Brain:
    async def decide(self, context: DaemonContext) -> Task: ...
    async def classify(self, text, categories, context) -> str: ...
    async def evaluate_result(self, task: Task, result: dict) -> float: ...

class ToolRegistry:
    skills: dict[str, SkillDef]
    mcps: dict[str, MCPDef]
    pipelines: dict[str, PipelineStep]
    endpoints: dict[str, EndpointDef]
    async def invoke(self, tool_name: str, **kwargs) -> dict: ...
```

---

## 4. MCP ECOSYSTEM 2026

### TOP 10 INTEGRAR
1. **Playwright MCP (MS)** github.com/microsoft/playwright-mcp — 33k stars — navigate/click/snapshot/eval/network — fallback browser pra QA flows
2. **Apollo.io MCP** thevgergroup/apollo-io-mcp — search_people/enrich/sequence_create — enrichment PME Cuiabá
3. **Hunter.io MCP** NimbleBrainInc/mcp-hunter — domain_search/email_finder/verifier — reduz bounce email
4. **Firecrawl MCP** firecrawl-dev/firecrawl-mcp — scrape/crawl/deep_research/extract — qualificação ICP
5. **Exa MCP** exa-labs/exa-mcp — web_search/find_similar — semantic search empresas
6. **Postgres MCP Pro** crystaldba/postgres-mcp — query/explain/perf_analyze — read-only safe
7. **Slack MCP oficial** (GA fev/2026) — notificações deal won
8. **GitHub MCP oficial** github/github-mcp-server — self-improvement loop F.4 (Hermes abre PRs)
9. **MCP Omnisearch** spences10/mcp-omnisearch — unified Tavily+Brave+Exa+Firecrawl+Kagi
10. **AgentMail MCP** agentmail.to — inbox próprio agents

### 3 MCPs CUSTOM DESENVOLVER
1. **`hermes-linkedin-mcp`** (CRÍTICO — moat técnico): wrap Patchright+stealth+limiter+cooldown. Tools: send_connection_request, send_inmail, scrape_profile, search_sales_navigator, get_inbox, warmup_action. Permite reuso em workflows + MCP Inspector debug.
2. **`hermes-prospects-mcp`**: search_prospects, score_lead, mark_converted, get_campaign_stats, enrich_pipeline(provider=apollo|hunter|firecrawl). Camada sobre Postgres + scoring ICP.
3. **`hermes-skills-mcp`**: propose_skill, test_skill_sandbox, promote_skill, list_skills_performance. Plumbing pra F.4 auto-skill loop.

### Frameworks/padrões
- **FastMCP 3.0 Python** (Jeremiah Lowin) — default Hermes (já Python stack). Decorator @mcp.tool, OAuth 2.1, OpenTelemetry
- **MCP Gateway** — NUNCA expor 15 MCPs ao agent. Compor atrás de 1 gateway que multiplex+auth+rate-limit. Hermes precisa `hermes-mcp-gateway` na VM
- **Streamable HTTP + OAuth 2.1** — abandona stdio puro pra produção
- **mcp-agent (Swarms)** — 10 orchestration architectures out-of-box. Útil F.6

### AVISOS RISCO
- **mcp-server-sqlite oficial**: NÃO usar prod (Anthropic marca como reference/educacional). Use Postgres MCP Pro
- **LinkedIn-Posts-Hunter-MCP** kevin-weitgenant: Playwright sem stealth, ban risk alto. NÃO conectar conta real
- **Apify wrappers**: lock-in marketplace, custo escala mal
- **Browser-use wrappers**: fragmentados/abandonados. Prefere Playwright oficial MS
- **Segurança 2026**: 30 CVEs em 60d, validator tool descriptions obrigatório. Allowlist por gateway

---

## 5. SKILLS + WORKFLOWS PATTERN

### Schema YAML canônico (8 campos obrigatórios)
```yaml
name: string                # kebab-case único
description: string         # 1 frase PT-BR
version: string             # semver
active: boolean
model: string               # "deepseek/...", "qwen3:8b", etc
provider: string            # "openrouter" ou "ollama"
temperature: float          # 0.5-0.7
max_tokens: integer         # 500-2000
system_prompt: |            # multiline rígido
triggers: [string]          # frases PT-BR
input_schema: object        # Pydantic-like, interpretado runtime
```

### GAPS no schema atual
- Sem versionamento evolutivo (todas v1.0)
- Sem `output_schema` explícito
- Sem `cost_budget_per_day` (skill pode estourar API)
- Sem retry policy / error handling declarativo
- Sem dependencies entre skills

### Sync VM mecanismo atual
- `/hermes-deploy` skill: scp seletivo + restart hermes-api + health check 5s + rollback se fail
- API hermes.py proxy GET/PATCH `/api/hermes/skills` → VM
- **Sem hot-reload** — skill nova exige restart

### Fluxo Auto-Skill Loop F.4 proposto
```
Hermes analisa execuções+erros → propõe skill YAML
  → tabela skill_proposals (status: draft)
  → dashboard mostra accept/reject/edit+test-lab
  → Lab test executa skill SANDBOX isolado (10+ fixture inputs incluindo injection)
  → Se 8+ passam: lab_result.status='lab_pass', owner Accept
  → Accept → POST /api/skill-proposals/{id}/deploy → scp staged + ssh validate + PATCH active
  → 10s polling confirma + rollback if error
  → 7 dias A/B test: sucesso_rate / latência_p99 / custo
  → Métrica boa: mantém ativa. Ruim: auto-disable + Telegram notify
```

### Schema `skill_proposals` SQL
```sql
CREATE TABLE skill_proposals (
  id UUID PRIMARY KEY,
  created_at TIMESTAMP,
  proposed_yaml TEXT NOT NULL,
  rationale TEXT,
  status TEXT,  -- draft|lab_pending|lab_pass|lab_fail|approved|rejected|active|disabled
  lab_result JSON,
  owner_notes TEXT,
  activated_at TIMESTAMP,
  disabled_at TIMESTAMP,
  metrics JSON
);
```

### RISCOS F.4 + mitigações
| Risco | Mitigação |
|---|---|
| Skill bugada passa lab (3 runs lucky) | 10+ fixtures parametrizadas + injection tests |
| Owner aprova sem ler YAML | Dashboard obriga VISUAL DIFF highlight deltas |
| Skill estoura crédito API | cost_budget_per_day no schema, rejeita se excede |
| Propõe alta freq | Cooldown 1x/dia máximo, acumula feedback |
| Silenciosamente bugada em prod | Auto-disable após 5+ erros + Telegram notify |
| Lab fixture fake vs prod real | Snapshot DB prod, wipe IDs, fixture realista |

### Padrão workflow (deep-audit.js exemplar — reusar pra phase-orchestrator)
- meta.phases declarativo
- Schemas estruturados (FINDINGS_SCHEMA, VERDICT_SCHEMA)
- `phase()` + `parallel()` + `pipeline()` + `agent({schema})`
- Multi-lens verify ≥2/3 valid (workflow novo usa ≥3/4 — rigor maior)

### Skills Claude Code (.claude/skills/) ≠ Skills YAML (skills/)
- **Claude Code**: SKILL.md procedimento determinístico PC-only (hermes-deploy, hermes-li-lab, etc)
- **YAML**: configuração LLM runtime VM-sync (linkedin-post-generator, etc)
- **Workflows** (.claude/workflows/): JS multi-agent orchestration (deep-audit, li-anti-detection)

---

## 6. EXPECTATIVAS OWNER (síntese entrevista + contexto)

### EXPLÍCITAS
1. Operar TUDO no-code via UI (zero CLI)
2. Real-time TOTAL controle (WS, sem polling stale)
3. Cérebro Hermes despacha multi-tool, executa na VM, Claude Code orquestra PC
4. Descobrir + integrar MCPs novos + desenvolver custom benéficos
5. Auto-skill loop (Hermes evolui sozinho sem owner gargalo)
6. UI muito mais capaz: pipelines configuráveis, interativos, bonitos, 100% monitoráveis

### IMPLÍCITAS (deduzidas)
- Revenue real (PMF B2B Cuiabá não validado ainda — cobaia viva mas zero outreach)
- Owner solo, escala via Hermes
- Conta Caio sagrada (insubstituível)
- Zero API paga além Claude (assinatura Max)
- VM-GPU pendente (decisão financeira futura)
- Hermes vira produto multi-projeto eventualmente?

### RESTRIÇÕES INVIOLÁVEIS
- 20/22 findings PASS preservados (Fases A-D + E.1 + E.2 XSS)
- GUARDRAILS regras: PC vs VM, tunnel, fail-closed auth, regression-test gate
- Sem mocks/stubs em testes
- Backend bem-resolvido — F.4-F.9 não devem regredir A-D
- Cada toque em código MADURO exige pre+post test

---

## 7. ÁREAS MADURAS (regression-test gate)

Qualquer task Fase F que toque essas áreas EXIGE pre_test + post_test + validate --phase A B C D E antes/depois:

- `core/{state,models,ai,pipeline,limiter}.py` + `core/brain.py` (futuro)
- `loops/*` (6 loops PC pós-MERGED-011)
- `api/*` (10+ routers PC)
- `vm_api/routes.py` (VM consolidado)
- `linkedin/{stealth,human,limiter,account_profile,preflight,stealth_compliance,ollama_router}.py`
- `channels/email/*` (recém-maduro E.1 MERGED-010)
- `daemon/orchestrator.py`
