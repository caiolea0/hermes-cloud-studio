# hermes-llm MCP

**Status**: F.5.7 scaffold · **Version**: 0.1.0-f5.7 · **Owner chapter**: F.6 / F.7 / F.4 / F.8

3-tier LLM routing fallback chain. NIM Free → NIM credit → Ollama PC RTX 2060.
T4 OpenRouter explicit `force_provider` override only (coexiste skills/*.yaml legacy).

## Topology (4-tier, T4 explicit only)

```
Skill request
  → hermes-llm.route(prompt, task_type, policy)
     ↓
  T1 NIM Free Endpoint     (cloud, $0, 40 RPM cap)        primary
     ↓ fallback if 429/5xx/timeout/auth_fail/empty
  T2 NIM credit-based      (cloud, 5000 credits initial)  OPT-IN per-skill
     ↓ fallback if balance esgotado/model unavailable
  T3 Ollama PC RTX 2060 6GB  (offline-safe)               final auto-fallback
     ↓ owner explicit force only
  T4 OpenRouter             (existing legacy)              força explícita
```

## Tools (6)

| Tool | Purpose |
|---|---|
| `route(prompt, task_type, model_hint, max_latency_ms, max_cost_credits, force_provider, policy)` | Core dispatcher 3-tier fallback chain |
| `list_available_models(provider, capability_filter)` | Catalog routing_matrix de config.yaml |
| `get_provider_status()` | Health check 3 providers paralelo timeout 2s |
| `track_cost(call_id, provider, model, tokens_in, tokens_out)` | INSERT mcp_calls extended cost row idempotente |
| `set_routing_policy(policy_name)` | Muda policy ativa runtime (balanced/cost-optimize/latency-optimize) |
| `get_call_history(skill_name, window_days, limit)` | SELECT mcp_calls WHERE server='hermes-llm' |

## Routing matrix

Source of truth: `.claude/NVIDIA-MODELS-ROUTING-MATRIX.md` §4.
Local copy: `mcps/hermes-llm/config.yaml` `routing_matrix` (8 task_types + default).

Valid task_types: `default | reasoning | classify | code_gen | code_gen_light | creative_ptbr | summarize | embedding | generic_light`.

Valid policies:
- `balanced` (default) — deny openrouter T4 (explicit force only)
- `cost-optimize` — deny nim_credit + openrouter
- `latency-optimize` — allow nim_free + ollama_pc only

## Safety / guardrails

- `SENSITIVE_KEYS` extended F.5.2 pattern: inclui `nvidia_api_key`, `nvapi`, `nim_token`, `hermes_nim_api_key`, `openrouter_api_key`, `anthropic_api_key`, `openai_api_key`.
- Auto-redact strings prefix `nvapi-` em `_sanitize`.
- API keys env-only (`HERMES_NIM_API_KEY`, `OPENROUTER_API_KEY`) — NUNCA hardcode.
- Adapters try/except wrap — NUNCA propaga raise pra caller (gotcha `mem_mq7i9caw`).
- RpmLimiter margin 38/40 NIM Free (safety vs cap exato off-by-one).
- BLACKLIST R2 intact — zero touch `linkedin/ollama_router.py` (coexiste, refactor F.future).

## Path resolution

- VM primary: `~/.hermes/data/command_center.db`
- PC fallback: `hermes_local.db` repo root

## Run

```bash
python mcps/hermes-llm/server.py                            # stdio
HERMES_MCP_TRANSPORT=http python mcps/hermes-llm/server.py  # :55414
```

## Smoke

```bash
python mcps/hermes-llm/_smoke.py
```

Smoke valida 8 checks fixture-safe (sem chamar NIM real). Pipeline spawn-only quando `HERMES_NIM_API_KEY` ausente.

## Cross-refs

- `.claude/PLAN.md` § F.5.7 (cristalizada decisões D1-D6 commit `a76d828`)
- `.claude/NVIDIA-MODELS-ROUTING-MATRIX.md` (ground truth §4 routing per task)
- `.claude/NVIDIA-INTEGRATION-PLAN.md` (architecture 4-tier + per-chapter)
- `.claude/NVIDIA-MODELS-CATALOG.md` (32 shortlist base Sessão B)
- `mcps/hermes-skills/server.py` (F.5.2 pattern reference)
- `mcps/gateway/config.yaml` upstream `hermes-llm` (F.5.7b wire)
- `migrations/2026_06_<seq>_mcp_llm_extension.sql` (F.5.7b schema extend mcp_calls)
