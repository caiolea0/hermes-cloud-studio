# Hermes 2.0 — Market + Repo Landscape
**Sealed**: 2026-06-21

---

## 1. TL;DR (plain language)

### What the best products do that Hermes should steal
- **Dense filterable lead TABLE as the home surface** (Apollo: 65+ attributes, sortable, multi-filter rail). This is the default surface of every winning tool.
- **Waterfall enrichment shown as cascading provider attempts** w/ pay-only-on-success (Clay). Communicates effort + builds trust; Hermes shows free sources cascading the same way at $0.
- **Per-field confidence badges** (green/yellow/red verified) on email + phone (Seamless live-verify, Lusha confidence).
- **Lead/account SCORING that reorders the work queue** (Apollo reorders sequences by score, not FIFO) → a prioritized "work next" queue, not a flat list.
- **Buying-signal timeline feed** (job changes, funding, hiring, new-website, ad-spend) as a chronological stream (ZoomInfo intent + Surfe job-change alerts) → maps to Hermes `daemon.*` WS events.
- **One-click enrich/add-to-pipeline from an inline overlay** (Surfe/Lusha Chrome extension on LinkedIn).
- **"Digital worker" persona framing** with an activity dashboard (11x Alice, Artisan Ava) → higher perceived value than "a tool".
- **Auto-generated digital-presence GAP AUDIT** (0-100 score + plain-language gap report) as the door-opener artifact (MyWebAudit). This IS the gap-to-sell input.

### Top repos to reuse
- **Discovery (backend)**: `gosom/google-maps-scraper` (4.4k★, Go, ships a Claude Code MCP skill) — primary business-finder.
- **BR data spine (backend)**: `rictom/cnpj-sqlite` + `fabioserpa/CNPJ-full` + `turicas/socios-brasil` — official Receita Federal CNPJ/CNAE/owner data, offline, zero ban risk.
- **Website enrichment (backend)**: `unclecode/crawl4ai` (68k★) driven by local Ollama → site → structured JSON.
- **Full-loop reference (backend)**: `eracle/OpenOutreach` (2.2k★) — discover→ICP rank→email→multichannel state machine.
- **Map UI**: `visgl/deck.gl` + `visgl/react-map-gl` + MapLibre (no token) — H3HexagonLayer for "found vs unexplored" coverage; `keplergl/kepler.gl` for fast prototype.
- **Table UI**: `openstatusHQ/data-table-filters` on `TanStack/table` — faceted filters + virtualized 10k+ rows.
- **Conveyor UI**: `marmelab/atomic-crm` (MIT Kanban) or `twentyhq/twenty` (AGPL); `CodeRyderX/leadtracker` for the dnd-kit drag pattern.
- **Patterns**: `assafelovic/gpt-researcher` (planner/executor research), `sentient-agi/EvoSkill` (failure→skill synthesis), `BerriAI/self-improving-agent` (propose-diff→approve→PR, targets claude-agent-sdk).

### Hermes' unique angle (what NONE of them do)
**Gap-reverse-filter** (find businesses that LACK what you sell, inverting BuiltWith/Wappalyzer) + **$0 self-hosted** (whole category is credit-metered) + **agentic end-to-end** (find→audit→pitch→fulfill via Geronimo/Vuecra) + **Cuiabá/BR-native** (CNPJ + Maps long-tail + PT-BR + WhatsApp) + **24/7 self-improving Brain**. No commercial tool combines these.

---

## 2. Commercial products — what to learn

### Sales / market-intelligence (global)
4 archetypes:
1. **All-in-one DB + execution** — Apollo (210-270M contacts), ZoomInfo (deepest firmo/techno/intent + org charts, WebSights de-anonymized visitors).
2. **Enrichment orchestrators** — Clay (waterfall across 150+ providers, Claygent AI agent, "Find Local Businesses via Google Maps" recipe w/ owner-finding waterfall).
3. **Point contact-finders** — Lusha, Seamless (live-verify at query time).
4. **Channel/signal tools** — Instantly (outbound), Surfe (LinkedIn→CRM overlay), BuiltWith/Wappalyzer (technographic), Google Maps scrapers (local).

**Best features worth adopting**: Apollo 65+-attribute filter rail; Clay waterfall visualization + pay-on-success; per-cell confidence badges; score-reordered work queue; signal timeline; inline overlay; Maps scraper field set (name/address/phone/website-present/email/social/reviews/rating) as the local-prospecting schema; **`has-no-website` / `running-X-tech` as filterable columns** (the gap angle); saved-search auto-refresh lists.

### Agentic AI-SDR (global)
Mature autonomous outbound on 270-400M DBs: **Artisan/Ava** ("AI BDR", ~80% automation), **11x/Alice+Julian** ("digital worker", 105 langs, voice add-on), **Relevance AI** (no-code multi-agent builder, 400+ templates, exact-cost-no-markup credits — good cost mental model), **Apollo** (cheapest credible full stack), **Clay/Claygent**. Strong autonomy, weak BR data, expensive + annual contracts.

### BR market-intelligence
Strong local data, light on true autonomy: **Econodata** (24M+ BR cos), **Speedio** (80+ filters CNAE/size/geo, decisor LI/email/WhatsApp/phone + active-number check), **Driva** (closest BR full agentic analog, freemium), **Cortex** (enterprise LatAm). Reuse the *patterns* (80-filter segmentation, active-number validation), replicate the *data* free via CNPJ.

### Emerging niche directly on-target
**Maps Scraper AI / Scrap.io / n8n Maps templates** — find owner-operated locals absent from any DB (Hermes's exact target). **AI-visibility/digital-presence audit** (MyWebAudit) — audit→show gap→sell fix motion.

### Pricing reality (why $0 self-hosted is the wedge)
- ZoomInfo ~$15k-25k/yr, per-seat $1.5-2.5k, opaque.
- Apollo $49-149/user/mo; Clay $149-800/mo + credit-per-action.
- 11x ~$5k/mo, min $50-60k yr1; Artisan $280-2k/mo annual-only.
- BR: Speedio R$300-2k/mo; Econodata/Cortex quote-based.
- Entire category is **per-record + per-action billed**. Hermes on free public sources + own VM session = **no marginal cost per lead, no credit anxiety** = structural undercut.

---

## 3. Reusable GitHub repos (the build accelerators)

### Scrapers + data (business discovery, ad-library, enrichment, BR data)
| Repo | URL | Maturity | How Hermes reuses |
|---|---|---|---|
| gosom/google-maps-scraper | https://github.com/gosom/google-maps-scraper | 4.4k★, very active (v1.14 May 2026), Go | **Primary discovery engine.** Ships Claude Code MCP skill + REST API + LeadsDB dedup; wrap behind Hermes gateway, feed Cuiabá category+geo queries, enable email-crawl flag. 33+ fields incl. website-present, reviews, rating. |
| rictom/cnpj-sqlite | https://github.com/rictom/cnpj-sqlite | Active BR, maintained, Python | Load Receita Federal CNPJ → SQLite (empresas/estabelecimentos/socios). JOIN gmaps phone/name → official CNAE+address. Zero ban risk, offline. |
| fabioserpa/CNPJ-full | https://github.com/fabioserpa/CNPJ-full | Popular BR, Python | Alt full-dataset loader + QSA partner graph. ICP filtering by city+CNAE. |
| turicas/socios-brasil | https://github.com/turicas/socios-brasil | Established BR civic-tech, Python | Owner/partner (QSA) name extraction for outreach personalization w/o LinkedIn risk. |
| unclecode/crawl4ai | https://github.com/unclecode/crawl4ai | 68k★, top trending, Python | Website → clean Markdown/JSON enrichment via local Ollama. Enrich gmaps website URLs (services, hours, stack, contacts). Apache-2.0. |
| ScrapeGraphAI/Scrapegraph-ai | https://github.com/ScrapeGraphAI/Scrapegraph-ai | tens of k★, active, Python | Prompt-defined extraction survives site redesigns; resilient for heterogeneous SMB sites; works w/ local LLM. |
| firecrawl/firecrawl | https://github.com/firecrawl/firecrawl | 110k★, YC, TS | Self-host only (skip hosted per guardrail). Map endpoint enumerates a domain's URLs. Heavier than crawl4ai. |
| mocnik-science/osm-python-tools | https://github.com/mocnik-science/osm-python-tools | Established, Python | Free Overpass/Nominatim POI discovery; supplement gmaps, no ban risk. |
| gboeing/osmnx | https://github.com/gboeing/osmnx | Widely used, Python | `features_from_place('Cuiabá')` → POIs as GeoDataFrame; dedup-by-coordinate vs gmaps. |
| faniAhmed/GoogleAdsTransparencyScraper | https://github.com/faniAhmed/GoogleAdsTransparencyScraper | Niche, working, Python | Intent signal: who's buying Google Ads = warm prospects already spending. |
| skylarcheung/Facebook-Ad-Library-Scraper | https://github.com/skylarcheung/Facebook-Ad-Library-Scraper | Small, functional, Python | Official Meta Ad Library API = active advertisers = high intent. |
| georgekhananaev/google-reviews-scraper-pro | https://github.com/georgekhananaev/google-reviews-scraper-pro | Maintained 2026, Python | Mine complaints/low ratings → concrete outreach hooks; incremental feed. |
| irfanalidv/trustpilot_scraper | https://github.com/irfanalidv/trustpilot_scraper | Small utility, Python | Cross-source reputation signal beyond Google. |

### Geo-dashboard + heatmap (the map UI)
| Repo | URL | Maturity | How Hermes reuses |
|---|---|---|---|
| visgl/deck.gl | https://github.com/visgl/deck.gl | Very mature, Uber/OpenJS, MIT | **Coverage map engine.** H3HexagonLayer/HexagonLayer bins prospect lat/lng → color=density found; empty cells=unexplored. GPU handles thousands+. Second translucent layer = "area swept" polygons. |
| visgl/react-map-gl | https://github.com/visgl/react-map-gl | Mature, MIT, TS | React `<Map>` over **MapLibre (no token)** basemap under deck.gl layers. Honors zero-paid-API. |
| keplergl/kepler.gl | https://github.com/keplergl/kepler.gl | Very mature, Uber, MIT | Embeddable React-Redux drop-in; OOTB heatmap/hexbin → fastest coverage-map MVP, then graduate to custom deck.gl. |

### CRM / lead-pipeline UI (the conveyor)
| Repo | URL | Maturity | How Hermes reuses |
|---|---|---|---|
| marmelab/atomic-crm | https://github.com/marmelab/atomic-crm | Mature, **MIT** (safe to fork), TS | Kanban deal pipeline = found→audited→ready conveyor; shadcn/ui + TanStack Query match Hermes UI; Supabase minimal backend. |
| twentyhq/twenty | https://github.com/twentyhq/twenty | ~50k★, YC S23, **AGPL** (note copyleft), TS | Table↔Kanban toggle + custom objects + workflow automation = ready-made stage model; GraphQL/REST to push leads in. |
| CodeRyderX/leadtracker | https://github.com/CodeRyderX/leadtracker | Small/early, TS | Copy the **dnd-kit** drag pattern for moving cards between columns w/o a CRM dependency. |
| krayin/laravel-crm | https://github.com/krayin/laravel-crm | 22k★, MIT, PHP/Vue | Fallback only — stack mismatch (PHP/Vue vs Hermes Python/React). Lower priority. |

### Data-table / filter UI (thousands of businesses)
| Repo | URL | Maturity | How Hermes reuses |
|---|---|---|---|
| openstatusHQ/data-table-filters | https://github.com/openstatusHQ/data-table-filters | Active reference impl, MIT, TS | **Near-exact match** for "thousands of businesses + many filters." Faceted filter chips → niche/size/missing-service. Lift components wholesale. |
| TanStack/table (+react-virtual) | https://github.com/tanstack/table | De-facto standard, MIT | Headless engine: column faceting = unique-value lists for filters; react-virtual = 10k+ rows, <100ms filter, no pagination. |

### MCPs / agents / skills / 24-7 + self-improving patterns
| Repo | URL | Maturity | How Hermes reuses |
|---|---|---|---|
| firecrawl/firecrawl-mcp-server | https://github.com/firecrawl/firecrawl-mcp-server | Very high (~130k★ parent) | Self-host scrape/crawl/extract MCP behind existing Hermes gateway. |
| exa-labs/exa-mcp-server | https://github.com/exa-labs/exa-mcp-server | High (top-2 research MCP) | Neural "find companies like X" prospect-expansion. **Paid — gate behind owner key.** |
| Inferensys/apollo-io-mcp | https://github.com/Inferensys/apollo-io-mcp | Most complete Apollo MCP | Enrichment-only (verified email/phone) for gaps. **Paid — gate strictly.** |
| assafelovic/gpt-researcher | https://github.com/assafelovic/gpt-researcher | Very high, top DeepResearch scorer | Port planner/executor + pluggable-retriever split into account-research subsystem; point LLM at local Ollama. |
| mayooear/ai-company-researcher | https://github.com/mayooear/ai-company-researcher | ~206★, **ARCHIVED Mar 2026** | Pattern reference only: LangGraph conditional routing + revision-count state + HITL → per-prospect research card. |
| (topic) Bricks / clay-alternative | https://github.com/topics/clay-alternative | Emerging, on-target | Fully-local Clay-style waterfall enrichment (CSV-in→enriched-out). Best guardrail fit. |
| sentient-agi/EvoSkill | https://github.com/sentient-agi/EvoSkill | New, multi-runtime (Claude Code) | Failure-trajectory→skill synthesis feeds Hermes F.4 auto-skill-forge; validate via hermes-skill-forge-runner. |
| BerriAI/self-improving-agent | https://github.com/BerriAI/self-improving-agent | New, minimal | Propose-diff→approve→draft-PR; **targets claude-agent-sdk** → maps to owner-confirmation guardrail w/ near-zero glue. |
| swarmclawai/swarmclaw | https://github.com/swarmclawai/swarmclaw | Active | Borrow cron-drift-repair logic for daemon scheduler/watchdog. |
| punkpeye/awesome-mcp-servers | https://github.com/punkpeye/awesome-mcp-servers | Canonical discovery feed | Recurring scan source for hermes-mcp-survey skill (+ modelcontextprotocol/servers). |

---

## 4. The Hermes differentiation (the moat)

1. **Gap-reverse-filter = the product.** Competitors filter for what a company HAS (tech, intent). Hermes filters for what they LACK (no site, no Google profile, weak presence) = positive sell-trigger. Inverts BuiltWith/Wappalyzer. Output isn't "here are leads" but "here is each prospect's weakness + the agentic service to sell."
2. **$0 / zero-paid-API self-hosted.** Whole category is credit-metered ($15k-25k/yr down to per-phone credits). Hermes = free public sources + own VM LinkedIn session = near-zero marginal cost as a *selling point*.
3. **Agentic end-to-end closed loop.** discover→gap-audit→pitch→**fulfill** (Geronimo agency + Vuecra sites build the fix autonomously). AI-SDRs only outreach; BR tools only data; audit tools only score. Hermes finds the gap AND delivers the fix.
4. **Cuiabá / BR-native by default.** CNPJ/CNAE/QSA + Maps long-tail of owner-operated locals absent from every DB + PT-BR + WhatsApp channel. All incumbents US/EU-centric, thin/paid on BR.
5. **Owns the channels end-to-end** (LinkedIn stealth + email + WhatsApp on VM) — no tool-stitching, no per-seat sequencer fee, no vendor data-sharing.
6. **24/7 self-improving Brain** (Brain.decide() F.6 + F.4 auto-skill-forge w/ sandbox + golden-case gating). Single-operator command-center, not seat-priced enterprise SaaS.
7. **"Unexplored zones" as a first-class concept** — no CRM/map repo surfaces where the agent has NOT swept. Hermes renders swept-vs-unswept territory to drive the next crawl (coverage feedback loop). Stage gating is **computed** (missing-service detection + audit score), not human-dragged.

---

## 5. Backend + UI/UX shopping list (consolidated)

### Backend stack to adopt/reuse
- **Discovery worker**: gosom/google-maps-scraper wrapped as Hermes MCP/CLI tool (uses its built-in Claude Code skill + REST API + dedup'd LeadsDB).
- **BR data spine (build once)**: rictom/cnpj-sqlite (or CNPJ-full) → local SQLite; JOIN gmaps → official CNAE/legal name/address; turicas/socios-brasil → owner name.
- **Website enrichment**: crawl4ai (primary) / ScrapeGraphAI (resilient fallback), driven by existing local Ollama (qwen2.5:3b + nomic) → structured JSON for ICP scoring.
- **Coverage supplement**: osmnx `features_from_place` for OSM POIs; dedup by coordinate vs gmaps.
- **Intent signals**: Google Ads Transparency + Meta Ad Library + google-reviews-scraper-pro fused into one Brain qualification score.
- **Enrichment orchestration model**: local Clay-style waterfall (Bricks pattern) — try free CNPJ → BrasilAPI/ReceitaWS → Maps scrape → only then any owner-keyed paid MCP.
- **Account-research subsystem**: port gpt-researcher planner/executor + ai-company-researcher LangGraph schema/HITL pattern.
- **MCP layer**: wrap self-hosted Firecrawl + (gated) Exa/Apollo/Hunter behind existing Hermes gateway; feed awesome-mcp-servers into hermes-mcp-survey.
- **Daemon robustness**: SwarmClaw cron-drift-repair; Autobot "cron = message on same bus" unification.
- **Validation**: Speedio-style active-number check before WhatsApp/email send to protect deliverability.

### UI/UX components + patterns to adopt/reuse
- **One dashboard, one design system**: shadcn/ui + Tailwind (matches Hermes F.2.4 tokens.css/light.css) so map + table + conveyor share components.
- **Coverage map**: react-map-gl + MapLibre (no token) + deck.gl H3HexagonLayer (found density) + translucent swept-polygon layer (unexplored zones). Prototype with kepler.gl first.
- **Lead conveyor table**: lift openstatusHQ/data-table-filters; TanStack column faceting → niche/size/missing-service chips; react-virtual for thousands of rows.
- **Conveyor stages**: Atomic CRM (MIT) Kanban for found→audited→ready, or Twenty table↔Kanban toggle; dnd-kit drag from LeadTracker.
- **Patterns from commercial tools**: dense filterable table as home; waterfall enrichment cascade visualization; per-cell confidence badges; score-reordered "work next" queue; signal timeline (→ daemon.* WS events); inline enrich overlay; "digital worker" persona + activity dashboard; auto-generated gap-audit artifact; saved-search auto-refresh lists.
- **Modular IA** (Instantly pattern): Prospects | Sequences | Replies | Deals as distinct panels.

### Build vs reuse vs proprietary
- **Reuse (lift wholesale)**: data-table-filters, deck.gl/react-map-gl/kepler.gl, Atomic CRM Kanban, dnd-kit pattern, CNPJ loaders, gmaps-scraper, crawl4ai, ad/review scrapers.
- **Port as pattern (don't fork)**: OpenOutreach state machine, gpt-researcher, ai-company-researcher (archived), EvoSkill, BerriAI self-improving loop, SwarmClaw cron repair.
- **Proprietary / keep Hermes-owned (the moat)**: LinkedIn stealth stack (stealth/human/limiter/cooldown on Patchright), Brain decision + safety + golden-case harness, gap-reverse-filter scoring, "unexplored zones" coverage feedback loop, Geronimo+Vuecra fulfillment handoff, BR-local ICP scoring + PT-BR messaging, MCP gateway + daemon + 3-scope agentmemory.

---

## 6. Open questions for owner

1. **AGPL vs MIT for the conveyor**: Twenty (AGPL, richer, table↔Kanban + workflows) vs Atomic CRM (MIT, safe to embed). If Hermes UI ships as a product, AGPL copyleft is a real constraint. Default recommendation: Atomic CRM. Confirm?
2. **Paid MCP exceptions**: any scenario where you'd approve owner-keyed Apollo/Hunter/Exa for verified email/phone gaps, or is it strictly $0 forever? (Affects enrichment coverage ceiling.)
3. **Gap-audit scope**: should the digital-presence audit measure AI-visibility (ChatGPT/Claude/Perplexity) like MyWebAudit, or stay on classic signals (no-site / outdated / no-Google-profile / weak SEO)?
4. **Discovery source priority**: gmaps-scraper carries Google anti-bot risk on the VM. Lead with CNPJ+OSM (zero ban) and use gmaps only for phone/website/reviews gaps, or run gmaps as primary?
5. **"Digital worker" persona**: name + framing for the Hermes pipeline persona in the dashboard (perceived-value lever)?
6. **Map basemap**: confirm MapLibre (no token, free) over Mapbox — any need for Mapbox-only styles?
7. **Conveyor backend**: stand up Supabase (Atomic CRM default) or push conveyor state into the existing Hermes prospects DB? (Avoids a second datastore.)
