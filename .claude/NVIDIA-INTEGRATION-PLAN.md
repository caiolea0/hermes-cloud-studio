# NVIDIA NIM Integration Plan — Hermes Cloud Studio

> **Status**: Planejamento canônico (zero código) — pendente owner approval D1–D6
> **Autor**: Sessão B dedicada planejamento NVIDIA NIM (2026-06-11)
> **Versão**: 1.0
> **Escopo**: Integrar NVIDIA NIM API como 3o provider routing chain (Ollama PC + OpenRouter + **NIM cloud**) sem touch BLACKLIST R2 nem `linkedin/ollama_router.py`
> **Cross-ref**: `.claude/PLAN.md` F.5/F.6/F.7/F.8/F.9 · `.claude/MCP-ENFORCEMENT-STRATEGY.md` · `.claude/GUARDRAILS.md` · `mem_mq9usnxr` · `.claude/NVIDIA-MODELS-CATALOG.md`

---

## 1. Executive Summary

Owner Caio descobriu acesso gratuito a 100+ modelos NVIDIA via API NIM (`https://integrate.api.nvidia.com/v1`, OpenAI-compatible). 46 modelos zero-credit + ~50 credit-based via tier free 1000–5000 credits + 40 req/min. Plataforma inclui modelos de ponta (Llama 4 Maverick, MiniMax M2.7 230B, Qwen3 Coder 480B, Mistral Large 3 675B, Nemotron Super 49B, DeepSeek R1, GLM-4) com **function calling auto-enabled** em Llama 3.x/Mistral/Nemotron e suporte confirmado em DeepSeek/GLM/Qwen3/Kimi. Sem cartão pra criar conta, integração zero refactor SDK (OpenAI-compatible).

**Por que NIM vs apenas OpenRouter + Ollama**:
- **Zero-cost reasoning premium**: Nemotron Super 49B + DeepSeek R1 são Free Endpoints — hoje Hermes paga OpenRouter pra reasoning, NIM substitui
- **Function calling oficial**: Hermes F.6 Brain orchestrator precisa tool calling robusto — NIM declara support oficial Llama 3.3/Nemotron/Mistral (OpenRouter alguns providers cortam tool support)
- **Português oficialmente declarado**: Nemotron Super 49B lista PT entre 7 idiomas oficiais — F.7 message generation outreach PT-BR ganha 3o caminho além Ollama qwen3:8b local + OpenRouter
- **Latência cloud previsível**: SLO NVIDIA infra DGX vs OpenRouter (proxy) — F.6 Brain real-time chat ganha tier consistente

**Topologia proposta (4-tier routing chain)**:
```
Skill request → hermes-llm router (4o custom MCP NOVO)
  T1: Ollama PC local       — zero cost, mínima latência, modelos limitados (RTX 2060 6GB)
  T2: NIM Free Endpoints    — zero cost, ~46 modelos, 40 RPM hard cap, cloud latency
  T3: NIM credit-based      — 5000 credits initial, modelos premium opt-in
  T4: OpenRouter            — fallback final OR explicit owner override
```

**Effort total estimado** (3 opções D1):
- Opção A: 3 sub-sessões F.5.7/F.5.8/F.5.9 (~10h)
- Opção B: Integrar F.6 direto (~3–4h overhead)
- Opção C **(recomendada)**: F.5.7 scaffold + integração orgânica F.6 (~5h)

**Sub-sessão pioneira**: depende D1 — recomendação C inicia com F.5.7 hermes-llm scaffold MCP custom.

**6 Open Decisions** aguardando owner aprovar (seção 10): D1 roadmap · D2 MCP custom vs extensão · D3 NIM credit OPT-IN · D4 self-host containers · D5 key rotation · D6 Inception Program.

---

## 2. NVIDIA NIM — Catálogo Hermes-Relevant (Resumo)

Detalhe completo em `.claude/NVIDIA-MODELS-CATALOG.md` (tabela 25–40 modelos shortlist). Aqui resumo executivo dos 8 modelos mais relevantes pra Hermes:

| Model | Free? | Function Calling | Context | Use-case Hermes |
|---|---|---|---|---|
| `nvidia/llama-3.3-nemotron-super-49b-v1` | Sim¹ | Sim (auto) | 64k | **F.6 Brain reasoning + F.7 PT-BR outreach** (PT oficial) |
| `meta/llama-4-maverick-17b-128e-instruct` | Sim | Sim (auto) | 1M | General + F.7 long context prospect dossier |
| `mistralai/mistral-large-3-675b` | Sim | Sim (auto) | 128k | General SOTA backup F.6 Brain |
| `qwen/qwen3-coder-480b` | Sim | Sim | 256k | **F.4 skill synthesis code-gen** |
| `minimax/minimax-m2.7-230b` | Sim | Sim | 200k | Claude-grade coding backup F.4 |
| `zhipu/glm-4` | Sim | Sim | 128k | Reasoning lightweight + classifier |
| `nvidia/llama-3.1-nemotron-nano-8b-v1.1` | Sim | Sim (auto) | 128k | **Substitui Ollama qwen3:8b classifier F.6** |
| `deepseek-ai/deepseek-r1` | Credit² | Sim (community) | 64k | Premium reasoning opt-in (D3) |

¹ "Free?" = sem credit consumption no plano Free Endpoints tag (validar build.nvidia.com cada modelo individual).
² Modelos premium-credit consomem do balance 1000–5000 inicial; após esgotar = fallback OpenRouter.

**Função calling oficial NIM** (auto-enabled): Llama 3.1/3.2/3.3, Mistral, Nemotron Nano/Super/Ultra com `detailed thinking off`. Community-tested: DeepSeek V4/V3.2, GLM-5/4.7, Qwen3, Kimi K2.6. Parâmetros OpenAI-compatible (`tool_choice`, `tools`, `parallel_tool_calls`).

**Sources**:
- [build.nvidia.com/models](https://build.nvidia.com/models)
- [docs.nvidia.com/nim/large-language-models/latest/function-calling](https://docs.nvidia.com/nim/large-language-models/latest/function-calling.html)
- [llama-3.3-nemotron-super-49b modelcard](https://build.nvidia.com/nvidia/llama-3_3-nemotron-super-49b-v1/modelcard)
- [aihola NIM free 100+ models 2026](https://aihola.com/article/nvidia-nim-free-api-models)

---

## 3. Arquitetura Integração (sem touch BLACKLIST)

### 3.1 Diagrama ASCII

```
┌────────────────────────────── PC Windows (Hermes orchestrator) ─────────────────────────────┐
│  skills/*.yaml + core/brain.py (F.6) + auto-skill F.4 + cobaia F.7                          │
│                                            │                                                  │
│                                  invoke via gateway                                          │
│                                            ▼                                                  │
│       ┌──────────────────── mcps/gateway (F.5.1 ContextForge :55401) ────────────────┐       │
│       │  dispatch: hermes-linkedin · hermes-prospects · hermes-skills · hermes-llm   │       │
│       │                                                                              │       │
│       │                       ┌─────────────────┐                                    │       │
│       │                       │ hermes-llm NEW  │  ◀── 4o custom MCP (esta sessão)    │       │
│       │                       │  6-8 tools      │                                    │       │
│       │                       └────────┬────────┘                                    │       │
│       └────────────────────────────────│─────────────────────────────────────────────┘       │
│                                        │ route(prompt, task_type, policy)                    │
│                                        ▼                                                      │
│                          ┌─── Routing Policy Engine ──┐                                       │
│                          │ cost / latency / balanced  │                                       │
│                          └─┬───────┬───────┬────────┬─┘                                       │
│                            │       │       │        │                                         │
│                          ▼ T1    ▼ T2    ▼ T3     ▼ T4                                        │
│                    Ollama PC  NIM Free  NIM credit  OpenRouter                                │
│                    (existing)  (NEW)     (NEW)       (existing)                               │
│                                                                                              │
│  ⚠ linkedin/ollama_router.py (owner-imposed scope): NÃO TOCAR. Coexiste com hermes-llm.     │
│    Owner migra skills/*.yaml uma-a-uma de provider=ollama → provider=auto (router decide).  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Coexistência com `linkedin/ollama_router.py`

`linkedin/ollama_router.py` (154 linhas, F.C.4 MERGED-014 path) é **scope restriction esta sessão** — refactor F.future via wrapper MCP, não modificar. Estratégia:

- **Fase Phase 1 (F.5.7 esta proposta)**: hermes-llm MCP NOVO coexiste. Skills atuais com `provider: ollama` continuam routing via `linkedin/ollama_router.py` (unchanged). Skills novas/migradas usam `provider: auto` (delega hermes-llm router).
- **Phase 2 (F.6 implementação)**: `core/brain.py` invoca `mcp.hermes-llm.route()` via gateway (não chama Ollama direto nem ollama_router). Ollama router permanece path para wrapper LinkedIn-specific calls (mantém compat 100%).
- **Phase 3 (F.future)**: refactor `linkedin/ollama_router.py` virar thin client de `hermes-llm.route()` — DAR-BAIXA scope restriction só quando owner aprovar explicitamente (sessão dedicada com BLACKLIST re-audit).

### 3.3 Custom MCP `mcps/hermes-llm/` — scaffold proposto

Segue pattern F.5.2 (FastMCP 3.0, ~300-400 linhas, 6-8 tools). Localização VM canônica `~/.hermes/mcps/hermes-llm/` deployado via SCP igual hermes-skills/prospects/linkedin.

**Estrutura proposta**:
```
mcps/hermes-llm/
  __init__.py
  server.py           # FastMCP entry + 6 tools
  config.yaml         # default policy + tier thresholds + NIM key reference
  README.md           # tools list + invocation examples
  _adapters.py        # provider clients: ollama / nim / openrouter
  _policy.py          # routing decision engine
  _smoke.py           # isolated smoke tests (per pattern F.5.2 D7)
```

**6 tools proposed** (granularidade D1 F.5.2 — 6-8 tools médio):

1. **`route(prompt: str, task_type: str, model_hint: str = "", max_latency_ms: int = 30000, max_cost_credits: int = 0, force_provider: str = "") → dict`**
   - Core dispatcher. task_type ∈ {`reasoning`, `classify`, `creative_ptbr`, `code_gen`, `summarize`, `embedding`}
   - Returns `{ok, provider, model, response, latency_ms, tokens_in, tokens_out, cost_credits, fallback_chain_attempted}`
   - Aplica routing policy ativa (definida via tool 5)

2. **`list_available_models(provider: str = "", capability_filter: str = "") → dict`**
   - List rows from local mcp_llm_models table (mirror NIM catalog refreshed mensal via cron — ver seção 5)
   - capability_filter ∈ {`function_calling`, `streaming`, `json_mode`, `ptbr_official`, `long_context_128k+`}

3. **`get_provider_status() → dict`**
   - Health check 3 providers em paralelo (timeout 2s each)
   - Returns `{ollama: {up, latency_ms, models_loaded}, nim: {credits_remaining, free_rpm_used, rate_limit_window}, openrouter: {quota_used, models_available}}`

4. **`track_cost(call_id: str, provider: str, model: str, tokens_in: int, tokens_out: int) → dict`**
   - INSERT em `mcp_calls` extended row (ver seção 5)
   - Idempotente por call_id (UUID — duplicate INSERT é no-op)

5. **`set_routing_policy(policy_name: str) → dict`**
   - policy_name ∈ {`cost-optimize`, `latency-optimize`, `balanced`}
   - Persiste em runtime_state.user_prefs.llm_routing_policy (reusa F.2.5b infra)
   - Returns prev + new state

6. **`get_call_history(skill_name: str = "", window_days: int = 7, limit: int = 50) → dict`**
   - SELECT mcp_calls WHERE server='hermes-llm' filtros opcionais
   - Útil F.8 dashboard observability + F.4 skill performance audit

**Sanitization SENSITIVE_KEYS** (defesa-em-profundidade F.5.2 pattern): incluir `nvidia_api_key`, `nvapi-`, `openrouter_api_key`, além das 17 keys hermes-linkedin já cobre.

---

## 4. Routing Strategy + Policies

### 4.1 3 políticas pré-definidas

| Policy | T1 Ollama | T2 NIM Free | T3 NIM credit | T4 OpenRouter | Trigger |
|---|---|---|---|---|---|
| **cost-optimize** | primary | fallback | DENY | DENY | Maximum savings, accept higher latency / lower quality on fallback fail |
| **latency-optimize** | race¹ | race¹ | DENY | DENY | Parallel hedge T1+T2, primeiro responder vence, custo CPU+1 call descartada |
| **balanced** (default) | 70% routing | 25% routing | 5% routing | fallback final | Weighted A/B distribution, owner observa via F.8 dashboard quais ganham |

¹ `race` = `asyncio.gather` com `return_exceptions=True` + `asyncio.wait(FIRST_COMPLETED)` cancel pendentes.

### 4.2 Fallback chain decision tree (per call)

```
IF force_provider != "" THEN use force_provider, NO fallback (owner explicit)
ELSE per active policy:
  step_1 = primary tier per policy
  step_2..N = ordered fallback list

FALLBACK TRIGGERS (cada step → next step):
  - HTTP 429 rate limit
  - HTTP 5xx transient (max 1 retry exponential 1s)
  - asyncio.TimeoutError > max_latency_ms
  - Provider client raise (offline / model not available)
  - Empty response / response < 10 chars

ABORT TRIGGERS (sem fallback):
  - HTTP 401/403 auth fail (chave inválida)
  - HTTP 400 client error (prompt malformed)
  - force_provider set explicitly (owner override)
```

### 4.3 Critério de switch primário T1 → T2

Inline lógica em `_policy.py`:
- PC Ollama latency p95 últimas 10 calls > 5s → temporary T2 primário por 5min (decay)
- Modelo solicitado não disponível em `ollama list` → T2 imediato
- Health check T1 fail 2x consecutivo → T2 primário por 10min
- Owner-defined per-skill override em `skills/*.yaml` campo NOVO `force_provider:` (e.g., `nim-free`)

### 4.4 Hedging racing (latency-optimize)

```python
# pseudo (NÃO implementar nesta sessão — fica em hermes-llm/_policy.py F.5.7)
results = await asyncio.wait(
    [call_ollama(prompt), call_nim_free(prompt)],
    return_when=asyncio.FIRST_COMPLETED,
    timeout=max_latency_ms / 1000,
)
winner = next(iter(results.done))
# cancel pending tasks, refund cost trackers
```

Custo: 1 chamada "desperdiçada" por race. Aceitável quando latency crítico (F.6 Brain real-time chat owner).

---

## 5. Cost & Observability

### 5.1 Extension proposta `mcp_calls` schema

Schema existing (F.5.3 `migrations/2026_06_mcp_calls.sql`):
```sql
CREATE TABLE IF NOT EXISTS mcp_calls (
    id TEXT PRIMARY KEY, server TEXT NOT NULL, tool TEXT NOT NULL,
    args TEXT, response TEXT, error TEXT,
    duration_ms INTEGER, requester TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Extension proposta (5 columns NOVAS, **code block markdown inline — NÃO criar `.sql` file novo**):

```sql
-- F.5.7 PROPOSAL — adicionar 5 columns mcp_calls pra cost tracking multi-provider.
-- ALTER TABLE idempotente. Orquestrador sessão impl cria migration real com sequence number correto.
ALTER TABLE mcp_calls ADD COLUMN provider TEXT;        -- 'ollama' | 'nim-free' | 'nim-credit' | 'openrouter' | NULL
ALTER TABLE mcp_calls ADD COLUMN model TEXT;           -- 'nvidia/llama-3.3-nemotron-super-49b-v1' | 'qwen3:8b' | etc
ALTER TABLE mcp_calls ADD COLUMN tokens_in INTEGER;    -- prompt tokens
ALTER TABLE mcp_calls ADD COLUMN tokens_out INTEGER;   -- completion tokens
ALTER TABLE mcp_calls ADD COLUMN cost_credits REAL;    -- NIM credits consumed (0.0 free / X.X credit-based / 0.0 ollama+openrouter)

-- Optional new table mcp_llm_models (NIM catalog mirror refreshed mensal):
CREATE TABLE IF NOT EXISTS mcp_llm_models (
    model_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,                            -- 'nim' | 'ollama' | 'openrouter'
    free_endpoint INTEGER DEFAULT 0,                   -- bool: 1 = zero credit
    context_window INTEGER,
    function_calling INTEGER DEFAULT 0,                -- bool
    streaming INTEGER DEFAULT 0,                       -- bool
    json_mode INTEGER DEFAULT 0,                       -- bool
    capabilities TEXT,                                 -- JSON array of tags (ptbr_official, reasoning, code, etc)
    last_refresh_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deprecated_at TIMESTAMP                            -- NULL if active
);
```

**Regra docs-only crítica**: schema acima é **proposta** em markdown code block. Sessão de implementação real cria migration `.sql` file novo com sequence number correto (e.g., `migrations/2026_07_mcp_calls_llm.sql` ou next mês) — **NÃO** criar `.sql` nesta sessão B.

### 5.2 NIM credit balance polling

Script proposto `scripts/check_nim_credits.py` (NÃO criar nesta sessão — apenas descrever):
- Cron daily 09h BRT (alinhar cron F.5.5 audit mensal pattern)
- GET `https://integrate.api.nvidia.com/v1/account/credits` (validar endpoint real F.5.7 implementação)
- INSERT row em `nim_credit_history` table NOVA (balance, free_rpm_window_count_today, recorded_at)
- Alert thresholds: balance < 1000 → toast warning dashboard + log; balance < 200 → Telegram alert

### 5.3 F.8 Cost Observability dashboard integration

Reusa shell `dashboard/observability` proposto F.8. 5ª tab `MCP Coverage` (já F.8 design) ganha:
- Provider breakdown cards: Ollama `$0` (zero cost) + NIM Free `$0` + NIM credit `$X equivalent` + OpenRouter `$Y`
- Cost projection mensal baseado uso atual (linear extrapolation últimas 7d)
- Top 10 skills por consumo credits NIM (gap closer F.5 enforcement S2 already)

---

## 6. Per-Chapter Integration Points

### 6.1 F.5.6 (próximo executável)

Integrar 5 MCPs públicos prioritários (GitHub F.4, Sentry F.4+F.7, Postgres Pro F.6+F.7, Playwright F.3, Omnisearch F.7) — escopo confirmado PLAN.md.

**Touchpoint NIM em F.5.6**:
- Adicionar NIM como **6o MCP no gateway upstream** (registro `mcp_registry` status=`reserved` chapter_owner=`F.5.7` required_by_dc=`["F.6","F.7","F.4"]`)
- Update `.claude/mcp_registry_seed.json` adicionando row `hermes-llm` (server) com tools list (placeholder 6 tools listados seção 3.3)
- **NÃO implementar hermes-llm/server.py em F.5.6** — apenas registro/reservation

Touch: docs only + JSON registry update (orquestrador outra sessão).

### 6.2 F.6 Brain Orchestrator

Brain.decide() invoca `mcp.hermes-llm.route(task_type="reasoning")` via gateway dispatch. Default model hint: `nvidia/llama-3.3-nemotron-super-49b-v1` (Free Endpoint, function calling auto-enabled, PT-BR oficial) com fallback Nemotron-Nano-8B (free, função calling, classifier-grade).

Decision replay log inclui `provider+model` na coluna existing `brain_decisions.rationale` (JSON field expansion, sem schema change Brain) OR via cross-join `mcp_calls.context_id` (cleaner).

**HARD REQUIREMENT F.6**:
- `Brain.decide()` invoca **APENAS** via `mcp.hermes-llm.route()` (PROIBIDO `httpx.post` direto NIM endpoint) — ver F.6 MCP HARD REQUIREMENTS PLAN.md já incorporado
- Pydantic schema output validado ANTES dispatch (existing F.6 D constraint)

### 6.3 F.4 Auto-Skill Loop

Skill synthesis usa `mcp.hermes-llm.route(task_type="code_gen")` com default model `qwen/qwen3-coder-480b` (Free Endpoint, agentic coding purpose-built) OR fallback `minimax/minimax-m2.7-230b` (Claude-grade coding free). YAML synthesizer prompt + few-shot examples mantém compat 100% com OpenRouter format (zero refactor `skill_proposals` template).

Auto-skill YAML inclui campo NOVO `synth_provider: nim-free` default — substitui hardcoded OpenRouter Claude em F.4 task 1 (PLAN.md atual ainda referencia OpenRouter para synthesis).

**Hibrid path D3**: skills críticas owner-approved podem opt-in `synth_provider: nim-credit` com modelo premium (DeepSeek R1) — owner-explicit, não default.

### 6.4 F.7 Cobaia Live Ops

Message gen LinkedIn outreach via `mcp.hermes-llm.route(task_type="creative_ptbr")` com default `nvidia/llama-3.3-nemotron-super-49b-v1` (PT oficial declarado, reasoning post-trained) — A/B test vs Ollama qwen3:8b local atual via `mcp_calls.provider` segmentation.

Hit-rate tracking: cobaia_daily_metrics ganha column NOVA `reply_rate_by_provider` (JSON `{ollama: 0.12, nim: 0.18, openrouter: 0.10}`). Owner vê F.7 dashboard qual provider gera maior reply rate em outreach real Cuiabá.

**Caveat PT-BR**: NIM Llama-3.3-Nemotron-Super-49B declara Portuguese oficial mas **benchmark BR-Português específico NÃO publicado**. F.7 deve smoke test paralelo: 100 outreach NIM vs 100 Ollama local primeira semana, owner valida qualidade antes scale.

### 6.5 F.8 Cost & Performance Observability

Dashboard `/cost-observability` ganha provider breakdown (seção 5.3 acima). Migration extension `mcp_calls` columns 5 NOVAS (seção 5.1) é F.5.7 + F.5.8 propostas.

Sentry weekly digest (já F.5 + F.8 enforcement) inclui novo alert tipo: `nim_credit_balance < 1000 sustentado 14d → consider Inception Program OR reduce credit-based usage`.

### 6.6 F.9 Pipeline Studio Visual

Form builder skill step ganha **dropdown provider**: `[auto, ollama, nim-free, nim-credit, openrouter]`. Default `auto` (routing policy decide).

Preview cost estimate per-step ANTES save pipeline: query `mcp_llm_models` table → estimate tokens via len(prompt)/4 + tipo modelo → display `$0 free` OR `~X credits NIM` OR `~$Y OpenRouter`.

Step library JOIN `mcp_registry` mostra hermes-llm como first-class MCP igual outros (badge `chapter_owner=F.5.7` + `tier=active` se cadastrado).

---

## 7. Migration Path Existing Skills

Skills atuais (6 YAMLs em `skills/*.yaml`):
- 4 com `provider: openrouter` (linkedin-post-generator + linkedin-connection-sender + linkedin-engagement + linkedin-trend-monitor + weekly-mission-planner)
- 1 com `provider: ollama` (linkedin-profile-researcher → qwen3:8b)

### Phase 1 — F.5.7 hermes-llm scaffold + opt-in (zero touch existing skills)
- hermes-llm MCP deployed VM, 6 tools functional
- skills/*.yaml schema valida campo NOVO opcional `provider: auto` (default mantém atual)
- Owner pode editar YAML manual de `provider: openrouter` → `provider: auto` skill-por-skill (revert trivial)

### Phase 2 — F.6 Brain default + skills críticas migradas
- Brain.decide() invocações usam hermes-llm.route() (não OpenRouter direto)
- 2-3 skills owner-priorizadas migradas pra `provider: auto`
- F.8 dashboard mostra cost comparison: pre-migration baseline vs pós

### Phase 3 — F.future bulk migration + ollama_router refactor
- Skills paid OpenRouter (4 skills today) migradas pra NIM Free quando equivalent comprovado
- `linkedin/ollama_router.py` refactor virar thin client `hermes-llm.route()` — owner explicit go/no-go (BLACKLIST re-audit)
- Deprecate `provider: openrouter` raw, manter only via `provider: auto` + force_provider fallback

**Rollback path**: cada skill mantém git history YAML — revert 1 commit reverte 1 skill. Schema `provider:` retro-compat (string field, qualquer valor não-mapeado vai fallback OpenRouter).

---

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **NIM 40 RPM hard limit** | High (acontece) | Médio (call queue) | Pool + retry queue 60s exponential, fallback T3/T4 se sustained 5min |
| **"1 year duração" owner inferred — programa não confirmado** | Médio | Baixo (já hoje hosted free indefinido) | D6 owner valida qual programa específico aceitou (D6 open question) |
| **Free Endpoints catálogo muda** | Médio (NVIDIA rotaciona) | Médio (skills quebram) | Cron mensal `refresh_nim_catalog.py` daily 09h BRT update `mcp_llm_models` table + Sentry alert se model deprecated |
| **Cold start latency NIM > Ollama PC warm** | High | Baixo (UX) | Keep-alive ping skill rodando dawn UTC (cron 05h BRT) + accept first-call lag |
| **OpenAI-compat parcial — alguns NIM models NÃO suportam function calling** | Médio | Médio (Brain dispatch) | Tabela `mcp_llm_models.function_calling` field explicit. Router T2 selects FC-capable models when task_type requires tool_use |
| **PT-BR quality drift Nemotron vs Ollama local** | Médio | High (reply rate cobaia F.7) | F.7 A/B test 100/100 primeira semana + cobaia_daily_metrics reply_rate_by_provider tracking |
| **NIM credit balance drain inesperado** | Médio | Alto (paralisa T3) | Daily poll + alerts < 1000 / < 200 + auto-disable T3 routing se balance=0 |
| **NVIDIA Inception Program decision delay** | Médio | Baixo | D6 owner valida agora, decisão não bloqueia F.5.7 scaffold (vive em Free tier hosted) |
| **NIM key exposure em logs / repo** | Baixo | Crítico | SENSITIVE_KEYS extended (`nvidia_api_key`, `nvapi-`, `nim_token`); env-only storage `HERMES_NIM_API_KEY` em `~/.hermes/.env` VM |
| **Self-host NIM container PC indisponível** | High | Baixo | D4 owner-decide. Free hosted suficiente F.5.7-F.7 — self-host só se latency cloud insuficiente F.future |

---

## 9. Effort Estimate

### Opção A — 3 sub-sessões dedicadas F.5.7/F.5.8/F.5.9
- **F.5.7** hermes-llm MCP custom scaffold (server.py + 6 tools + smoke + deploy VM + gateway upstream config wire): **3–4h, 1 sessão**
- **F.5.8** Routing policies + cost tracking + migrations extension `mcp_calls` 5 columns + `mcp_llm_models` table + `nim_credit_history`: **4–5h, 1–2 sessões**
- **F.5.9** Catalog refresh cron + NIM credit polling + F.8 dashboard widget mini + Sentry alert config: **2–3h, 1 sessão**
- Total: **~10h, 3 sub-sessões**, atrasa F.5 closeout (F.6 começa post F.5.9)
- Vantagens: separação concerns clara, cada sub-sessão tem reviewer dedicado, regression gate isolado por commit
- Desvantagens: 3 setup/teardown overhead, F.6 atrasa 2 dias

### Opção B — Integrar F.6 direto
- F.6 Brain implementation absorve hermes-llm scaffold + routing + cost tracking integrado em 1 mega-sessão
- Total overhead F.6: **+3–4h** acima da estimativa F.6 original (6 sessions → 6.5–7 sessions)
- Vantagens: F.5 closeout planejado mantém, F.6 entrega NIM end-to-end day 1
- Desvantagens: F.6 sessão fica gigante, regression gate mais arriscado, hermes-llm não tem reviewer próprio

### Opção C **(recomendada)** — F.5.7 mínimo + resto F.6
- **F.5.7** SCAFFOLD ONLY: hermes-llm MCP custom server.py + 6 tools stubs (route returns 503 placeholder) + gateway wire + smoke isolated: **2–3h, 1 sessão**
- **F.6** absorve routing policies + cost tracking + migrations + catalog refresh: **+2h overhead F.6 estimate**
- Total: **~5h, 1 NOVA sub-sessão F.5.7 + ~+2h F.6 overhead**
- Vantagens: scaffold cedo (registry + gateway integration), integração orgânica F.6 (Brain consome MCP funcional), F.5 closeout 1 sub-sessão de atraso vs Opção A 3
- Desvantagens: F.6 ainda absorve scope cost tracking (não 100% isolado)

**Recomendação**: Opção C. Compromise pragmático: scaffold rápido + integração natural Brain.

---

## 10. Open Decisions Pra Owner Aprovar

### D1 — Implementação roadmap (effort comparativo)
- **Opção A**: 3 sub-sessões F.5.7/F.5.8/F.5.9 (~10h, separação concerns, atrasa F.5 closeout)
- **Opção B**: Integrar F.6 direto (~3–4h overhead na F.6, F.5.6 mantém closeout planejado)
- **Opção C** (recomendada): F.5.7 mínimo (hermes-llm scaffold) + resto F.6 (~5h, meio termo — scaffold cedo, integração orgânica F.6)

### D2 — hermes-llm custom MCP OR extension hermes-skills?
- **A (recomendada)**: 4o custom MCP separado `mcps/hermes-llm/` — segue pattern F.5.2 clean, responsabilidade isolada (LLM routing ≠ skill management), tools list distintas
- **B**: Estender `mcps/hermes-skills/` adicionando 6 tools llm-routing — menos boilerplate mas mistura concerns (skill mgmt + LLM dispatch num MCP só)

### D3 — NIM credit-based modelos premium OPT-IN per-skill OR fallback default?
- **A (recomendada)**: OPT-IN per-skill via campo YAML `force_provider: nim-credit` + `cost_budget_per_day` — owner controla custo skill-por-skill
- **B**: T3 NIM credit é fallback automático se T2 NIM Free indisponível — risco drain silencioso 5000 credits initial

### D4 — Self-host NIM containers VM GCP futuro?
- **A**: Defer F.future indefinido (Free hosted suficiente até F.7 cobaia)
- **B** (recomendada): Defer com checkpoint — re-avaliar pós-F.7 baseado em (1) NIM cloud latency p95 vs SLO F.7 cobaia messaging, (2) Inception Program elegibilidade (D6), (3) VM GCP cost incremental Docker NIM
- **C**: Investigar agora (NÃO recomendado — VM e2-standard-4 4 vCPU + 16GB RAM ≠ GPU host, NIM container precisa NVIDIA GPU = upgrade VM nova SKU $$$)

### D5 — NIM key rotação cadence
- **A (recomendada)**: Manual mensal alinhado com gateway OAuth F.5.1 rotação pattern. Owner gera nova key build.nvidia.com → atualiza `HERMES_NIM_API_KEY` em `~/.hermes/.env` VM
- **B**: Auto cron dia 15 BRT (alinhar audit mensal F.5.5) — over-engineering solo, key rotation requer UI build.nvidia.com manual ainda
- **C**: Sem rotação (manter key indefinido) — risco vazamento crônico

### D6 — NIM Inception Program aplicar agora ("1 ano benefits" owner mencionou)?
- **Pre-requisitos** (validar owner): (1) Hermes Cloud Studio incorporado como empresa? (2) <10 anos idade? (3) ≥1 developer (Caio conta)? (4) Website público (hermes.caioleo.com cobre)?
- **NÃO elegível se**: empresa consultoria PJ-só / crypto / CSP / reseller / public company
- **A (recomendada se elegível)**: aplicar agora, 2-4 semanas review. Benefits = DLI training credits + SDK + hardware discount + DGX Cloud credits + NIM API access prototyping + cloud partner credits ($100K AWS / $150K Nebius)
- **B**: Aplicar após F.7 cobaia validar use-case (mais traction signals na application)
- **C**: Skip (Free tier hosted suficiente, $0 cost benefit shorter-term)
- Sources: [nvidia.com/startups](https://www.nvidia.com/en-us/startups/) · [thundercompute Inception guide](https://www.thundercompute.com/blog/nvidia-inception-program-guide)

---

## 11. Cross-Refs

- `.claude/PLAN.md` chapters:
  - F.5.6 (próximo executável) — registry add hermes-llm + NIM como 6o MCP
  - F.5.7 (NOVA proposta D1 Opção C) — hermes-llm scaffold
  - F.6 — Brain orchestrator consome hermes-llm.route() reasoning
  - F.4 — Auto-skill synth_provider campo NOVO `nim-free` default
  - F.7 — Cobaia outreach PT-BR A/B test NIM Nemotron vs Ollama
  - F.8 — Dashboard cost observability provider breakdown + projection
  - F.9 — Pipeline Studio dropdown provider per-step
- `.claude/MCP-ENFORCEMENT-STRATEGY.md` — hermes-llm seria 4o consumer S2 `mcp_calls` table (extensão 5 columns proposta seção 5.1)
- `.claude/GUARDRAILS.md` BLACKLIST R2 literal: `.env, *.db, linkedin_data/, logs/, linkedin/lab/artifacts/` — esta sessão zero touch ALL
- `.claude/NVIDIA-MODELS-CATALOG.md` — catalog 25-40 modelos shortlist detalhado
- Memory: `mem_mq9usnxr` (NVIDIA NIM descobertas pesquisa orquestrador 2026-06-11)
- `linkedin/ollama_router.py` (owner-imposed scope esta sessão — coexiste, refactor F.future)
- `mcps/hermes-skills/server.py` (~370 linhas, pattern reference F.5.2 wrap pra hermes-llm scaffold)

---

**Status este documento**: COMPLETE pendente owner D1–D6 approval. Orquestrador outra sessão lê + aprova decisions + atualiza `.claude/PLAN.md` chapters F.5.7/F.6/F.4/F.7/F.8/F.9 + prepara prompts implementação real.
