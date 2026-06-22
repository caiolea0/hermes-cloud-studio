# Hermes 2.0 — Candidate Layers Catalog
**Sealed**: 2026-06-21
**Purpose**: wide menu of possible Hermes layers for the owner to FILTER. A buffet, not a plan.

> Built from 15 research agents + 4 cluster syntheses (discover-intel, diagnose-prescribe, transform-deliver, system-ux-emerging). Anchored to Caio's reality: solo founder, Cuiaba/Brazil, HERMES (find+qualify locals) -> GERONIMO (40+ agents, makes companies 24/7 agentic) -> VUECRA (auto-builds sites). Goal: turn the MAX number of businesses agentic, lead Brazil's agentic market 2026-2027. Constraints: $0-first, self-hosted Contabo, 24/7 self-improving. Signature: gap-reverse-filter (find businesses MISSING a service to sell).

---

## 0. How to read this (plain language, no analogies)

This file is a **menu**, not a roadmap. Nothing here is committed. Every row is one possible "layer" Hermes could grow. Your job is to **cross out what you don't want** and keep the few that matter, then scope ONE focused workflow around the survivors.

Each layer has 6 fields:
- **What** — the thing it does, in plain words.
- **Helps goal** — why it moves the needle on "turn max businesses agentic / lead Brazil".
- **Effort** — rough build size: `low` (days), `medium` (1-2 weeks), `high` (weeks, real architecture).
- **Reuse** — what you ALREADY have that this extends, so you don't build from zero.
- **Tag** — `QUICK-WIN` (cheap + high payoff now), `BIG-BET` (expensive but transformational), `FUTURE` (later / emerging).

Two honest warnings:
1. **Most "industry" tools that inspired these are paid SaaS.** Your edge is replicating them self-hosted on Contabo for $0. Every layer below is buildable free (BrasilAPI, ReceitaWS, OSM/Overpass, Wappalyzer-style OSS, H3, PostGIS, MapLibre, n8n, Langfuse OSS, local Ollama).
2. **Don't pick everything.** A solo founder who builds 10 layers half-way loses to one who ships 3 fully. The catalog is generous so you can SEE the whole board — but the win is in the filter (section 6).

---

## 1. Workflow map (the full loop, with layers placed)

The dominant 2026 pattern across all research: it's ONE closed loop, not separate tools. The same artifact (the **gap report**) should flow through every stage so you never re-enter context.

```
                          ┌─────────────────────────────────────────────────┐
                          │                  HERMES 2.0 LOOP                  │
                          └─────────────────────────────────────────────────┘

 [1] DISCOVER ───► [2] MARKET-INTEL ───► [3] DIAGNOSE ───► [4] PRESCRIBE ───► [5] PROVE
  find every biz     where's the         score readiness    pick the          gap report +
  in territory       opportunity         + gap-reverse      playbook/SKU      demo + proposal
  (CNPJ, OSM,        (heatmap, TAM,      (what's MISSING)   per gap            (audit-as-offer)
   gap scanner,       penetration)              │                                   │
   signals)                                     │                                   ▼
       ▲                                        │                              [6] DELIVER
       │                                        │                              GERONIMO agents
       │                                        │                              + VUECRA build
       │                                        │                              (orchestrate)
       │                                        │                                   │
       │                                        ▼                                   ▼
 [8] LEARN ◄───────────────────────────── [10] AUTHORITY ◄───────────── [7] RETAIN/UPSELL
  self-improve:       Command Center /     inbound: be the              ROI proof + QBR
  re-weight which     Mission Control      visible agentic              + lifecycle CRM
  gaps actually sell  (spans ALL stages)   leader in Cuiaba            (stop churn)
```

**Layers placed by stage:**

| Stage | Layers living here |
|---|---|
| **1. Discovery** | CNPJ Firmographic Foundation; Digital/Agentic Gap-Depth Scanner; Hiring-Surge Detector; New-Location Sentinel; Ad-Activity Monitor; Ownership-Change Detector; Review-Velocity Watcher |
| **2. Market-Intelligence** | Niche×Region Opportunity Heatmap; Competitive-Saturation Layer; Penetration/Whitespace Conquest Map; Territory Coverage Engine (H3 sweep); Living Scored Database |
| **3. Diagnose/Readiness** | External Signal Harvester; Per-Process Automatability Map; Gap-Reverse-Filter Scorer; 5-Stage Maturity Ladder; Composite Signal Scorer + Decay Engine |
| **4. Prescribe/Playbooks** | Productized Offer Ladder / Auto-Proposal; Signal-to-SKU router; Versioned Template Library (delivery side) |
| **5. Prove/Demo-Proposal** | Gap Report / Audit-as-Offer Engine; Gap-to-Spec Audit Engine; Live demo generator |
| **6. Deliver/Orchestrate** | Onboarding Automation (handoff); Multi-Tenant Provisioning; Self-Hosted Orchestration+Observability; Shared Skills/Capabilities Layer; Pipeline/CRM Lifecycle State Machine |
| **7. Retain/Upsell** | Client ROI Proof Layer + QBR Generator; At-Risk Flagging; Upsell trigger |
| **8. Learn/Self-improve** | Continuous Re-Score Loop; Self-Improvement Eval+Memory Loop; Cost/FinOps Governance |
| **9. Authority/Inbound** | AI-Search Visibility Audit (doubles as offer); Public conquest/leaderboard; Case-study auto-gen |
| **10. System/UX (spans all)** | Command Center / Mission Control; Live Coverage Map UI; Conquest Feed; Guardrails/HITL Gate |

---

## 2. Catalog by stage

### Stage 1 — DISCOVERY (find every business + the raw gap signals)

#### CNPJ Firmographic Foundation `BIG-BET`
- **What**: Ingest the full Brazilian company registry per region via BrasilAPI (primary) + ReceitaWS (fallback): CNAE activity codes, status (ativa/baixada), opening date, partners (QSA), address, phone, email, declared capital. Geocode to Cuiaba neighborhoods.
- **Helps goal**: Defines the TOTAL addressable set of MT businesses by niche — the denominator for penetration %, TAM, and conquest tracking. Opening-date deltas catch brand-new greenfield CNPJs before any competitor.
- **Effort**: medium
- **Reuse**: Free, no-account public APIs. Pairs with existing prospect DB schema. Hermes already does top-funnel finding; this is the universe behind it.

#### Digital/Agentic Gap-Depth Scanner (gap-reverse-filter core) `QUICK-WIN`
- **What**: Per-business multi-signal scan of what's MISSING vs the agentic baseline: no website, outdated CMS, no online booking, no chatbot/WhatsApp-API, no analytics, no email capture, phone-only contact, slow/non-responsive site. Outputs a "missing-service vector" mapped 1:1 to GERONIMO/VUECRA SKUs. Re-scans periodically.
- **Helps goal**: Caio's signature operationalized as a standing layer. Converts output from "a prospect" into "a prospect + exact thing to sell + why". Highest direct ROI to the agentic goal.
- **Effort**: medium
- **Reuse**: Wappalyzer-style fingerprinting is OSS/self-hostable ($0, ~90% coverage). Extends the crawl Hermes already does. Google Places data already in pipeline.

#### Review-Velocity & Sentiment Watcher (Google Business Profile) `QUICK-WIN`
- **What**: Poll each business's GBP listing; track review COUNT delta, velocity, star trend, owner reply-rate. Flag: positive spike = growing/overwhelmed = ripe; negative cluster = reputation pain; reviews growing + owner never replies = sell auto-review-response agent.
- **Helps goal**: THE primary local-SMB intent signal. Growth + zero replies is a textbook gap-reverse hit (demand proven + service missing). Catches businesses when they're most likely to say yes.
- **Effort**: medium
- **Reuse**: GBP/Maps already a core data source. Add a dated-snapshot diff loop + `review_snapshots` table.

#### Hiring-Surge Detector `FUTURE`
- **What**: Watch "now hiring" on BR job boards (Catho, Indeed BR, Vagas, Gupy) + the business's own social/GBP posts. Role tells you the pain (hiring 3 atendentes = drowning in calls = sell 24/7 agent).
- **Helps goal**: Top-tier free buying signal — proves budget is moving NOW. Hiring + new-leader = 3x meeting acceptance in 90-day window.
- **Effort**: medium
- **Reuse**: Pure scraping of public BR boards + channels Hermes already monitors.

#### New-Location / Expansion Sentinel `FUTURE`
- **What**: Detect new unit/branch: new GBP listing same brand, hours/address changes, Cuiaba prefeitura alvara filings, "nova unidade" posts.
- **Helps goal**: Expansion = capital + need to standardize ops across sites = ideal GERONIMO pitch (one agentic layer serving N locations).
- **Effort**: medium
- **Reuse**: GBP diffing (already needed for review layer) + Cuiaba open-data scraper. Geo-scoped so volume is tractable.

#### Ad-Activity / Spend-Change Monitor `FUTURE`
- **What**: Check Meta Ad Library (free/public) + Google Ads transparency: running ads? just started/ramped? SMB spending on ads but with no booking/landing/chat behind it = leaking clicks = gap.
- **Helps goal**: Reveals businesses that ALREADY decided to invest in growth (budget confirmed) + exposes "spending money but doing it wrong" pitch.
- **Effort**: medium
- **Reuse**: Meta Ad Library fully public/scriptable. New monitor into the signal store.

#### Ownership / Leadership-Change Detector `QUICK-WIN`
- **What**: Detect new owner/manager: LinkedIn role changes, GBP "under new management", Junta Comercial updates, local news. New deciders re-evaluate everything in first 90-120 days.
- **Helps goal**: New owner = clean slate + active vendor evaluation = 10x more likely to adopt. Rare for SMB but very high-conversion; cheap passive watch.
- **Effort**: low
- **Reuse**: Mostly LinkedIn + GBP diffing Hermes infra already touches. Passive flag, not heavy crawler.

---

### Stage 2 — MARKET-INTELLIGENCE (where's the opportunity)

#### Niche × Region Opportunity Heatmap (Market Opportunity Score) `BIG-BET`
- **What**: Per CNAE-niche × neighborhood cell, compute composite = (density × demand × dispersity) / competitive saturation. Render heatmap; flag "Blue Ocean" cells (high demand, low competition).
- **Helps goal**: Answers "where is the biggest agentic opportunity in Cuiaba". Aim Hermes at high-density under-served pockets first; avoid crowded zones where "first agentic" isn't defensible.
- **Effort**: medium
- **Reuse**: Rides existing dashboard (F.2.4 tokens; MapLibre+deck.gl H3HexagonLayer, all $0). Sits on CNPJ + saturation layers; mostly aggregation.

#### Competitive-Saturation & Category-Dispersity Layer `QUICK-WIN`
- **What**: Per niche × region, measure competitor count + concentration. Separate saturated zones (avoid) from fragmented under-served zones (easy entry).
- **Helps goal**: Refines the heatmap from raw density to TRUE opportunity; flags defensible "first-agentic" niches.
- **Effort**: low
- **Reuse**: Pure derivation from CNPJ+OSM counts already collected. Minimal new data.

#### Penetration & Whitespace Conquest Map `BIG-BET`
- **What**: Track per niche × region what fraction of the addressable CNPJ set is already-agentic / in-pipeline / virgin, overlaid on the heatmap.
- **Helps goal**: Converts the abstract "lead Brazil 2026-2027" into a measurable conquest %. Reuses Geronimo conversion-state joined onto the CNPJ denominator; every win sharpens the next target.
- **Effort**: medium
- **Reuse**: Sits on CNPJ denominator + scored DB; needs Geronimo conversion-state join.

#### Territory Coverage Engine (H3 hex grid + frontier sweep) `BIG-BET`
- **What**: Tile Cuiaba->MT->Brazil into Uber-H3 hexes, each with a lifecycle (unexplored -> in_progress -> swept -> re-sweep-due via TTL decay). "Swept" = DISCOVERY-COMPLETENESS (Overpass/OSM business count vs Hermes-found count), NOT visitation. Boustrophedon/expanding-ring daemon sweeps outward from Cuiaba, guaranteeing 100% eventual coverage with no backtracking.
- **Helps goal**: Turns "city to country" into a literal self-paced 24/7 algorithm. The map of found/swept/unexplored zones Caio explicitly asked for.
- **Effort**: high
- **Reuse**: All $0 self-hostable (h3-py/h3-js, PostGIS, MapLibre+deck.gl, Overpass). Decay mirrors agentmemory 5%/day precedent.

#### Living Scored Database / Continuous Re-Score `BIG-BET`
- **What**: Stop treating the prospect list as static. Score the ENTIRE Cuiaba market against closed-won patterns from Geronimo/Vuecra wins; assign propensity tiers; re-score continuously as state changes (new biz, adds site, hires, fires staff = fresh gap).
- **Helps goal**: Hermes always works the highest-propensity untouched accounts. The model learns which gaps actually sell in Cuiaba = compounding lead. Matches the 24/7 constraint.
- **Effort**: high
- **Reuse**: Feedback loop reuses Geronimo close data + agentmemory self-improve cron. Re-runs the gap scanner on a Contabo scheduler.

---

### Stage 3 — DIAGNOSE / READINESS (score how agentic-able a business is)

#### External Signal Harvester (cold readiness fingerprint) `BIG-BET`
- **What**: Score a business's automation maturity from OUTSIDE-only signals with zero target cooperation: site present+responsive, booking widget, live-chat/chatbot, WhatsApp Business+catalog, contact-form vs phone-only, social cadence, review count+reply-rate+latency, tech fingerprint (CMS/pixel/CRM/booking SaaS/payment links), hours vs "24/7 reachable". Emits a 0-100 readiness score.
- **Helps goal**: THE engine that turns Hermes from prospect-finder into perfect diagnostic tool. Detects the EXACT missing surface (no booking->scheduling agent; no chat->attendance agent), handing GERONIMO a pre-diagnosed lead.
- **Effort**: high
- **Reuse**: Extends existing crawl with a signal-extraction pass. Wappalyzer-style OSS. Places data in pipeline. $0 on Contabo.

#### Per-Process Automatability Map `BIG-BET`
- **What**: Decompose each target into the 5 canonical processes (attendance, sales, post-sale, scheduling, billing); score each on automatability = f(volume, repetitiveness, structured-data, decision-criteria, revenue-leak). Per process: state, score 0-100, estimated ROI (hours/yr + revenue), recommended Geronimo agent. Pre-rank by sellable ROI.
- **Helps goal**: Directly answers "which processes can become agentic" + "how much of a business can become agentic". Turns "is behind" into a line-item shopping list; lets the 40+ agents self-route. Only 21% of enterprises are AI-ready, <1% score >50/100 = enormous gap inventory.
- **Effort**: high
- **Reuse**: Maps 1:1 onto Geronimo 40+ agent catalog. ROI benchmarks (scheduling ~200h/yr, lead-response 4h->15min, billing 45d->18d) hardcoded as priors.

#### Gap-Reverse-Filter Scorer (the signature) `QUICK-WIN`
- **What**: Invert the readiness score — rank businesses NOT by how ready they are but by SIZE-OF-GAP on a sellable process. Critical-bottleneck rule: strong overall but scoring 1 on one pillar = prime target. Filter for has-revenue AND has-digital-presence AND missing >=1 high-ROI automatable process. Output a prioritized sell-queue with reason + expected deal value + chosen SKU.
- **Helps goal**: Caio's named signature shipped as a final ranker. What makes Hermes "beyond just finding prospects" — hands GERONIMO a ranked, reasoned, product-matched target list.
- **Effort**: low-medium
- **Reuse**: Pure scoring logic over Harvester + Automatability outputs. No new data. Slots into existing qualification stage.

#### 5-Stage Maturity Ladder + Composite Readiness Score `QUICK-WIN`
- **What**: Roll signals + process map into one canonical stage (Stage1 Manual/Reactive -> Stage5 Autonomous/Predictive) + numeric composite. Defines the "agentic-ready" threshold; computes how MUCH of a business can become agentic (% processes with automatability >=70).
- **Helps goal**: The headline metric Caio asked for + a market-wide leaderboard to prove Brazil-2026 leadership. Stage label drives the GERONIMO playbook.
- **Effort**: low
- **Reuse**: Pure presentation/aggregation over Harvester + Automatability + Gap-Filter. No new collection.

#### Composite Signal Scorer + Decay Engine (intent brain) `BIG-BET`
- **What**: Central service: every discovery/signal layer writes dated events to one store. Scorer = sum(signal_strength × fit_weight) with time-decay (15-20%/week, auto-expire stale) MULTIPLIED by gap-fit (only count businesses MISSING the service we sell). On threshold-cross inside an active window, emit a qualified trigger to GERONIMO with SKU + evidence + timing reason. Logs which triggers closed; re-weights.
- **Helps goal**: Without it, the cheap monitor layers are noise. Stacking 2-3 signals jumps reply rate from ~1-5% to 25-45%. Decay ensures outreach fires inside the 7-60d window (first vendor to respond wins 35-50%). The fit-multiplier hard-wires gap-reverse-filter. The win-rate loop is the self-improving moat.
- **Effort**: high
- **Reuse**: Builds on prospect DB + agentmemory decay patterns. Scoring math cheap, no ML needed initially. Dated-event store replaces static is_prospect flag.

---

### Stage 4 — PRESCRIBE / PLAYBOOKS (pick the fix per gap)

#### Signal-to-SKU Router `QUICK-WIN`
- **What**: Deterministic mapping: no website -> VUECRA; no booking/chatbot/24-7 channel -> GERONIMO agent; ad spend + leaky funnel -> VUECRA landing + GERONIMO agent; reviews growing + no owner replies -> review-response agent. Hermes emits the chosen SKU + pitch angle automatically.
- **Helps goal**: Signal-to-product is deterministic for this ecosystem — exploit it. GERONIMO outreach starts already-personalized (the 15-25% reply driver vs 3-5% cold).
- **Effort**: low
- **Reuse**: Pure rules over gap-scanner output. No new data.

#### Productized Offer Ladder / Auto-Proposal `QUICK-WIN`
- **What**: Codified tiered offers (audit -> starter site/automation -> full agentic transformation -> managed retainer) with hybrid pricing (base 40-60% of expected monthly + outcome incentive). Hermes auto-assembles a scoped proposal + price from the gap report per prospect+vertical.
- **Helps goal**: Standardized offers make delivery repeatable; each client cheaper than the last (3rd client = half the time of 1st). Auto-proposal collapses pitch->close, key for converting MAX businesses solo.
- **Effort**: medium
- **Reuse**: Gap Report + Automatability output feeds the proposal. Mostly templating + pricing logic.

#### Versioned Automation/Agent Template Library `BIG-BET`
- **What**: Governed, versioned catalog of reusable agent bundles, workflows, prompts, tools ("templates = the junior team") that Geronimo clones per client. Each = a productized transformation (lead-capture, WhatsApp triage, review-collector, content engine). Every successful build auto-promotes into the library.
- **Helps goal**: #1 documented solo-founder scaling lever: Nth client costs near-zero. Without it, headcount scales with clients and market leadership is impossible solo.
- **Effort**: medium
- **Reuse**: n8n self-host (7000+ free community AI workflows) + Agent SDK skills. Generalizes existing hermes-skill-forge-runner (sandbox/promote/quarantine) into a cross-ecosystem registry.

---

### Stage 5 — PROVE / DEMO-PROPOSAL (turn diagnosis into a closeable artifact)

#### Gap Report / Audit-as-Offer Engine `QUICK-WIN`
- **What**: Auto-generate a per-prospect evidence report proving the gap (AI-search invisibility, missing/weak site, no booking/chat, no automation, inconsistent NAP, outdated tech). One artifact = the cold-outreach hook + the sales pitch + the machine-readable delivery spec for Geronimo/Vuecra.
- **Helps goal**: Highest-leverage layer in the whole catalog. Turns "we found you're missing X" from a claim into PROOF (the highest-converting AAA pitch). Same spine flows find->prove->pitch->deliver with zero handoff loss. Rides the 88%-no-AI-strategy / 1.2%-recommended / 45%-consumers-use-AI gap.
- **Effort**: medium
- **Reuse**: Hermes already finds+qualifies + computes the missing-service signal. Gap-depth/tech scanners feed it. Insites/Origami audit blueprints to mirror. Local Ollama for narrative, $0.

#### Gap-to-Spec Audit Engine (delivery-side) `QUICK-WIN`
- **What**: Deeper post-qualification audit converting detected MISSING services into a concrete prioritized GERONIMO build-spec: which agents/automations, expected ROI, effort, tier. Output = machine-readable roadmap + client-facing audit.
- **Helps goal**: Lets one founder scope at scale — the same "what's missing" engine becomes auto-scoping telling Geronimo exactly what to build, eliminating manual discovery.
- **Effort**: medium
- **Reuse**: Extends Gap Report + Automatability map. Planner->Generator->Evaluator (Agent SDK) directly buildable.

#### Live Demo Generator `FUTURE`
- **What**: For a high-fit prospect, auto-spin a throwaway demo of the fix (a sample VUECRA landing, a working WhatsApp triage agent answering as their business) attached to the gap report.
- **Helps goal**: "Show, don't tell" — a working demo of THEIR automation converts far above a deck. Strongest possible proof.
- **Effort**: high
- **Reuse**: Vuecra already auto-builds sites; needs a sandboxed per-demo trigger + teardown TTL.

---

### Stage 6 — DELIVER / ORCHESTRATE (build + run the client's agentic machine)

#### Onboarding Automation (Hermes->Geronimo->Vuecra handoff) `QUICK-WIN`
- **What**: On deal-won: collect client assets/access, validate vs requirements checklist, spin up isolated delivery workspace, route gap-spec to the right Geronimo agents / trigger Vuecra build, send SLA-risk reminders.
- **Helps goal**: Onboarding gaps cause 40% of at-risk churn in the first 90 days. Automating the handoff makes the ecosystem flow end-to-end and lets one founder absorb many simultaneous clients.
- **Effort**: medium
- **Reuse**: Lifecycle state machine + template library + shared skills provide the rails. Vuecra needs only a trigger contract.

#### Pipeline/CRM + Lifecycle State Machine `BIG-BET`
- **What**: Unified record per business carried through: found -> qualified -> gap-audited -> pitched -> won -> onboarding -> delivering -> live/retained -> at-risk. One source of truth with auto-handoffs between Hermes/Geronimo/Vuecra, stage SLAs, auto-routing.
- **Helps goal**: This is what CONVERTS found-businesses into RETAINED agentic companies — the stated goal. SLA risk flags close the onboarding gaps that cause 40% of churn.
- **Effort**: medium
- **Reuse**: Hermes already tracks prospects/sequences/replies/deals (cobaia-status). Extend prospect DB into full-lifecycle CRM.

#### Multi-Tenant Provisioning & Isolation `BIG-BET`
- **What**: One-command provisioning that clones a template bundle into an isolated per-client tenant on Contabo (own namespace/DB schema/credentials/runtime), with Hermes as master control plane; each client gets isolated access.
- **Helps goal**: Required to run MANY transformations on one $0 box without cross-client leakage. The operational backbone for volume — must be architected early (retrofitting isolation after clients exist is painful).
- **Effort**: high
- **Reuse**: Docker-per-client (agentbot OSS pattern), Postgres schema-per-tenant, n8n multi-instance. All self-hostable.

#### Self-Hosted Orchestration + Observability (Agent-Ops) `BIG-BET`
- **What**: Run-and-watch layer: orchestrate each client's agents (scheduling, state, retries, recovery) + full observability (traces, latency p50/p99, cost, error rates, guardrail checks) with alerts when a client automation breaks.
- **Helps goal**: 24/7 self-improving requires knowing when client agents fail and auto-recovering BEFORE the client notices. Per-tenant traces of which templates win/fail FEED the self-improvement loop. A silently-broken automation = churn.
- **Effort**: medium
- **Reuse**: Langfuse OSS + OpenTelemetry, both self-hostable on Contabo. No lock-in.

#### Shared Skills/Capabilities Layer `BIG-BET`
- **What**: Centralized typed-skill library (sendEmail, generateImage, searchMaps, runWorkflow, scrapeSite, draftSequence, buildPage) that ALL agents across Hermes/Geronimo/Vuecra pull from. Single-point updates propagate to every agent.
- **Helps goal**: With 40+ agents, duplicated integrations = unmaintainable. Change once, every agent benefits — the maintainability keystone for a large self-improving fleet run by one person.
- **Effort**: medium
- **Reuse**: Stack already thinks in skills (forge-sdk skill runner, hermes-skill-forge-runner). Generalize into a cross-ecosystem registry.

---

### Stage 7 — RETAIN / UPSELL (stop churn, grow accounts — the profit engine)

#### Client ROI Proof Layer + QBR Generator `QUICK-WIN`
- **What**: Per-client dashboard quantifying delivered value (leads captured, hours saved, replies handled, revenue influenced, AI-visibility before/after) + auto-generated QBR/retention narratives. Agent pulls tenant metrics via read-only MCP, drafts narrative, renders before/after view, ~20min human approval gate before send.
- **Helps goal**: 2026 is the ROI era — proof before clients reopen wallets (47% higher 90-day retention). Retention = the profit engine (maintenance retainer near-pure margin). Closes deliver->prove->upsell; shows transformation, not activity.
- **Effort**: medium
- **Reuse**: Hermes already computes channel hit-rates/pipeline metrics (cobaia-status) — repoint from internal-ops to per-client value proof. Agent SDK 5-stage pipeline documented.

#### At-Risk Flagging + Upsell Trigger `QUICK-WIN`
- **What**: Watch each live tenant for drop signals (usage decline, automation errors, lower ROI trend) and growth signals (new location, hiring, capacity strain) -> fire a retention alert or an upsell-the-next-tier trigger to Caio.
- **Helps goal**: Proactive retention beats reactive firefighting; upsell into existing accounts is the cheapest growth. Turns the lifecycle CRM into an active account-management brain.
- **Effort**: low
- **Reuse**: Reuses lifecycle CRM stages + the same signal watchers from Stage 1 (now pointed at clients, not prospects).

---

### Stage 8 — LEARN / SELF-IMPROVE (the 24/7 compounding edge)

#### Continuous Re-Score Loop `BIG-BET`
- **What**: Re-run the readiness fingerprint + gap scan on a 24/7 cadence so scores drift with reality (business adds booking -> drops off scheduling-gap queue; goes quiet -> fresh attendance-gap). Feed deal-outcome data back to re-weight automatability/ROI priors.
- **Helps goal**: Matches the 24/7 constraint; turns Hermes into a living radar. Outcome-feedback sharpens the gap-reverse-filter so it never pitches an already-closed gap = compounding lead.
- **Effort**: medium
- **Reuse**: Reuses the harvester on a Contabo cron. Outcome loop plugs into agentmemory lessons (confidence + 5%/day decay). $0.

#### Self-Improvement Eval + Memory Loop `BIG-BET`
- **What**: Closed feedback loop across the fleet: trace every agent run, score outcomes (reply rate, deal close, build quality), feed wins/losses back as evals + lessons so the 40+ agents AND the prospecting heuristics improve autonomously. Learns which gaps/verticals convert best in Cuiaba.
- **Helps goal**: The stated constraint is 24/7 self-improving. Without traces+evals you can't debug or improve agent behavior; with them the whole ecosystem compounds.
- **Effort**: high
- **Reuse**: AgentMemory already exists (lessons + insights + consolidate/reflect cron); hermes-skill-forge-runner already does dry-run->metrics->promote/quarantine. Wire fleet outcomes into that loop.

#### Cost / Resource Governance (FinOps for $0-first Contabo) `QUICK-WIN`
- **What**: Track token/compute/storage spend per agent, per client, per pipeline stage; rate-limit + fallback to cheaper/local models; budget caps with alerts.
- **Helps goal**: The hard constraint is $0-first. Without per-agent cost visibility a 40+ agent 24/7 fleet silently blows the budget; FinOps governance is what makes "lead the market" financially survivable solo.
- **Effort**: low
- **Reuse**: AgentMemory already self-hosted (Ollama local = near-zero marginal cost). Add a usage/cost meter + gateway routing layer.

---

### Stage 9 — AUTHORITY / INBOUND (become the visible agentic leader, pull deals in)

#### AI-Search Visibility Audit (doubles as offer) `QUICK-WIN`
- **What**: Per-business, test whether ChatGPT/Perplexity/Gemini recommend them for their category+city; score AI-search invisibility. The result IS a gap-report section AND a standalone offer ("you're invisible to AI search; here's the fix").
- **Helps goal**: 88% of local businesses have NO AI-search strategy, only 1.2% are recommended by AI, yet 45% of consumers now use AI to find local services (up from 6%). Massive, fresh, fear-inducing gap-reverse market.
- **Effort**: medium
- **Reuse**: Feeds the Gap Report engine directly. Cheap to run, high-emotion pitch.

#### Public Conquest / Leaderboard (inbound magnet) `FUTURE`
- **What**: A public-facing "agentic Cuiaba" tracker — how many businesses are now 24/7 agentic, by niche, with anonymized before/after. Position Caio/Geronimo as the obvious market leader.
- **Helps goal**: Authority pulls inbound (cheaper than outbound) and cements the "lead Brazil 2026-2027" narrative publicly. Self-reinforcing as conquest % grows.
- **Effort**: medium
- **Reuse**: Reads from Penetration/Whitespace Conquest Map. Vuecra builds the public page.

#### Case-Study Auto-Generator `FUTURE`
- **What**: On each retained win, auto-draft a before/after case study from the ROI proof layer (with client consent) for outreach + the public tracker.
- **Helps goal**: Social proof is the #1 conversion lever for SMB; auto-generating it removes the bottleneck that kills most solo case-study pipelines.
- **Effort**: low
- **Reuse**: Reads from Client ROI Proof Layer. Mostly templating (local Ollama).

---

### Stage 10 — SYSTEM / UX (spans every stage — how Caio actually operates it)

#### Command Center / Mission Control (goal-oriented) `BIG-BET`
- **What**: Single pane above Hermes+Geronimo+Vuecra where Caio manages by GOALS not terminals: Kanban of every prospect/deal/build/campaign as cards (queued/running/completed/needs-attention), live fleet status for 40+ agents, exception surfacing (failures bubble up instead of dying in logs), reprioritize without code, cron/event/webhook scheduling.
- **Helps goal**: THE single highest-leverage build. A solo founder can't run 40+ agents across 3 systems by reading logs. Goal-based mission control is the mechanism that lets one person operate at fleet scale — the literal "agency OS".
- **Effort**: high
- **Reuse**: Hermes already has dashboard + daemon + WS broadcast (F.2.3 dot-notation daemon.{subsystem_status,log_event,decision}; F.2.4 design system). Extend prospecting view to whole-agency view.

#### Live Coverage Map UI (choropleth hex + funnel pins + HUD) `QUICK-WIN`
- **What**: Single MapLibre/Leaflet view: H3 hex choropleth by coverage state (gray=unexplored, amber=in-progress, green=swept, blue=re-sweep-due) UNDER a pin layer colored by funnel stage. Zoom aggregates country->state->city->hex->business. HUD: coverage %, businesses found, % turned agentic, frontier size. Layer toggles.
- **Helps goal**: The exact "map of found businesses + swept areas + unexplored zones" Caio asked for — makes a 24/7 autonomous sweep legible and motivating at a glance.
- **Effort**: medium
- **Reuse**: MapLibre + deck.gl H3HexagonLayer + OSM tiles, all $0. Rides existing dashboard. Needs the Territory Coverage Engine behind it for full value.

#### Conquest Feed & Coverage Leaderboard `QUICK-WIN`
- **What**: Gamified activity stream + stats: "Cuiaba Centro 100% swept", "Varzea Grande +47 businesses found", "state coverage 12%->14% this week", fastest-converting segments.
- **Helps goal**: Keeps a solo founder oriented and the 40+ fleet accountable; turns abstract 24/7 progress into visible momentum reinforcing the lead-the-market narrative.
- **Effort**: low
- **Reuse**: Reads from coverage state + lifecycle CRM. Re-points SPOTIO/SalesRabbit leaderboard pattern from human reps to agents/territories.

#### Guardrails / Human-in-the-Loop Approval Gate `QUICK-WIN`
- **What**: Policy-as-code gate before irreversible/destructive actions (mass outreach, publishing a client site, spending, touching a client account): low-confidence or destructive intents require Caio's confirm; everything else runs autonomously. Audit log of every decision.
- **Helps goal**: Lets ONE founder safely delegate to 40+ autonomous agents touching real client businesses without blowing up a relationship — the trust foundation for scaling delegation.
- **Effort**: low
- **Reuse**: Already designed in Hermes Brain (brain/safety.py: destructive intents 100% requires_confirm, low_conf<0.5 -> confirm) + hermes-brain-test golden cases. Generalize the gate across Geronimo/Vuecra actions.

---

## 3. Top QUICK-WINS shortlist
Cheap, high-payoff, mostly logic/templating over data you'll already have. Ship these first.

1. **Gap Report / Audit-as-Offer Engine** — one artifact that is hook + pitch + delivery spec. The spine. (medium, but #1 payoff)
2. **Gap-Reverse-Filter Scorer** — Caio's signature as a final ranker; pure logic, no new data. Produces the reasoned, SKU-matched sell-queue. (low-medium)
3. **5-Stage Maturity Ladder + Composite Readiness Score** — the headline "how much of this business can become agentic %" metric + leaderboard; pure aggregation. (low)
4. **Signal-to-SKU Router + Productized Offer Ladder/Auto-Proposal** — auto-personalized outreach + auto-scoped proposal; collapses pitch->close. (low / medium)
5. **Digital/Agentic Gap-Depth Scanner** — the standing layer that feeds everything; Wappalyzer-style OSS, $0. (medium)

Honorable mentions: AI-Search Visibility Audit (fresh fear-pitch), Guardrails/HITL Gate (already half-built in Brain), Client ROI Proof Layer, FinOps Governance, Competitive-Saturation layer.

## 4. Top BIG-BETS shortlist
Expensive but transformational. Pick at MOST one or two to anchor the next focused workflow.

1. **Command Center / Mission Control** — the agency OS; the single highest-leverage build for a solo founder running 40+ agents across 3 systems.
2. **External Signal Harvester + Per-Process Automatability Map** — the deepest moat: zero-cooperation diagnosis at scale on $0 Contabo, turned into a line-item agentic shopping list mapped to the 40+ agents.
3. **Territory Coverage Engine (H3 sweep)** — turns "city to country" into a literal 24/7 algorithm with provable discovery-completeness; powers the coverage map.
4. **Living Scored Database + Continuous Re-Score / Self-Improvement Loop** — the compounding edge that learns which gaps actually sell in Cuiaba; satisfies the self-improving constraint.
5. **Self-Hosted Multi-Tenant Delivery + Observability** (provisioning + orchestration + shared skills) — the backbone that lets one founder run MANY client machines on one box and feeds the win/fail flywheel.

## 5. FUTURE / emerging bets
Real, but later — depend on earlier layers or carry more risk.

1. **Live Demo Generator** — auto-spin a working demo of THEIR automation attached to the gap report. Strongest proof, but needs Vuecra trigger + sandbox teardown maturity.
2. **Public Conquest / Authority Tracker + Case-Study Auto-Gen** — flip from outbound to inbound once conquest % and retained wins are real enough to show.
3. **Full signal-stack expansion** (Hiring-Surge, New-Location, Ad-Activity, Competitor-Goes-Digital FOMO trigger) — each cheap independent monitor; add as new layers into the signal store once the Composite Scorer brain exists.

---

## 6. Recommended FILTER (sharp questions to pick layers for the focused workflow)

Answer these to collapse the buffet into ONE scoped workflow:

1. **Pick the bottleneck.** Right now, what is actually limiting more-businesses-agentic: (a) not finding enough prospects, (b) not converting the ones found, (c) not delivering/retaining the ones won, or (d) you can't SEE/steer the whole thing? Your answer selects the stage (1-2 / 3-5 / 6-7 / 10).

2. **Spine first or breadth first?** Do you want the **Gap Report spine** (one artifact flowing find->prove->deliver) built end-to-end on a few verticals, OR wide discovery coverage (Territory + CNPJ + heatmap) across all of Cuiaba? You probably can't do both well next.

3. **One BIG-BET, max.** If you could only build ONE big-bet this quarter, is it the **Command Center** (operate everything), the **Diagnosis engine** (Harvester+Automatability, sell better), or the **Territory Coverage Engine** (find everything)? Cross out the other two for now.

4. **Does the layer need data you don't yet collect?** Any layer requiring signals you don't harvest yet is implicitly TWO builds (collector + consumer). Prefer layers that are pure logic over existing data for the first workflow.

5. **What's the single metric this workflow must move?** Conquest % (territory), qualified-sell-queue size (diagnosis), reply rate (signal/gap report), or retained-agentic-count (delivery/ROI)? One metric = one focused workflow.

6. **Manual-acceptable vs must-be-autonomous?** Which steps are you OK doing by hand for now (keeps scope small) vs which MUST run 24/7 unattended (raises effort)? Be honest — autonomy is where effort explodes.

7. **Reuse test.** For each surviving candidate: name the existing Hermes asset it extends. If you can't name one, it's probably a `FUTURE`, not a `next`.

8. **Demo or proof?** Is your closing bottleneck believability? If yes, prioritize **Gap Report + AI-Search Visibility Audit** (proof) over more discovery. If you already close what you pitch, prioritize finding/diagnosing more.
