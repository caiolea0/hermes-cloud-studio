---
name: hermes-brain-test
description: Bateria deterministica de testes pro Cerebro Hermes (Brain.decide() orquestrador — F.6) antes de soltar em producao Cobaia Live Ops (F.7). Roda 6 dimensoes: (1) contract API agent-zero/*, (2) decisao reproduzivel via golden cases, (3) gateway MCP isolation (Brain consulta SO via ContextForge), (4) guardrails (zero acao destrutiva sem owner confirm se score<0.7), (5) latencia p95 < 4s, (6) observabilidade Sentry+OTel trace completo. Trigger: "testar brain", "brain test", "validar cerebro hermes", "/hermes-brain-test". Roda ANTES de qualquer merge que toque api/agent_zero.py, brain/decide.py, brain/skills_router.py, ou config dos MCPs (ContextForge/FastMCP custom).
---

# /hermes-brain-test — Bateria deterministica Cerebro Hermes

Skill PRE-PRODUCAO. NUNCA pula. Roda end-to-end em <5min. Saida `.claude/BRAIN-TEST-{YYYY-MM-DD-HHMM}.md` priorizado + memory_save por Critical + TaskCreate por bug Critical.

## Quando rodar (gates obrigatorios)
- ANTES de merge em `api/agent_zero.py`, `brain/decide.py`, `brain/skills_router.py`, `brain/policies.py`, `brain/golden_cases/*.json`
- ANTES de adicionar/remover MCP custom (hermes-linkedin/prospects/skills) ou alterar config ContextForge gateway
- APOS qualquer mudanca em FastMCP version ou OAuth 2.1 scope filtering
- Daily smoke (cron VM 06:00 BRT) — detecta drift de decisao por mudanca em modelo Claude / contexto MCP
- ANTES de Phase F.7 Cobaia Live Ops ativar com conta real (Caio sagrada)

## Dimensoes obrigatorias (rodar TODAS, ordem fixa)

### 1. Contract API agent-zero/*
Arquivos: `api/agent_zero.py` + `tests/api/test_agent_zero_contract.py`

Endpoints:
- `GET /api/agent-zero/status` — retorna `{state, last_decision_at, mcps_healthy: [...], queue_depth, last_error}`
- `POST /api/agent-zero/chat` — payload `{message, context_id?, dry_run?}` → `{decision, reasoning, mcps_consulted, actions_planned, confidence, requires_owner_confirm}`
- `GET /api/agent-zero/timeline` — stream WS eventos `brain.thinking | brain.consulted_mcp | brain.decided | brain.action_executed | brain.action_blocked_owner_required`
- `POST /api/agent-zero/decision/{id}/approve` — owner confirma acao bloqueada
- `POST /api/agent-zero/decision/{id}/reject` — owner rejeita + razao (alimenta golden cases negativos)

Checks deterministicos:
- [ ] Schema response bate JSONSchema em `brain/contracts/*.schema.json` (validar com `jsonschema.validate()`)
- [ ] `requires_owner_confirm` SEMPRE true se `confidence < 0.7` OU acao tipo `linkedin.send_proposal | linkedin.send_inmail | email.send_external | crm.deal_update`
- [ ] WS `/api/agent-zero/timeline` exige `X-Hermes-Token` (regressao auth A) — fail-closed
- [ ] `POST /chat` aplica `@limiter.limit("10/minute")` por IP (regressao MERGED-016 slowapi)
- [ ] `dry_run=true` NUNCA emite efeito colateral (zero MCP write call, zero DB mutation)

Comando rapido:
```
python tests/api/test_agent_zero_contract.py --strict
```

### 2. Decisao reproduzivel — Golden cases replay
Arquivo: `brain/golden_cases/*.json` (>=12 cases curados manualmente pelo owner)

Cada golden case JSON:
```json
{
  "id": "GC-001-icp-pme-cuiaba-qualificado",
  "input": {"message": "qualifica prospect X CNPJ YYYY", "context_snapshot": {...}},
  "expected": {
    "decision_type": "qualify_and_enqueue_outreach",
    "confidence_min": 0.85,
    "mcps_consulted": ["hermes-prospects", "firecrawl", "hunter"],
    "actions_planned_signature": "sha256:..."
  },
  "tolerance": {"confidence_drift_max": 0.05, "extra_mcps_allowed": ["sentry"]}
}
```

Categorias minimas obrigatorias:
- 3x `qualify_prospect` (ICP match alto, medio, fora-ICP)
- 2x `decide_outreach_channel` (LinkedIn vs Email vs WhatsApp)
- 2x `handle_reply` (positivo/negativo/spam)
- 2x `skill_proposal_review` (auto-disable trigger 5+ erros vs aprovacao)
- 2x `daemon_subsystem_health` (pause linkedin se warning vs continue)
- 1x `owner_confirmation_required` (acao destrutiva → DEVE bloquear)

Checks:
- [ ] Replay roda em modo `dry_run=true` (zero efeito real)
- [ ] Cada case: `decision_type` IDENTICO ao expected (hard match)
- [ ] `confidence` dentro de tolerance (`expected.confidence_min - drift_max`)
- [ ] `mcps_consulted` superset de `expected.mcps_consulted` (extras OK so se whitelisted em `tolerance.extra_mcps_allowed`)
- [ ] `actions_planned` hash bate com signature (detecta drift de prompt/temperatura)
- [ ] Falha hard se >=2 cases divergem — bloqueia merge

Comando:
```
python brain/replay_golden_cases.py --strict --dry-run
```

### 3. Gateway MCP isolation (ContextForge)
Arquivo: `mcps/gateway-config.yaml` + `brain/mcp_client.py`

Garantia arquitetural: Brain NUNCA fala direto com MCP custom — SEMPRE via ContextForge gateway (auth+rate-limit+audit centralizados).

Checks:
- [ ] `brain/mcp_client.py` so importa `from contextforge_client import GatewayClient` — `grep -rn "import.*mcp" brain/` NAO pode retornar imports diretos a hermes-linkedin/prospects/skills/playwright/github/sentry
- [ ] Gateway config exige OAuth 2.1 JWT scope por tool (sem wildcard `*`)
- [ ] Rate limit por MCP: linkedin 30/min, prospects 100/min, skills 10/min (write), sentry 50/min, omnisearch 20/min
- [ ] Audit log gateway captura `{timestamp, brain_decision_id, mcp_name, tool, args_hash, latency_ms, status}` — validar 1 linha por chamada em ultimo replay
- [ ] Brain consegue degradar gracioso se gateway 503 (3 retries exponential + fallback decision `defer_to_owner`)

Comando:
```
python tests/mcp/test_gateway_isolation.py
grep -rnE "^from (hermes_linkedin|hermes_prospects|hermes_skills|playwright_mcp|github_mcp|sentry_mcp)" brain/ && echo "VIOLATION" || echo "OK"
```

### 4. Guardrails — Zero acao destrutiva sem confirm owner
Arquivo: `brain/policies.py` + `brain/action_executor.py`

Acoes que SEMPRE exigem `requires_owner_confirm=true`:
- `linkedin.send_proposal | linkedin.send_inmail | linkedin.send_connection_with_note`
- `linkedin.comment.delete | linkedin.comment.edit` (toca conta Caio sagrada)
- `email.send_external` (qualquer destinatario @ fora do dominio cobaia)
- `crm.deal_update | crm.contact_delete`
- `skills.auto_disable | skills.deploy_new_version`
- `daemon.pause_subsystem | daemon.resume_subsystem` (operacional, owner ciente)
- QUALQUER acao se `confidence < 0.7`

Checks:
- [ ] Test matrix: pra cada acao acima, criar input que dispara `confidence=0.95` E acao destrutiva → SEMPRE `requires_owner_confirm=true`
- [ ] Action executor: se `requires_owner_confirm=true` E `owner_approval_token` ausente → raise `OwnerApprovalRequired` + audit log + WS broadcast `brain.action_blocked_owner_required`
- [ ] Replay: passar `owner_approval_token=null` em 5 acoes destrutivas → todas devem bloquear (zero false-negative)
- [ ] Verificar `brain/policies.py` tem allowlist explicit, NUNCA blocklist (fail-closed)
- [ ] Cross-check com FRONTEND-GAP.md F.1: cada endpoint destrutivo aparece em UI com modal de confirmacao (manual visual — registrar screenshot em `.claude/brain-test/screenshots/`)

Comando:
```
python tests/brain/test_owner_confirm_gates.py --all-destructive
```

### 5. Latencia p95
Brain decide() roda end-to-end (MCP consults + LLM call + action plan): alvo p95 < 4s, p99 < 8s.

Checks:
- [ ] Rodar 50 golden cases sequenciais (3x cada = 150 runs), medir percentis com `numpy.percentile`
- [ ] p95 < 4000ms, p99 < 8000ms — falha hard se exceder
- [ ] Breakdown por fase: `mcp_consult_total | llm_call | action_plan_serialize` — nenhuma fase >70% do orcamento
- [ ] Detectar regressao vs baseline anterior (.claude/brain-test/baseline-latency.json) — alertar se p95 piorar >20%

Comando:
```
python tests/perf/brain_latency_bench.py --runs 150 --baseline .claude/brain-test/baseline-latency.json
```

### 6. Observabilidade — Sentry + OpenTelemetry trace completo
Arquivos: `brain/instrumentation.py` + Sentry MCP integration

Cada decisao Brain DEVE emitir:
- Sentry transaction `brain.decide` com tags `{decision_type, confidence_bucket, mcps_count, owner_confirm_required}`
- OTel span hierarchy: `brain.decide` → `mcp.consult.{name}` (N filhos) → `llm.call` → `action.plan`
- Span attributes obrigatorios: `decision_id`, `golden_case_id` (se replay), `dry_run`, `gateway_audit_id`
- Errors capturados via `sentry_sdk.capture_exception()` com contexto `{decision_id, last_mcp, partial_state}`

Checks:
- [ ] Rodar 10 golden cases com Sentry self-hosted (VM `--insecure-http`) e validar 10 transactions chegaram
- [ ] OTel trace export: validar span tree completo via `jaeger-query` ou `tempo` (1 trace por decision_id)
- [ ] Inject failure: matar gateway mid-decision → Sentry recebe exception com stacktrace + context
- [ ] auto-disable skill criterio (5+ erros em janela): consultar Sentry `search_errors` MCP — deve retornar contagem real, nao mock

Comando:
```
python tests/observability/brain_trace_validate.py --sentry-url $SENTRY_URL --otel-collector $OTEL_URL
```

## Output esperado

Arquivo `.claude/BRAIN-TEST-{YYYY-MM-DD-HHMM}.md`:

```
HERMES BRAIN TEST — {timestamp}
Branch: {git branch} | Commit: {sha7}
Duracao total: {Xs}

DIMENSION 1 — Contract API agent-zero/*
  PASS  /status schema valido
  PASS  /chat dry_run zero efeito
  FAIL  [BT-001] /timeline WS aceita conexao sem X-Hermes-Token — auth regression
        fix: adicionar verify_token dependency em ws_agent_zero handler

DIMENSION 2 — Golden cases replay (12/12)
  PASS  GC-001 ate GC-010
  FAIL  [BT-002] GC-011 owner_confirmation_required — confidence retornou 0.72 (expected min 0.85, drift 0.13 > tolerance 0.05)
        fix: investigar prompt regression brain/prompts/qualify.j2

DIMENSION 3 — Gateway MCP isolation
  PASS  zero import direto MCP em brain/
  PASS  audit log gateway 47/47 chamadas registradas

DIMENSION 4 — Guardrails owner confirm
  PASS  6/6 acoes destrutivas bloqueadas sem owner_approval_token

DIMENSION 5 — Latencia
  p50=1.2s p95=3.4s p99=6.1s — DENTRO orcamento
  PASS  baseline drift +8% (limite +20%)

DIMENSION 6 — Observabilidade
  PASS  10/10 Sentry transactions
  PASS  OTel trace tree completo
  FAIL  [BT-003] auto-disable criterio consulta Sentry retornou mock em test mode
        fix: criar fixture sentry_mcp_live em tests/conftest.py

SUMARIO:
- Critical: 1 (BT-001 auth regression bloqueia merge)
- High: 1 (BT-002 confidence drift)
- Medium: 1 (BT-003 fixture mock)
- Low: 0

VEREDICTO: BLOQUEAR MERGE (1 Critical)

Priorizado:
1. BT-001 — fix auth WS timeline (5min)
2. BT-002 — investigar prompt drift (30min)
3. BT-003 — fixture sentry live (15min)
```

## Integracao

- **Critical achado** → `TaskCreate` com title `Fix {BT-id}` + body apontando arquivo+linha+fix sugerido
- **Persistir relatorio** em `.claude/BRAIN-TEST-{date}.md` (nunca sobrescreve — historico)
- **memory_save** tipo `bug` por Critical/High, concepts=[hermes, brain, phase-f6, dimension-N]
- **mark_chapter** se rodada manual no fim de sessao Phase F.6: `Brain test passed — N findings resolvidos`
- **Gate CI/CD**: workflow `.github/workflows/brain-test.yml` roda skill em PR que toca `brain/**` ou `mcps/gateway-config.yaml` — falha hard se Critical > 0
- **Daily cron VM** (06:00 BRT): roda smoke (dimensoes 1+2+5) e abre issue GitHub se regressao detectada vs baseline

## Pre-requisitos

- Brain F.6 implementado (api/agent_zero.py + brain/* + ContextForge gateway up)
- Golden cases curados (>=12 em brain/golden_cases/*.json)
- Sentry self-hosted ou cloud configurado, OTel collector reachable
- FastMCP 3.0 instalado (framework dos custom MCPs)
- baseline-latency.json existe (criar com primeira rodada `--save-baseline`)

## Falha modes (NAO rodar skill se)

- ContextForge gateway DOWN → abort dimensao 3 com warning, demais rodam
- Sentry unreachable → dimensao 6 SKIP com warning (nao falha total)
- Golden cases <12 → abort total com erro `INSUFFICIENT_COVERAGE`
- Brain endpoint /status retorna `state=initializing` → wait max 30s, depois abort

## Sanity guards (defesa em profundidade)

- Skill SEMPRE roda em `--dry-run` por default — flag `--live` exige confirm explicito do owner via prompt CLI (`type CONFIRM`)
- Zero golden case pode tocar conta LinkedIn Caio real (validacao: todos `context_snapshot.account_id` devem comecar com `cobaia-*`)
- Audit log gateway deve ser append-only — verificar permissao arquivo `chmod 600` + dono = service account
- Latencia bench nao roda em horario business owner (08-20 BRT) se VM compartilhada
