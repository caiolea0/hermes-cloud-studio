# Brain Golden Cases — Owner Guide

Regression test suite for F.6 Brain orchestrator. 12 YAML cases (2 per intent × 6 intents)
executed against `Brain.decide()` via `pytest` harness with `GoldenMockDispatcher` (no
network, no real LLM — fully deterministic).

## Running

```bash
# Run all golden cases
pytest tests/test_brain_golden.py -v

# Parallel (pytest-xdist)
pytest tests/test_brain_golden.py -n auto

# Only golden marker
pytest tests/ -m golden

# Single case
pytest tests/test_brain_golden.py -v -k "answer_owner_happy"
```

## Adding a new case

1. Copy an existing YAML file as starting point (e.g. `cp answer_owner_happy.yaml my_new_case.yaml`)
2. Edit fields:
   - `intent`: must match a key in `brain/intents.py::INTENT_REGISTRY`
   - `case_id`: short slug (filename stem after intent prefix)
   - `description`: 1-3 lines explaining the case
   - `context`: dict passed to `Brain.decide()`
   - `mock_dispatcher_responses`: see schema below
   - `expected`: outcome assertions
3. Run `pytest tests/test_brain_golden.py -v --collect-only` to verify schema loads
4. Run the case: `pytest tests/test_brain_golden.py -v -k my_new_case`

## YAML schema

| Field | Type | Required | Notes |
|---|---|---|---|
| `intent` | str | yes | Must exist in `INTENT_REGISTRY` |
| `case_id` | str | yes | Unique within intent |
| `description` | str | no | Owner-facing doc |
| `context` | dict | no | Brain.decide() context arg |
| `mock_dispatcher_responses` | dict | no | See "Mock response keys" |
| `expected.status` | str | yes | `completed` \| `requires_confirm` \| `error` |
| `expected.requires_confirm` | bool | yes | Must match Brain.decide() return |
| `expected.intent_classified` | str | no | Echo check |
| `expected.min_confidence` | float | no | Range floor (0.0–1.0) |
| `expected.max_confidence` | float | no | Range ceiling |
| `expected.max_iterations` | int | no | ReAct cap (≤5) |
| `expected.final_state` | str | no | FSM final state (always `IDLE` post-decide) |
| `expected.tools_invoked` | list[str] | no | Substring-match in tool_calls |

### Mock response keys

- `"hermes-llm.route"` — catch-all for ALL `route()` calls (any task_type)
- `<task_type>` (e.g. `reasoning`, `code_gen`, `classify`, `summarize`, `creative_ptbr`) — match by task_type
- `"<server>.<tool>"` (e.g. `hermes-prospects.score_lead`) — `invoke_tool()` match

Value can be:
- single dict `{ok, response, cost_credits}` — single call response
- list of dicts — sequential calls use `list[call_index]` (clamped to last)

### `response` field formats

- string — used verbatim as LLM text (must be valid JSON per ReAct loop contract):
  `{"rationale":"...","planned_tool":null,"final_answer":"...","confidence":0.85}`
- dict — auto-JSON-encoded into the same string contract

## Destructive intents — safety contract

Cases for intents in `DESTRUCTIVE_ACTIONS` (`send_outreach`, `send_message`, `send_inmail`,
`synth_skill_promote`, `deploy_skill_pr`) **MUST** set `expected.requires_confirm: true`.
The test `test_destructive_intents_always_require_confirm` enforces this — trying to set
`false` will fail collection loud.

## CI integration

**LOCAL ONLY** in F.6.5 (owner solo no-code workflow). GitHub Actions workflow `.github/workflows/brain-regression.yml`
on push to master is **deferred to F.future** — owner runs `pytest tests/test_brain_golden.py -v` manually
before any merge touching `brain/*.py`.

## Files

```
.claude/brain-golden-cases/
├── README.md                              # this file
├── answer_owner_happy.yaml                # 1
├── answer_owner_low_conf.yaml             # 2
├── send_outreach_happy.yaml               # 3  destructive
├── send_outreach_max_iter.yaml            # 4  destructive
├── synth_skill_happy.yaml                 # 5
├── synth_skill_code_error.yaml            # 6
├── classify_prospect_happy.yaml           # 7
├── classify_prospect_low_conf.yaml        # 8
├── summarize_conversation_happy.yaml      # 9
├── summarize_long_context.yaml            # 10
├── route_skill_run_happy.yaml             # 11 utility (no LLM)
└── route_skill_run_unknown_skill.yaml     # 12 utility (no LLM)
```
