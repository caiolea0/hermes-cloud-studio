# Hermes Cloud Studio 2.0 — Design Mockup QA Report

**Reviewer:** QA + Design Director pass
**Date:** 2026-06-21
**Scope:** 12 standalone HTML pages + `design-system.css` in `.claude/design-mockups/`

---

## 0. Verdict at a glance

The set is **strong — genuinely award-tier 2026 work**, not a template. Every page links the shared
`design-system.css`, every page uses real CDN libraries with working init, **zero `<table>` elements
anywhere** (cards/charts/graphs only — the owner's #1 mandate is honored), dark OKLCH + Geist throughout,
real glow/blur/depth/motion, realistic Cuiabá/MT data (no lorem), and the honest measured-vs-projected
material law is applied consistently.

The weaknesses are **plumbing, not craft**: broken cross-page navigation, no shared nav/index, and a few
single-surface gaps (real geolocation drill-down, re-audit failure view). None of the pages is a "flat
restricted widget."

**Overall: PASS with a punch-list.** 9 of 12 pass clean; 3 need-work are minor.

---

## 1. Per-page verdict

| # | Page | Verdict | Notes |
|---|------|---------|-------|
| 00 | hero | **PASS** | MapLibre + deck.gl (heatmap/scatter/ping) + tsParticles + GSAP + countUp. Living radar sweep, region modal, zoom city/state/country, legend-as-filter recoloring the map, radial nav, featured `card-hot`. Cinematic, premium. **Bug:** links to `01-conveyor.html` (does not exist; should be `02-lead-conveyor.html`) x2. |
| 01 | sweep-map | **PASS (best-in-class)** | MapLibre + deck.gl H3 hexbins (own h3-js, deck-H3 deliberately avoided = robust), heat toggle, fog-of-war, pins, paint-to-sweep workflow with reticle + animated fill, live filter recolor, region modal with donuts + biz preview, scope segmented control. Directly satisfies Surface A in full. No cross-page nav links. |
| 02 | lead-conveyor | **PASS** | Kinetic Kanban, ApexCharts sparklines, GSAP Flip re-rank, glow-by-band cards, channel dots, ads/posts micro-bars, secondary gap+CTA well, per-card action row (9 actions), drag between states, dispatch dock (Vuecra/Geronimo), drawer. Surface B columns all present. **Bug:** nav links to `03-dossier.html` and `04-command-center.html` (wrong filenames). |
| 03 | conveyor-filters | **PASS** | Max-density filters + reverse-filter ("show me what's MISSING") concept (77 reverse/exclude refs), GSAP Flip, ApexCharts. Deepens Surface B filtering exactly as briefed. Cards, no tables. No cross-page nav. |
| 04 | dossier | **PASS** | ECharts (revenue bands/ring/radar) + GSAP ScrollTrigger + SplitText + countUp. BLUF verdict hero, score, revenue-gap ring (measured now vs projected potential, committed number), competitor mini-section, "what they do vs what prospect doesn't," honest measured/projected legend. Satisfies Surface C sales-report goal. No cross-page nav. |
| 05 | competitors | **PASS (excellent)** | ECharts radar (vs leader / vs market), reverse-gap matrix heatmap, market-dominance treemap, SEO/SEM keyword bubble chart with quadrant logic, gap-vector → recommended-offer materialization, source notes + measured/projected tags on every chart. Adversarial report fully realized. No cross-page nav. |
| 06 | command-center | **PASS** | graphology + sigma.js live nervous-system graph (44 agents), subsystem gauges, decision ticker, cross-project dispatch cards (Vuecra/Geronimo), command dock + ⌘K palette, health ribbon (measured/projected). Surface D realized strongly and stays Hermes-only. **Bug:** nav links are dead `href="#"`. |
| 07 | agent-detail | **PASS** | ECharts + GSAP + tsParticles. Per-agent deep view: capabilities, flows, execution cycle, triggering. Crumb links back to command-center (the only correct internal links in the set). |
| 08 | action-dispatch | **PASS** | MapLibre + ECharts + GSAP + drag-to-trigger handoff stage with particle rail + ⌘K command palette + 5 tactile gestures + optimistic toasts. Satisfies ACTION DISPATCH spec. No cross-page nav. |
| 09 | my-day | **PASS (strongest narrative)** | Scroll-driven 7-step morning ritual: explore → opportunities → analyze → competitors → dossier → services → contact. MapLibre + ECharts + GSAP + aurora canvas + progress spine. This page IS the OWNER DAILY FLOW spec, end-to-end. No cross-page nav out (internal anchors only). |
| 10 | onboarding-empty | **PASS** | MapLibre + GSAP. Premium empty states per surface with skeletons, honest projected ghost figures, first-run guidance. Keeps "alive" feel even with no data. |
| 11 | design-system | **PASS** | ECharts + ApexCharts + GSAP/ScrollTrigger. Living style-guide: tokens, color-as-meaning legend, components, honesty law. Useful reference page. (Copy is in EN while product is PT-BR — minor.) |

---

## 2. Owner-spec coverage

### Fully shown
- **No tables, cards/visual-only, glance-readable, dive-in feel** — universal. ✅
- **Premium 2026 dark OKLCH aesthetic, real glow/gradient/blur/depth/motion** — universal, not flat. ✅
- **Surface A (Sweep Map):** region click→modal stats (total/opp/niche), expand businesses, status colors (high-opp/consolidated/gray-unexplored), painted swept-vs-unexplored, paint-to-sweep workflow, filters that recolor the map, city/state/country zoom with live info. (00 + 01). ✅
- **Surface B (Lead Conveyor):** all requested front columns (name, score, niche, size, revenue, social channels, ads+posts), secondary gap+CTA well, max filters, per-business actions (dossier, contacted, →Geronimo, re-audit, compare direct+indirect competitors, adversarial report, market-dominance, SEO/SEM), states found→audited→ready (+contacted/proposal/won). (02 + 03). ✅
- **Surface C (Dossier + Competitors):** glance-and-decide, the "5+ yrs + reviews + movement + no site" goldmine signal, revenue measured-vs-projected committed number with range, competitors what-they-do-vs-what-prospect-doesn't, real-number offers. (04 + 05). ✅
- **Surface D (Command Center):** Hermes-only, fully visual, 40+ agents live graph, realtime monitoring, cross-project send to Vuecra/Geronimo, monitor cross-project progress, ⌘K dispatch. (06 + 07). ✅
- **Action Dispatch** (08) and **Owner Daily Flow** (09) — both explicitly built. ✅
- **Honesty law (solid=measured / translucent=projected, range toggle, no fake precision)** — applied everywhere. ✅
- **WCAG AA + prefers-reduced-motion + reduced-transparency** — gated in CSS §13 and per-page `REDUCED` guards. ✅
- **$0 self-host posture** — vanilla, CDN libs pinned, perf-lite mode. ✅

### Partially shown
- **Exact geolocation drill-down** (Surface A "see exact geolocation"): modal shows biz preview + lat/long text and a button, but no dedicated address-level pin-zoom view. Implied, not fully built.
- **"See what failed in the audit" / RE-AUDIT result** (Surface B action): buttons/icons exist on the card action row, but no dedicated audit-failure detail panel is mocked.
- **Indirect competitors** explicitly: 05 nails direct + market; "indirect" category is present in copy but not as a distinct visual lane.

### Missing / not yet a page
- **No `index.html` / shared global nav.** The set is not navigable as a product — most pages have zero working cross-page links (see fixes). The hero is the de-facto entry but its links are broken.
- **No explicit "send to Geronimo software-house BUILD vs marketing-strategy" split UI** — dispatch cards treat Geronimo as one target; the brief asks to distinguish director-agents for marketing-strategy vs software-house build.

---

## 3. Prioritized punch-list (fixes)

### P0 — breaks navigation (fast wins)
1. **00-hero:** `href="01-conveyor.html"` → `02-lead-conveyor.html` (2 occurrences, lines ~383, ~546).
2. **02-lead-conveyor nav:** `03-dossier.html` → `04-dossier.html`; `04-command-center.html` → `06-command-center.html` (lines ~423–424, ~973). Also add `01-sweep-map` is correct; consider adding Competitors/My Day.
3. **06-command-center nav:** all four `href="#"` are dead → point to `01-sweep-map.html`, `02-lead-conveyor.html`, `04-dossier.html`, self.
4. **Add a shared top-nav (or `index.html` launcher)** so all 12 pages are reachable. Currently only 02 and 07 have any real cross-links. This is the single biggest gap to "navigable premium set."

### P1 — spec completeness
5. **Surface A:** add an address-level geolocation drill (zoom to exact pin / street view stub) from the region modal's "Ver geolocalização exata" button (currently routes to a wrong/relative file in hero).
6. **Surface B:** add a "what failed in the audit" detail panel + a re-audit-in-progress state (the action icons exist; the destination view doesn't).
7. **Cross-project dispatch:** split Geronimo target into "marketing strategy" vs "software-house build" (06 + 08), per brief.
8. **Indirect competitors:** give them a distinct visual lane in 05.

### P2 — polish
9. **11-design-system** copy is English while the product is PT-BR — translate for consistency (or mark it explicitly as internal EN reference).
10. **Version drift across CDNs:** maplibre is `5.24.0` (hero/09/10) vs `5.5.0` (01); deck.gl `9.3.4` vs `9.0.38`; countUp `2.10.0` vs `2.8.0`. Harmless now but pin one version per lib before prod for cache reuse.
11. **08-action-dispatch "Latência média 0ms (otimista)"** reads as fake-precision against the honesty law — relabel as "optimistic UI" badge, not a measured 0ms.
12. Confirm `bg-aurora` canvas in 09 has an OGL/canvas init (mount exists; verify it paints and is reduced-motion gated).

---

## 4. Bottom line
The craft, glow discipline, honest-data law, and per-surface lib choices are exactly what the brief
demanded — this is real designer work, not a restricted widget. Ship-blockers are limited to broken
internal links and the absence of a unifying nav/index. Fix the P0 link set (≈15 min) and the deck
becomes a fully navigable, demo-ready premium product.
