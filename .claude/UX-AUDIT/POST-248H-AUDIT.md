# POST-248H FRESH AUDIT — Hermes Cloud Studio
**Sealed**: 2026-06-19
**Scope**: adversarial verification of 25 commits / 248h UX-RM (F1-F8) + hardening (R1-R13, R5-PHASE1/2/3)
**HEAD**: `c6b3061` feat(R5-PHASE3): kill switch strict bearer env flag
**Method**: 14 adversarial audit reports across 3 phases, cross-checked against live code by synthesis agent. Contradictions between reports resolved by direct file reads (not trusting any single auditor).

---

## 1. Verdict Summary

### Overall health score: **7.5 / 10**
The 248h work is **substantially real**. Mock kill is genuine, BLACKLIST R2 is provably untouched, navigation/a11y/wizard deliverables landed. But integration wiring has **4 confirmed gaps** (1 broken script ref, 3 orphan WS listeners that silently never fire) and **2 gateway access-matrix gaps** that would 403 active MCPs. None reach into fake-data-to-UI territory — the cobaia silent-failure class is genuinely closed.

### Count by verdict
| Verdict | Count | Notes |
|---|---|---|
| **regression** | 2 | gateway access_matrix missing hermes-llm + hermes-hunter (active MCPs → fail-closed deny) |
| **new_debt** | 11 | broken script ref, 3 orphan WS listeners, 4 unapplied migrations (lazy-init compensates), orphan endpoints, untested daemon loop |
| **false_claim** | 3 | "0 emoji remaining" (23 remain), `sequenceDryRun` "never invoked" (auditor was WRONG — it IS wired), test count "502" (491 raw defs) |
| **consistency_gap** | 6 | WS `type` vs `event_type` split, 128+ hardcoded font-px, inline backdrop-filter, channel emoji icons, dual schema source-of-truth |
| **confirmed_ok** | 40+ | mock kill, R2 intact, nav 17→8, WCAG AA, keyboard nav, h1, brain confirm drawer, per-role bearer, fail-closed default |

### Cobaia Day 14: **GO (conditional)**
**GO** — every *blocking* criterion from PLAN.md §6 passes with verified evidence. The cobaia activation chain (start-warmup → real DB insert → WS → operator UI) is intact with zero mock fallback. Brain confirmation drawer gates all destructive intents.

**Conditional caveats (non-blocking, fix-before-or-during)**:
1. `template_gallery.js` 404s on every page load (broken `<script>` ref) — console error noise, harmless to function but unprofessional. **Fix: 2 min.**
2. Cobaia operator's **Today Queue** + **Sentry banner** widgets will NOT live-update via WebSocket (orphan listeners, no backend emit). They fall back to 60s polling, so cobaia is still *observable* — just not real-time for those two panels. **Acceptable for Day 14, fix in PA-F2.**

---

## 2. Critical Findings

### ✅ REGRESSION-1 — `hermes-llm` active MCP missing from access_matrix → **RESOLVED PA-F1 commit 0605d7c**
- **File**: `mcps/gateway/access_matrix.json` (no `hermes-llm` rule anywhere)
- **Evidence**: `config.yaml:92` defines `hermes-llm` as `status: active` (F.5.7, the 3-tier LLM routing dispatcher, `required_by_dc: [F.6, F.7, F.4, F.8]`). `access_matrix.json` rules (lines 5-19) have ZERO entry for `hermes-llm`. With `default_policy: "deny"` (line 4), any requester calling `mcp.hermes-llm.route` hits fail-closed and is BLOCKED with 403 `access_denied_by_matrix`.
- **Impact**: If Brain.decide() routes reasoning via `mcp.hermes-llm.route(task_type='reasoning')` (documented default in config.yaml:101), it will be denied — UNLESS the caller resolves to `brain-core` or `api` (the only `"*"` wildcards). Brain sub-requesters `brain-f5/f6/f7-cobaia/f9` etc. all lack `hermes-llm` in their allow-lists. **Direct cobaia-relevant risk**: `brain-f7-cobaia` (line 14) allows only `[sentry, hermes-linkedin, hermes-prospects]` — no `hermes-llm`.
- **Fix**: Add `hermes-llm` to allow-lists of every brain requester that calls LLM routing (at minimum `brain`, `brain-f4`, `brain-f5`, `brain-f6`, `brain-f7-cobaia`, `brain-f7-cobaia-autotune`, `brain-f8`, `brain-f9`). Restart gateway.
- **Effort**: 30 min (edit + verify each requester's actual dispatch targets + restart + smoke).

### ✅ REGRESSION-2 — `hermes-hunter` active MCP missing from access_matrix → **RESOLVED PA-F1 commit 0605d7c**
- **File**: `mcps/gateway/access_matrix.json` (no `hermes-hunter` rule)
- **Evidence**: `config.yaml:21` defines `hermes-hunter` as `status: active` (R7, Hunter.io email verifier, 4 tools). `core/email_verifier.py` dispatches to `hermes-hunter` via GatewayDispatcher using per-role bearer `HERMES_GATEWAY_BEARER_BRAIN_F7_COBAIA`. `access_matrix.json:14` (`brain-f7-cobaia` rule) allows `[sentry, hermes-linkedin, hermes-prospects]` — `hermes-hunter` MISSING.
- **Impact**: `EmailVerifier.verify_email()` → 403. Email verification is part of the cobaia prospecting pipeline. **This IS cobaia-relevant** but degrades gracefully (verification skip) rather than crashing — confirm fallback behavior before relying on it.
- **Fix**: Add `hermes-hunter` to `brain-f7-cobaia` allow-list (+ any other requester that verifies email). Restart gateway.
- **Effort**: 15 min.

> **Severity note**: Both flagged `regression` by the security auditor because R5-PHASE3/H7 hardening tightened the matrix to fail-closed *without* adding rows for the two newest active MCPs (hunter=R7, llm=F.5.7). The hardening is correct; the rule coverage lagged. These are the **only two findings that actively break a working path**.

### 🟠 FALSE_CLAIM-1 — Dead-code auditor wrongly flagged `sequence_dry_run.js` as orphan
- **Files**: `dashboard/components/sequence_dry_run.js`, `dashboard/components/sequence_canvas.js:385-386`
- **Evidence**: The Phase-1 dead-code report claimed `window.sequenceDryRun` is "never invoked" and the `/dry-run` endpoint is "unreachable." **This is FALSE.** Direct grep shows `sequence_canvas.js:385`: `if (window.sequenceDryRun) { window.sequenceDryRun.open(self._sequenceId, {...}) }`. The Phase-2 api-coverage report corroborates the endpoint IS called (`sequence_dry_run.js:132`). The component is wired.
- **Impact**: No code defect — this is an **auditor error**, surfaced here so the owner does NOT waste effort "fixing" working code. The dry-run feature is functional.
- **Fix**: None. (Documenting to prevent a wild-goose chase.)

### ✅ NEW_DEBT-1 (critical-severity) — `template_gallery.js` referenced but file does not exist → **RESOLVED PA-F1 commit 0605d7c**
- **File**: `dashboard/index.html:109` → `<script src="/dashboard/components/template_gallery.js" defer></script>`
- **Evidence**: `ls` confirms the file does NOT exist. The `<script>` tag loads on every page → 404 in network tab + console error. Template gallery functionality appears folded into `template_editor.js` (which IS wired), so no feature is lost — but the broken ref is real.
- **Fix**: Delete line 109 of index.html (or create the file if a separate gallery was intended). **Recommend delete** — `template_editor.js` covers template CRUD.
- **Effort**: 2 min.

### ✅ NEW_DEBT-2 (high) — 3 orphan WebSocket listeners — **RESOLVED PA-F2 commit b8c0467**
- **Files / evidence**:
  - `cobaia_today_queue.js:160` listens for `cobaia.queue_updated` — **zero backend emit** (grep across all `*.py` = 0). Widget IS mounted (`cobaia_operator.js:347`).
  - `cobaia_sentry_banner.js:136` listens for `sentry.issue_new` — **zero backend emit**.
  - `sequences.py:310` emits `sequence.enrolled` — **zero frontend listener**.
- **Impact**: Cobaia operator's Today-Queue and Sentry-banner panels never receive real-time pushes; they rely on 60s poll fallback. `sequence.enrolled` is broadcast into the void. **Cobaia is still observable (poll), so this is non-blocking for Day 14** — but it's a real-time UX gap on the exact operator surface the owner will watch.
- **Fix**: Either (a) add backend emits for `cobaia.queue_updated` (in enroll/advance paths) and `sentry.issue_new`, or (b) remove the dead listeners and rely on poll. Add a `sequence.enrolled` listener to refresh the canvas/queue.
- **Effort**: 2-3h to wire emits properly; 20 min to remove dead listeners if poll is acceptable.

---

## 3. Confirmed OK — what the 248h genuinely delivered

These claims were **adversarially verified against live code** and hold up:

| Claim | Verdict | Evidence |
|---|---|---|
| **Zero mocks in execution paths (C1+C2)** | ✅ REAL | `api/pipelines.py` has zero `random` import/calls (verified). `stub_execute_skill` deleted from codebase (0 grep matches). `generate_search_results()` returns `{source:'unavailable', profiles:[], simulated:False}` on failure — empty, not fake. This is the single most important claim for cobaia and it is **genuinely true**. |
| **BLACKLIST R2 (5 files) intact** | ✅ REAL | `stealth.py` (616 ln), `human.py` (385), `preflight.py` (133), `cooldown.py` (210), `ollama_router.py` (154) — all last touched in early commits (e5dcbe2, 472857f, cbddf9e, d4868fc) far before UX-RM window. Zero monkeypatch/setattr/sys.modules manipulation. Working tree clean. **68 SS claim consistent with untouched-files evidence.** |
| **Nav 17→8 + Cmd+K palette** | ✅ REAL | `index.html` sidebar = 8 top-level items w/ collapsible groups; `HermesCommandPalette` lazy-loaded on Cmd+K; localStorage group persistence. |
| **WCAG AA contrast fix (H4)** | ✅ REAL | `tokens.css:70` `--text-3: #8a8a9a` (was `#55556a`), ~4.7:1 on `#18181c`, passes AA 4.5:1. OKLCH variant present. |
| **Keyboard nav + h1 hierarchy (H5/H6)** | ✅ REAL | nav toggles are real `<button>` w/ `aria-expanded/controls/label`; `_ensurePageH1()` injects `h1.page-h1` per page in `navigate()`. |
| **Brain confirm drawer wired (destructive gating)** | ✅ REAL | `brain/safety.py` `DESTRUCTIVE_ACTIONS` frozenset gates send_outreach/send_message/send_inmail/synth_skill_promote/deploy_skill_pr; `POST /api/brain/confirm/{run_id}` returns 200; drawer mounted + WS handler active. |
| **Telegram STOP signal real (H3a)** | ✅ REAL | `orchestrator.py:213` CREATE TABLE telegram_stop_signals; `:968` `_check_human_stop()` real SELECT query (not stub). |
| **Per-role bearer infra (R5)** | ✅ REAL | `requester.py:16-29` 12 env vars; `derive_requester.py` rejects shared bearer w/ `denied_strict` when strict_bearer=True; requester NOT passed in body (spoof-blocked, `dispatch.py:155`). |
| **Fail-closed gateway default** | ✅ REAL | `access_matrix.py` defaults `deny`; missing file → `AccessMatrix(default_policy='deny')` + CRITICAL log. (This is exactly *why* REGRESSION-1/2 bite — the hardening works.) |
| **Sequences/Templates/ICP/Onboarding API coverage** | ✅ REAL | 24+ dedicated tests; all CRUD + enroll + dry-run + render + spintax + presets covered. Routers registered in `server.py:380-387` w/ consistent X-Hermes-Token auth. |
| **Legit randomness preserved** | ✅ REAL | `template_renderer.py:23` `random.choice` (spintax) + `send_scheduler.py:92` `random.randint` (anti-detection jitter) — both documented exceptions in MCP-BANNED-PATTERNS.json, NOT fake data. Correctly distinguished from killed mocks. |
| **intelligence/ skeleton safe** | ✅ REAL | `scoring.py` + `enrichment.py` raise `NotImplementedError('F.future')` — no silent execution, no import-time crash. |

---

## 4. New Debt + Consistency Gaps (non-blocking)

Sorted by severity × effort:

| # | Sev | Finding | File:line | Effort |
|---|---|---|---|---|
| ND-1 | crit | `template_gallery.js` broken script ref (404) | index.html:109 | 2 min |
| ND-2 | high | 3 orphan WS listeners (queue_updated, issue_new, sequence.enrolled) | see §2 ND-2 | 2-3h / 20min |
| ~~CG-1~~ | ~~med~~ | ~~WS field split: brain.py type vs sequences.py event_type~~ | **RESOLVED PA-F2** brain.py + cobaia.py + scheduler + skills_webhook all → event_type. BrainConfirmDrawer handler updated. | DONE |
| ND-3 | crit→deferred | 4 UX-RM migrations NOT in server.py lifespan (only cobaia_warmup_schedule applied). **Mitigated**: API modules self-apply via `_apply_migration()`/`_ensure_table()` on first request (verified `sequences.py:67,120,133,150,173`). Centralized startup guarantee lost; lazy-init compensates | server.py:88 | 1h |
| ND-4 | high | `sequence_nodes` schema divergence: migration has no DEFAULT for sequence_id/node_type; daemon adds `DEFAULT 0`/`DEFAULT 'action'`. IF NOT EXISTS hides it → first-creator wins | 2026_06_sequences.sql:16 vs orchestrator.py:220 | 1h |
| ND-5 | high | FK constraints in migration (`ON DELETE CASCADE`) absent from daemon init → cascade-delete availability depends on init order | orchestrator.py:220 | 1h |
| ND-6 | med | Dual schema source-of-truth: daemon_sequence_inbox tables defined in BOTH orchestrator.py:193 AND migration. Maintenance burden doubles | orchestrator.py:193 | 30min |
| CG-2 | high | 128+ hardcoded px font-sizes across pipeline-studio.css(37), skill-proposals.css(32), onboarding.css(35), observability.css(22) — should use `--text-*` tokens | dashboard/styles/* | 3-4h |
| CG-3 | high | 23 bare emoji remain (claim was "0"). CHANNEL_ICONS in sequence_dry_run.js uses 💼✉️💬📨; ✓✗ status emoji in app.js/skill_proposals_*/command_palette | sequence_dry_run.js:18 | 2-3h |
| CG-4 | med | Inline `backdrop-filter:blur()` bypasses glass utility classes (6 sites in styles.css + components + index.html:2070) | styles.css:59 | 1-2h |
| ND-7 | low-med | Orphan endpoints (no frontend caller): `POST /api/templates/render`, `POST /api/brain/decide`, `POST /api/brain/replay/{run_id}`, `GET /api/brain/intents`, `DELETE /api/sequences/{seq_id}`. Likely intentional internal/admin APIs | see reports | n/a (triage) |
| ND-8 | med | Untested: daemon `HermesDaemon.run()` main loop + DaemonState machine; `brain.py` queue-stats/list_intents endpoints | orchestrator.py:124, brain.py:304 | 2-3h |
| FC-3 | info | Test count claim "502" vs 491 raw `def test_` (diff likely parametrized cases — not a material false claim) | tests/ | n/a |
| ND-9 | low | Index definitions duplicated (migration + orchestrator.py:242) — idempotent, cosmetic | inbox migration:15 | 15min |
| info | info | Dead `"stub": True` metadata in `cobaia_intent.py:104` — never read, harmless cargo-cult | cobaia_intent.py:104 | 5min |

---

## 5. Remediation Roadmap

Cobaia Day 14 can proceed **without** completing these. Recommended ordering:

### ✅ PA-F1 — Gateway access-matrix fix — **DONE commit 0605d7c 2026-06-19**
- **Scope**: Add `hermes-llm` + `hermes-hunter` to correct requester allow-lists in access_matrix.json; restart gateway; smoke-test brain→llm route and email_verifier→hunter dispatch.
- **Effort**: 45 min
- **Cobaia-blocking?**: **Partially** — `hermes-hunter` (email verify in prospecting) and `hermes-llm` (brain reasoning) are both in the cobaia path. Not a crash, but degrades. **Strongly recommend before Day 14 if cobaia uses brain LLM routing or email verification.**

### ✅ PA-F1.5 — hermes-hunter VM deploy + telegram flaky fix — **DONE 2026-06-19**
- **Telegram fix**: `tests/test_telegram_integration.py:92` `_last_threshold_alert = float('-inf')` (was `0.0`). Root cause: `time.monotonic()` uptime-relative; if uptime < 3600s cooldown window, test failed. Verified 3/3 deterministic. +2 tests `test_pa_f15_closeout.py`.
- **hermes-hunter VM deploy**: SCP `mcps/hunter/server.py` → VM. Idempotent Python append to `~/.hermes/mcps/gateway/config.yaml`. Restarted `hermes-mcps-gateway` (systemctl --user). Smoke: `POST /dispatch/hermes-hunter/check_account_usage` → `{"status":"ok","plan_name":"Free","calls_used":0,"calls_available":75}`. Hunter.io key valid, free tier active.
- **Pytest**: 510 PASS, 0 FAIL. BLACKLIST R2 INTACTO 70 SS.

### ✅ PA-F2 — WS wiring + real-time operator UX — **DONE commit b8c0467 2026-06-19**
- **Scope**: (a) WS event_type standardized: brain.py + cobaia.py + cobaia_warmup_scheduler + skills_webhook (4 files). (b) cobaia.queue_updated emits added in 3 paths (enroll/advance/skip). (c) sentry.issue_new Option A: capture_exception emits WS on error/fatal. (d) sequence.enrolled listener in app.js + CobaiaTodayQueue.refresh exported. BrainConfirmDrawer handler updated to event.event_type. cobaia.py _ws_emit json.dumps bug fixed.
- **Tests**: +7 tests_pa_f2_ws_wiring + 1 fix ux_rm_f5a. 517 PASS. BLACKLIST R2 INTACTO 71 SS. Reviewer PASS-WITH-NOTES 0 BLOCKERs.

### ✅ PA-F3 — Migration centralization + schema reconciliation — **RESOLVED commit 95f937a**
- **Scope**: Apply 4 UX-RM migrations in server.py lifespan; reconcile sequence_nodes DEFAULTs + FK constraints between migration and daemon; collapse dual schema source-of-truth.
- **Effort**: 3-4h
- **Cobaia-blocking?**: **No** — lazy-init `_apply_migration()` compensates today.
- **Fix**: server.py PA-F3 block centralizes 5 migrations (sequences, templates, daemon_sequence_inbox, onboarding_state, icp_profile). Created `migrations/2026_06_templates.sql` as canonical. Removed `DEFAULT 0`/`DEFAULT 'action'` drift from `daemon/orchestrator.py:sequence_nodes`. Aligned `api/sequences.py` lazy-init with FK constraints + indices. Lazy-init fallback preserved (defense-in-depth). 12 tests (idempotency 2x, drift, fallback presence). 529 pytest PASS, BLACKLIST R2 INTACTO 72 SS.

### PA-F4 — Design consistency cleanup (polish) ✅ RESOLVED
- **Scope**: Tokenize 664 px font-sizes; move inline backdrop-filter to glass vars/classes.
- **Status**: RESOLVED — commit 5e14256.
- **Fix**: 9 orphan tokens added (--text-3xs→--text-3xl-alt) + 7 --glass-blur-* vars + 2 overlay-bg tokens. Python script replaced 664 font-size:Xpx → var(--text-TOKEN) across 14 files. 16 logical backdrop-filter migrated: CSS files use var(--glass-blur-*); JS overlay divs use .modal-scrim class; panel-close HTML uses .panel-close-glass class. 6 new tests. 535 pytest PASS, BLACKLIST R2 INTACTO 73 SS. frontend-ux-reviewer PASS-WITH-NOTES 0 BLOCKERs.
- **Note**: emoji→icon() portion deferred (out of scope for PA-F4). Zero visual change (Opção A). All token values exact to original px.

### ✅ PA-F5.1 — Wall-clock flaky fix + sweep — **RESOLVED commit TBD 2026-06-21**
- **Scope**: Fix 3 weekend-flaky tests + consolidate datetime source in cobaia_warmup + sweep 6 wall-clock sites.
- **Root cause**: `cobaia_warmup.daily_check()` used `date.today().weekday()` (unmockable local import) and `date.today().isoformat()` (unmockable). Weekend gate fired before auto-pause check on Sat/Sun → `auto_paused` never returned.
- **Fix**: Consolidated ALL time usage to `datetime.now(timezone.utc)` (mockable). Removed `date` from imports. Removed inline `from datetime import date as _date`. 3 tests wrapped with `patch("linkedin.cobaia_warmup.datetime")` → Tuesday mock (weekday=1).
- **Sweep verdict**: 6 wall-clock sites in tests. All deterministic or already mocked — no additional flaky sites found.
- **Tests**: 547 pytest PASS, 0 FAIL. BLACKLIST R2 INTACTO 75 SS. Determinism: 3 prev-flaky tests × 3 runs = 9/9 PASS.

### ✅ PA-F5 — Test debt + dead code (hygiene) — **RESOLVED commit a9cf0d1 2026-06-19**
- **Scope**: Test daemon run() loop + brain queue-stats/list_intents; remove `"stub":True` cargo-cult; dedupe indices; triage orphan endpoints.
- **Fix**: `cobaia_intent.py` stub:True REMOVED (dead field, orchestrator never reads args key). `hermes-skills/server.py` stub:True KEPT with descriptive comment (semantic LLM metadata, not cargo-cult). `orchestrator.py` dup indices documented (idempotent, safe). Orphan endpoints (/brain/decide /brain/replay /brain/intents /templates/render DELETE /sequences) all documented with caller context — none removed. New tests: `test_pa_f5_cleanup.py` +8 (run_forever x2, list_intents, stub triage x2, dup index x2, orphan triage). 543 pytest PASS, BLACKLIST R2 INTACTO 74 SS. **PA-F1..F5 100% COMPLETE.**
- **Cobaia-blocking?**: **No**.

---

## 6. Cobaia Day 14 Final Readiness Gate

PLAN.md §6 blocking criteria, re-verified by synthesis against live code:

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | UX-RM-F1 100% (zero mocks in exec paths) | ✅ PASS | `api/pipelines.py` zero random; `stub_execute_skill` deleted (0 grep); test_ux_rm_f1a_mock_kill.py |
| 2 | UX-RM-F2-A (sidebar 17→8 + breadcrumbs) | ✅ PASS | index.html 8 collapsible groups + localStorage persistence |
| 3 | UX-RM-F2-B (Cmd+K palette + shortcuts) | ✅ PASS | HermesCommandPalette IIFE, WCAG role=dialog/aria-modal/focus-trap |
| 4 | Brain confirm drawer wired (all destructive) | ✅ PASS | safety.py DESTRUCTIVE_ACTIONS frozenset; confirm endpoint 200; drawer mounted |
| 5 | LI_USE_MOCK removed | ✅ PASS | zero grep matches in dashboard/js |
| 6 | Comment edit/delete hidden + 501 | ✅ PASS | api/linkedin.py:431-442 return 501; UI buttons removed |
| 7 | Daemon TODOs closed (9) | ✅ PASS | test_ux_rm_f1b_daemon_todos.py; STOP/inbox/sequence-due implemented, rest 501 |
| 8 | All "n/c" channels configurable | ✅ PASS | app.js:3929 inline "Configurar" link → navigate(skills) |
| 9 | WCAG AA contrast fix | ✅ PASS | tokens.css:70 `--text-3:#8a8a9a` ~4.7:1 |
| — | **Cobaia activation chain intact** | ✅ PASS | start-warmup→`mgr.start_warmup()`→real INSERT cobaia_warmup_state→WS `cobaia.warmup_started`→CobaiaOperator mounts. **No mock fallback.** |
| — | Preflight endpoint (6 checks) | ✅ PASS | api/cobaia.py:496 returns {checks, all_pass} |

### Gate decision: ✅ **GO**

All 9 blocking criteria + activation chain pass with verified evidence. The cobaia silent-failure class (fake profiles, stub_execute returning mock_success) is **genuinely eliminated** — confirmed by direct code reads, not just auditor assertion.

**Recommended pre-flight actions (not blockers)**:
1. Run **PA-F1** (gateway matrix) if cobaia will use brain LLM routing or Hunter email verification — both currently hit fail-closed 403.
2. Be aware: Today-Queue + Sentry-banner operator panels update via 60s poll, NOT real-time WS (orphan listeners). Cobaia remains observable.
3. Delete `template_gallery.js` script ref to clear console 404 noise.

**Bottom line**: The 248h delivered real substance. No fake-data path reaches the UI. The honest gaps are integration-wiring (WS orphans, one broken ref) and gateway rule-coverage lag behind hardening — none of which silently fabricate cobaia state. Owner can activate the real LinkedIn account with the named caveats addressed or accepted.
