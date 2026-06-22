# Hermes Cloud Studio 2.0 — Design System Notes

Full reference for `design-system.css`. Every Surface page links that ONE file.
Dark, luminous, deep, premium (2026). OKLCH + Geist. $0 / Contabo self-hosted.
Brand: purple `#7c3aed`, energy lime `#d1fe17`.
**Honesty rule (enforced visually): solid/opaque/full-glow = MEASURED; translucent/dashed/soft-glow = PROJECTED. Never fake precision.**

---

## 0. Required `<head>` for every page

```html
<!-- design system (always first) -->
<link rel="stylesheet" href="./design-system.css">

<!-- Geist font (self-host woff2 on VPS for prod; this CDN is the dev fallback) -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fontsource/geist-sans@5/index.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fontsource/geist-mono@5/index.css">

<!-- Icons (pick Lucide; Tabler optional for dense action glyphs) -->
<script src="https://cdn.jsdelivr.net/npm/lucide@0.460.0/dist/umd/lucide.min.js" defer></script>
<!-- after DOM: lucide.createIcons(); -->
<!-- optional: <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.21.0/dist/tabler-icons.min.css"> -->
```

### Per-surface libs (load only where needed; pin versions, no `@latest` in prod)

| Surface | Libs (CDN) |
|---|---|
| A Sweep Map | maplibre-gl@5.24.0 (+css), pmtiles@4.3.0, deck.gl@9.3.4, @turf/turf@7.2.0, terra-draw@1.0.0 + maplibre adapter@1.0.0 |
| B Conveyor | apexcharts@3.54.1 (sparklines), gsap@3.13.0 + Flip.min.js (re-rank/morph), motion@11 (esm) |
| C Dossier | echarts@5.5.1 (revenue bands/radar/gauge), gsap@3.13.0 + ScrollTrigger + SplitText, countup.js@2.10.0 |
| D Command Center | force-graph@1.51.4 (40+ agents) OR sigma@3 + graphology, deck.gl ArcLayer, tsparticles slim@4, three@0.169 (optional selective bloom) |

CDN hosts used: `cdn.jsdelivr.net`, `unpkg.com`, `cdnjs.cloudflare.com`, `esm.sh`.

Reduced-motion guard every page runs once:
```js
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
if (REDUCED) { /* skip OGL/tsParticles/graph-particles init; flyTo duration:0 */ }
```

---

## 1. CSS Variables (tokens)

### Backgrounds
`--bg-void` `--bg-0` `--bg-1` `--bg-2` `--bg-3` `--bg-inset`
(deep brand-tinted near-black ladder; `--bg-0` = page, `--bg-2` = card)

### Text
`--text-hi` `--text` `--text-mid` `--text-dim` `--text-faint`

### Brand purple (accent / consolidated)
`--purple` `--purple-hot` `--purple-soft` `--purple-bleed` `--purple-ink`

### Energy lime (critical / hottest / committed)
`--lime` `--lime-hot` `--lime-soft` `--lime-bleed` `--lime-ink`

### Status semantics (map zones / pipeline / agents)
`--st-opportunity` (warm coral) `--st-opp-hot` `--st-opp-bleed`
`--st-consolidated` (cool blue) `--st-cons-bleed`
`--st-niche` (= lime) `--st-unexplored` (gray) `--st-unexplored-fill`
Feedback: `--ok` `--warn` `--danger` `--info`

### Opportunity ramp (perceptually-uniform low→high; heat/choropleth/scores)
`--opp-0` `--opp-1` `--opp-2` `--opp-3` `--opp-4` `--opp-5`

### RGB mirrors for deck.gl / canvas (libs need rgb)
`--rgb-lime` `--rgb-purple` `--rgb-opportunity` `--rgb-consolidated` `--rgb-unexplored`
Usage: `getFillColor: () => [209,254,23, alpha]` — or read via `getComputedStyle`.

### Borders
`--line` `--line-strong` `--line-lime` `--line-purple`

### Glass
`--glass-blur` `--glass-blur-hero` `--glass-sat` `--glass-tint` `--glass-tint-deep`
`--glass-border` `--glass-sheen` `--glass-tint-measured` `--glass-tint-projected`

### Spacing / radius / elevation / z
Spacing: `--sp-1`…`--sp-9` (4→96px)
Radius: `--r-xs --r-sm --r-md --r-lg --r-xl --r-2xl --r-pill`
Elevation: `--elev-0 --elev-1 --elev-2 --elev-3 --elev-4` (elev-4 has purple bloom)
Z-index: `--z-base --z-map --z-content --z-sticky --z-dock --z-drawer --z-modal --z-tooltip --z-palette --z-toast`
Light pools: `--pool-purple --pool-lime --pool-opp`

### Motion
Eases: `--ease-out --ease-inout --ease-spring --ease-snap`
Durations: `--d-fast --d-base --d-slow --d-slower`
Loop durations: `--breathe-dur --spin-dur --shimmer-dur --sweep-dur`

### Type scale
`--fs-display --fs-h1 --fs-h2 --fs-h3 --fs-lg --fs-base --fs-sm --fs-xs --fs-2xs`
Fonts: `--font-sans --font-mono`

### Registered @property (animatable)
`--angle` (conic borders) `--ring-pct` `--shimmer-x`

---

## 2. Utility classes

### Typography
`.t-display .t-h1 .t-h2 .t-h3 .t-lead .t-sm .t-xs` · `.t-dim .t-mid` · `.t-mono` · `.t-label` (uppercase caps)
`.num` / `.t-num` (mono tabular) · `.bluf` (big hero numeric) · `.t-gradient` (lime→purple text)

### Glow (HIERARCHY: max ONE `.glow-energy` per viewport)
`.glow-energy` — hottest element (critical CTA, top opportunity)
`.glow-purple` — active-but-secondary
`.glow-opportunity` — coral high-opp
`.glow-soft` — faint ambient · `.glow-none` — flat
Text: `.tglow-energy .tglow-purple`
Numbers: `.revenue` / `.num-glow` (gradient + drop-shadow; add `.is-projected` ancestor to dim)
Icons: `.iglow-energy .iglow-purple .iglow-opp`
Light pools: `.pool-purple .pool-lime .pool-opp`
Animated: `.breathe` (+ `.breathe--purple`) compositor-safe pulse on `::after`
Borders: `.edge-light` (static gradient rim) · `.energized` (+ `.running`, `.energized--purple`) rotating conic = processing/sweeping/agent-running

### Glass
`.glass` (base floating panel) · `.glass-hero` (bigger blur+radius) · `.glass-deep` (heavier tint)
`.glass-spec` (specular corner edge-light — add alongside `.glass`)
`.lift` (dive-in hover: translateY + scale + elev-4)
`.bar-backdrop` (Comeau masked 200%-height child for sticky bars over a panning map)
`.is-measured` / `.is-projected` (honest material; projected = translucent dashed, dims its numbers)

### Living background (full-bleed fixed; page opts in, content goes in `.app-shell`)
`.bg-base` (solid) · `.bg-mesh` (CSS aurora, reduced-motion-safe) · `.bg-aurora` (OGL canvas mount) · `.bg-particles` (tsParticles mount) · `.bg-grain` (feTurbulence, kills banding)
`.text-scrim` (radial dim behind text for AA over living bg) · `.app-shell` (z above bg)

### Animation helpers
`.anim-reveal .anim-reveal-scale .anim-pop .anim-float`
`.stagger` (auto-delays first 8 children) · `.skeleton` (shimmer loader) · `.countup` (count-up rest style)
`.live-dot` (+ `.live-dot--purple`) pulsing presence dot
`.sweep-overlay` (scanning light pass) · `.flow-line` / `.flow-line--active` (SVG data-flow strokes)

### Layout
`.row .row-between .col .wrap .grow .divider .container .scroll-x` · `[hidden]` · `.sr-only`

---

## 3. Component classes

- **Buttons:** `.btn` base · `.btn-primary` (purple) · `.btn-energy` (the ONE hottest CTA, lime) · `.btn-ghost` · `.btn-icon` · `.btn-sm` `.btn-lg` · `:disabled`/`[aria-disabled]`
- **Chips/filters:** `.chip` (+ `.active`/`[aria-pressed="true"]` = lime; `.chip--purple.active`) · `.chip-dot`
- **Cards (NEVER tables):** `.card` · `.card-glass` · `.card-hot` (rotating glow ring = top opportunity) · `.card-grid` (auto-fill minmax 320px)
- **Score ring:** `.score-ring` set `--pct` (0–100); variants `--high`(lime)/`--mid`(coral)/`--low`(blue); inner `.score-val`
- **Gauge:** `.gauge` set `--val` (0–100) — market-dominance half-circle
- **Badge / status pill (glow rises with readiness):** `.badge` + `--found --audited --ready --contacted --sent --won`; map: `--opportunity --consolidated --unexplored`; micro-tags `.tag-measured` `.tag-projected`
- **Modal/Drawer:** `.scrim` wrapper → `.modal` (dive-in pop) · `.drawer` (right slide; `.closed`/`[hidden]` to hide)
- **Tooltip:** `.tooltip` / `.signal-chip` (glass, pop-in)
- **Kanban (pipeline states):** `.kanban` → `.kanban-col` (+ `--ready` lime accent) → `.kanban-col__head` `.kanban-col__count`
- **Command palette:** `.palette` → `.palette__input` · `.palette__item` (`[aria-selected="true"]`) · `kbd`
- **Radial menu (per-business/agent dispatch):** `.radial` anchor → `.radial__item` (position items via inline transform)
- **Legend (map key):** `.legend` → `.legend__item` → `.legend__swatch` + `--opportunity --consolidated --niche --unexplored`
- **Dispatch dock (cross-project send):** `.dock` (bottom-center glass pill)
- **Toast:** `.toast` · **KPI:** `.stat` → `.stat__label .stat__value .stat__delta` (+ `--up/--down`)

---

## 4. Keyframes (all reduced-motion gated)

`breathe` `spin` `pulse-ring` `shimmer` `sweep-line` `reveal-up` `reveal-scale` `pop-in` `mesh-drift` `float-y` `blink-dot` `flow-dash`

---

## 5. Honesty pattern (copy this)

```html
<!-- MEASURED: solid, full glow -->
<div class="card is-measured">
  <span class="t-label">Revenue (measured)</span>
  <span class="revenue bluf">R$ 184.000</span>
  <span class="badge tag-measured">measured</span>
</div>

<!-- PROJECTED: translucent, dashed, dimmed number -->
<div class="card is-projected">
  <span class="t-label">Revenue with our services (projected)</span>
  <span class="revenue bluf">R$ 320.000–410.000</span>
  <span class="tag-projected">range</span>
</div>
```

---

## 6. Rules for page-builders

1. **ONE `.glow-energy` / one `.btn-energy` / one `.card-hot` per viewport.** Glow budget is scarce on purpose — that's what makes it premium not cheap.
2. **Cards, never tables** (Surfaces B/C). Primary signal in the card face; gap-info + CTA in a secondary expandable strip.
3. **Glass is the accent, not the wallpaper.** Reserve `.glass*` for tooltips/modals/top bar/active card/dock. Keep flat dark `--bg-*` as the primary canvas.
4. **Honest material always:** committed number = `.is-measured`/`.revenue`; estimate = `.is-projected`/`.tag-projected`. Range toggle reveals the projected band.
5. **Animate only opacity/transform.** Glow lives on `::after` (`.breathe`), never animate `box-shadow`.
6. **Gate all non-essential motion** behind `REDUCED`; offer `.perf-lite` body class for modest clients (kills aurora/particles, trims blur).
7. **Status color contract:** high-opportunity = lime/coral hot, consolidated = blue soft, unexplored = gray no-glow. Filters re-map: matching → full glow, rest → dim cold.
8. Text contrast comes from the TEXT fill on `--bg-*`, never from glow. Over living bg, wrap text in `.text-scrim`.
