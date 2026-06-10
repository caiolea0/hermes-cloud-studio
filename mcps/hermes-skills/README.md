# hermes-skills MCP

**Status**: F.5.2 scaffold · **Version**: 0.1.0-f5.2 · **Owner chapter**: F.4

YAML skills management + DB hybrid stubs. **HYBRID storage (D4)**:
- Reads filesystem (`skills/*.yaml` glob)
- Writes filesystem atomic via rename
- DB persistência **deferred F.4** (skill_proposals table)
- Metrics best-effort skill_runs table (silent empty se ausente)

## Tools (6)

| Tool | Storage | Plano |
|---|---|---|
| `list_skills()` | YAML glob | summary 6 fields per skill |
| `get_skill(name)` | YAML read | yaml_data completo + raw_chars |
| `toggle_active(name, active)` | YAML write atomic | rename pattern |
| `propose_skill_yaml_stub(name, description, model, provider)` | In-memory | F.4 entrega DB persist |
| `test_skill_dryrun(skill_name, input_data, mock_llm)` | Mock | F.future lab sandbox plug |
| `get_metrics(skill_name, window_days)` | DB best-effort | F.4 cria skill_runs |

## Path resolution

- VM primary: `~/.hermes/skills/` (deployed via scp F.5.2 commit 4)
- PC fallback: `skills/` repo root (smoke local)
- DB: `~/.hermes/data/command_center.db` (VM) OR `hermes_local.db` (PC)

## Safety

- Path traversal check em `_validate_skill_name` (rejeita `/`, `\`, `..`, `\x00`, len>64)
- Provider whitelist: `openrouter, ollama, anthropic, openai, deepseek`
- Atomic write via `.tmp` + rename (idempotent)
- DB queries try/except graceful — NUNCA propaga erro caller Brain

## YAML schema referência

```yaml
name: linkedin-engagement
description: "..."
version: "1.0"
active: true
model: minimax/minimax-m1:free
provider: openrouter
temperature: 0.7
max_tokens: 400
system_prompt: |
  ...
triggers: []
input_schema: {}
```

## Run

```bash
python mcps/hermes-skills/server.py                            # stdio
HERMES_MCP_TRANSPORT=http python mcps/hermes-skills/server.py  # :55413
```

## Smoke

```bash
python mcps/hermes-skills/_smoke.py
```

## Cross-refs

- `.claude/PLAN.md` § F.5.2 D4 (HYBRID storage)
- `.claude/PLAN.md` § F.4 Auto-Skill Loop (DB persistence target)
- `mcps/gateway/config.yaml` upstream `hermes-skills`
