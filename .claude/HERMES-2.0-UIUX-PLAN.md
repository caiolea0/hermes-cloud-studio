# Hermes 2.0 — VISUAL UI/UX Master Plan

> **Sealed**: 2026-06-21
> **Owner**: Caio (solo founder, Cuiabá / Mato Grosso, Brazil)
> **Mandate**: a completely-visual, glance-able, dive-in dashboard. A *visual sales machine*, not a CRUD app.
> **Master principle**: everything VISUAL · NO tables · NO walls of text · understandable at a glance · dive-in feel.
> **Constraints**: $0 budget · self-hosted on Contabo · zero CDN (all libs vendored local, hash-pinned) · current stack = vanilla JS + OKLCH + Geist · accent `#7c3aed` purple · energy `#d1fe17` lime · WCAG AA.
> **Companion file**: `.claude/uiux-stack.json` (machine-readable surface → concepts → libs map).

---

## 1. The Vision in One Screen — Hero Experience

Caio opens Hermes and lands on a **living map of his territory**. Mato Grosso glows in the dark, painted in OKLCH heat: coral blooms where money is uncaptured, cool blue where competitors already dominate, gray fog over land he has not swept yet. A corner **progress ring** shows "37% of Cuiabá swept" and ticks up on its own as the 24/7 discovery brain works. He doesn't read — he *sees*.

He drags a lasso over an unexplored neighborhood. The fog dissolves in an animated radial wipe, a scanning shimmer plays, and live opportunity hexes bloom into color. He clicks the hottest hex: a frosted-glass modal springs up anchored to it — total businesses vs opportunities vs niche as count-up donut gauges, exact geolocation, one button: **"Send 42 opportunities to conveyor."** One click. The leads slide into Surface 2.

That is the whole product in one gesture: **explore → spot → act**, no table ever touched. The four surfaces are four lenses on one machine, sharing one OKLCH color grammar so the eye learns "green/coral = money" once and applies it everywhere — map regions, conveyor cards, dossier rings, command-center monitors.

**Navigation model**: not tabs in a top bar. A **radial / dock switcher** (4 glyphs) that *morphs* between surfaces with a shared-element transition — the score ring on a conveyor card flies up to become the hero gauge on the dossier. The dashboard feels like one continuous space you fly through, not pages you load.

---

## 2. The Four Surfaces

### SURFACE 1 — Sweep Map (the territory)

**Purpose**: explore scanned cities/areas, see highlighted opportunities, paint conquered ground.

**Visuals**
- Self-hosted dark OKLCH basemap: one Brazil/MT `.pmtiles` file off Contabo nginx, **no tile server, no API key**. Restyled from Protomaps' night flavor into Hermes purple/lime.
- **deck.gl GPU overlay** synced to the MapLibre camera: `GeoJsonLayer` choropleth by status, `H3HexagonLayer` swept/unexplored hexes, `HeatmapLayer` opportunity density, `ScatterplotLayer` pulsing business dots.
- **Status semantics (fixed, OKLCH)**: high-opportunity = saturated warm coral/amber bloom · consolidated (has site + marketing) = cool muted blue/teal · unexplored = neutral gray fog. Intra-hot intensity uses a perceptually-uniform OKLCH ramp so the heatmap never lies.
- **Fog-of-war paint**: dark "unexplored" overlay punched out where swept (feature-state + canvas `destination-out`). Swept-vs-total **progress ring** in the corner.
- Always-visible **legend that doubles as a filter** (click a swatch to isolate/dim that status).

**Interaction**
- Continuous semantic zoom: country = state choropleth → state = municipality choropleth → city = H3 hexes + business pins. Layers crossfade via `interpolate` on opacity, never pop.
- `flyTo({curve:1.42})` cinematic dive on region click + globe→Mercator auto-morph ~zoom 12 = the literal "dive into the city" moment; non-focused regions desaturate (focus-dim).
- **Click-to-sweep**: Terra Draw lasso/rectangle → Turf.js finds enclosed H3 cells/municipalities → flip to swept → animated wipe + shimmer.
- **MANY filters that RECOLOR** (niche, score, size, has-site, has-ads, revenue band, "missing a service"): deck.gl `updateTriggers` on `getFillColor` repaints thousands of regions in **one GPU frame**, zero refetch; a live counter ticks "1,284 matching."
- **Region modal**: one PostGIS aggregate query → count-up donut gauges (total vs opportunities vs niche), geolocation mini-locator, scan-over-time sparkline, hand-off CTA to Surface 2.
- Realtime follow-cursor tooltip at every zoom tier; numbers tick when the WS scanner streams updates.

---

### SURFACE 2 — Lead Conveyor (the pipeline)

**Purpose**: scan 50 leads in seconds, decide, act — the funnel as a machine Caio operates.

**Visuals**
- **Cards, never tables.** Each card: name · opportunity-score ring (conic-gradient `@property`) · niche icon · size · revenue-expectation sparkline (inline SVG, no axes) · social-channel dot row (lit = present / dim = missing) · ads-posts estimate micro-bar.
- **Conveyor Kanban** of states: `found → audited → ready-to-contact → contacted`. Cards flow left→right; a conveyor micro-animation plays when background pipeline work auto-advances a card.
- **Score band micro-bar / chip** for dense rows where a full ring is too big — same OKLCH scale, glow-by-band so the hottest lead is literally the brightest thing on screen.

**Interaction**
- **Columns the brief demands** all render as visual atoms: name, score, niche, size, revenue-expectation, social-channels, ads-posts-estimate.
- **Max filters as chips** that don't just hide — they re-tint score bars and **FLIP-animate** cards into new rank so filtering feels alive. Shared filter vocabulary with the map (one lens system).
- **Reverse-filter — businesses MISSING a service** (negative-space gold): toggle a service chip into "missing" mode (strikethrough/red); conveyor + map recolor to show only the void; dim icons flare red; live "N businesses missing this" badge. The single most direct path from data to a pitch list.
- **Per-card action row on hover** (icon-buttons, no dropdown hunting): dossier · mark-contacted · send-to-Geronimo · re-audit · see-audit-failures · compare-competitors · adversarial-report · market-dominance-estimate · SEO-SEM-strategies. Primary actions (dossier, send-to-Geronimo) get visual weight.
- Drag a card between columns to change state (SortableJS).
- **Region→conveyor handoff** from Surface 1 lands cards here, pre-filtered.

---

### SURFACE 3 — Dossier (glance to decide → close)

**Purpose**: one-screen verdict, real revenue projection (no guessing ranges), conversion ammo Caio quotes on the call.

**Visuals & narrative**
- **BLUF verdict header** (inverted pyramid): ONE hero line states the conclusion before any evidence — "R$ 38k/mo left on the table" + status color + 0-100 score ring. Only the verdict + ring on the first viewport; everything else earns its scroll.
- **Scrollytelling**: 4 acts — who they are · what they're missing · what it costs · what we'd do. A sticky hero visual stays pinned while text steps scroll past and *mutate* it (IntersectionObserver / GSAP ScrollTrigger): gap bar grows → competitors fade in → "with Hermes" projection overlays.
- **Dual-arc potential-gap ring**: inner = current revenue (muted), outer = potential (vivid, glowing). The visible GAP **is** the pitch; center shows the delta. Potential arc sweeps slightly slower on open so the gap dramatically "opens up." **No ranges — one committed number** Caio can say out loud.
- **Range bullet bar / scenario fan** where honesty about uncertainty is needed: solid = measured, translucent = projected; conservative-likely-optimistic band; count-up animation reserved for real numbers, projected numbers only fade in.
- **Waterfall of upside levers** color-keyed to the project that delivers it (+new site = Vuecra, +ads/SEO = Geronimo, +missing service X). Toggle a lever off → potential total drops live = a what-if Caio runs mid-call.
- **Adversarial competitor view**: **stellar chart** (radial spears, not lying radar) client vs dominant competitor across SEO/ads/site/social/reviews; **reverse-gap matrix** heatmap (what-they-have-you-don't); **market-dominance Voronoi treemap** (FoamTree) sized by share.
- **Confidence encoding everywhere**: solid = high confidence, hatched = inferred, faint = guessed — premium tools earn trust, cheap ones bluff.

**Interaction**: hover any metric → the contributing factor highlights in the ring. Click a waterfall step → "show the strategy behind +R$X." Click a dominance vector → the exact services that close the gap appear as the recommended offer. Toggle "show as range / show likely only" to simplify for a skeptical client mid-call.

---

### SURFACE 4 — Command Center (mission control, ONLY Hermes)

**Purpose**: all Hermes actions + realtime monitoring + cross-project triggers, completely visual, no tables, no log lines.

**Visuals**
- **Living nervous-system graph** (Sigma.js WebGL + graphology): nodes = Hermes core + 40+ agents + cross-project targets (Vuecra, Geronimo). Edges = live triggers/dataflow. **Animated particles** travel edges to show work in flight. Node color/pulse = status (idle/running/done/error); done = halo, not a status cell.
- **Cross-project triggers drawn as edges firing**: Hermes → Vuecra "build a site", Hermes → Geronimo "run marketing / software strategy" — a particle pulse shoots down the edge on trigger.
- **deck.gl ArcLayer** overlay on the map ties command center to geography: closed leads fire glowing arcs across Cuiabá/MT to the project that delivers the work, camera-synced through every zoom.
- **Instrument-cluster needle gauges** (pure-CSS 270° conic-gradient + needle): per-agent / per-subsystem readiness & health, swinging in realtime off the WS stream — a cockpit, not a grid.

**Interaction**
- Click a node → **radial action menu** of that agent's capabilities + recent runs; click an edge → trigger payload/result.
- Trigger any action (incl. cross-project) straight from the node — orchestration becomes a physical gesture.
- Realtime status via existing **`daemon.{subsystem_status,log_event,decision}` WS broadcasts** (canonical F.2.3 layer) → patches pulses/particles/halos in place, transition-only emission. Monitor cross-project done vs in-progress as halos.
- Filter by subsystem/status dims unrelated subgraphs.

---

## 3. The 40+ Agent Visualization — Concrete Ideas

The Command Center is the home, but agents deserve many lenses. Concrete, buildable ideas:

1. **Nervous-system graph** (primary): WebGL force/layered node-link, particles = work in flight, pulse = status, halo = done. 40+ nodes at 60fps (Sigma.js).
2. **Cockpit gauge wall**: a bank of pure-CSS needle gauges, one per agent/subsystem, vital-signs view — needles twitch off WS. Toggle alongside the graph (topology vs vitals).
3. **Constellation / star-map layout**: agents as stars, brightness = activity, constellations = subsystems (discovery, enrichment, qualify, handoff). Idle agents dim, active ones flare.
4. **Swimlane heartbeat strip**: each agent a horizontal lane with a live ECG-style pulse line; spikes = runs, flatline = idle, red spike = error. Glanceable fleet health over time.
5. **Particle-flow river**: a left→right "river" where each particle is a lead moving through agents (discover → enrich → qualify → handoff); width of the river = throughput; eddies = bottlenecks.
6. **Capability radial / sunburst**: center = Hermes, ring 1 = subsystems, ring 2 = agents, ring 3 = capabilities; click to drill, hover for live run counts.
7. **Hex-grid agent board**: each agent a hex tile (reuse H3 visual language), tile fills/glows with current load; clustered by subsystem.
8. **Live timeline ticker**: a thin bottom rail showing the last N agent decisions as flowing chips (color = subsystem), click a chip → jump to that node.
9. **3D depth stack** (optional, CSS 3D transforms): subsystems on parallax layers, agents floating; tilt on mouse for a "machine has depth" feel — no heavy 3D lib needed.
10. **Trigger-pulse map overlay**: cross-project triggers visualized as arcs on the geographic map (deck.gl ArcLayer) so you see *where* the machine is acting, not just *that* it is.
11. **Mini-graph badges on cards**: each conveyor card carries a tiny "which agents touched this lead" sparkline-graph, tying Surface 2 to Surface 4.
12. **Error-spotlight mode**: filter the graph to only error/stuck nodes; the rest dims to fog — instant triage for a solo operator.

Recommended default: **graph + cockpit-gauge toggle**, with the **timeline ticker** always present and **trigger arcs** shared onto the map.

---

## 4. Action Dispatch UX — Visual Options

Every action must be one visible gesture, never a buried menu. Options:

- **Hover action row** on conveyor cards (icon-buttons with tooltips) — default for Surface 2.
- **Radial / pie menu** on Command Center nodes — actions fan out around the agent.
- **Drag-to-trigger**: drag a lead card onto a project node (Vuecra/Geronimo) to fire the handoff; the edge lights and a particle flies.
- **Command palette** (⌘K) as a power-user escape hatch — fuzzy-search any action across all surfaces, fully keyboard, for when Caio knows exactly what he wants.
- **Confirm-by-gesture for destructive/cross-project**: a slide-to-confirm or hold-to-fire micro-interaction (matches Brain F.6 `requires_confirm` guardrail) instead of a modal dialog.
- **Optimistic visual feedback**: the moment an action fires, the UI animates the expected result (card slides, particle flies, gauge swings) before the WS confirms — feels instant; reconcile on confirm.
- **Toast = `window.hermesToast`** (existing F.2.4 namespace) for non-blocking confirmations; skeleton = `window.skeleton` for loading. Reuse, don't reinvent.

---

## 5. Aesthetic System

Build ON the existing canonical tokens (`DESIGN-SYSTEM-TOKENS.md`), do not invent.

- **Color = meaning (OKLCH)**: one perceptually-uniform scale across all 4 surfaces. Coral/amber = uncaptured money, cool blue = consolidated/taken, gray = unexplored. Brand purple `#7c3aed` for primary/active, lime `#d1fe17` for daemon energy / critical highlight. Glow-by-band via OKLCH equal-intensity drop-shadows so the hottest thing outshines the rest. Colorblind-safe via lightness separation.
- **Depth**: frosted-glass (`backdrop-filter` blur) floating panels/modals over the live map — the defining 2026 layered look. Parallax depth on the agent view. Shadows from the token scale only.
- **Motion (restrained, `prefers-reduced-motion` aware)**: sweep-on-reveal (rings/gauges animate 0→value via `@property --angle` on scroll-into-view), count-up on real numbers only, FLIP reflow on filter, flyTo camera dives, particle flow on edges, fog wipe on sweep. Duration 150-400ms, single `--ease`. Isolate GSAP per the `no-gsap-outside` ESLint rule.
- **Typography**: Geist (existing). BLUF hero lines big and confident; numbers are the heroes, labels recede.
- **Wow moments** (see §7): the fog wipe, the GPU recolor, the dual-arc gap reveal, the living agent graph.

---

## 6. The Free Stack (per surface) + React-vs-Vanilla

**All free, all self-hostable on Contabo, all vendored local (zero CDN).** Real libs:

| Surface | Libs |
|---|---|
| 1 Sweep Map | MapLibre GL JS (BSD) · Protomaps PMTiles (OSM) · deck.gl v9 + @deck.gl/mapbox (MIT) · h3-js + h3-pg (Apache-2.0) · PostGIS (OSS) · Terra Draw + maplibre-gl-terradraw (MIT) · Turf.js (MIT) · IBGE/geobr/geodata-br/br-atlas (CC0/BSD-3) · mapshaper (build-time) · culori + d3-scale (MIT/ISC) · Motion One (MIT) |
| 2 Lead Conveyor | Pure CSS conic-gradient + @property + OKLCH · SortableJS (MIT) · Motion One (MIT, FLIP) · inline SVG sparklines (no lib) · culori (MIT) |
| 3 Dossier | Pure CSS rings · D3 (d3-shape/d3-scale modules, ISC/BSD) · Apache ECharts 6 (Apache-2.0, stellar/treemap/heatmap/bullet/gauge) · ApexCharts (MIT, range-bar/area) · FoamTree (free JS, Voronoi treemap) · GSAP + ScrollTrigger (free since 2025) · Motion One |
| 4 Command Center | Sigma.js + graphology (MIT) · deck.gl ArcLayer (MIT) · MapLibre (BSD) · pure-CSS conic needle gauges · Motion One · culori |

**Lib URLs**: see `.claude/uiux-stack.json` (every lib carries its canonical URL).

### React vs Vanilla — recommendation

**Stay vanilla JS for the shell + Surfaces 1, 2, 4.** Rationale: the existing dashboard is a large vanilla `app.js`; the highest-value libs (MapLibre, deck.gl, Sigma.js, h3-js, Terra Draw, ECharts, ApexCharts, FoamTree, Motion One, GSAP) are **all framework-agnostic** and run natively in vanilla. The score rings/gauges are pure CSS. There is **no React requirement** for any wow moment. React-coupled libs (visx, Nivo, Tremor) are **reference-only** — mine their arc/gauge math, don't import them.

**Optional React islands** only where it genuinely pays: a complex Dossier (Surface 3) with heavy stateful scrollytelling *could* be an isolated React island (hydrated in one mount node) if state management gets painful — but it is fully buildable in vanilla + GSAP today. kepler.gl (React) is an optional analyst "lab" side-tool, not part of the daily dashboard.

**Migration path** (only if React is ever adopted): (1) keep the vanilla shell; (2) mount React only inside specific surface containers as islands; (3) MapLibre/deck.gl/Sigma instances live outside React, React only drives the chrome/controls; (4) never rewrite the working vanilla surfaces wholesale — wrap, don't replace.

---

## 7. Wow-Moments Shortlist

1. **Fog-of-war sweep paint** — lasso a gray region, fog dissolves in a radial wipe + scanning shimmer, opportunity hexes bloom in, progress ring grows the painted empire. Prospecting as a conquest game.
2. **GPU recolor in one frame** — drag a filter slider and the ENTIRE map recolors in <16ms while a live counter ticks matching opportunities. No reload, no spinner — the map reacts like it's thinking.
3. **Cinematic country→state→city dive** — flyTo(curve:1.42) + globe→Mercator morph, data representation morphing per tier, live tooltip following the cursor the whole way down.
4. **Dual-arc gap ring** — the empty space between current and potential revenue IS the pitch; the gap visibly opens on reveal. One persuasive image, no ranges.
5. **Living nervous-system agent graph** — 40+ WebGL nodes, cross-project triggers fire visible particle pulses (Hermes→Vuecra, Hermes→Geronimo), status as pulse/halo/red. You SEE the machine think.
6. **Reverse-gap one-click pitch generator** — hit "missing a service" and the grid recolors to only the exploitable gaps; the adversarial report writes itself.
7. **One OKLCH color language** across all four surfaces — Caio learns "coral = money" once and reads the whole machine instantly.
8. **Solid=measured / translucent=projected** ruthless honesty law + count-up only on real numbers — restraint that reads as expensive and earns the buyer's trust.

---

## 8. Phased UI Build Plan (+ integration with diagnosis-engine)

Hermes 2.0's data brain (discovery → enrichment → qualify → score → handoff, per `HERMES-2.0-PLAN.md`) produces the records every surface renders. UI phases dovetail with it.

- **UI-P0 — Foundation**: vendor all libs local (hash-pinned), Brazil/MT `.pmtiles` on Contabo, OKLCH map style, PostGIS + h3-pg schema (business points, IBGE polygons, precomputed H3 indexes), thin GeoJSON REST endpoint. *Depends on*: discovery engine writing business rows.
- **UI-P1 — Sweep Map MVP (Surface 1)**: MapLibre + deck.gl choropleth + H3 hexes + status colors + region modal + flyTo. *Consumes* qualify/score output for status colors.
- **UI-P2 — Sweep mechanics**: Terra Draw lasso, fog-of-war paint, progress ring, filters-that-recolor + live counter, reverse-filter ("missing a service" = SQL WHERE-NOT-EXISTS, shared with conveyor).
- **UI-P3 — Lead Conveyor (Surface 2)**: cards + score rings + Kanban states + chips + FLIP + per-card actions + region→conveyor handoff. *Consumes* golden lead records.
- **UI-P4 — Dossier (Surface 3)**: BLUF header + dual-arc gap ring + waterfall + scrollytelling + competitor stellar/matrix/treemap + confidence encoding. *Consumes* enrichment + PageSpeed needs-score + competitor data + revenue projection.
- **UI-P5 — Command Center (Surface 4)**: Sigma.js agent graph + WS pulse/particles + radial actions + cockpit gauges + cross-project trigger arcs. *Consumes* `daemon.*` WS broadcasts + handoff layer (Geronimo NATS, Vuecra HI1/HI2 REST).
- **UI-P6 — Polish & unify**: shared-element surface transitions, command palette (⌘K), reduced-motion pass, WCAG AA audit (axe-core local vendor), perf budget per surface.

Each phase ships a working surface; surfaces are independent so they can land as the diagnosis-engine fills each data layer.

---

## 9. Open Decisions for Owner

1. **Navigation**: radial/dock morph-switcher vs persistent rail vs ⌘K-first? (Recommend dock morph + ⌘K.)
2. **Agent-view default**: nervous-system graph, cockpit gauges, or constellation as the landing layout? (Recommend graph + gauge toggle.)
3. **Dossier framework**: pure vanilla + GSAP (recommended) vs isolated React island for heavy scrollytelling state?
4. **Basemap hosting**: Contabo nginx static `.pmtiles` (recommended, truly $0) vs Cloudflare R2 (zero-egress, off-box redundancy)?
5. **kepler.gl analyst lab**: include as a side "lab" tool or skip to keep one cohesive brand surface?
6. **Honest-ranges default**: always show range vs always show single committed number with a per-client toggle? (Recommend single number + toggle.)
7. **Map data scale at launch**: Cuiabá-only first (smallest `.pmtiles`, fastest) vs full-MT vs full-Brazil from day one?
8. **Cross-project trigger confirm**: slide-to-confirm gesture vs explicit modal for Vuecra/Geronimo dispatches (per Brain `requires_confirm`)?
