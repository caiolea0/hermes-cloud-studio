# Hermes 2.0 — Build #1: Diagnosis Engine (Design + Real POC)

**Sealed**: 2026-06-21
**Status**: design locked (8/8 scope filter passed)
**Build #1 metric**: number of businesses with a ready, owner-approved sales dossier.

---

## 1. What we're building (plain) + the locked scope

A **Diagnosis Engine** that, for any Cuiabá business, auto-produces a **sales dossier** — a structured marketing audit the owner can read in 2 minutes and use to pitch. The engine runs autonomously on the daemon; the **owner approves each dossier** (reusing the existing Brain HITL safety gate) before anything goes downstream. Approved dossiers feed **Geronimo** (sales/CRM) and **Vuecra** (site-brief generation).

**Locked scope — 6 dimensions (A–F):**

| Dim | Name | What it answers |
|---|---|---|
| **A** | Presence / social / ads + creatives | Where are they online? Pixel installed? Running ads? Split brand? |
| **B** | SEO / Google position | Do they rank? On-page health? Schema gaps? |
| **C** | Competitive comparison | How do 3 local rivals stack vs them? |
| **D** | Keywords + AdWords competition | Which money keywords do they win/lose? Volume/CPC est? |
| **E** | Organic strategy | Tactical recommendations (LLM synthesis of A–D). |
| **F** | Revenue projection | 3 scenarios using the business's OWN prices + market data. |

**Hard rules (anti-mock invariant):**
- Every number tagged `[FACT]` / `[ESTIMATE]` / `[NEEDS-TOOL]` / `[NO-DATA]`.
- **NEVER a guessed point number.** Revenue = **ranges** (conservative / likely / optimistic) with **visible premises**.
- `$0`-first, self-hosted on Contabo. No paid API in v1.
- Deep on **1–2 Cuiabá niches first** (POC niche: veterinária + pet shop).
- Autonomy boundary = the **approval gate**. Engine audits auto; owner approves + contacts manually.

---

## 2. REAL PROOF-OF-CONCEPT — Clube dos Bichos, Cuiabá

> This is the star section. Everything below is from **real web data pulled during the POC** against a **real, verified, operating** Cuiabá business. Nothing is mocked. Where `$0` web reach hit a wall, it is tagged honestly — not guessed.

**Target**: Clube dos Bichos — Petshop e Clínica/Hospital Veterinária 24h.
Founded 2006 by Dr. Daniela Freire Krakhecke. **Two central units**: R. Comandante Costa 1718 (Centro Sul) + R. Barão de Melgaço 1756 (Porto), Cuiabá-MT.
**Site**: https://clubedosbichoscuiaba.com.br/ (WordPress + Rank Math, ~31-page sitemap, per-specialty SEO landing pages).
**Verified real** via convergence of: own domain + founding story, directory listings (Petboop, GuiaMais, ZoomInfo), live Instagram/Facebook, public reviews.

### Dimension A — Presence / Social / Ads + Creatives

| Finding | Value | Tag |
|---|---|---|
| Instagram primary @clube.dos.bichos | 4,371 followers / 780 posts (retail/brand side) | **FACT** |
| Instagram secondary @clubedosbichoscimv | 8,520 followers / 1,231 posts — the real flagship, more active | **FACT** |
| Split-brand problem | 12.9k combined but fragmented across two inconsistent handles | **FACT** |
| Facebook 'Clubedosbichoscimv' | ~2,049 likes, 442 check-ins | **FACT** |
| Website tracking stack | GTM-N8JQ6R8 + Google Tag GT-TQVKNZR present | **FACT** |
| **Meta Pixel ABSENT** | No `fbq`/`connect.facebook.net`/`fbevents.js` in HTML → cannot retarget 12.9k IG audience or track Meta conversions | **FACT** |
| Conversion funnel | WhatsApp `5565992145232` hardcoded 11× on homepage. No booking/form-to-CRM | **FACT** |
| Engagement rate sample | 211 likes / 8,520 = ~2.5% on one 2024-11-26 reel (single data point) | **ESTIMATE** |
| Posting cadence per week | 1,231 posts implies regular, but per-week needs timeline scrape | **NEEDS-TOOL** |
| YouTube @clubedosbichos | Channel indexed, stats JS-walled | **NEEDS-TOOL** |
| Meta Ad Library — active ads | facebook.com/ads/library returns 403 + JS-rendered. No Meta Pixel is a strong indirect signal they run NO tracked Meta ads | **NEEDS-TOOL** |
| Google Ads Transparency | JS-rendered, login/empty to fetch. Google Tag present ≠ proof of active campaigns | **NEEDS-TOOL** |
| Ad creative images | Both ad libraries JS-walled to plain fetch | **NO-DATA** |

**Pitch angle**: "You have 12.9k followers across two Instagram accounts but **no Meta Pixel** on your site — you're paying for attention you can't measure or re-target." Three demonstrable gaps: split brand, no pixel, WhatsApp-only untracked funnel.

### Dimension B — SEO / Google Position

| Finding | Value | Tag |
|---|---|---|
| Title tag | "Clínica Veterinária \| Clube dos Bichos \| (65) 99214-5232" — keyword-rich | **FACT** |
| Meta description | Present, 156 chars, but no neighborhood/city keyword | **FACT** |
| Mobile viewport / canonical | Both present + correct (canonical guards legacy domains) | **FACT** |
| SEO plugin | Rank Math on WordPress, OG tags present — actively managed | **FACT** |
| **Schema gaps** | JSON-LD LocalBusiness present but minimal: **MISSING address, geo, telephone, openingHours, aggregateRating, priceRange; NOT typed VeterinaryCare** → lost rich-result eligibility | **FACT** |
| XML sitemap | Rank Math sitemap_index.xml, ~31 URLs, some updated 2026-04-30 | **FACT** |
| Homepage lead form | No inline `<form>` — relies on WhatsApp/phone click | **FACT** |
| Rank 'clínica veterinária Centro Sul Cuiabá' | **#1 and #2** (homepage + /sobre-nos) | **FACT** |
| Rank 'pet shop ... Porto Cuiabá MT' | Top-3 (#2), service pages also indexed | **FACT** |
| Rank broad 'veterinário Cuiabá melhor clínica' | Present but NOT #1 — outranked by Vivet, Cândido Mariano, aggregators | **FACT** |
| Core Web Vitals / Lighthouse | Heavy galleria (70+ imgs) suggests LCP risk; needs PageSpeed Insights | **NEEDS-TOOL** |
| Ranked-keyword set + positions over time | ~31 pages confirmed, but full ranked set needs Search Console/DataForSEO | **NEEDS-TOOL** |
| Backlink profile / domain authority | Needed to explain broad-term gap; needs Ahrefs/Moz | **NEEDS-TOOL** |

**Pitch angle**: "You OWN the neighborhood searches (#1-2) but leak the big head term 'veterinário Cuiabá' to Vivet/Cândido Mariano. Two fast wins: turn on the half-empty schema (free rich-result stars + map pin) and add a lead-capture form."

### Dimension C — Competitive Comparison

3 direct rivals (same 24h hospital + specialty + Cuiabá niche):

| | Clube dos Bichos (target) | Vivet | Cândido Mariano (HVCM) |
|---|---|---|---|
| Instagram | 4,371 (primary) / 8,520 (secondary) | ~17K (~3.9×) **FACT** | ~10K (~2.3×) **FACT** |
| Facebook | active, likes NO-DATA | 4,528 likes **FACT** | active **FACT** |
| Google rating | NOT surfaced **NEEDS-TOOL** | 4.4 / 250+ (discrepancy 250 vs 49 — reconcile live) **NEEDS-TOOL** | NOT surfaced **NEEDS-TOOL** |
| Website | **best SEO surface** (per-specialty pages) + pet shop + 2 locations **FACT** | blog + specialties, no shop | rich specialties + family portal, no shop |
| Hero claim | (none yet) | chemo/oncology center | **"ONLY vet ICU in MT"** |
| Funnel | WhatsApp/phone (parity) **FACT** | WhatsApp/phone | WhatsApp/phone |

**Overall standing**: **MIDDLE-to-BEHIND** — behind on social reach + visible social-proof, AHEAD on SEO breadth + multi-location + integrated retail. *The gap is marketing execution, not service capability.* (synthesis = **ESTIMATE**.)

**Pitch angle**: "Established since 2006, best website, only one with two central locations AND a pet shop — but Vivet has 4× your Instagram and Cândido Mariano owns the 'only ICU in MT' headline. You win on substance, lose on visibility."

### Dimension D — Keywords + AdWords Competition

| Keyword cluster | Status | Tag |
|---|---|---|
| 'veterinário 24 horas Cuiabá' | Money keyword, Clube ranks but 6+ rivals contest | **FACT** |
| 'clínica veterinária Cuiabá' | Highest-volume head term, saturated SERP (10+) | **FACT** |
| 'pet shop Cuiabá / Centro Sul' | Strong geo-anchor (2 units) but underused — site buries retail | **FACT** |
| 'banho e tosa Cuiabá' | High-frequency recurring revenue — **Clube INVISIBLE**, aggregators win | **FACT** |
| 'castração/vacina/microchip' | Mid-funnel — VetPrev owns positioning, content gap | **FACT** |
| Specialty long-tail (oftalmo/felina/ortopedia) | Low-volume, HIGH-value, LOW-competition — easiest wins | **ESTIMATE** |
| Search volume — head terms | ~1,000–2,500/mo (from Cuiabá 660k pop + pet-ownership) | **NEEDS-TOOL** |
| Search volume — '24h' emergency | ~300–700/mo | **ESTIMATE** |
| Search volume — banho e tosa | ~700–1,500/mo | **ESTIMATE** |
| AdWords competition | MED-HIGH head terms / LOW specialty long-tail | **ESTIMATE** |
| **Their own prices** | Site says "preços justos" but publishes **ZERO R$** | **NO-DATA** |
| Niche ticket benchmark BR 2025-26 | Consulta R$100-250; especialista R$200-500; banho/tosa R$35-150; blended Cuiabá ~R$120-180 | **ESTIMATE** |

### Sample Revenue Projection (Dimension F) — ranges, premises visible

**Formula**: `new_clients = demand × capture% × conversion%` ; `revenue = clients × blended_ticket`
**Premises** (all tagged): demand 2,500–5,000/mo `[EST, NEEDS-TOOL DataForSEO]`; capture 8–15% `[EST]`; conversion 5–10% `[EST]`; blended ticket **R$150** `[EST — business hides real prices, NO-DATA; replace with sales-call price list]`.

| Scenario | New clients/mo | Revenue/mo | Revenue/yr | Tag |
|---|---|---|---|---|
| **Conservative** | 10 | R$1,500 | R$18,000 | EST |
| **Likely** | 27 | R$4,000 | R$48,000 | EST |
| **Optimistic** | 75 | R$11,250 | R$135,000 | EST |

**Disclaimer (shown on dossier)**: marketing-attributable **LIFT**, not total revenue. Optimistic = upper bound contingent on full-funnel execution. Cuiabá 660k = deliberately SMALL realistic volumes, NOT inflated. **Recurring lever**: captured grooming client ~R$80 × 8 visits/yr ≈ R$640 LTV; plano-saúde-pet from R$19,90/mo = predictable MRR.

### HONEST VERDICT — what worked $0 NOW vs what needs installed tools

**Worked $0 via plain web RIGHT NOW (all FACT):**
- Both IG accounts + exact follower/post counts; FB likes; one dated reel engagement.
- Full website tracking stack from raw HTML grep (GTM ids, **Meta Pixel absence** — high-value indirect signal, no scraping needed).
- Complete on-page SEO audit + schema-gap detection (grep returning 0 = FACT).
- Sitemap URL count, SERP ordering for niche+neighborhood queries (#1-2 local, mid-pack broad).
- Competitor identities, addresses, feature inventories, follower counts (Vivet ~17K, HVCM ~10K).
- Keyword set + "currently ranks or not" from live SERP.
- Niche ticket benchmarks from public BR sources.

**NEEDS-TOOL in production (headless / free-API, VM-only):**
1. **Meta Ad Library + Google Ads Transparency** — both JS-walled/403 → headless Playwright (VM) to confirm active ads + pull creatives.
2. **Exact Google Maps rating + review count** for target AND competitors — the **#1 missing number** for a credible comparison. → **Google Places free-tier API** (clear winner over scraping).
3. **Exact keyword volume / CPC / competition index** → ship `[EST]` ranges first; **$0 Keyword-Planner-via-Playwright** next; DataForSEO only as paid escape hatch.
4. **Lighthouse / Core Web Vitals** → free **PageSpeed Insights API**.
5. IG posting cadence per week, YouTube stats → IG/JS timeline scraper.

**NO-DATA (genuinely unavailable):** ad creative images behind JS walls; the business's real prices (they publish none — publishing prices becomes a pitch recommendation).

**Conclusion**: the $0 web path alone produces a **genuinely sellable dossier** — concrete, numeric, demonstrable gaps the owner feels immediately (no pixel, split brand, 4.4K vs 10-17K IG reach, invisible on banho-e-tosa). Installed tools upgrade specific `[EST]`/`[NEEDS-TOOL]` cells to `[FACT]`; they do not gate the product.

---

## 3. Engine architecture

### 3.1 Daemon placement (P-priority)

Diagnosis is **non-destructive, batch, latency-tolerant** → low-urgency band, never competing with replies/outreach.

```
P0  COBAIA      (warmup absolute override)        — untouched
P1  REPLY                                          — untouched
P2  OUTREACH    (destructive, HITL)               — untouched
P3  ENRICHMENT                                     — untouched
P4  DISCOVERY                                      — untouched
P5  AUDIT        ← shallow score (existing pipeline audit, fast) = the GATE
P5.5 DIAGNOSIS   ← NEW: deep 6-dim dossier (priority=5, ordered AFTER audit)
P6  SCORING / P7 REPORTING                          — untouched
```

`TaskCategory.DIAGNOSIS = "diagnosis"` emitted at **priority 5**, only for `stage='audited' AND dossier_status='pending'`. Shallow audit gates; deep dossier runs on survivors. Clean funnel: **audited → diagnosed → ready**. Heavy stage restricted to off-peak (night) via the existing emitter clock-check (no new scheduler).

### 3.2 The 6 stages (sequential orchestration, fan-out inside)

`PipelineRunner.diagnosis_batch(limit=10)` in `core/pipeline.py`, next to `audit_pending()`. A–D are independent → `asyncio.gather`; E, F depend on A–D output.

```
diagnosis_batch(prospect)
├─ gather(   # parallel, $0, I/O-bound
│   A presence_audit()      → social/ads/creatives/pixel
│   B seo_audit()           → on-page SEO + SERP position
│   C competitive_audit()   → 3 local rivals
│   D keyword_audit()       → keyword clusters + volume/CPC est
│  )
├─ E organic_strategy(A,B,C,D)      # LLM synthesis (Ollama), all EST
├─ F revenue_projection(D, prices)  # ranges, business OWN prices
└─ DossierTagger.assemble() → tagged JSON → prospects row + dossier_runs
```

Each sub-audit returns a uniform envelope: `{dimension, status, metrics[], fact_ratio, tool_gaps[]}`.

### 3.3 FACT/EST discipline (built into the stage contract)

No metric leaves a stage untagged. `DossierTagger.tag_metric(value, source, method, confidence)` → `TaggedMetric {label, value, tag, source, method, confidence}`.

- **FACT** (conf 1.0) — direct extraction: live HTML grep, observed SERP order, public follower counts, sitemap count, schema presence/absence, Google Places.
- **ESTIMATE** (conf 0.3–0.7) — LLM inference, benchmark extrapolation, formula output; **always carries a visible premise string**.
- **NEEDS-TOOL** (conf 0.0) — data exists but needs headless/free-API not yet wired; surfaces as explicit gap, NEVER a guess.
- **NO-DATA** (conf 0.0) — genuinely unavailable.

**Anti-mock invariant (enforced in tagger):** a revenue/volume number may NEVER be a point value tagged FACT unless `method ∈ {customer_provided, live_extraction}`. Projections are **ranges only**; tagger **raises** if a single point R$ value is FACT-tagged without verifiable source. Confidence rollup `dossier_confidence = weighted_mean(per-dim fact_ratio)` → drives HITL gate.

---

## 4. Dossier schema

**Two-table design** (mirrors existing `prospects` + `pipeline_executions` split): thin summary cols on `prospects` for fast dashboard/sync; full payload + history in new `dossier_runs`.

### 4.1 `prospects` migration (idempotent — same try/SELECT/ALTER pattern as core/state.py)

```sql
ALTER TABLE prospects ADD COLUMN dossier_status TEXT DEFAULT 'pending';
  -- pending | running | complete | needs_review | approved | rejected
ALTER TABLE prospects ADD COLUMN dossier_confidence REAL;   -- 0.0-1.0 rollup
ALTER TABLE prospects ADD COLUMN dossier_fact_ratio REAL;   -- count(FACT)/total
ALTER TABLE prospects ADD COLUMN dossier_run_id INTEGER;    -- FK -> dossier_runs.id (latest)
ALTER TABLE prospects ADD COLUMN dossier_approved_at TIMESTAMP;
ALTER TABLE prospects ADD COLUMN dossier_approved_by TEXT;  -- owner id / 'auto'
```

> Rejected the asset-map's 6 per-dimension JSON columns on the hot sync table — bloats it and duplicates `dossier_runs`. Keep `prospects` thin.

### 4.2 New table `dossier_runs`

```sql
CREATE TABLE IF NOT EXISTS dossier_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id   INTEGER NOT NULL,
    brain_run_id  TEXT,                  -- links to brain_runs (HITL trace)
    status        TEXT DEFAULT 'running',-- running|complete|failed|needs_review|approved|rejected
    confidence    REAL,                  -- rollup 0.0-1.0
    fact_ratio    REAL,                  -- count(FACT)/total metrics
    dim_a_presence    TEXT,  -- JSON: handles, follower counts, pixel/GTM, ad-library status, creatives
    dim_b_seo         TEXT,  -- JSON: title/meta/canonical/schema gaps, sitemap count, SERP positions
    dim_c_competitive TEXT,  -- JSON: [{competitor, ig_followers, fb_likes, google_rating, advantages[], gaps[]}]
    dim_d_keywords    TEXT,  -- JSON: [{term, intent, volume_est, cpc_est, competition_est, currently_ranks}]
    dim_e_strategy    TEXT,  -- JSON: {recommendations[], priority_order[], quick_wins[]}  (all EST)
    dim_f_revenue     TEXT,  -- JSON: scenarios + premises + own-price source (see 4.3)
    tool_gaps     TEXT,      -- JSON: ["meta_ad_library","places_exact_rating","lighthouse",...]
    pitch_angles  TEXT,      -- JSON: opener strings (feeds Geronimo)
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at  TIMESTAMP,
    approved_at   TIMESTAMP,
    FOREIGN KEY (prospect_id) REFERENCES prospects(id)
);
CREATE INDEX IF NOT EXISTS idx_dossier_prospect ON dossier_runs(prospect_id);
CREATE INDEX IF NOT EXISTS idx_dossier_status   ON dossier_runs(status);
```

History is free: each re-audit inserts a new row; `prospects.dossier_run_id` → latest. Owner can diff.

### 4.3 `dim_f_revenue` payload shape (ranges, visible premises, OWN prices)

```json
{
  "ticket": { "value": 150, "tag": "EST", "method": "niche_benchmark_blend",
    "source": "GetNinjas/AcharVet 2025-2026; Cuiaba below SP/RJ",
    "own_price_status": "NO-DATA",
    "own_price_note": "site publishes zero R$; replace with sales-call price list" },
  "premises": {
    "formula": "new_clients = demand*capture%*conversion%; revenue = clients*ticket",
    "demand_monthly": {"range": [2500,5000], "tag": "EST", "method": "Cuiaba 660k pop * pet-ownership; NEEDS-TOOL DataForSEO for exact"},
    "capture_pct":    {"range": [0.08,0.15], "tag": "EST"},
    "conversion_pct": {"range": [0.05,0.10], "tag": "EST"} },
  "scenarios": {
    "conservative": {"new_clients_mo": 10, "revenue_mo": 1500,  "revenue_yr": 18000,  "tag": "EST"},
    "likely":       {"new_clients_mo": 27, "revenue_mo": 4000,  "revenue_yr": 48000,  "tag": "EST"},
    "optimistic":   {"new_clients_mo": 75, "revenue_mo": 11250, "revenue_yr": 135000, "tag": "EST"} },
  "disclaimer": "Marketing-attributable LIFT, not total revenue. Upper bound contingent on full-funnel execution."
}
```

Owner-price is first-class: published → `own_price_status="FACT"`, ticket is real. Hidden (Clube case) → `NO-DATA`, and "publish prices" becomes a pitch angle. **No fabricated R$.**

---

## 5. Extend-vs-new decisions (grounded in real Hermes assets)

> Ground-truth corrections applied from verifying real code (asset-map had wrong assumptions):
> 1. **MCP servers are TypeScript/Node** (`src/`, `package.json`, `tsconfig.json`) — template = `mcps/hermes-control/`. NOT Python.
> 2. **`core/web_audit.py` does not exist** — audit logic lives in `core/pipeline.py` (`audit_pending`) + `api/audit.py` which **proxies to the VM**. Heavy fetch/scrape runs **VM-only**; PC orchestrates + stores. (BLACKLIST R2.)
> 3. **`INTENT_REGISTRY` is locked at exactly 6 (D3).** Cobaia uses a SEPARATE registry via `startswith` fast-path. Diagnosis must follow the same separate-registry pattern, NOT mutate the canonical 6.
> 4. Daemon uses integer `priority` on a `Task` dataclass + `TaskCategory` enum; AUDIT=5. No literal P0-P7 method slots.
> 5. `brain/safety.py` confidence threshold is **0.5**, not 0.75 — don't change the global; add a dimension-specific 0.75 for dossiers.

| # | Component | Decision | Where | Why |
|---|---|---|---|---|
| 1 | Prospects schema | **EXTEND** | `core/state.py` init_db | 6 thin `dossier_*` cols, idempotent |
| 2 | dossier_runs table | **NEW** | `core/state.py` | History + audit trail; mirrors pipeline_executions split |
| 3 | Daemon category | **EXTEND** | `daemon/orchestrator.py` (TaskCategory enum + emitter) | Add DIAGNOSIS, priority 5 post-audit, night window |
| 4 | Pipeline stage | **EXTEND** | `core/pipeline.py` | `diagnosis_batch()` next to `audit_pending()` |
| 5 | 6 sub-audits | **EXTEND/REUSE + thin NEW** | `core/diagnosis/*.py` + VM `api/audit.py` proxy | A/B/C reuse httpx+regex audit path (VM); C/D/E/F new modules |
| 6 | Diagnosis MCP | **NEW (TypeScript)** | `mcps/diagnosis-engine/` (copy `hermes-control` scaffold) | 6 tools, register in `mcps/gateway` access matrix |
| 7 | Brain intent | **EXTEND via separate registry** | new `brain/diagnosis_intent.py` + `startswith("diagnosis_")` in `brain/decide.py` | Canonical 6 LOCKED — mirror cobaia pattern |
| 8 | Safety/HITL gate | **REUSE + 1 condition** | `brain/safety.py` | Non-destructive path; add `dossier_requires_review()` @0.75 |
| 9 | Confidence tagger | **NEW** | `core/dossier_tagger.py` | TaggedMetric + rollup + anti-mock invariant |
| 10 | Dashboard viewer | **EXTEND** | `dashboard/` + `api/dossiers.py` | 6-pane page, color-coded tags, approve button |
| 11 | Geronimo/Vuecra feeds | **NEW** | `api/dossier_export.py` | Export endpoints + webhook on approval transition |

**Net: 6 EXTEND, 5 NEW.** Heaviest reuse: VM-proxied audit fetch (httpx+regex), gateway/dispatcher, Brain ReAct loop, HITL safety, daemon emitter.

**HITL flow (reuse, not rebuild):** diagnosis is non-destructive → won't trip the destructive path; it trips the confidence path. `dossier_requires_review(confidence, fact_ratio)` → review if `fact_ratio<0.75` OR `confidence<0.75`. Below → status `needs_review` + `pending_confirmation` row in `brain_runs` (reuse `brain/persistence.py`). Owner approves via `POST /api/dossiers/{id}/approve` → sets `dossier_approved_at`, locks dossier from auto-re-audit (`WHERE dossier_status='pending'` excludes approved). Downstream Geronimo/Vuecra fires **only on the approval transition** — the autonomy boundary is exactly the approval gate.

---

## 6. $0 tool stack per dimension + keyword/Places source recommendation

All self-hosted on Contabo / VM. No paid API in v1. Tag honestly when a $0 path can't reach a number.

| Dim | $0 tool (v1) | Reaches (FACT) | NEEDS-TOOL (v2) |
|---|---|---|---|
| **A** | httpx+regex (pixel/GTM/social) + VM-Playwright (followers, ad libraries) | pixel presence, GTM id, follower counts, split-brand | ad creative images (NO-DATA), cadence |
| **B** | httpx+regex (title/meta/canonical/schema/sitemap) + VM SERP scrape | on-page, schema gaps, sitemap count, relative SERP rank | Lighthouse (→ free PageSpeed Insights API), backlinks (Ahrefs paid) |
| **C** | A+B run on 3 rivals; rival discovery via SERP | rival URLs/followers/features, standing (EST synth) | exact Google rating (→ Places free tier) |
| **D** | Ollama (hermes-llm) keyword clusters + SERP "currently ranks" | keyword set, ranks-or-not | exact volume/CPC/competition (see below) |
| **E** | Ollama synthesis of A–D | recommendations, quick-wins (all EST) | — inherently EST |
| **F** | Python formula + niche benchmarks + own prices if published | scenarios (EST), formula premises (FACT-tagged) | exact ticket (sales call), exact volume (feeds from D) |

**Keyword volume/CPC — test both, tiered:**
- **v1 ($0, ship now):** DO NOT buy DataForSEO. Emit volume/CPC as `[EST]` ranges anchored to Cuiabá pop. Honest and sellable — the pitch is gap-mapping ("rivals rank for X, you don't"), which needs *ranking presence* (FACT from SERP), not exact volume.
- **v1.5 (still $0):** scrape **Google Keyword Planner** via VM-Playwright under a throwaway Ads account → upgrades `[EST]`→`[FACT]` free. **Test this path first.**
- **v2 (paid, only if revenue justifies):** **DataForSEO** (~$0.05/req, cheapest) behind a feature flag; tagger auto-flips when present.

**Places exact rating — clear winner:** **Google Places API free tier.** The `prospects` table already has `google_rating`/`google_reviews` + `source='google_maps'`. **Reuse the existing Maps discovery path** to pull exact rating into dim_c at `[FACT]`. Do NOT Playwright-scrape Maps (brittle; the POC's #1 missing number) when the free API covers it. Highest-value, lowest-cost upgrade — kills the biggest POC gap for both target and rivals.

**Lighthouse/CWV:** free **PageSpeed Insights API** — no scraping, no cost.

---

## 7. Phased build plan H2D-F0..F8 (goal / scope / effort / acceptance-on-real-business / model / gates)

**Global gates on EVERY phase** (cobaia-style): BLACKLIST R2 intact (no direct import of `linkedin/*` or scraper modules — all scraping via `mcp.diagnosis.*` → gateway dispatch; scrape/browser **VM-only**); pytest green (no regression in `tests/test_brain_golden.py`); `$0` verified (no paid key in `.env`); **anti-mock proof on Clube dos Bichos** — every number `[FACT]`/`[EST]`, never a bare point.

| Phase | Goal | Scope | Effort | Model | Acceptance (on real business) |
|---|---|---|---|---|---|
| **F0** Foundation | Schema + tagger + separate intent registry | cross-cutting | S (8-12h) | Sonnet | `init_db()` twice = no error; `tag_metric(4371, ig_raw_html, 1.0)`→FACT, `tag_metric("~R$150", benchmark, 0.5)`→EST; tagger **raises** on untagged bare number; insert+read a real Clube row |
| **F1** MCP skeleton + gateway | TS MCP, 6 tool stubs, dispatchable | all 6 (stubs) | M (12-16h) | Sonnet | `decide(intent=audit_diagnosis, {Clube dos Bichos})` returns 6 keys all `[NEEDS-TOOL]` (honest, not fake); `brain_runs` row persisted |
| **F2** Dim A Presence | Presence/social/ads/pixel audit | A | M (12-16h) | Sonnet | Reproduces real POC: 2 IG accounts + counts, GTM ids, **Meta Pixel absent** = FACT; ad libraries = NEEDS-TOOL; creatives = NO-DATA |
| **F3** Dim B SEO | On-page + schema + SERP position | B | M | Sonnet | Reproduces: title/canonical/Rank Math FACT, schema-gap detection FACT, #1-2 local rank FACT, CWV = NEEDS-TOOL |
| **F4** Dim C Competitive | 3 rivals + Places free-tier rating | C | M-L (16-20h) | Sonnet | Vivet ~17K / HVCM ~10K IG = FACT; target+rival Google rating now FACT via Places (was NEEDS-TOOL); standing = EST synth |
| **F5** Dim D Keywords | Clusters + ranks + EST volume | D | M | Sonnet | Clube ranks '24h' FACT, INVISIBLE on banho-e-tosa FACT; volume = EST ranges w/ premise; own prices = NO-DATA |
| **F6** Dim E+F Strategy+Revenue | LLM strategy + ranged projection | E, F | M | Sonnet | Strategy all EST; revenue 3 scenarios w/ visible premises; tagger blocks any point-R$ FACT |
| **F7** HITL + Dashboard | Review gate + 6-pane viewer | cross-cutting | M-L | Sonnet | Clube dossier confidence<0.75 → needs_review; approve sets timestamp + locks; tags color-coded blue/amber/grey/red |
| **F8** Exports | Geronimo CRM + Vuecra brief + webhook | cross-cutting | S-M | Sonnet | On approval, export endpoints emit tagged JSON; webhook fires on `dossier_approved_at` transition only |

Build order is dependency-correct: schema → tagger → MCP pipe → dimensions A→F → HITL/dashboard → exports.

---

## 8. Honest risks + open owner decisions

**Risks:**
1. **VM scraping fragility** — Meta/Google ad libraries + Keyword Planner are JS-walled/anti-bot; headless paths break on their UI changes. Mitigation: tag `[NEEDS-TOOL]` and degrade gracefully; never block a dossier on a scrape.
2. **Region skew in SERP** — POC WebSearch was US-region; absolute BR positions may shift. Relative ordering + own-domain dominance are reliable; exact positions need Search Console.
3. **Ticket honesty** — when a business hides prices (common), revenue ticket is `[EST]` until a sales call. The number is only as good as the premise; the dossier shows the premise.
4. **Confidence threshold tuning** — 0.75 is a guess; may over- or under-trigger HITL. Watch the first ~20 real dossiers and adjust.
5. **Places free-tier quota** — generous but finite; batch + cache ratings, don't re-pull per re-audit.

**Open owner decisions:**
- **D1 — Keyword volume tier:** ship `[EST]` only (v1) vs invest VM time in Keyword-Planner-via-Playwright (v1.5) now? (Recommendation: ship EST, add Planner next sprint, DataForSEO only if revenue justifies.)
- **D2 — Places API:** confirm OK to enable Google Places free tier (kills the #1 POC gap). Free but requires a Google Cloud project + key.
- **D3 — HITL strictness:** auto-approve dossiers with confidence ≥0.75 + fact_ratio ≥0.75, or require owner review on **every** dossier in Build #1? (Recommendation: review every one during POC niche, then relax.)
- **D4 — Niche depth:** lock veterinária + pet shop as the only Build #1 niche, or add a 2nd (e.g. restaurantes) before declaring Build #1 done?
- **D5 — Export timing:** fire Geronimo/Vuecra webhooks automatically on approval, or keep export manual (owner clicks "send to Geronimo") for Build #1?

---

**Relevant files (absolute):**
- `D:\dev-projects\main\hermes-cloud-studio\core\state.py` (schema migration, init_db)
- `D:\dev-projects\main\hermes-cloud-studio\core\pipeline.py` (diagnosis_batch next to audit_pending)
- `D:\dev-projects\main\hermes-cloud-studio\daemon\orchestrator.py` (TaskCategory + priority emitter)
- `D:\dev-projects\main\hermes-cloud-studio\brain\safety.py` (HITL gate reuse + dossier threshold)
- `D:\dev-projects\main\hermes-cloud-studio\mcps\hermes-control\` (NEW MCP template, TypeScript) + `mcps\gateway\` (register)
- New: `core\dossier_tagger.py`, `core\diagnosis\*.py`, `brain\diagnosis_intent.py`, `mcps\diagnosis-engine\`, `api\dossiers.py`, `api\dossier_export.py`
