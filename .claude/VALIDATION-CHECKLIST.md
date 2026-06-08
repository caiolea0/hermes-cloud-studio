# Validation Checklist — Hermes Implementation Plan

> Asserts concretos por finding. Consumido por `scripts/validate_implementation.py`.
> Cada finding define 1+ check; PASS quando todos passam.

## Formato

```
### MERGED-XXX
phase: A|B|C|D|E
checks:
  - kind: grep_present|grep_absent|file_exists|sqlite_table|sqlite_pragma|http|ast
    target: <file path or url>
    pattern: <regex or string>
    expected: <PASS condition>
    description: <human readable>
```

---

## Fase A — Security Critical

### MERGED-001 — WebSocket /ws auth
- phase: A
- checks:
  - grep_present: server.py / `websocket\.close\(code=1008` / WS handshake reject impl
  - grep_present: server.py / `compare_digest` / timing-safe compare in WS handler
  - grep_present: dashboard/app.js / `\?token=` / WS URL carries token

### MERGED-002 — Fail-closed AUTH_TOKEN
- phase: A
- checks:
  - grep_present: core/state.py / `if not AUTH_TOKEN:\s*\n\s*raise` / fail-closed startup (moved from server.py by MERGED-011)
  - grep_present: hermes_api_v2.py / `if not VM_AUTH_TOKEN:\s*\n\s*raise` / VM fail-closed
  - grep_absent: server.py / `if not AUTH_TOKEN:\s*\n\s*return await call_next` / no bypass
  - grep_absent: hermes_api_v2.py / `if not.*AUTH_TOKEN:.*return await call_next` / no bypass

### MERGED-003 — Internal token + bind loopback
- phase: A
- checks:
  - grep_present: server.py / `HERMES_INTERNAL_TOKEN|INTERNAL_TOKEN` / token defined
  - grep_present: server.py / `X-Internal-Token` / endpoints check header
  - grep_present: server.py / `host="127.0.0.1"` / bind loopback only (no 0.0.0.0)
  - grep_present: .env.example / `HERMES_INTERNAL_TOKEN=` / INTERNAL_TOKEN documented in env.example

## Fase B — State & Robustness

### MERGED-005 — SQLite busy_timeout
- phase: B
- checks:
  - grep_present: linkedin/limiter.py / "PRAGMA busy_timeout" / pragma applied
  - grep_present: linkedin/limiter.py / "PRAGMA journal_mode=WAL" / WAL still set
  - file_exists: linkedin/db_utils.py / centralized helper

### MERGED-004 — Globals persistence
- phase: B
- checks:
  - sqlite_table: ~/.hermes/data/command_center.db / campaign_runs / VM table exists (SSH check)
  - grep_present: hermes_api_v2.py / "campaign_runs" / table usage
  - grep_present: hermes_api_v2.py / "WHERE status = 'running'" / lifespan reconciliation
  - sqlite_table: hermes_local.db / runtime_state / PC table exists

### MERGED-015 — asyncio create_task hold refs
- phase: B
- checks:
  - grep_present: core/state.py / "def spawn\(" / spawn helper defined (moved from server.py by MERGED-011)
  - grep_absent: server.py / `asyncio\.create_task\((?!coro\))` / no bare create_task outside spawn helper
  - grep_absent: hermes_api_v2.py / `asyncio\.create_task\((?!coro\))` / idem

### MERGED-007 — except Exception: pass logging
- phase: B
- checks:
  - count_max: server.py / `except Exception:\s*\n\s*pass(?!.*noqa)` / fewer than 5 silent bare excepts
  - count_max: hermes_api_v2.py / `except Exception:\s*\n\s*pass(?!.*noqa)` / fewer than 3
  - grep_present: daemon/orchestrator.py / "logger.exception\(" / explicit logging present

### MERGED-016 — dispatch error preservation
- phase: B
- checks:
  - grep_present: server.py / "_local_error_until_ack|preserve_local_error" / preservation flag exists
  - grep_present: dashboard/app.js / "dismiss.*error|ack.*error" / UI dismiss button

## Fase C — Architecture Consistency

### MERGED-013 — Settings central (pydantic-settings)
- phase: C
- checks:
  - file_exists: config.py / Settings root file
  - grep_present: config.py / "pydantic_settings|BaseSettings" / pydantic-settings used
  - grep_present: requirements.txt / "pydantic-settings" / dep declared
  - count_max: server.py / `os\.environ\.get\(` / fewer than 3 (only in startup config bootstrap)
  - count_max: hermes_api_v2.py / `os\.environ\.get\(` / fewer than 3

### MERGED-009 — IP VM via env
- phase: C
- checks:
  - count_max: server.py / "136\.115\.74\.69" / 0 hardcoded
  - count_max: hermes_api_v2.py / "136\.115\.74\.69" / 0 hardcoded
  - count_max: daemon/orchestrator.py / "136\.115\.74\.69" / 0 hardcoded
  - count_max: scripts/tunnel_supervisor.py / "136\.115\.74\.69" / 1 (env default OK)
  - grep_present: config.py / "vm_host" / config field exists

### MERGED-008 — Topology enforced
- phase: C
- checks:
  - grep_absent: server.py / "from linkedin.viewer" / NO direct import linkedin viewer in PC
  - grep_absent: server.py / "from linkedin.engager" / idem
  - grep_absent: server.py / "from linkedin.connector" / idem
  - grep_present: server.py / "proxy.*linkedin|httpx.*linkedin" / proxy pattern present

### MERGED-014 — Ollama fallback router
- phase: C
- checks:
  - file_exists: linkedin/ollama_router.py / router exists
  - grep_present: linkedin/ollama_router.py / "fallback|timeout" / fallback logic

### MERGED-011 — Split monolitos
- phase: C
- checks:
  - line_count_max: server.py / 500 lines max (target after split)
  - line_count_max: hermes_api_v2.py / 500 lines max
  - file_exists: api/__init__.py OR api/prospects.py / split done
  - file_exists: loops/__init__.py / loops separated

### MERGED-012 — Pipeline dedupe
- phase: C
- checks:
  - file_exists: core/pipeline.py / shared pipeline module
  - grep_present: daemon/orchestrator.py / "from core.pipeline|from \.\.core" / daemon imports shared
  - grep_present: scripts/pipeline.py / "from core.pipeline" / script imports shared

## Fase D — Infra & Supervision

### MERGED-017 — Subprocess scraper supervision
- phase: D
- checks:
  - grep_present: hermes_api_v2.py / "psutil" / psutil used for process checks
  - grep_present: hermes_api_v2.py / "start_new_session=True" / proper Popen isolation
  - grep_present: requirements.txt / "psutil" / dep declared

### MERGED-018 — Session monitor consecutive failures
- phase: D
- checks:
  - grep_present: server.py / "consecutive_fail|REQUIRED_FAILS|fail_count" / consec failure counter
  - grep_present: server.py / "(>=|>=\s*3)" / threshold for confirmation

### MERGED-020 — Rate-limit restart endpoints
- phase: D
- checks:
  - grep_present: server.py / "slowapi|Limiter\(|@limiter\." / rate limiter applied
  - grep_present: requirements.txt / "slowapi" / dep declared
  - http_test: POST /api/server/restart-local 5x rapid / expect 429 in last 2

### MERGED-006 — Sync versioning
- phase: D
- checks:
  - sqlite_column: command_center.db / prospects.version / column exists
  - sqlite_column: command_center.db / prospects.updated_at / column exists
  - grep_present: server.py / "version.*conflict|conflict.*version" / conflict resolution

## Fase E — Features & Hardening

### MERGED-010 — Channels Email
- phase: E.1
- checks:
  - file_exists: channels/email/sender.py / non-empty
  - file_exists: channels/email/config.py
  - file_exists: channels/email/limiter.py

### MERGED-010 — Channels WhatsApp
- phase: E.2
- checks:
  - file_exists: channels/whatsapp/sender.py / non-empty
  - file_exists: channels/whatsapp/config.py
  - file_exists: channels/whatsapp/limiter.py

### MERGED-010 — Channels Instagram
- phase: E.3
- checks:
  - file_exists: channels/instagram/sender.py / non-empty
  - file_exists: channels/instagram/config.py
  - file_exists: channels/instagram/limiter.py

### MERGED-019 — XSS markdown allowlist
- phase: E
- checks:
  - grep_present: dashboard/ / "DOMPurify|sanitize" / sanitization library used
  - grep_present: dashboard/ / "ALLOWED_TAGS|allow_list" / allowlist defined

---

## Cross-cutting checks (rodam sempre)

- grep_absent: any *.py / `secrets in code` / no hardcoded credentials
- grep_absent: any *.py / `print\("[A-Z][A-Z_]{4,}=` / no print of env-like values (likely secrets)
- file_exists: .claude/GUARDRAILS.md / updated within last 30 days
- file_exists: .claude/PLAN.md / updated within last 14 days
