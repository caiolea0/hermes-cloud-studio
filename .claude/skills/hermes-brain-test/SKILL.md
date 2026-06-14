---
name: hermes-brain-test
description: Bateria deterministica de testes pro Cerebro Hermes (Brain.decide() orquestrador — F.6) antes de soltar em producao Cobaia Live Ops (F.7). Roda 6 dimensoes F.6 real (golden cases YAML + smoke offline): (1) contract API agent-zero/brain, (2) decisao reproduzivel via 12 golden cases pytest, (3) gateway MCP isolation (Brain consulta SO via dispatcher), (4) guardrails (destructive intents 100% requires_confirm + low_conf<0.5 → confirm), (5) latencia p95 < 4s offline mock, (6) observabilidade brain_runs + brain_decisions persistidos + Sentry. Trigger: "testar brain", "brain test", "validar cerebro hermes", "/hermes-brain-test". Roda ANTES de qualquer merge que toque brain/decide.py, brain/intents.py, brain/safety.py, brain/persistence.py, brain/_react.py, brain/_smoke.py, api/brain*.py, tests/test_brain_golden.py, ou .claude/brain-golden-cases/*.yaml.
---

# /hermes-brain-test — Bateria deterministica Cerebro Hermes

Skill PRE-PRODUCAO. NUNCA pula. Roda end-to-end em <5min OFFLINE (golden cases <1s).
Saida `.claude/BRAIN-TEST-{YYYY-MM-DD-HHMM}.md` priorizado + memory_save por Critical
+ TaskCreate por bug Critical.

**F.6.5 update:** substitui baseline F.6.0 (golden_cases JSON mock placeholder) por
F.6 real (YAML golden cases pytest harness + `brain/_smoke.py` 20/20 baseline).

## Quando rodar (gates obrigatorios)

- ANTES de merge em `brain/decide.py`, `brain/intents.py`, `brain/safety.py`,
  `brain/persistence.py`, `brain/_react.py`, `brain/_smoke.py`, `brain/dispatch.py`,
  `api/brain*.py`
- ANTES de adicionar/remover golden case em `.claude/brain-golden-cases/*.yaml`
- ANTES de alterar `INTENT_REGISTRY` (intents.py) ou `DESTRUCTIVE_ACTIONS` (safety.py)
- ANTES de Phase F.7 Cobaia Live Ops ativar com conta real (Caio sagrada)
- ANTES de promote skill F.4 que toque path Brain
- Daily smoke (cron VM 06:00 BRT) — detecta drift por mudanca em modelos roteados

## Tabela de Conteudos (6 Baterias)

| # | Bateria | Ferramenta | Critical Path |
|---|---|---|---|
| 1 | Contract API agent-zero/brain | `requests` schema check | `POST /api/agent-zero/brain/decide` |
| 2 | Decisao reproduzivel | `pytest` golden cases × 3 trials | 12 YAML cases zero divergencia |
| 3 | Gateway MCP isolation | `grep` imports + dispatcher reuse | Zero `from mcps.*` em brain/ |
| 4 | Guardrails confirm gate | golden cases destructive + low_conf | 5/5 destructive requires_confirm |
| 5 | Latencia p95 | 30 runs synthetic | p95 < 4s offline mock |
| 6 | Observability | DB SELECT + Sentry sdk check | brain_runs + brain_decisions persistidos |

---

## Bateria 1 — Contract API agent-zero/brain

**Arquivos:** `api/brain.py` (endpoints) + `dashboard/components/brain-confirm-drawer.js`
(F.6.4 consumer)

**Endpoints obrigatorios (F.6 real):**

| Endpoint | Payload | Response shape |
|---|---|---|
| `POST /api/agent-zero/brain/decide` | `{intent, context, requester}` | `{run_id, status, result, requires_confirm, latency_ms, total_cost_credits, final_state}` |
| `POST /api/agent-zero/brain/confirm` | `{run_id, approved, comment}` | `{ok, run_id, final_state, result, comment}` |
| `GET /api/agent-zero/brain/runs?status=requires_confirm` | query | `{ok, count, runs: [...]}` |
| `POST /api/agent-zero/brain/replay/{run_id}` | path | `{ok, run, decisions, total_decisions}` |

**Checks deterministicos:**

- [ ] Pydantic schema response bate exata com `BrainDecideResponse` em `api/brain.py`
- [ ] `requires_confirm: true` SEMPRE se `intent ∈ DESTRUCTIVE_ACTIONS` OR `confidence < 0.5`
- [ ] `POST /confirm` exige `X-Hermes-Token` (regressao auth — fail-closed)
- [ ] `dry_run` flag NAO existe (F.6 substituiu por requires_confirm gate)
- [ ] `resume_from_run_id` idempotent (re-resume retorna `not_awaiting_confirm`)
- [ ] `run_id` UUID v4 valido (regex)

**Como rodar:**

```bash
# Endpoints up locally (server.py :55000 proxy → :8500)
curl -s -X POST http://localhost:55000/api/agent-zero/brain/decide \
  -H "X-Hermes-Token: $HERMES_AUTH_TOKEN" -H "Content-Type: application/json" \
  -d '{"intent":"answer_owner","context":{"question":"smoke"}}' | jq

# Schema assert (jq)
# requires fields: run_id, status, result, requires_confirm, latency_ms,
#                  total_cost_credits, final_state
```

**Failure interpretation:**

- 401 → token rotacionado, atualizar `HERMES_AUTH_TOKEN`
- 500 + `unknown_intent` → INTENT_REGISTRY drift, verificar `brain/intents.py`
- `requires_confirm: false` para `send_outreach` → BUG CRITICAL safety, revert imediato

---

## Bateria 2 — Decisao reproduzivel (Golden cases × 3 trials)

**Arquivos:** `tests/test_brain_golden.py` + `.claude/brain-golden-cases/*.yaml` (12 cases)

**Garantia determinismo:** Rodar 12 golden cases × 3 trials sequenciais → 100% mesmo
outcome em todas as runs (intent_classified, status, requires_confirm, confidence
dentro de range, max_iterations). Divergencia entre trials = drift de prompt OU
non-determinism em ReAct loop = BLOQUEIA MERGE.

**Categorias cobertas:**

| Intent | Happy case | Edge case |
|---|---|---|
| answer_owner | conf 0.92 completed | conf 0.42 low_conf → requires_confirm |
| send_outreach | conf 0.92 destructive → requires_confirm | max_iter 5 → requires_confirm |
| synth_skill | conf 0.88 completed | conf 0.38 low_conf → requires_confirm |
| classify_prospect | conf 0.85 completed | conf 0.40 low_conf → requires_confirm |
| summarize_conversation | conf 0.80 completed | conf 0.72 long context completed |
| route_skill_run | utility no LLM completed | utility unknown skill completed |

**Como rodar:**

```bash
# Single run
rtk proxy python -m pytest tests/test_brain_golden.py -v --tb=short

# 3 trials sequenciais (determinism check)
for i in 1 2 3; do
  echo "=== Trial $i ==="
  rtk proxy python -m pytest tests/test_brain_golden.py -v 2>&1 | tail -5
done

# Parallel xdist (smoke race conditions)
rtk proxy python -m pytest tests/test_brain_golden.py -n auto
```

**Failure interpretation:**

- 1 case falha → ler `pytest --tb=long` + comparar com YAML expected
- Múltiplas falhas em mesmo intent → INTENT_REGISTRY drift OR react_loop regression
- Divergencia entre trials → non-determinism: investigar `asyncio.gather` (bug pattern
  mem_mq7i9caw) ou random seeds não-fixados
- 11/12 ou 13/12 collected → YAML novo/removido sem update README, rodar count test

---

## Bateria 3 — Gateway MCP isolation

**Arquivos:** `brain/dispatch.py` (GatewayDispatcher) + `brain/decide.py` + `brain/intents.py`

**Garantia arquitetural:** Brain NUNCA fala direto com MCPs custom — SEMPRE via
`GatewayDispatcher.route()` ou `.invoke_tool()` (ContextForge gateway F.5.1 +
auth+rate-limit+audit centralizados).

**Checks:**

- [ ] `grep -rnE "^from mcps\." brain/` deve retornar ZERO matches
- [ ] `grep -rnE "^from hermes_(linkedin|prospects|skills)" brain/` ZERO matches
- [ ] `brain/dispatch.py` é UNICO ponto que conhece gateway URL
- [ ] MockDispatcher subclassing preserva contract (route + invoke_tool signatures)
- [ ] Gateway 503 → Brain degrada gracioso (3 retries exponential + fallback decision)

**Como rodar:**

```bash
# Verify zero direct MCP imports em brain/
rtk proxy grep -rnE "^from mcps\.|^import mcps\.|^from hermes_(linkedin|prospects|skills)" brain/ \
  && echo "VIOLATION" || echo "OK"

# MockDispatcher contract preserved
rtk proxy python -c "from brain._smoke import MockDispatcher; \
  m = MockDispatcher(); assert hasattr(m, 'route') and hasattr(m, 'invoke_tool'); print('OK')"
```

**Failure interpretation:**

- Match em `from mcps.*` → BUG CRITICAL: alguem bypassou gateway, revert + refactor pra
  usar dispatcher
- MockDispatcher contract broken → golden tests vão falhar em massa, revert _smoke.py

---

## Bateria 4 — Guardrails confirm gate (Zero acao destrutiva sem owner)

**Arquivos:** `brain/safety.py` (DESTRUCTIVE_ACTIONS frozenset) + `brain/decide.py`
(needs_confirm gate)

**Acoes que SEMPRE exigem `requires_confirm: true`:**

```python
DESTRUCTIVE_ACTIONS = frozenset({
    "send_outreach",        # F.7 LinkedIn outreach dispatch
    "send_message",         # email + WhatsApp
    "send_inmail",          # LinkedIn InMail premium
    "synth_skill_promote",  # F.4 skill ativacao producao
    "deploy_skill_pr",      # F.4 PR creation
})
```

PLUS: `confidence < 0.5` para QUALQUER intent → requires_confirm `low_confidence`.

**Checks (cobertos por golden cases B2):**

- [ ] 5 destructive intents — golden case requires_confirm: true 100%
- [ ] Confidence < 0.5 — golden case requires_confirm: true (testado por
      answer_owner_low_conf, classify_prospect_low_conf, synth_skill_code_error)
- [ ] DESTRUCTIVE_ACTIONS frozenset NAO mutavel (security check)
- [ ] Sanity test `test_destructive_intents_always_require_confirm` em
      `tests/test_brain_golden.py`

**Como rodar:**

```bash
# Sanity tests sozinhos
rtk proxy python -m pytest tests/test_brain_golden.py::test_destructive_intents_always_require_confirm -v

# Frozenset immutability check
rtk proxy python -c "from brain.safety import DESTRUCTIVE_ACTIONS; \
  assert isinstance(DESTRUCTIVE_ACTIONS, frozenset); \
  try: DESTRUCTIVE_ACTIONS.add('hack'); raise SystemExit('FAIL: mutable!')
  except AttributeError: print('OK: immutable frozenset')"
```

**Failure interpretation:**

- destructive intent retornando `requires_confirm: false` → BUG CRITICAL safety,
  revert imediato + investigar `safety.requires_owner_confirm()` regression
- DESTRUCTIVE_ACTIONS mutavel → mudanca arquitetural inaceitavel, revert

---

## Bateria 5 — Latencia p95 (offline mock)

**Garantia performance:** Brain.decide() roda end-to-end (state transitions +
dispatcher mock + persistence) — alvo p95 < 4000ms em OFFLINE_MODE (generous threshold
mock simula network latency zero).

**Real-mode latencia (NIM live) target F.7: p95 < 8000ms — não testado F.6.5
(NIM rotation defer F.future).**

**Como rodar:**

```bash
# 30 runs synthetic + percentil
rtk proxy python -c "
import asyncio, time
from brain.decide import Brain
from brain._smoke import MockDispatcher

async def bench():
    latencies = []
    for i in range(30):
        b = Brain(dispatcher=MockDispatcher())
        t0 = time.monotonic()
        await b.decide('answer_owner', {'i': i})
        latencies.append((time.monotonic() - t0) * 1000)
    latencies.sort()
    p50 = latencies[14]
    p95 = latencies[28]
    p99 = latencies[29]
    print(f'p50={p50:.1f}ms p95={p95:.1f}ms p99={p99:.1f}ms')
    assert p95 < 4000, f'FAIL: p95={p95:.1f}ms exceeds 4000ms'
    print('OK: p95 within budget')

asyncio.run(bench())
"
```

**Failure interpretation:**

- p95 > 4000ms offline → regression: investigar persistence lock contention,
  asyncio gather (mem_mq7i9caw bug pattern), ou debug overhead
- p95 entre 2000-4000ms → borderline, considerar profile cProfile

---

## Bateria 6 — Observability (DB + Sentry)

**Arquivos:** `brain/persistence.py` (brain_runs + brain_decisions) + Sentry SDK init
em `server.py`

**Checks:**

- [ ] Cada `Brain.decide()` persiste 1 row em `brain_runs` (SYNC insert no inicio,
      UPDATE no final)
- [ ] Cada state transition persiste >= 5 rows em `brain_decisions` (async writer
      queue drain)
- [ ] `replay_run(run_id)` retorna full trace (covered por brain/_smoke.py P3)
- [ ] Sentry SDK importavel + `capture_exception()` callable em path de erro
- [ ] `owner_comment` column populado em rows `owner_approved` / `owner_rejected`
      (F.6.4 confirm flow)

**Como rodar:**

```bash
# Brain._smoke baseline cobre 20/20 (incluindo persistence + replay + confirm)
rtk proxy python -m brain._smoke

# Sentry SDK importavel
rtk proxy python -c "import sentry_sdk; print('Sentry SDK OK', sentry_sdk.VERSION)"

# DB inspection ultimas runs
rtk proxy python -c "
import sqlite3
c = sqlite3.connect('hermes_local.db')
rows = c.execute('SELECT id, intent, final_state, total_latency_ms FROM brain_runs ORDER BY started_at DESC LIMIT 5').fetchall()
for r in rows: print(r)
"
```

**Failure interpretation:**

- `brain_runs` count = 0 → persistence quebrou, investigar `insert_run` SQL OR
  schema migrate not applied
- `brain_decisions` count < 5 per run → writer queue não drenou, investigar
  `_ensure_writer` task lifecycle
- Sentry SDK missing → `pip install sentry-sdk`, depois config em server.py init

---

## Output esperado

Arquivo `.claude/BRAIN-TEST-{YYYY-MM-DD-HHMM}.md`:

```
HERMES BRAIN TEST — 2026-06-14T12:30
Branch: master | Commit: ff7124e
Duracao total: 1m12s

BATERIA 1 — Contract API agent-zero/brain
  PASS  POST /brain/decide schema valido (7/7 fields)
  PASS  POST /brain/confirm idempotent (409 not_awaiting_confirm)
  PASS  GET /brain/runs?status=requires_confirm

BATERIA 2 — Decisao reproduzivel (12 golden cases × 3 trials)
  PASS  Trial 1: 14/14 PASSED 0.5s
  PASS  Trial 2: 14/14 PASSED 0.5s
  PASS  Trial 3: 14/14 PASSED 0.5s
  PASS  Zero divergencia entre trials (determinism)

BATERIA 3 — Gateway MCP isolation
  PASS  grep mcps.* em brain/ → ZERO matches
  PASS  MockDispatcher contract preserved

BATERIA 4 — Guardrails confirm gate
  PASS  5/5 destructive intents → requires_confirm: true
  PASS  3/3 low_conf cases (<0.5) → requires_confirm
  PASS  DESTRUCTIVE_ACTIONS frozenset immutable

BATERIA 5 — Latencia
  p50=12.4ms p95=18.7ms p99=24.1ms — DENTRO orcamento (limite p95 < 4000ms)
  PASS

BATERIA 6 — Observability
  PASS  brain_runs ultima 5 rows OK (final_state populated)
  PASS  brain_decisions avg N=6 per run (>=5 esperado)
  PASS  Sentry SDK importavel (2.18.0)
  PASS  brain/_smoke.py 20/20 baseline (P1-P11 persistence + confirm)

SUMARIO:
- Critical: 0
- High: 0
- Medium: 0
- Low: 0

VEREDICTO: PASS — merge LIBERADO
```

## Integracao

- **Critical achado** → `TaskCreate` com title `Fix {BT-id}` + body apontando
  arquivo+linha+fix sugerido
- **Persistir relatorio** em `.claude/BRAIN-TEST-{date}.md` (nunca sobrescreve —
  historico)
- **memory_save** tipo `bug` por Critical/High, concepts=[hermes, brain, phase-f6,
  bateria-N]
- **mark_chapter** se rodada manual no fim de sessao Phase F.6: `Brain test passed —
  N findings resolvidos`
- **CI integration:** LOCAL ONLY F.6.5 (owner solo no-code). GitHub Actions workflow
  `.github/workflows/brain-regression.yml` defer F.future
- **Daily cron VM** (06:00 BRT): roda Baterias 2 + 5 smoke (golden cases + latencia)
  e abre Telegram alert se regressao vs baseline

## Pre-requisitos

- Brain F.6 implementado (`brain/decide.py` + `brain/intents.py` + `brain/safety.py`
  + `brain/persistence.py` + `brain/dispatch.py`)
- 12 golden cases em `.claude/brain-golden-cases/*.yaml`
- pytest>=9.0 + pytest-asyncio + pytest-xdist + PyYAML instalados
- `brain/_smoke.py` 20/20 baseline PASSED (pre-flight)
- `pytest.ini` com `asyncio_mode=auto`
- Sentry SDK opcional (Bateria 6 degrada gracioso se ausente)

## Falha modes (NAO rodar skill se)

- Golden cases <12 OR >12 → abort total com erro `INSUFFICIENT_COVERAGE` ou `OVER_COVERAGE`
- `brain/_smoke.py` baseline FAIL → abort pre-flight, fix _smoke primeiro
- Gateway gateway DOWN → Bateria 1 SKIP com warning, demais rodam offline
- Sentry unreachable → Bateria 6 partial PASS (skip SDK check, persistence ainda valida)
- HERMES_AUTH_TOKEN expirado → Bateria 1 SKIP, demais rodam

## Sanity guards (defesa em profundidade)

- Skill SEMPRE roda em modo OFFLINE_MODE=1 por default — flag `--live` exige confirm
  explicit do owner via prompt CLI (`type CONFIRM`)
- Zero golden case pode tocar conta LinkedIn Caio real (validacao: BLACKLIST R2
  zero matches em `linkedin/`)
- DB tmp isolado por test (`golden_db_path` fixture) — zero pollution em
  `hermes_local.db` real
- Latencia bench OFFLINE — não testa NIM live (NIM key rotation defer F.future,
  decisão owner formal)

## Quick reference (one-liners)

```bash
# Full battery (todas 6)
rtk proxy python -m pytest tests/test_brain_golden.py -v && \
rtk proxy python -m brain._smoke && \
echo "ALL BRAIN TESTS PASSED"

# Just golden cases (Bateria 2)
rtk proxy python -m pytest tests/test_brain_golden.py -v

# Just baseline (Baterias 4 + 6 cobertas)
rtk proxy python -m brain._smoke

# Parallel speed run
rtk proxy python -m pytest tests/test_brain_golden.py -n auto
```
