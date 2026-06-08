# Validation Checklist — Fase F (Hermes Evolution)

> Asserts concretos por task de cada chapter F.x. Consumido por `scripts/validate_implementation.py`.
> Cada chapter define N tasks; PASS quando todos checks passam.
> Gate inegociável: validate --phase A B C D E continua 20/22 PASS após cada task.

## Tipos de assert disponíveis (Fase F)

### Existentes (legados Fase A-E)
```
- kind: grep_present | grep_absent
  target: <file or dir>
  pattern: <regex>
  description: <human readable>

- kind: file_exists
  target: <path>
  description: <human readable>

- kind: sqlite_table | sqlite_column | sqlite_pragma
  target: <db path> / <table>[.<column>] OR <pragma>
  description: <human readable>

- kind: count_max
  target: <file>
  pattern: <regex>
  max: <int>
  description: <human readable>

- kind: line_count_max
  target: <file>
  max: <int>
  description: <human readable>

- kind: http
  target: <url>
  expected_status: <int>
  description: <human readable>

- kind: ast
  target: <file>
  rule: <ast rule>
  description: <human readable>
```

### NOVOS pra Fase F
```
- kind: ui_visible
  target: <page_url>
  selector: <css selector>
  description: Playwright preview_screenshot + DOM query selector returns 1+ elements

- kind: ws_subscribed
  target: <source file, ex dashboard/app.js>
  event: <event_name>
  description: grep app.js por handleWSEvent / addEventListener / case 'event_name'

- kind: endpoint_consumed
  target: <source file, ex dashboard/app.js>
  api_path: <api path like /api/foo>
  description: grep source por fetch/apiCall com api_path (tolera template literals)

- kind: regression_phase_pass
  phase: A|B|C|D|E
  description: re-run scripts/validate_implementation.py --phase X, exige 0 fail vs baseline

- kind: table_exists
  db: <db path>
  table: <table name>
  description: sqlite SELECT name FROM sqlite_master WHERE name='X'

- kind: screenshot_match
  target: <page_url>
  baseline: <path to .png baseline>
  description: preview_screenshot + manual diff vs baseline (acceptance via revisão owner)

- kind: workflow_exists
  target: <path .claude/workflows/X.js>
  description: file_exists + node -e parse OK + has valid meta export

- kind: mcp_registered
  target: .mcp.json
  name: <mcp name>
  description: grep .mcp.json por "name": "X"

- kind: skill_exists
  target: <name>
  description: file_exists .claude/skills/<name>/SKILL.md + valid YAML frontmatter schema

- kind: subagent_exists
  target: <name>
  description: file_exists .claude/agents/<name>.md
```

---

## Chapter F.1 — Backend↔Frontend Gap Audit

### F.1.task_1 — Parser AST routes PC+VM
- phase: F.1
- checks:
  - kind: file_exists
    target: .claude/skills/hermes-frontend-gap/scripts/parse_routes.py
    description: parser AST script existe
  - kind: file_exists
    target: .claude/frontend-gap/routes.json
    description: inventário rotas gerado
  - kind: ast
    target: .claude/skills/hermes-frontend-gap/scripts/parse_routes.py
    rule: contains ast.parse + walk decorators @router\.(get|post|put|delete|patch|websocket)
    description: parser detecta decorators FastAPI

### F.1.task_2 — Grep consumo dashboard/app.js
- phase: F.1
- checks:
  - kind: file_exists
    target: .claude/skills/hermes-frontend-gap/scripts/grep_frontend.py
  - kind: file_exists
    target: .claude/frontend-gap/frontend-consumption.json
  - kind: grep_present
    target: .claude/skills/hermes-frontend-gap/scripts/grep_frontend.py
    pattern: "fetch\\(|apiCall\\(|WebSocket"
    description: regex captura fetch/apiCall/WS

### F.1.task_3 — Diff + ranking → FRONTEND-GAP.md
- phase: F.1
- checks:
  - kind: file_exists
    target: .claude/skills/hermes-frontend-gap/scripts/rank_gaps.py
  - kind: file_exists
    target: .claude/FRONTEND-GAP.md
  - kind: grep_present
    target: .claude/FRONTEND-GAP.md
    pattern: "TOP 10|Top 10"
    description: seção top 10 priorizada
  - kind: grep_present
    target: .claude/FRONTEND-GAP.md
    pattern: "/api/daemon/timeline"
    description: endpoint fantasma 1 presente
  - kind: grep_present
    target: .claude/FRONTEND-GAP.md
    pattern: "/api/prospects/.+/resolve-conflict"
    description: endpoint fantasma resolve-conflict presente
  - kind: grep_present
    target: .claude/FRONTEND-GAP.md
    pattern: "/api/linkedin/visited"
    description: endpoint fantasma visited presente

### F.1.task_4 — Skill + slash command
- phase: F.1
- checks:
  - kind: skill_exists
    target: hermes-frontend-gap
    description: SKILL.md com frontmatter válido
  - kind: file_exists
    target: .claude/commands/hermes-frontend-gap.md
  - kind: grep_present
    target: .claude/skills/hermes-frontend-gap/SKILL.md
    pattern: "audit frontend|frontend gap"
    description: triggers documentados

### F.1.task_5 — Validação regressão + persistência
- phase: F.1
- checks:
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E
  - kind: grep_present
    target: .claude/PLAN.md
    pattern: "F\\.1.*complete|F\\.1.*✅"
    description: PLAN.md marca F.1 done
  - kind: grep_present
    target: .claude/GUARDRAILS.md
    pattern: "Backend novo SEM consumo frontend"
    description: regra nova GUARDRAILS

---

## Chapter F.2 — Mission Control Real-Time + Design System Polish

### F.2.1 — Backend /api/daemon/subsystems + schema runtime_state.subsystem_pauses
- phase: F.2
- checks:
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/daemon/subsystems
  - kind: grep_present
    target: api/daemon.py
    pattern: "subsystems"
    description: endpoint implementado
  - kind: grep_present
    target: api/daemon.py
    pattern: "Depends\\(get_current_user\\)|verify_token"
    description: auth fail-closed
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D

### F.2.2 — Loops gate subsystem_pauses
- phase: F.2
- checks:
  - kind: grep_present
    target: loops/sync.py
    pattern: "subsystem_pause|subsystems_pauses"
  - kind: grep_present
    target: loops/linkedin_sync.py
    pattern: "subsystem_pause"
  - kind: grep_present
    target: loops/linkedin_scheduler.py
    pattern: "subsystem_pause"
  - kind: grep_present
    target: channels/email/sender.py
    pattern: "subsystem_pause|paused"
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E

### F.2.3 — WS broadcast subsystem_status + daemon_log_event + decision_event
- phase: F.2
- checks:
  - kind: ws_subscribed
    target: dashboard/app.js
    event: subsystem_status
  - kind: ws_subscribed
    target: dashboard/app.js
    event: daemon_log_event
  - kind: ws_subscribed
    target: dashboard/app.js
    event: decision_event
  - kind: grep_present
    target: daemon/orchestrator.py
    pattern: "decision_event"
  - kind: grep_absent
    target: api/daemon.py
    pattern: "asyncio\\.create_task\\((?!.*spawn)"
    description: usa spawn() helper (MERGED-015)
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: D

### F.2.4 — Design system tokens + dark + toast + skeleton
- phase: F.2
- checks:
  - kind: file_exists
    target: dashboard/styles/tokens.css
  - kind: file_exists
    target: dashboard/styles/dark.css
  - kind: file_exists
    target: dashboard/components/toast.js
  - kind: file_exists
    target: dashboard/components/skeleton.js
  - kind: grep_present
    target: dashboard/components/toast.js
    pattern: "sanitizeClaudeHtml|DOMPurify"
    description: XSS-safe (MERGED-019)
  - kind: grep_absent
    target: dashboard/components/toast.js
    pattern: "https?://cdn|jsdelivr|unpkg"
    description: zero CDN runtime
  - kind: screenshot_match
    target: http://127.0.0.1:8500/dashboard#control
    baseline: .claude/screenshots/baseline/control_light.png

### F.2.5 — UI Mission Control rework
- phase: F.2
- checks:
  - kind: file_exists
    target: dashboard/components/subsystem_tile.js
  - kind: file_exists
    target: dashboard/components/live_log_tail.js
  - kind: file_exists
    target: dashboard/components/pref_panel.js
  - kind: ui_visible
    target: http://127.0.0.1:8500/dashboard#control
    selector: "[data-component='subsystem-tile-grid']"
  - kind: ws_subscribed
    target: dashboard/app.js
    event: subsystem_status
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/user-prefs
  - kind: grep_present
    target: dashboard/app.js
    pattern: "sanitizeClaudeHtml"
    description: sanitizer preservado
  - kind: screenshot_match
    target: http://127.0.0.1:8500/dashboard#control
    baseline: .claude/screenshots/f2/mission_control_v2.png
  - kind: regression_phase_pass
    phase: E

---

## Chapter F.3 — Lab Cockpit no-code

### F.3.1 — Schema DB + state guard
- phase: F.3
- checks:
  - kind: table_exists
    db: hermes_local.db
    table: lab_runs
  - kind: table_exists
    db: hermes_local.db
    table: lab_artifacts
  - kind: table_exists
    db: hermes_local.db
    table: lab_fingerprint_baselines
  - kind: file_exists
    target: core/lab_state.py
  - kind: regression_phase_pass
    phase: A

### F.3.2 — lab_runner.py wrapper estruturado
- phase: F.3
- checks:
  - kind: file_exists
    target: linkedin/lab/_event_emitter.py
  - kind: grep_present
    target: linkedin/lab/lab_runner.py
    pattern: "--emit-events|emit_events"
    description: flag NDJSON events
  - kind: grep_present
    target: linkedin/lab/_event_emitter.py
    pattern: "step_start|step_done|screenshot|compliance_score"
    description: events estruturados

### F.3.3 — api/lab.py backend SSH spawn
- phase: F.3
- checks:
  - kind: file_exists
    target: api/lab.py
  - kind: file_exists
    target: core/lab_orchestrator.py
  - kind: grep_present
    target: api/lab.py
    pattern: "create_subprocess_exec|ssh"
    description: SSH via asyncio subprocess (padrão server_ctrl)
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/lab/start
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/lab/runs
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: D

### F.3.4 — Artifact fetcher + thumbnail + cache
- phase: F.3
- checks:
  - kind: file_exists
    target: core/lab_artifacts.py
  - kind: file_exists
    target: lab_cache/.gitkeep
  - kind: grep_present
    target: core/lab_artifacts.py
    pattern: "sftp|scp|Pillow|PIL"
    description: SFTP + thumbnail
  - kind: regression_phase_pass
    phase: B

### F.3.5 — Dashboard /lab page UI
- phase: F.3
- checks:
  - kind: ui_visible
    target: http://127.0.0.1:8500/dashboard#lab
    selector: "[data-page='lab']"
  - kind: ws_subscribed
    target: dashboard/app.js
    event: lab.run.update
  - kind: grep_present
    target: dashboard/app.js
    pattern: "sanitizeClaudeHtml"
    description: sanitizer preservado (MERGED-019)
  - kind: screenshot_match
    target: http://127.0.0.1:8500/dashboard#lab
    baseline: .claude/screenshots/baseline/lab-idle.png
  - kind: regression_phase_pass
    phase: E

### F.3.6 — Compliance score + baseline delta + drawer
- phase: F.3
- checks:
  - kind: grep_present
    target: core/lab_orchestrator.py
    pattern: "compute_compliance_score|compute_baseline_delta"
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/lab/baseline
  - kind: ui_visible
    target: http://127.0.0.1:8500/dashboard#lab
    selector: "[data-component='lab-compliance-card']"

---

## Chapter F.4 — Auto-Skill Loop W3 (forge + lab + accept)

### F.4.task_1 — Schema DB skill_proposals + metrics + fixtures
- phase: F.4
- checks:
  - kind: table_exists
    db: hermes_local.db
    table: skill_proposals
  - kind: table_exists
    db: hermes_local.db
    table: skill_proposals_revisions
  - kind: file_exists
    target: migrations/pc/2026_06_08_skill_proposals.sql
  - kind: file_exists
    target: migrations/vm/2026_06_08_skill_metrics.sql
  - kind: regression_phase_pass
    phase: A

### F.4.task_2 — Backend api/skill_proposals.py + 10 endpoints
- phase: F.4
- checks:
  - kind: file_exists
    target: api/skill_proposals.py
  - kind: file_exists
    target: core/skill_forge.py
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/skill-proposals
  - kind: grep_present
    target: api/skill_proposals.py
    pattern: "X-Read-Yaml"
    description: gate header humano
  - kind: ws_subscribed
    target: dashboard/app.js
    event: skill_proposal.created
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B

### F.4.task_3 — Workflow hermes-skill-forge.js
- phase: F.4
- checks:
  - kind: workflow_exists
    target: .claude/workflows/hermes-skill-forge.js
  - kind: grep_present
    target: .claude/workflows/hermes-skill-forge.js
    pattern: "cooldown|24h|cost_budget_per_day"
    description: cooldown + cost budget enforced

### F.4.task_4 — Lab sandbox runner (VM)
- phase: F.4
- checks:
  - kind: file_exists
    target: vm_lab/skill_sandbox.py
  - kind: file_exists
    target: vm_lab/fixtures/seed_default.py
  - kind: file_exists
    target: vm_lab/snapshot_prod.py
  - kind: grep_present
    target: vm_lab/skill_sandbox.py
    pattern: "happy|edge|injection|cost_limit"
    description: 4 categorias fixtures

### F.4.task_5 — Deploy pipeline accept → staged → restart → health
- phase: F.4
- checks:
  - kind: file_exists
    target: core/skill_deployer.py
  - kind: grep_present
    target: core/skill_deployer.py
    pattern: "scp|staged|rollback"
  - kind: grep_present
    target: api/skill_proposals.py
    pattern: "X-Read-Yaml.*required|400.*X-Read-Yaml"
    description: gate header obrigatório no accept
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: C

### F.4.task_6 — VM instrumentation skill_metrics
- phase: F.4
- checks:
  - kind: grep_present
    target: hermes_api_v2.py
    pattern: "track_skill_metrics|skill_metrics"
  - kind: grep_present
    target: linkedin/ollama_router.py
    pattern: "skill_metrics|track_skill"
  - kind: table_exists
    db: ~/.hermes/data/command_center.db
    table: skill_metrics
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E

### F.4.task_7 — Auto-disable hook + Telegram alert
- phase: F.4
- checks:
  - kind: file_exists
    target: loops/skill_monitor.py
  - kind: grep_present
    target: loops/skill_monitor.py
    pattern: "spawn\\(|_background_tasks"
    description: spawn helper (MERGED-015)
  - kind: grep_present
    target: loops/skill_monitor.py
    pattern: "logger\\.exception"
    description: try/except (MERGED-007)
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: E

### F.4.task_8 — UI /skills/proposals + YAML diff
- phase: F.4
- checks:
  - kind: file_exists
    target: dashboard/vendor/diff2html.min.js
  - kind: file_exists
    target: dashboard/vendor/diff2html.min.css
  - kind: file_exists
    target: dashboard/components/skill-proposals.js
  - kind: file_exists
    target: dashboard/components/yaml-diff-viewer.js
  - kind: ui_visible
    target: http://127.0.0.1:8500/dashboard#/skills/proposals
    selector: "[data-component='skill-proposals-list']"
  - kind: grep_present
    target: dashboard/components/skill-proposals.js
    pattern: "sanitizeClaudeHtml"
  - kind: grep_absent
    target: dashboard/components/yaml-diff-viewer.js
    pattern: "https?://cdn|jsdelivr|unpkg"
    description: vendor local não CDN
  - kind: regression_phase_pass
    phase: E

### F.4.task_9 — UI lab runner + metrics chart + autodisable
- phase: F.4
- checks:
  - kind: file_exists
    target: dashboard/components/lab-result-panel.js
  - kind: file_exists
    target: dashboard/components/skill-metrics-chart.js
  - kind: file_exists
    target: dashboard/vendor/chart.umd.min.js
  - kind: ws_subscribed
    target: dashboard/components/lab-result-panel.js
    event: skill_proposal.lab_fixture_progress
  - kind: regression_phase_pass
    phase: E

### F.4.task_10 — Validation harness extensions + persistência
- phase: F.4
- checks:
  - kind: grep_present
    target: scripts/validate_implementation.py
    pattern: "check_ui_visible|check_ws_subscribed|check_regression_phase_pass"
    description: 3 novos CHECK_RUNNERS
  - kind: grep_present
    target: .claude/VALIDATION-CHECKLIST.md
    pattern: "F\\.4\\.task_"
    description: tasks F.4 documentadas
  - kind: grep_present
    target: .claude/GUARDRAILS.md
    pattern: "X-Read-Yaml|skill_proposal"
    description: regras F.4 em guardrails
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E

---

## Chapter F.5 — MCP Discovery + Integration + Gateway

### F.5.1 — Workflow mcp-discovery-survey + tabela + skill
- phase: F.5
- checks:
  - kind: workflow_exists
    target: .claude/workflows/mcp-discovery-survey.js
  - kind: skill_exists
    target: hermes-mcp-survey
  - kind: file_exists
    target: api/mcp_discovery.py
  - kind: table_exists
    db: hermes_local.db
    table: mcp_discovery_runs
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/mcp/discovery/runs

### F.5.2 — Tabela mcp_registry + UI + .mcp.json
- phase: F.5
- checks:
  - kind: file_exists
    target: api/mcp.py
  - kind: table_exists
    db: hermes_local.db
    table: mcp_registry
  - kind: ui_visible
    target: http://127.0.0.1:8500/dashboard#mcp-control
    selector: "[data-component='mcp-registry-table']"
  - kind: ws_subscribed
    target: dashboard/app.js
    event: mcp.registry.updated
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B

### F.5.3 — hermes-mcp-gateway VM (FastMCP 3.0 + OAuth)
- phase: F.5
- checks:
  - kind: file_exists
    target: mcps/gateway/server.py
  - kind: file_exists
    target: mcps/gateway/config.yaml
  - kind: file_exists
    target: mcps/gateway/audit.py
  - kind: file_exists
    target: mcps/gateway/allowlist.py
  - kind: grep_present
    target: config.py
    pattern: "mcp_gateway_url|mcp_gateway_token"
    description: settings canônicos
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/mcp/gateway/health
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E

### F.5.4 — hermes-linkedin-mcp custom (11 tools FastMCP)
- phase: F.5
- checks:
  - kind: file_exists
    target: mcps/hermes-linkedin/server.py
  - kind: file_exists
    target: mcps/hermes-linkedin/tools.py
  - kind: file_exists
    target: mcps/hermes-linkedin/README.md
  - kind: grep_present
    target: mcps/hermes-linkedin/tools.py
    pattern: "from linkedin.stealth|from linkedin.human|from linkedin.limiter|from linkedin.cooldown"
    description: reuso módulos linkedin (zero duplicação)
  - kind: grep_present
    target: mcps/hermes-linkedin/server.py
    pattern: "HERMES_MCP_LI_WRITE_ENABLED"
    description: guard write
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E

### F.5.5 — 4 MCPs públicos integrados via gateway
- phase: F.5
- checks:
  - kind: mcp_registered
    target: .mcp.json
    name: firecrawl
  - kind: mcp_registered
    target: .mcp.json
    name: postgres-pro
  - kind: mcp_registered
    target: .mcp.json
    name: telegram
  - kind: mcp_registered
    target: .mcp.json
    name: playwright-ms
  - kind: file_exists
    target: mcps/public/playwright-ms/README.md
  - kind: file_exists
    target: mcps/public/firecrawl/README.md
  - kind: file_exists
    target: mcps/public/postgres-pro/README.md
  - kind: file_exists
    target: mcps/public/telegram/README.md
  - kind: grep_present
    target: mcps/gateway/allowlist.py
    pattern: "cobaia_only|playwright"
    description: guard Playwright cobaia-only

### F.5.6 — GitHub MCP + F.4 ready
- phase: F.5
- checks:
  - kind: mcp_registered
    target: .mcp.json
    name: github
  - kind: file_exists
    target: mcps/public/github/README.md
  - kind: file_exists
    target: mcps/public/github/oauth-scopes.md
  - kind: grep_absent
    target: mcps/gateway/allowlist.py
    pattern: "admin_delete|admin_repo"
    description: admin tools bloqueados

### F.5.7 — Validator + WS audit + agent + GUARDRAILS
- phase: F.5
- checks:
  - kind: file_exists
    target: mcps/gateway/validator.py
  - kind: subagent_exists
    target: mcp-integrator
  - kind: grep_present
    target: mcps/gateway/validator.py
    pattern: "ignore previous|system:|jailbreak"
    description: regex anti-injection
  - kind: ws_subscribed
    target: dashboard/app.js
    event: mcp.audit.new
  - kind: grep_present
    target: .claude/GUARDRAILS.md
    pattern: "MCP|Gateway"
    description: seção MCP em guardrails
  - kind: ui_visible
    target: http://127.0.0.1:8500/dashboard#mcp-control
    selector: "[data-component='mcp-audit-drawer']"

---

## Chapter F.6 — Cérebro Hermes (brain.py + tools.py + decision replay)

### F.6.1 — Schema brain_sessions/turns/decisions PC+VM
- phase: F.6
- checks:
  - kind: table_exists
    db: hermes_local.db
    table: brain_sessions
  - kind: table_exists
    db: hermes_local.db
    table: brain_turns
  - kind: table_exists
    db: hermes_local.db
    table: brain_decisions
  - kind: file_exists
    target: migrations/F6_brain_schema.sql
  - kind: file_exists
    target: scripts/apply_brain_migration.py

### F.6.2 — core/tools.py ToolRegistry
- phase: F.6
- checks:
  - kind: file_exists
    target: core/tools.py
  - kind: file_exists
    target: core/tools_registry.json
  - kind: grep_present
    target: core/tools.py
    pattern: "class ToolRegistry|def invoke"
  - kind: grep_present
    target: core/tools.py
    pattern: "cost_budget|permission"
    description: cost guard + permission allowlist
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B

### F.6.3 — core/brain.py + ollama_router task_types
- phase: F.6
- checks:
  - kind: file_exists
    target: core/brain.py
  - kind: file_exists
    target: tests/fixtures/brain_contexts.json
  - kind: grep_present
    target: core/brain.py
    pattern: "def classify|def decide|def evaluate_result"
  - kind: grep_present
    target: linkedin/ollama_router.py
    pattern: "brain_classify|brain_decide"
    description: novos task_types
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E

### F.6.4 — Daemon shadow mode
- phase: F.6
- checks:
  - kind: grep_present
    target: daemon/orchestrator.py
    pattern: "HERMES_BRAIN_SHADOW|brain_shadow|shadow_mode"
  - kind: grep_present
    target: config.py
    pattern: "brain_enabled|brain_shadow"
    description: feature flags em settings (não os.environ)
  - kind: grep_absent
    target: daemon/orchestrator.py
    pattern: "asyncio\\.create_task\\((?!.*spawn)"
    description: spawn helper obrigatório (MERGED-015)
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E

### F.6.5 — Cutover HERMES_BRAIN_ENABLED=true
- phase: F.6
- checks:
  - kind: grep_present
    target: daemon/orchestrator.py
    pattern: "_legacy_decide|brain\\.decide"
    description: cutover com fallback
  - kind: grep_present
    target: daemon/orchestrator.py
    pattern: "settings\\.brain_enabled"
    description: flag via pydantic settings
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E

### F.6.6 — api/brain.py + WS events
- phase: F.6
- checks:
  - kind: file_exists
    target: api/brain.py
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/brain/chat
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/brain/decisions
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/brain/tools
  - kind: ws_subscribed
    target: dashboard/app.js
    event: brain.token
  - kind: ws_subscribed
    target: dashboard/app.js
    event: brain.tool_call
  - kind: ws_subscribed
    target: dashboard/app.js
    event: brain.decision
  - kind: grep_present
    target: api/brain.py
    pattern: "\\?token=|token query|ws.*auth"
    description: WS auth via ?token= (MERGED-001)

### F.6.7 — Dashboard /brain chat
- phase: F.6
- checks:
  - kind: file_exists
    target: dashboard/brain.html
  - kind: file_exists
    target: dashboard/brain.js
  - kind: ui_visible
    target: http://127.0.0.1:55000/dashboard#brain
    selector: "[data-component='chat-panel']"
  - kind: grep_present
    target: dashboard/brain.js
    pattern: "sanitizeClaudeHtml"
  - kind: screenshot_match
    target: http://127.0.0.1:55000/dashboard#brain
    baseline: .claude/screenshots/baseline/brain-chat.png

### F.6.8 — Dashboard /brain/replay Decision Replay
- phase: F.6
- checks:
  - kind: file_exists
    target: dashboard/brain-replay.html
  - kind: file_exists
    target: dashboard/brain-replay.js
  - kind: ui_visible
    target: http://127.0.0.1:55000/dashboard#brain/replay
    selector: "[data-component='decision-timeline']"
  - kind: grep_present
    target: dashboard/brain-replay.js
    pattern: "sanitizeClaudeHtml|DOMPurify"
    description: rationale/result_json sanitizado

### F.6.9 — Dashboard /brain/tools Tool Registry Explorer
- phase: F.6
- checks:
  - kind: file_exists
    target: dashboard/brain-tools.html
  - kind: file_exists
    target: dashboard/brain-tools.js
  - kind: endpoint_consumed
    target: dashboard/brain-tools.js
    api_path: /api/brain/tools
  - kind: ui_visible
    target: http://127.0.0.1:55000/dashboard#brain/tools
    selector: "[data-component='tool-grid']"

### F.6.10 — Agent Zero via ToolRegistry
- phase: F.6
- checks:
  - kind: grep_present
    target: core/tools_registry.json
    pattern: "agent_zero"
  - kind: grep_present
    target: api/agent_zero.py
    pattern: "/solve|agent-zero/solve"
  - kind: grep_present
    target: core/brain.py
    pattern: "complex_reasoning|agent_zero"
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E

### F.6.11 — Smoke cobaia 48h pós-cutover
- phase: F.6
- checks:
  - kind: file_exists
    target: scripts/brain_cobaia_smoke.py
  - kind: file_exists
    target: .claude/F6-COBAIA-REPORT.md
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E

---

## Chapter F.7 — Cobaia Live Ops (warmup 14d real)

### F.7.task_1 — Documentar plano warmup 14d
- phase: F.7
- checks:
  - kind: file_exists
    target: .claude/COBAIA-WARMUP-PLAN.md
  - kind: grep_present
    target: .claude/COBAIA-WARMUP-PLAN.md
    pattern: "lurking|ramp|outreach"
  - kind: grep_present
    target: .claude/COBAIA-WARMUP-PLAN.md
    pattern: "d0-6|d7-13|d14"
  - kind: grep_present
    target: .claude/GUARDRAILS.md
    pattern: "cobaia|warmup gates day-by-day"

### F.7.task_2 — challenges_in_last_24h + tabelas cobaia_*
- phase: F.7
- checks:
  - kind: grep_present
    target: linkedin/account_profile.py
    pattern: "challenges_in_last_24h"
  - kind: file_exists
    target: migrations/2026-06-08-cobaia-metrics.sql
  - kind: table_exists
    db: linkedin_data/rate_limits.db
    table: cobaia_daily_metrics
  - kind: table_exists
    db: linkedin_data/rate_limits.db
    table: cobaia_actions_log
  - kind: table_exists
    db: linkedin_data/rate_limits.db
    table: cobaia_pause_events
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E

### F.7.task_3 — Day-aware execução + 4 stop gates
- phase: F.7
- checks:
  - kind: grep_present
    target: daemon/orchestrator.py
    pattern: "_check_stop_gates|stop_gates"
  - kind: grep_present
    target: daemon/orchestrator.py
    pattern: "WarmupState|warmup_state.*phase"
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/cobaia/gates
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/cobaia/status
  - kind: ws_subscribed
    target: dashboard/app.js
    event: cobaia_gate_triggered
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E

### F.7.task_4 — Daily Telegram report 19h + skill
- phase: F.7
- checks:
  - kind: grep_present
    target: daemon/orchestrator.py
    pattern: "_daily_report_task|daily_report"
  - kind: skill_exists
    target: hermes-cobaia-status
  - kind: file_exists
    target: .claude/commands/hermes-cobaia.md
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/cobaia/daily-report/preview
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E

### F.7.task_5 — Dashboard /cobaia timeline + métricas + controls
- phase: F.7
- checks:
  - kind: ui_visible
    target: http://localhost:8500/dashboard/#cobaia
    selector: "[data-page='cobaia']"
  - kind: ws_subscribed
    target: dashboard/app.js
    event: cobaia_metrics_update
  - kind: ws_subscribed
    target: dashboard/app.js
    event: cobaia_action_executed
  - kind: ws_subscribed
    target: dashboard/app.js
    event: cobaia_paused
  - kind: ws_subscribed
    target: dashboard/app.js
    event: cobaia_day_advanced
  - kind: grep_present
    target: dashboard/app.js
    pattern: "sanitizeClaudeHtml"
  - kind: screenshot_match
    target: http://localhost:8500/dashboard/#cobaia
    baseline: .claude/screenshots/baseline/cobaia-day0.png

---

## Chapter F.8 — Cost & Performance Observability

### F.8.task_1_schema_migrations
- phase: F.8
- checks:
  - kind: file_exists
    target: core/observability/__init__.py
  - kind: file_exists
    target: core/observability/schema.py
  - kind: file_exists
    target: core/observability/migrations.sql
  - kind: table_exists
    db: hermes_local.db
    table: llm_costs
  - kind: table_exists
    db: hermes_local.db
    table: perf_metrics
  - kind: table_exists
    db: hermes_local.db
    table: errors_inbox
  - kind: table_exists
    db: hermes_local.db
    table: brain_decisions
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E

### F.8.task_2_cost_instrumentation
- phase: F.8
- checks:
  - kind: file_exists
    target: core/observability/cost_tracker.py
  - kind: grep_present
    target: core/ai.py
    pattern: "@track_llm_cost"
  - kind: grep_present
    target: linkedin/ollama_router.py
    pattern: "on_completion|cost_tracker"
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D

### F.8.task_3_perf_middleware
- phase: F.8
- checks:
  - kind: file_exists
    target: core/observability/middleware.py
  - kind: file_exists
    target: core/observability/error_handler.py
  - kind: file_exists
    target: core/observability/sql_tracer.py
  - kind: grep_present
    target: server.py
    pattern: "PerfMiddleware|ErrorInboxHandler"
  - kind: grep_present
    target: hermes_api_v2.py
    pattern: "PerfMiddleware|ErrorInboxHandler"
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E

### F.8.task_4_api_router_observability
- phase: F.8
- checks:
  - kind: file_exists
    target: api/observability.py
  - kind: file_exists
    target: core/observability/aggregations.py
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/observability/costs
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/observability/perf
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/observability/errors
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/observability/summary
  - kind: ws_subscribed
    target: dashboard/app.js
    event: obs_error_new
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B

### F.8.task_5_dashboard_observability_page
- phase: F.8
- checks:
  - kind: file_exists
    target: dashboard/vendor/chart.umd.min.js
  - kind: ui_visible
    target: http://localhost:8500/dashboard/#observability
    selector: "[id='observability']"
  - kind: grep_absent
    target: dashboard/vendor/chart.umd.min.js
    pattern: "^(?!.*license).*https?://cdn"
    description: vendor local não CDN
  - kind: grep_present
    target: dashboard/app.js
    pattern: "sanitizeClaudeHtml"
    description: sanitizer preservado (MERGED-019)
  - kind: regression_phase_pass
    phase: E

### F.8.task_6_vm_deploy_summary_widget
- phase: F.8
- checks:
  - kind: file_exists
    target: vm_api/observability_vm.py
  - kind: grep_present
    target: loops/sync.py
    pattern: "sync_observability_from_vm|observability"
  - kind: grep_present
    target: .claude/GUARDRAILS.md
    pattern: "observability|@track_llm_cost|middleware perf"
  - kind: ui_visible
    target: http://localhost:8500/dashboard/#control
    selector: "[data-component='summary-widget']"
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D
  - kind: regression_phase_pass
    phase: E

---

## Chapter F.9 — Pipeline Studio Visual (form-driven builder + A/B)

### F.9.task_1 — Schema + catalog + bootstrap
- phase: F.9
- checks:
  - kind: file_exists
    target: core/pipeline_studio/__init__.py
  - kind: file_exists
    target: core/pipeline_studio/catalog.py
  - kind: file_exists
    target: core/pipeline_studio/models.py
  - kind: table_exists
    db: hermes_local.db
    table: pipeline_drafts
  - kind: table_exists
    db: hermes_local.db
    table: pipeline_runs
  - kind: table_exists
    db: hermes_local.db
    table: pipeline_run_steps
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C

### F.9.task_2 — PipelineStudioRunner + step executors
- phase: F.9
- checks:
  - kind: file_exists
    target: core/pipeline_studio/runner.py
  - kind: file_exists
    target: core/pipeline_studio/step_executors.py
  - kind: grep_present
    target: core/pipeline_studio/runner.py
    pattern: "run_dsl|asyncio\\.CancelledError"
  - kind: grep_absent
    target: core/pipeline_studio/runner.py
    pattern: "class PipelineRunner"
    description: zero subclass invasiva (composição)
  - kind: grep_present
    target: daemon/orchestrator.py
    pattern: "from core.pipeline"
    description: MERGED-012 imports intactos
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D

### F.9.task_3 — api/pipeline_studio.py 13 endpoints + WS
- phase: F.9
- checks:
  - kind: file_exists
    target: api/pipeline_studio.py
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/pipeline-studio/steps
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/pipeline-studio/drafts
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/pipeline-studio/execute
  - kind: ws_subscribed
    target: dashboard/app.js
    event: pipeline_studio_step_started
  - kind: ws_subscribed
    target: dashboard/app.js
    event: pipeline_studio_step_completed
  - kind: grep_present
    target: api/pipeline_studio.py
    pattern: "@limiter\\.limit"
    description: rate limit (MERGED-020 pattern)
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D

### F.9.task_4 — UI /pipeline-studio builder
- phase: F.9
- checks:
  - kind: file_exists
    target: dashboard/pipeline-studio/builder.js
  - kind: file_exists
    target: dashboard/pipeline-studio/step-library.js
  - kind: file_exists
    target: dashboard/pipeline-studio/draft-storage.js
  - kind: ui_visible
    target: http://localhost:8500/dashboard/#/pipeline-studio
    selector: "[data-component='builder-canvas']"
  - kind: ui_visible
    target: http://localhost:8500/dashboard/#/pipeline-studio
    selector: "[data-component='step-library-panel']"
  - kind: grep_present
    target: dashboard/pipeline-studio/builder.js
    pattern: "sanitizeClaudeHtml"
    description: XSS gate (MERGED-019)
  - kind: screenshot_match
    target: http://localhost:8500/dashboard/#/pipeline-studio
    baseline: .claude/screenshots/baseline/f9-builder.png
  - kind: regression_phase_pass
    phase: E

### F.9.task_5 — UI Live Execution Monitor
- phase: F.9
- checks:
  - kind: file_exists
    target: dashboard/pipeline-studio/run-monitor.js
  - kind: ui_visible
    target: http://localhost:8500/dashboard/#/pipeline-studio/runs
    selector: "[data-component='steps-timeline']"
  - kind: ws_subscribed
    target: dashboard/pipeline-studio/run-monitor.js
    event: pipeline_studio_step_started
  - kind: ws_subscribed
    target: dashboard/pipeline-studio/run-monitor.js
    event: pipeline_log_line
  - kind: screenshot_match
    target: http://localhost:8500/dashboard/#/pipeline-studio/runs
    baseline: .claude/screenshots/baseline/f9-monitor.png
  - kind: regression_phase_pass
    phase: A
  - kind: regression_phase_pass
    phase: E

### F.9.task_6 — Template Gallery + 5 curated seeds
- phase: F.9
- checks:
  - kind: file_exists
    target: core/pipeline_studio/templates_seed.py
  - kind: file_exists
    target: dashboard/pipeline-studio/templates.js
  - kind: ui_visible
    target: http://localhost:8500/dashboard/#/pipeline-studio/templates
    selector: "[data-component='template-gallery-grid']"
  - kind: grep_present
    target: core/pipeline_studio/templates_seed.py
    pattern: "lead_gen_b2b|linkedin_warmup|email_outreach|prospect_audit|full_funnel"
    description: 5 curated templates
  - kind: screenshot_match
    target: http://localhost:8500/dashboard/#/pipeline-studio/templates
    baseline: .claude/screenshots/baseline/f9-templates.png

### F.9.task_7 — A/B Test variants + compare view
- phase: F.9
- checks:
  - kind: file_exists
    target: dashboard/pipeline-studio/ab-compare.js
  - kind: grep_present
    target: core/pipeline_studio/runner.py
    pattern: "run_ab_test|asyncio\\.gather"
  - kind: endpoint_consumed
    target: dashboard/app.js
    api_path: /api/pipeline-studio/runs
  - kind: ui_visible
    target: http://localhost:8500/dashboard/#/pipeline-studio/runs
    selector: "[data-component='ab-compare-view']"
  - kind: screenshot_match
    target: http://localhost:8500/dashboard/#/pipeline-studio/runs
    baseline: .claude/screenshots/baseline/f9-ab.png
  - kind: regression_phase_pass
    phase: B
  - kind: regression_phase_pass
    phase: C
  - kind: regression_phase_pass
    phase: D

---

## Cross-cutting checks Fase F (rodam sempre após qualquer task F.x)

- kind: regression_phase_pass
  phase: A
  description: WS auth + fail-closed AUTH_TOKEN + internal token preservados
- kind: regression_phase_pass
  phase: B
  description: state + asyncio + try/except + dispatch error preservation
- kind: regression_phase_pass
  phase: C
  description: settings central + ollama_router + pipeline dedupe + topology
- kind: regression_phase_pass
  phase: D
  description: subprocess supervision + session monitor + rate-limit + sync versioning
- kind: regression_phase_pass
  phase: E
  description: channels + DOMPurify XSS allowlist
- kind: file_exists
  target: .claude/GUARDRAILS.md
  description: atualizado em cada chapter
- kind: file_exists
  target: .claude/PLAN.md
  description: checkboxes F.x marcados conforme tasks fecham
- kind: file_exists
  target: .claude/FRONTEND-GAP.md
  description: re-rodado após cada chapter pra tracking órfãos restantes
