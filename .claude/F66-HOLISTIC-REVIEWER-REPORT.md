# F.6 Brain Stack Holistic Audit — 1500+ LOC Cross-File Invariants

**Date**: 2026-06-14
**Sub-session**: F.6.6 (Closeout F.6)
**Reviewer**: general-purpose subagent (holistic cross-file scope, NÃO code-reviewer single-commit)
**Verdict overall**: **PASS-WITH-NOTES** — zero BLOCKERS

F.6.1→F.6.5 cross-file invariants validados sólidos. 3 WARNs F.future (LOW severity) + 1 NOTE arquitetural. F.6 production-ready para F.7 Cobaia Live Ops.

---

## Por dimensão (8 invariants)

### 1. State machine 6 states consistency — PASS
`brain/states.py` BrainState enum (IDLE, CLASSIFY, REASON, ACT, REVIEW, COMMIT) + 8 transitions FSM canonical. `decide.py` linhas 109-215 usa exatamente `start_classify → to_reason → to_act → to_review → {owner_confirm_required | to_commit → complete}`. `resume_from_run_id` (linhas 275-292) restaura via mesma sequência determinística. `_smoke.py` linha 107 asserta final IDLE. Zero state literal hardcoded fora do enum.

### 2. INTENT_REGISTRY 6 intents consistency — PASS
6 intents exato em `intents.py` (linha 28-81): answer_owner, send_outreach, synth_skill, classify_prospect, summarize_conversation, route_skill_run. Todos com 5 fields obrigatórios (description, task_type, destructive, default_tools, agentmemory_save). Golden cases 12/12 confirmados via `grep ^intent:` = 2 per intent × 6. D4 agentmemory_save 3 True (answer_owner, synth_skill, classify_prospect) / 3 False validado em `_smoke.py` P7 linhas 260-265.

### 3. Safety enforcement decide() flow — PASS
`safety.py` DESTRUCTIVE_ACTIONS é `frozenset` imutável (linha 16). `decide.py` linha 162 chama `requires_owner_confirm(intent, confidence, action_class)` SEMPRE antes de COMMIT. CONFIDENCE_THRESHOLD=0.5 hardcoded F.6.1 (D8 cristalizado). Golden cases `send_outreach_max_iter.yaml` + `answer_owner_low_conf.yaml` (conf=0.42 < 0.5) ambos asseguram requires_confirm=true. `test_brain_golden.py` linhas 113-123 `test_destructive_intents_always_require_confirm` é safety contract test.

### 4. Persistence schema match migration — PASS
`migrations/2026_06_brain_runs_decisions.sql` brain_runs 12 cols + brain_decisions 11 cols com FK `ON DELETE CASCADE`. `persistence.py` INSERT brain_runs (linhas 105-117) usa exatamente 5 cols obrigatórios (id, intent, context_json, requester, otel_trace_id); UPDATE final cobre 5 cols + owner_comment opcional. Migration F.6.4 ALTER TABLE ADD COLUMN owner_comment aplicado idempotentemente via `server.py` lifespan (linhas 113, 126). Pydantic schemas `api/brain.py` BrainDecideResponse alinhados.

### 5. Replay determinism — PASS
`replay.py` mode="show_recorded" é o único válido (linha 49 rejects "re_invoke" com 501). Read-only via `persistence.get_run()` + `get_decisions()` ordered by sequence ASC. `decide.py` `_reconstruct_react_result` (linhas 317-371) DRY-reusa `replay.replay_run()` (linha 343) para hidratar accumulated em F.6.4 resume. Zero re-invoke de tool calls confirmado.

### 6. MockDispatcher contract match — PASS
`_smoke.py` `_MockDispatcher.route(task_type, prompt, **kw)` + `invoke_tool(server, tool, args)` (linhas 66-81) match exato signature `GatewayDispatcher.route/invoke_tool` em `dispatch.py` (linhas 97-124, 126-168). Public alias `MockDispatcher = _MockDispatcher` (linha 86, F.6.5 D4) reexportado para `tests/conftest.py` linha 27. `GoldenMockDispatcher` subclassa preservando contract.

### 7. BLACKLIST R2 INTACTO 5 sub-sessions — PASS
`git log a058247..HEAD -- linkedin/` zero commits (output vazio). Grep `from linkedin|import linkedin` em `brain/` retorna ZERO match. Única referência string `mcp.hermes-linkedin.send_invite` em `brain/intents.py` linha 43 é nome MCP gateway tool (não import). Brain dispatch via `GatewayDispatcher.invoke_tool("hermes-linkedin", "send_invite", ...)` — passa por gateway loopback :55401, JAMAIS linkedin/patches/* direto.

### 8. WS broadcast namespace canonical — PASS
`api/brain.py` linha 116 emit `"brain.run_awaiting_confirm"` + linha 208 `"brain.run_confirm_resolved"` — ambos dot-notation F.2.3 pattern. `_emit_ws_event()` linha 69 fire-and-forget via `core.state.ws_manager.broadcast`. Zero contaminação `daemon.*`. Consumers confirmados: `dashboard/components/brain_confirm_drawer.js` + `dashboard/styles/brain-confirm.css`.

---

## Cross-file inconsistencies (NOTES não-bloqueantes)

**WARN #1 (F.future, severity LOW)** — `dispatch.py` SENSITIVE_KEYS frozenset duplica logic da gateway-side (defense-in-depth intencional, doc'd linha 34). Manter ambos sync via single source F.future (constants module shared).

**WARN #2 (F.future, severity LOW)** — `decide.py` linha 285 `confidence_score = float(run.get("confidence_score") or 0.5)` em resume_from_run_id reusa 0.5 fallback igual `requires_owner_confirm` threshold; se F.future tornar threshold configurável via PrefPanel (já doc'd `safety.py` linha 10), ajustar fallback para `CONFIDENCE_THRESHOLD - 0.01` evitar borderline.

**WARN #3 (F.future, severity LOW)** — `_smoke.py` linhas 354-364 hardcoded tmp path `hermes_brain_smoke_f64_confirm.db` poderia colidir em CI paralelo (uso `tempfile.mkdtemp` like P3 evitaria). Pytest conftest já usa mkdtemp correto — só `_smoke.py` standalone afetado.

**NOTE arquitetural** — `_reconstruct_react_result` (decide.py linha 317) faz import dinâmico `from .replay import replay_run` para evitar circular dependency; `intents.py` linha 104 também faz lazy import `from ._react import react_loop`. Pattern consistente e correto, mas indica acoplamento bidirecional brain.decide ↔ brain.replay ↔ brain.intents ↔ brain._react que poderia ser refatorado F.future com `brain.core` shared module.

---

## Recommendations

**F.6.7 hotfix**: NENHUM — zero BLOCKER critical.

**Defer F.future** (backlog tracked PLAN.md F.6 STATUS COMPLETE):
- Consolidar SENSITIVE_KEYS source único (WARN #1)
- Substituir hardcoded confidence fallback por config-driven (WARN #2)
- Migrar `_smoke.py` confirm tmp DB pra mkdtemp (WARN #3)
- Refactor circular import lazy → `brain.core` (NOTE arquitetural)

---

## F.6 Production-readiness verdict

**APROVADO para F.7 Cobaia Live Ops.** Stack F.6.1→F.6.5 entrega:

- Safety contract destructive intents 100% (G13 enforced em test + smoke + golden)
- Persistence 12+11 cols + owner_comment idempotent lifespan
- Replay determinístico read-only (zero side-effect double dispatch)
- BLACKLIST R2 LinkedIn INTACTO (zero diff em linkedin/ desde a058247)
- WS namespace canonical brain.* (zero daemon.* pollution)
- MockDispatcher contract estável (F.6.2 → F.6.5 preservado)
- 12 golden cases YAML × pytest harness + 20 smoke assertions

Próximo passo: F.6.6 Commit 2 closeout PLAN.md + Task #6 [completed] + memory_save + mark_chapter → F.7 Schedule Architecture com confiança total na camada Brain.
