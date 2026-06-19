# UX-AUDIT - Hermes Cloud Studio

**Sealed**: 2026-06-18
**Cobaia ETA**: ~Day 14 (warmup launch 1-2 weeks)
**Owner**: Caio (non-technical, solo)
**Audit scope**: 35+ components, 145+ API routes, 50+ WS events, 17+ skills, dashboard `app.js` (~7000 LOC) + `index.html` (~2400 LOC)

---

## 1. Executive Summary

Hermes is technically dense but UX-immature for a non-technical solo operator. Backend (FastAPI + APScheduler + Brain.decide + MCP gateway) is production-shaped, but the dashboard exposes raw F.x scaffolding (17 sidebar items, 5+ modal-heavy wizards, n/c placeholders, no Cmd+K, no breadcrumbs, no keyboard shortcuts). Worse, **two CRITICAL fake-data paths** ship to UI: (a) `api/pipelines.py:354` returns randomly-generated LinkedIn profiles flagged `simulated=True` but rendered as real findings, and (b) `linkedin/cobaia_warmup.py:357` `stub_execute_skill()` returns hardcoded `mock_success` for every warmup action. Both are cobaia-blocking — shipping them once Caio activates the real account = silent zero-action warmup + fabricated prospect counts.

### Top 5 wins (if F1-F4 ship)
1. Kill 2 critical mocks + 6 daemon TODOs → Hermes becomes 100% real
2. Consolidate 17 nav items → 8 + Cmd+K palette (kbar) → power-user navigation
3. Lemlist-style multi-channel canvas (LI+email+WA) → 1 view replaces 3 pages
4. Brain confirmation flow with rich preview (recipient, body, channel, ETA) → Caio approves every outbound action with confidence
5. Tremor/shadcn tokenized design system (OKLCH) + Geist + Lucide → professional cockpit feel

### Top 5 risks if NOT shipped
1. Cobaia Day 1 silent failure — stub_execute_skill returns success, Caio sees green KPIs, zero LI activity
2. Fabricated prospect data in pipeline runs misleads Caio into bad outreach decisions
3. 17-item sidebar + 4-tab subsystems → Caio gets lost, abandons dashboard, runs ops blind
4. No keyboard nav + no Cmd+K → 3x slower workflows vs Apollo/Lemlist benchmark
5. Accessibility violations (text-3 contrast 2.8:1, divs as buttons, no H1) → fails axe-core in F.2.4 follow-through

### Hermes "100% Real" Readiness Gate Criteria
- ZERO `random.randint`, `random.choice`, `mock_success`, `simulated=True` in execution paths reachable from UI
- ZERO `TODO` in `daemon/orchestrator.py` lines 548, 660, 666, 906, 911, 948, 955, 986, 1001
- Comment edit/delete endpoints either complete or hidden from UI
- `LI_USE_MOCK` flag removed from `dashboard/app.js`
- `intelligence/` package implemented OR removed
- Every "n/c" channel either configurable inline or hidden
- Brain confirmation drawer required for ALL destructive intents (send_outreach, accept_connect, send_email, send_whatsapp) before Day 14

---

## 2. Current State Inventory

### Navigation map
- 17 sidebar items (Control, Dashboard, Prospects, Propostas, Auditoria, Pipeline Studio, Fila do Dia, Skills, Skill Proposals, LinkedIn, Cobaia, Lab, Memoria, Missoes, AI Terminal, MCP Gateway, Observability) + footer (Novo Scraping, Configuracoes)
- Hash routing (`#<page>`) with single `index.html`, no SPA framework
- 4-5 internal tabs each on Pipeline Studio, Observability, LinkedIn monitor, Work Queue
- 1 modal-overlay settings panel (Configuracoes), 1 side-drawer (Brain Confirm), 1 global topbar search

### Components inventory
- **35 JS components** under `dashboard/components/` covering: skeleton/toast (F.2.4), subsystem tile grid, pref/panic panels, live log tail, lab cockpit suite (gauge + fingerprint diff + cockpit), MCP gateway, brain confirm (card + drawer), observability shell (5 tabs), pipeline studio shell (4 tabs), cobaia suite (status card + KPIs + activity feed + emergency stop + timeline + studio), skill proposals studio
- **Critical paths**:
  - Cobaia: `cobaia_studio.mount()` → WS `cobaia.*` events → KPI/timeline/activity render
  - Brain: `brain_confirm_drawer` → WS `brain.run_awaiting_confirm` → confirm card → POST `/api/brain/confirm/{id}`
  - Pipeline: `pipeline_studio_runs_monitor` → WS `pipeline.step_*` + 5s polling fallback
  - LinkedIn: 4 campaign cards + monitor tabs → POST `/api/linkedin/campaigns/{view|engage|connect|discover}`

### API routes catalog (145+)
11 router groups: `bootstrap`, `linkedin` (40+), `cobaia` (~25), `observability` (8 + debug), `daemon` (8+), `brain` (5+), `pipelines/pipeline-studio` (10+), `prospects`/`audit` (10+), `lab` (8+), `skills`/`skills_webhook` (8+), `mcp_coverage`. Notable: `bootstrap` loopback-only for Tauri/extension auth.

### WS events catalog (50+)
- `daemon.subsystem_status`, `daemon.log_event`, `daemon.decision`
- `cobaia.daily_check_done`, `cobaia.state_changed`, `cobaia.auto_paused`, `cobaia.activity`, `cobaia.metrics_updated`
- `brain.run_awaiting_confirm`, `brain.run_confirm_resolved`
- `lab.run_started/step_progress/screenshot_captured/compliance_score/fingerprint_dump/run_completed/failed/aborted`
- `pipeline.step_*`, `pipeline.run_complete/aborted`
- `skill_proposal.*`

### Design system maturity score: **4/10**
- **Have**: tokens.css/light.css canonical (F.2.4), window.hermesToast, window.skeleton, DOMPurify, axe-core vendored, FOUC inline script
- **Missing**: OKLCH color space, typography scale (Geist/Geist Mono), motion budget, icon library decision (currently inline emoji + scattered), Cmd+K, focus-visible styles, density toggle, AI component state variants (idle/streaming/loading/complete/error), light/dark/auto runtime switch, semantic intent colors (success/warning/danger/info)
- **Coexists**: legacy styles.css with shadow CSS variables (back-compat preserved)

---

## 3. Issues Catalog

See `issues.json` for full machine-readable list. Summary counts:
- **CRITICAL**: 4 (2 mock kills + 2 navigation overload)
- **HIGH**: 13 (TODO daemon, hardcoded thresholds, UX coupling, a11y violations, no breadcrumbs, hidden features)
- **MEDIUM**: 11 (in-memory stubs, no auto-refresh, modal-heavy, contrast)
- **LOW**: 14 (comments, dead code, stub indicators, observability gaps)

### Critical (cobaia-blocking)
| # | File:line | Issue | Effort | Status |
|---|-----------|-------|--------|--------|
| C1 | `api/pipelines.py:354` | `generate_search_results()` returns random fake LI profiles flagged simulated=True but rendered as real | 8h | ✅ RESOLVED UX-RM-F1-A 3ef83ee |
| C2 | `linkedin/cobaia_warmup.py:357` | `stub_execute_skill()` returns `mock_success` for every warmup action | 12h | ✅ RESOLVED UX-RM-F1-A 3ef83ee |
| C3 | `dashboard/index.html:274` | 17 sidebar items, no Cmd+K, cognitive overload for non-technical | 16h | open |
| C4 | `dashboard/index.html:1070` | Modal-heavy create flows (Pipeline/Task/Mission) — 640px cramped forms | 12h | open |

### High (top 5 of 13)
| # | File:line | Issue | Effort |
|---|-----------|-------|--------|
| H1 | `dashboard/app.js:5432` | Comment edit "Salvar (placeholder)" — modal open but operation fails | 4h |
| H2 | `brain/_smoke.py:55` + `_react.py:32` + `safety.py:11` | MockDispatcher reachable via env + hardcoded MAX_REACT=5 + CONFIDENCE=0.5 | 6h |
| H3 | `daemon/orchestrator.py:548,660,666,906,911,948,955,986,1001` | 9 TODOs — Telegram STOP, scoring, PDF report, sequence inbox, channel sending, enrichment, auto-reply, follow-up | 32h | ✅ RESOLVED UX-RM-F1-B — 4 real + 5 stub-501 |
| H4 | `dashboard/styles.css:34` | `--text-3` (#55556a) on `--s2` (#18181c) = 2.8:1, fails WCAG AA 4.5:1 | 2h |
| H5 | `dashboard/index.html:275` | 19+ interactive divs without role/tabindex/aria-label, no keyboard nav | 8h |

---

## 4. 2026 Tech Stack Recommendations

### AI UX patterns top 5
1. **Command Palette (Cmd+K)** via `kbar` — fuzzy search across 145 endpoints + entities
2. **Agent Confirmation Flow** with rich preview (recipient, body, channel, scheduled time) — extends existing BrainConfirmDrawer
3. **Streaming AI Sidebar** — Brain.decide ReAct trace streaming token-by-token per prospect/deal
4. **Citation Pills** — every enriched field (email/role/funding) shows source provider (Hunter/Apollo/LinkedIn/Firecrawl) + freshness
5. **Generative UI components** — Brain returns typed ProspectCard/DealColumn/SequenceTimeline via Vercel AI SDK streamUI

### Sales dashboard patterns top 5
1. **Lemlist-style visual multi-channel canvas** — LI+email+WhatsApp+task in single drag-drop sequence
2. **Apollo-style ICP Pipeline Builder** — 3-tier intent score (Low 0-61 / Med 62-75 / High 76-100)
3. **MailReach/Lemwarm deliverability dashboard** — single health score 0-100 + placement-per-provider
4. **HubSpot AI Summary cards** — drag-drop home cards (Stalled / Next Best Action / Today's Replies / Cobaia Health)
5. **HeyReach unified inbox** — LI+email+WA in single conversation per prospect

### Visual stack final
- **Base**: shadcn/ui + Tailwind v4 (OKLCH) + Next.js (matches forge-sdk v1.0)
- **Typography**: Geist Sans (UI) + Geist Mono (IDs/timestamps/scores) + Inter Tight fallback for dense tables
- **Animation**: Motion 12 (95% UI) + GSAP locked behind ESLint `no-gsap-outside` (hero/storytelling only)
- **Icons**: Lucide primary (1500+, smallest bundle) + Phosphor Fill for active tab states
- **Color**: OKLCH B2B blue `oklch(0.62 0.21 260)` + semantic tokens (success/warning/danger/info), auto theme
- **Liquid Glass**: SELECTIVE — ambient surfaces only (Cmd+K, toasts, Brain side panel). NEVER on prospect list/inbox/pipeline kanban
- **Motion budget**: 200/250/300/350ms (fast/base/slow/toast), hard cap 500ms, NO animation on data refresh

### Component library decision
- **Vercel AI SDK** (`streamUI` + RSC) for Brain streaming + generative cards
- **kbar** for Cmd+K (Linear/Sourcegraph proven)
- **Tremor charts** (Vercel-owned) for KPI dashboards (cobaia health, brain decisions/day, hit-rate)
- **Recharts/Visx** retained from existing observability if migration cost > value

---

## 5. Roadmap UX-RM-F1..F8

### UX-RM-F1: Mock Kill + Real Backend Wire-Up (COBAIA-BLOCKING) ✅ COMPLETE
- **Goal**: Zero fake-data in execution paths. 100% real backend before Day 14.
- **Effort**: 40h
- **Files**: `api/pipelines.py`, `linkedin/cobaia_warmup.py`, `daemon/orchestrator.py` (9 TODOs), `dashboard/app.js` (remove LI_USE_MOCK), `brain/safety.py`, `brain/_react.py`, `intelligence/`
- **Acceptance**:
  - ✅ `grep -rE "random\.(randint|choice)" api/ linkedin/ daemon/` returns zero in production paths (F1-A)
  - ✅ `stub_execute_skill` deleted, `_exec_cobaia_warmup` calls real LI MCP (F1-A)
  - ✅ Comment edit/delete UI hidden, endpoints return 501 F.future (F1-C)
  - ✅ All "n/c" channels have inline "Configurar" link (F1-C)
  - ✅ LI_USE_MOCK removed entirely from dashboard/app.js (F1-C)
  - ✅ 9 daemon TODOs killed — 4 real + 5 deferred 501 stubs (F1-B)
  - ✅ intelligence/ skeleton with scoring.py + enrichment.py raise NotImplementedError (F1-C)
- **Cobaia-blocking**: YES → RESOLVED 2026-06-18
- **Deps**: VM linkedin MCP healthy

### UX-RM-F2: IA Consolidation + Cmd+K (COBAIA-BLOCKING)
- **Goal**: Reduce sidebar 17→8. Add Cmd+K palette. Breadcrumb trail.
- **Effort**: 32h
- **Files**: `dashboard/index.html`, `dashboard/app.js`, new `dashboard/components/command_palette.js`, new `dashboard/components/breadcrumb.js`
- **Acceptance**:
  - Sidebar: Control, Cobaia, Pipeline, Outreach (=Prospects+Propostas+Auditoria merged), Skills, Observability, AI Terminal, Settings — plus collapsible "Advanced" (Lab, MCP Gateway, Skill Proposals, Memory, Missions)
  - Cmd+K opens kbar with fuzzy search of all pages + entities + actions
  - Breadcrumb: `Dashboard > Outreach > [Business Name] > Audit`
- **Cobaia-blocking**: YES
- **Deps**: F1

#### UX-RM-F2-A: Sidebar consolidation 17→8 groups + breadcrumbs ✅ DONE 2026-06-18
- 8 collapsible .nav-group / .nav-single items (4 groups + 3 singles + settings footer)
- All 17 original pages routable via sub-items, data-page attrs preserved
- localStorage 'hermes.nav.expanded_groups' persistence + auto-expand owning group on navigate()
- aria-current="page", aria-expanded, aria-controls, role="navigation" + aria-label
- Breadcrumb bar: Dashboard › Group › Page rendered by HermesBreadcrumbs component
- Contrast WCAG AA fix: bc-link uses --text-2 (5.88:1), focus-visible on all new elements
- 5 new tests, 303 pytest PASS, C3 RESOLVED in issues.json

#### UX-RM-F2-B: Cmd+K palette + G-prefix shortcuts + filter persistence ✅ DONE 2026-06-18
- HermesCommandPalette: Ctrl/Cmd+K toggle, fuzzy filter, grouped results, Arrow/Enter/Escape nav
- WCAG 2.1 AA: role=dialog, aria-modal, aria-label, focus trap, live region aria-live=polite
- 17 navigation commands + 4 action commands registered from app.js startup
- HermesKeyboardShortcuts: g-prefix 1500ms window, 9 shortcuts (g d/c/b/p/o/l/s/m/x)
- Skips when focused on INPUT/TEXTAREA/SELECT, ? key triggers help overlay
- HermesShortcutsHelp: grouped modal, Escape/click-outside to close, focus restored on close
- HermesFilterPersistence: localStorage namespace hermes.filters.<page>, prospects+proposals wired
- Filter restore after loadFilters() populates dropdowns; change listeners auto-save
- H4 RESOLVED: --text-3 #55556a → #8a8a9a (~4.7:1 WCAG AA pass) in styles.css
- 33 new tests, 336 pytest PASS, C3+H4 RESOLVED in issues.json
- UX-RM-F2 100% COMPLETE (F2-A 14h + F2-B 18h = 32h)

### UX-RM-F3: Onboarding Wizard 5min
- **Goal**: Caio Day 0 → working cobaia in <5min without docs.
- **Effort**: 20h
- **Cobaia-blocking**: SOFT (Caio can manually configure but wizard is launch-confidence boost)
- **Deps**: F1, F2

#### UX-RM-F3-A: Wizard Framework + Welcome + Profile + Channels ✅ DONE 2026-06-18
- HermesOnboardingWizard IIFE: register(step), open({resume,startStep}), next/prev/skip/complete
- First-run detection in startPage() via _checkOnboarding() — server-side + localStorage fallback
- api/onboarding.py: GET/POST /api/onboarding/state + POST /api/onboarding/complete + POST /api/channels/configure + GET /api/channels/{ch}/test (501 for unconfigured)
- migrations/2026_06_onboarding_state.sql: onboarding_state table, idempotent
- Step 1 Welcome: 3 value cards (AI Brain/Cobaia Segura/Observabilidade), "~5min" disclosure, Comecar button
- Step 2 Profile: 8-item checklist, min 4 done to advance (aria-disabled), inline 14-day playbook expandable
- Step 3 Channels: 4 accordion sections (LI/Email/WA/TG), inline config fields + Test/Save per channel, aria-live status
- WCAG: role=dialog aria-modal focus-trap Tab/Shift+Tab Escape focus-restore aria-valuenow progressbar aria-disabled next-btn
- CSS: dashboard/styles/onboarding.css — all tokens, --accent-l for summary contrast (6.93:1 AA pass)
- 6 tests (355 pytest PASS), frontend-ux-reviewer PASS-WITH-NOTES (B1+B2 fixed pre-commit, 5 WARNs F.future)
- Browser smoke: all 3 steps navigate, skip persists, resume from state works

#### UX-RM-F3-B: ICP Filters + Launch Preflight + Start Warmup CTA ✅ DONE 2026-06-18
- migrations/2026_06_icp_profile.sql: icp_profile table (11 cols, idempotent)
- core/icp_store.py: DAL upsert_profile+get_profile, JSON array serialization for list fields
- api/icp.py: GET/POST /api/icp/profile + GET /api/icp/presets (3 Cuiaba-MT templates)
- Step 4 ICP: 3 preset cards + custom fieldsets (industries/size/job_titles/seniority/geo/daily)
  - _loadPreset updates inputs directly (no re-render) — avoids async card listener bug
  - _escAttr on all value= attributes; onExit POSTs /api/icp/profile; validate requires target+geo
- Step 5 Launch: 5 async preflight checks via Promise.all
  - profile/channels/icp/connections(warn)/hermes — aria-live polite + spinners + prefers-reduced-motion
  - allGreen enables "Iniciar Warmup" CTA; connections is warn-only (not blocking)
  - _startWarmup: POST start-warmup + hermesToast + complete() + navigate(cobaia)
  - _escHtml on user-derived strings in innerHTML
- onboarding.css +271 lines: ICP form, fieldsets, preset grid, seniority chips, preflight list, launch CTA
  - BLOCKER fixed: .wiz-field input:focus-visible outline (WCAG 2.1 AA 2.4.7)
  - amber as var(--amber, #f59e0b) token; btn-secondary added
- 7 tests (362 pytest PASS, 2 skipped), frontend-ux-reviewer NEEDS-FIXES→fixed (1 BLOCKER + 5 WARNs resolved pre-commit)
- Browser smoke: presets load+click fills form, 5 preflight items render, ICP=ok, hermes=ok
- UX-RM-F3 100% COMPLETE (F3-A + F3-B = 20h), BLACKLIST R2 INTACTO 56 SS

### UX-RM-F4: Visual Redesign (tokens + typography + motion)
- **Goal**: Tremor-aligned cockpit feel. Pro-grade typography. Motion budget enforced.
- **Effort**: 36h
- **Files**: `dashboard/styles/tokens.css` (OKLCH migration), `dashboard/styles/typography.css` (Geist), `dashboard/styles/motion.css` (200/250/300/350ms tokens), all components
- **Acceptance**:
  - OKLCH color system + light/dark/auto toggle persisted
  - Geist Sans/Mono loaded with preload, Inter Tight fallback
  - All animations within budget, ESLint rule `no-motion-over-500ms`
  - WCAG AA contrast 4.5:1 minimum (text-3 fix from H4)
  - Lucide icons replacing inline emoji
- **Cobaia-blocking**: NO (cosmetic, but builds trust)
- **Deps**: F2

### UX-RM-F5: AI Command Bar + Streaming Brain Sidebar

#### UX-RM-F5-A: Brain streaming endpoint + Cmd+K AI mode SSE ✅ DONE 2026-06-18
- POST /api/brain/stream-decide SSE endpoint, rate limit 10/min (BRAIN_STREAM_MAX_RPM), fail-CLOSED 429+Retry-After
- react_loop_streaming() async generator yields thought/tool_call/tool_result/final/error events
- Brain.stream_decide() wires streaming ReAct to Cmd+K AI mode (/ or ?ask prefix)
- HermesCommandPalette extended: AI mode detection, SSE reader+AbortController, typewriter thoughts, tool pills, conf badge
- WCAG AA: Tab→Stop btn, role=log+aria-live, XSS-safe (Number.isFinite coercion), all contrast ≥4.5:1
- WS telemetry brain.ai_query_used after stream, 6 new tests (342 PASS total)
- commit 1195d4b

#### UX-RM-F5-B: Brain sidebar + citation pills + multimodal paste + confirm flow ✅ DONE 2026-06-18
- Citation events in stream_decide + brain/citation_resolver.py (skill/memory/log/tool/doc resolvers)
- Citation pills in Cmd+K: clickable buttons, Tab+Enter nav, CSS tooltip, confidence badge, navigate() on click
- Image paste handler: clipboard paste → base64 → image_b64 POST field → graceful 501 stub
- BrainStreamRequest.image_b64 field (server-side 10MB cap, client 5MB guard)
- "Expandir →" button on final answers > 1000 chars → opens HermesBrainSidebar
- HermesBrainSidebar: right-side 420px panel, follow-up questions, 10-turn localStorage history
- BrainConfirmDrawer.show({intent, confidence, source}) + palette_ai_mode telemetry WS broadcast
- requires_confirm=True in final event → palette closes → BrainConfirmDrawer.show() in 600ms
- WCAG AA: --accent-l (#a78bfa) 6.50:1 on --s2, all pills Tab+Enter, sidebar focus mgmt
- 7 new tests, 349 pytest PASS, BLACKLIST R2 INTACTO 54 SS
- frontend-ux-reviewer: PASS-WITH-NOTES (1 BLOCKER fixed, W1+W2 fixed, 5 WARNs F.future)
- UX-RM-F5 100% COMPLETE (F5-A 16h + F5-B 12h = 28h)

### UX-RM-F6: Multi-Channel Campaign Editor (Lemlist-style)
- **Goal**: Single drag-drop canvas mixing LI DM + email + WhatsApp + manual task with conditional branching.
- **Effort**: 48h
- **Files**: new `dashboard/pages/sequences.html`, new `dashboard/components/sequence_canvas.js`, `api/outreach.py`, `daemon/orchestrator.py` (sequence_enrollments)
- **Acceptance**:
  - Visual flow with channel icons + delay nodes + branching diamonds
  - AI variables with side-by-side per-prospect preview
  - Template gallery (Cuiabá tech recruiters, retail audit, follow-up)
  - Unified inbox merging replies across channels per prospect
- **Cobaia-blocking**: NO (cobaia uses LI-only initially)
- **Deps**: F1, F2, F3

### UX-RM-F7: Performance + Accessibility Polish
- **Goal**: WCAG 2.1 AA pass, axe-core green, FCP <1.5s, TTI <3s.
- **Effort**: 20h
- **Files**: all components (ARIA pass), `dashboard/index.html` (H1 hierarchy), `dashboard/app.js` (keyboard handlers), `tests/a11y/*.spec.js`
- **Acceptance**:
  - axe-core CI passing zero violations
  - All interactive divs → buttons or role/tabindex/aria-label + keyboard handlers
  - H1 per page via navigate()
  - Form labels associated via `for`/`id`
  - Live regions for real-time updates (decisions, activity feed, KPIs)
  - Focus-visible 3:1 contrast
- **Cobaia-blocking**: NO
- **Deps**: F4

#### UX-RM-F7-B: axe-core + H1 hierarchy + div→button + Optimistic UI + Error Boundary ✅ DONE 2026-06-19
- dashboard/components/axe_runner.js NEW: HermesAxeRunner + ObservabilityA11y tab adapter (17 pages, wcag2a+wcag2aa+wcag21aa)
- dashboard/components/optimistic_mutations.js NEW: HermesOptimisticMutation (optimisticUpdate + rollback sync + aria-live announce)
- dashboard/components/error_boundary.js NEW: window.error scoped to [data-component] + _renderFallback + telemetry POST
- dashboard/app.js: _ensurePageH1() sr-only injection per page + called from navigate()
- dashboard/app.js: div→button 7 conversions (list-row, hl-exec-card, pl-role-chip, renderHistoryRow, claude history, li-section-header, li-campaign-card-header)
- dashboard/app.js: B2 fix — li-campaign-card-top wrapper; actions extracted as sibling of toggle button (no nested buttons)
- dashboard/app.js: B1 fix — aria-expanded="${!isCollapsed}" + liToggleCampaignCard() syncs aria-expanded on toggle
- dashboard/app.js: data-dismiss-fn event delegation replaces all 4 inline onclick on modal-overlay divs
- dashboard/app.js: toggleSkill wired to window.optimisticMutation with rollback
- dashboard/index.html: 2 sidebar nav-items + topbar-status + li-chip-custom → semantic button
- dashboard/index.html: 4 modal-overlay divs: onclick removed, data-dismiss-fn + role/aria-labelledby added
- dashboard/index.html: A11y tab added to Observability tabnav; axe-runner-panel mount point
- dashboard/styles.css: button reset block (border:none; font:inherit; appearance:none) for all 8 converted classes
- dashboard/styles.css: .page-h1 sr-only, .error-boundary fallback, focus-visible ring, li-chip-custom border fix, li-campaign-card-top flex layout
- observability_shell.js: TAB_KEYS + TAB_TO_COMPONENT extended with a11y → ObservabilityA11y
- frontend-ux-reviewer: NEEDS-FIXES → fixed (B1 aria-expanded, B2 nested buttons, W1 escapeHtml, W5 focus-visible, W6 aria-labelledby, W7 li-chip dashed border)
- 12 tests (385 PASS total), BLACKLIST R2 INTACTO 58 SS
- H1: 0 → 17 H1s (1 per page section, sr-only)
- div onclick: 8 → 0 in index.html; 7 dynamic templates in app.js converted to button
- UX-RM-F7 100% COMPLETE (F7-A + F7-B)

#### UX-RM-F7-A: Bundle Splitting + Skeleton Patterns + WS Reconnect Badge ✅ DONE 2026-06-18
- dashboard/loader.js NEW: window.loadComponent(name, subdir) + BUNDLE_VERSION cache-busting + in-flight dedup
- dashboard/components/skeleton_patterns.js NEW: 4 presets table/card_grid/kpi_strip/timeline with aria-busy + tokens
- dashboard/components/ws_status_indicator.js NEW: topbar badge reconnecting(N)... + role=status + aria-live=polite + amber pulse
- Lazy-loaded (removed from eager index.html): command_palette, brain_sidebar, brain_confirm_card+drawer, shortcuts_help_overlay, onboarding_wizard+5steps, skill_proposals_studio+modal, lab_gauge+fingerprint_diff+cockpit
- Exponential backoff in connectWS: 1s/2s/4s/8s/16s/30s cap + _wsRetryAttempt counter
- B1 fix: skeleton in prospects uses <tr><td colspan=9> for valid tbody HTML
- Lazy wiring: Ctrl+K, ? key, brain.* WS event, _checkOnboarding, navigate(skill-proposals), navigate(lab)
- Skeleton applied: loadProspects (table 20x6), loadProposals (card_grid 10)
- frontend-ux-reviewer: NEEDS-FIXES → fixed (B1 tbody, W2 amber class, W3 brain_sidebar gap)
- 11 tests (373 PASS total), BLACKLIST R2 INTACTO 57 SS
- Component bundle: 543KB → 283KB eager (47.9% reduction > 40% gate G3)
- commit f9f01ed

### UX-RM-F8: Cobaia Operator Mode
- **Goal**: 1-screen cockpit for Caio during live ops — pause/resume per subsystem, deliverability health, Brain queue, today's actions.
- **Effort**: 24h
- **Files**: new `dashboard/pages/operator.html`, new `dashboard/components/operator_cockpit.js`, extends existing cobaia/* components
- **Acceptance**:
  - Single screen: cobaia health (green/amber/red) + warmup day + Brain queue count + today's outreach count + LI rate-limit gauge + email reputation + emergency pause
  - Voice-to-action (Whisper) optional ("pause cobaia", "what's today's hit rate")
  - Mobile-friendly (Caio checks from phone)
- **Cobaia-blocking**: SOFT
- **Deps**: F1, F2
- **F8-A DONE** 2026-06-19 — cobaia_operator.js + cobaia_day_countdown.js + cobaia_today_queue.js + today-queue API + operator CSS grid + mode toggle (localStorage) + migration cobaia_warmup_schedule. 393 pytest PASS. BLACKLIST R2 INTACTO 59 SS. Browser smoke OK (both modes). commit feat(UX-RM-F8-A). F8-B NEXT.
- **F8-B DONE** 2026-06-19 — mobile responsive CSS (768/480 breakpoints) + cobaia_brain_queue_badge.js + cobaia_rate_limit_gauge.js + cobaia_sentry_banner.js + inline panic confirm + /api/brain/queue-stats endpoint + 14 new tests. 404 pytest PASS. BLACKLIST R2 INTACTO 60 SS. commit feat(UX-RM-F8-B).
- **UX-RM-F8 100% COMPLETE** 2026-06-19 — F8-A (12h) + F8-B (12h) = 24h. All acceptance criteria met: operator cockpit, warmup day countdown, Brain queue badge, LI rate-limit gauge, Sentry banner, mobile responsive, inline panic confirm.

---

## 6. Cobaia Day 14 Readiness Gate

**BLOCKING criteria** (must pass before Caio activates real LI account):
- [x] UX-RM-F1 100% complete — zero mocks in execution paths (F1-A+B+C 2026-06-18)
- [x] UX-RM-F2-A complete — 8-item sidebar + breadcrumbs (2026-06-18)
- [x] UX-RM-F2-B — Cmd+K palette + G-prefix shortcuts + filter persistence (2026-06-18)
- [ ] Brain confirmation drawer required for ALL destructive intents
- [x] `LI_USE_MOCK = false` removed entirely (F1-C 2026-06-18)
- [x] Comment edit/delete: UI hidden + endpoints 501 (F1-C 2026-06-18)
- [x] Daemon TODOs 548 (Telegram STOP), 906 (inbox), 911 (sequence due), 948 (channel send) closed (F1-B 2026-06-18)
- [x] All `n/c` channels have inline "Configurar" link (F1-C 2026-06-18)
- [x] `intelligence/scoring.py` skeleton raises NotImplementedError (F1-C 2026-06-18)
- [ ] cobaia_preflight green-light required to start warmup (block button if any check red)
- [ ] Manual smoke: schedule fake LI campaign → confirm flow → real execution OR confirmed no-op
- [ ] Sentry breadcrumbs flowing for all cobaia events
- [ ] WCAG AA: text-3 contrast fix (4.5:1 minimum)

**SOFT criteria** (warmup can proceed with these open, fix during 14-day window):
- F3 onboarding wizard
- F4 visual redesign
- F5 streaming sidebar
- F7 full a11y pass
- F8 operator mode

---

## 7. Cross-session Persistence Protocol

### TaskCreate batch (run after audit synthesis)
```
TaskCreate UX-RM-F1 "Mock Kill + Real Backend" priority=critical effort=40h
TaskCreate UX-RM-F2 "IA Consolidation + Cmd+K" priority=critical effort=32h
TaskCreate UX-RM-F3 "Onboarding Wizard 5min" priority=high effort=20h
TaskCreate UX-RM-F4 "Visual Redesign tokens+typo+motion" priority=high effort=36h
TaskCreate UX-RM-F5 "AI Command Bar + Streaming" priority=medium effort=28h
TaskCreate UX-RM-F6 "Multi-Channel Campaign Editor" priority=medium effort=48h
TaskCreate UX-RM-F7 "Performance + A11y Polish" priority=medium effort=20h
TaskCreate UX-RM-F8 "Cobaia Operator Mode" priority=medium effort=24h
```

### memory_save (agentmemory)
```
type="architecture" content="Hermes UX-AUDIT 2026-06-18 sealed. 8 phases UX-RM-F1..F8. F1+F2 cobaia-blocking. Stack: shadcn+Tailwind v4 OKLCH+Motion 12+Geist+Lucide+Tremor charts+kbar Cmd+K. Mocks killed: api/pipelines.py:354 + linkedin/cobaia_warmup.py:357. PLAN+issues.json+roadmap.json at .claude/UX-AUDIT/"
concepts=["hermes","ux-audit","cobaia","mock-kill","cmd-k","shadcn","oklch","brain-confirm"]
files=[".claude/UX-AUDIT/PLAN.md",".claude/UX-AUDIT/issues.json",".claude/UX-AUDIT/roadmap.json"]
```

### Chapter marker
`mark_chapter title="UX-AUDIT Sealed" summary="8 phases roadmap UX-RM-F1..F8 sealed 2026-06-18, F1+F2 cobaia-blocking, mocks identified, stack 2026 chosen"`

### Slash command suggestion
Create `/hermes-ux-start <N>` slash command (mirror `/forge-be-start`) reading `.claude/UX-AUDIT/PHASES/UX-RM-F[N].md` (to be expanded from this PLAN) + GUARDRAILS + memory.

### Re-audit cadence
Re-run this audit after every 2 phases ship (F2, F4, F6, F8) to validate progress + spot regressions. Save snapshots `.claude/UX-AUDIT/_snapshots/2026-XX-XX.json`.
