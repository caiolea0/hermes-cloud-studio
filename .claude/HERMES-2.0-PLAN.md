# Hermes 2.0 — Strategic Re-scope + Migration Master Plan
**Sealed**: 2026-06-21

---

## 1. Executive Summary

**The pivot.** Hermes 1.x was a LinkedIn-cobaia-outreach machine — warmup, stealth automation, direct sends. Hermes 2.0 freezes all of that behind `FEATURE_LINKEDIN=off` and becomes a **multi-source, 24/7, $0-first lead-discovery + enrichment + market-intelligence brain**. Hermes 2.0 never sends outreach itself: it produces *golden lead records* and *market signals*, then hands off.

**Role in the ecosystem.** Hermes is the **top of the funnel**. It discovers + enriches + qualifies businesses (Cuiabá first) → pushes qualified leads to **Geronimo** (multi-agent agency execution: outreach, sales, support) → pushes site-ready briefs to **Vuecra** (autonomous site delivery). Hermes feeds; Geronimo and Vuecra execute.

**Top 5 to BUILD:**
1. Self-hosted **Overpass** (OSM) discovery backbone — Docker, Brazil extract, unlimited $0 24/7.
2. **CNPJ open-data** authority/enrichment layer (Receita Federal dumps → shared Postgres, Cuiabá subset).
3. **Own-website contact scraper** (curl_cffi → Patchright fallback) to fill OSM's contact gaps.
4. **Categorize + ICP + qualify** engine (local Ollama + PageSpeed Insights 0-100 needs-our-services score).
5. **Handoff layer** — Geronimo (NATS) + Vuecra (HI1/HI2 REST contract).

**Top 3 to FREEZE / remove:**
1. LinkedIn cobaia / warmup / stealth (Patchright-LI) — feature-flag OFF, code preserved, zero deletion.
2. Daemon **P0 COBAIA** + **P2 SEQUENCE-send** priorities — skipped when flag off.
3. Direct-outreach send paths (`api/cobaia.py`, `api/lab.py`, `dashboard/components/cobaia_*.js`) — hidden/gated. **Google Maps / Places dependency dropped** (breaks $0).

---

## 2. Hermes 2.0 Architecture

### 2.1 The Discovery Engine (data flow)

```
DISCOVER (multi-source)
   └─ Self-hosted Overpass (OSM) · CNPJ dumps · [later: Apple Maps cross-check]
        ↓
NORMALIZE → one Prospect schema + source_type
        ↓
DEDUP / MERGE → golden record (fuzzy match: name + address + phone + CNPJ)
        ↓
CATEGORIZE → CNAE → industry/sub-category + ICP match (local Ollama qwen2.5)
        ↓
ENRICH → CNPJ authority data (razão social, situação, sócios) + own-website scrape (phone/email/wa.me/social, schema.org first)
        ↓
AUDIT / SCORE → web_audit.py + PageSpeed Insights → 0-100 "needs-our-services" qualifier
        ↓
MARKET-ANALYZE → aggregate CNAE density + churn + new-registration velocity → market_signal events
        ↓
KNOWLEDGE-BASE → hermes prospects DB + agentmemory (golden records + signals)
        ↓
HANDOFF → qualified leads → Geronimo (NATS) · site-ready briefs → Vuecra (REST)
```

**Discovery is a PIPELINE, not a single source** (research consensus). No single free map source gives name+address+phone+website+reviews reliably for a mid-size Brazilian city. The Overpass + CNPJ + website trio is the engine.

### 2.2 24/7 Daemon Design (reuse `daemon/orchestrator.py`)

Keep the existing P0–P7 loop and `TaskCategory` enum. Re-map priorities:

| Priority | 1.x meaning | 2.0 meaning |
|---|---|---|
| P0 | COBAIA override | **FROZEN** when flag off (later: market-intel proactive trigger) |
| P1 | Replies | KEEP (inbound handling, if any) |
| P2 | Sequence steps (send) | **FROZEN** when flag off → becomes handoff push |
| P3 | Enrichment | **REPURPOSE**: CNPJ + website scrape |
| P4 | Discovery | **REPURPOSE**: multi-source (Overpass + CNPJ) |
| P5 | Audit | KEEP: scoring + PageSpeed qualifier |
| P6 | Scoring | KEEP; add **P6b MARKET-INTEL** |
| P7 | Reporting | KEEP → handoff push to Geronimo/Vuecra |

### 2.3 Subsystem Disposition (KEEP / PIVOT / FREEZE / BUILD-NEW)

| Subsystem | Path | Disposition | Notes |
|---|---|---|---|
| Dashboard shell + WS + cards | `dashboard/` | **KEEP** | Add Market-Intel page + Source-health panel; hide `cobaia_*.js` behind flag |
| Backend core | `server.py`, `core/state.py`, `core/models.py` | **KEEP** | Add `source_type` + cnpj fields |
| Pipeline runner | `core/pipeline.py` | **PIVOT** | Stage 1 → multi-source; rename outreach stage → handoff |
| Daemon orchestrator | `daemon/orchestrator.py` | **PIVOT** | Re-map priorities (table above) |
| Brain / intents | `api/brain.py`, `brain/intents.py` | **PIVOT** | Add `market_analysis`, `dedup_merge`, `handoff_decision`; `send_outreach` → `handoff_decision` |
| Gateway + MCP routing | `mcps/gateway/` | **KEEP** | Register new MCP servers behind it |
| Prospects DB + audit | `api/prospects.py`, `api/audit.py`, `scripts/web_audit.py` | **KEEP** | Extend score weighting + source tracking |
| Hunter enrichment MCP | `mcps/hunter/` | **KEEP** | Evolve into multi-source enricher facade |
| Prospects MCP + persistence | `mcps/hermes-prospects/`, `core/persistence.py` | **KEEP** | Golden-record storage |
| Observability | `core/observability.py` | **KEEP** | Extend for scraper/source health + per-source cost |
| Sequences framework | `api/sequences.py` | **PIVOT** | F6 node action → `geronimo_handoff` |
| Rate limiter | `linkedin/limiter.py` → `core/limiter.py` | **PIVOT** | Generalize to all channels + per-domain scrape limiter |
| Loops | `loops/sync.py` | **KEEP** | Add `multi_source_discovery_loop` |
| LinkedIn cobaia/warmup/stealth | `linkedin/`, `linkedin/lab/`, `api/cobaia.py`, `api/lab.py` | **FREEZE** | `FEATURE_LINKEDIN=off`; zero deletion; Patchright-LI stays VM-only |
| LinkedIn dashboard pages | `dashboard/components/cobaia_*.js` | **FREEZE** | Hidden behind flag |
| Multi-source scrapers | `scripts/discovery_overpass.py`, `scripts/enrich_cnpj.py`, `scripts/scrape_website.py` | **BUILD-NEW** | The engine |
| Business categorizer + ICP | `scripts/business_categorizer.py`, `api/icp.py` | **BUILD-NEW** | CNAE → industry/ICP (Ollama) |
| Market analyzer | `brain/market_analyzer.py` | **BUILD-NEW** | Rule-based first |
| Enrichment orchestrator | `core/enricher.py`, `api/enrichment.py` | **BUILD-NEW** | Unified multi-vendor facade |
| Geronimo handoff MCP | `mcps/hermes-geronimo/` | **BUILD-NEW** | POST /handoff + jobs table |
| Vuecra handoff (HI1/HI2) | `migrations/006_vuecra_stages.py`, `/api/vuecra/*` | **BUILD-NEW** | Schema + REST contract |
| Source dedup/tracking | `migrations/2026_07_multi_source_schema.sql` | **BUILD-NEW** | golden-record merge |
| Market-Intel dashboard | `dashboard/components/market_intelligence.js` | **BUILD-NEW** | Heat by category/region |

---

## 3. Free Lead-Source Shortlist (build order)

All sources **$0**, all legal. Cuiabá first (município code **5103403**, UF=MT).

| # | Source | Data yielded | Reliability | Legality | Effort | Build |
|---|---|---|---|---|---|---|
| 1 | **Self-hosted Overpass** (Docker `wiktorn/overpass-api` + Geofabrik `brazil-latest.osm.pbf` + minute diffs) | name, coords, category (shop/amenity/office/craft); when tagged: phone/website/hours/whatsapp/social | high (self-hosted) | ODbL — attribute on display | med (Docker + ~8GB DB) | **FIRST** |
| 2 | **Receita Federal CNPJ** (quarterly CSV dumps → shared Postgres, Cuiabá subset by município+CNAE) | razão social, nome fantasia, CNAE, full address, situação cadastral, data abertura, sócios (QSA) | high | gov open data; LGPD on partner PII | med-high (load filtered subset) | **SECOND** |
| 3 | **BrasilAPI / ReceitaWS** (no key, no auth) | per-lookup CNPJ validation + situação freshness on golden record | high | free wrappers; LGPD | low | alongside #2 |
| 4 | **Own-website scrape** (curl_cffi T1 static; Patchright T2 only if JS, VM-only) | phone, email, wa.me, og: social, schema.org JSON-LD (phone/email/address/aggregateRating) | medium | public pages, robots.txt, polite rate-limit; lower-risk than Google | med | **THIRD** |
| 5 | **Google PageSpeed Insights API** (free key, 25k/day, 240/min) | Perf/SEO/Accessibility/Best-Practices 0-100 + Core Web Vitals → anchors the qualifier score | high | official Google API | low | **H2-F4** |

**The $0 qualification pipeline.** One logged-out crawl (~3-10 pages) feeds tech-stack + contacts + social + schema.org. Parse **schema.org JSON-LD first** (often gives phone/email/address + aggregateRating before scraping). Anchor the **0-100 "needs-our-services" score** on PageSpeed: no website / parked / non-HTTPS +30; PSI Perf<50 +15, SEO<70 +10, A11y<70 +5; not mobile-responsive +10; no schema.org / no rating +10; weak social +10; reviews <4.0 or <10 +10; stale site (Wayback no change 2+yr) +10; DIY/outdated tech +10. **Higher = hotter lead for Vuecra.** Weight high-reliability free signals (PSI, on-site tech, schema, Overpass) heavily; treat fragile sources as low-confidence bonus so a broken source never corrupts the score.

**DEFER / AVOID:** Google Maps scraping (breaks $0 — needs paid proxies — + Google ToS + civil-suit risk for resold leads); Bing/Azure Maps (retired 2025); Foursquare/Overture bulk parquet (good but heavier ingest — phase-2 enrichment); Apple Maps Server API (free 25k/day but ToS caching/display limits — optional cross-check only); Nominatim (geocoding gap-fill only, self-host if any volume).

---

## 4. Ecosystem Integration Contracts

### 4.1 Hermes → Geronimo (push qualified leads)

Geronimo has **no public lead-ingest API yet** — cross-project dependency.

- **New Geronimo endpoint** (coordinate with Geronimo team): `geronimo-entries:8700 POST /api/v1/qualified_leads`
- → `Envelope(source='hermes_qualified', type='lead.qualified')`
- → NATS publish `geronimo.in.hermes.qualified_leads`
- → **new `hermes-leads-router` consumer** (parallel to `atendimento_cliente`) classifies intent (sales|support|partnership)
- → Kanban `side='hermes'` OR HITL escalation (Caio approval).

**Contract payload:**
```json
{
  "lead_id": "...", "business_name": "...", "cnpj": "...", "cnae": "...",
  "category": "...", "score": 0,
  "phone": "...", "email": "...", "whatsapp": "...",
  "website": "...", "has_website": true,
  "address": "...", "city": "Cuiabá", "state": "MT",
  "source_type": ["osm","cnpj","website"],
  "market_signals": [],
  "idempotency_key": "hermes:{lead_id}:{discovered_at_epoch}",
  "tenant_id": "hermes"
}
```
- **Auth:** `X-Internal-Token` (shared `HERMES_INTERNAL_TOKEN`, hmac.compare_digest).
- **Transport:** Tailscale mesh (`geronimo-mesh.ts.net`, sub-100ms, co-hosted on Contabo) — NOT cloudflared.
- **Hermes side:** new `mcps/hermes-geronimo/` MCP (FastAPI `POST /handoff`, `handoff_jobs` table status pending/sent/failed, retries 3× exp-backoff 1s/4s/16s). Brain `handoff_decision` intent gates which leads cross (score ≥ threshold + audit_done).
- Route handoffs through Geronimo `constitution_gates` (PII redact pre-send, business_hours, DPA).

### 4.2 Hermes → Vuecra (site-ready briefs)

Contract **already documented** in `vuecra/.claude/CROSS-PROJECT-ENV.md` + `PHASE-HI1/HI2`.

**Hermes ships HI1 schema FIRST**, then HI2 endpoints:
- `migrations/006_vuecra_stages.py`: add columns `site_url, site_delivered_at, site_project_id, idempotency_key, hermes_source`; add stages `site_ready / site_in_progress / site_delivered`.
- **HI2 endpoints (Hermes side):**
  - `GET /api/vuecra/queue` → `ProspectBrief[]` ordered by score DESC (Vuecra V4 Inbox consumes)
  - `POST /api/vuecra/{prospect_id}/claim` → site_ready → in_progress
  - `POST /api/vuecra/{prospect_id}/delivered` → in_progress → delivered (body `site_url + project_id`)
  - `POST /api/vuecra/{prospect_id}/failed` → revert in_progress → site_ready
- **WS events** on `wss://{hermes}/ws`: `site.ready / site.claimed / site.delivered / site.failed`.

**ProspectBrief schema:** `{prospect_id, business_name, category, audit_summary, score, phone, email, website, has_website, photo_ref, social_instagram, social_facebook, address, city, state, marked_at, hermes_source}`.

**Headers:** `X-Internal-Token` + `X-Idempotency-Key` (`hermes:{prospect_id}:{discovered_at_epoch}`) + `X-Correlation-Id`. Same key + same state = 200 replay; same key + different state = 409.

**Round-trip:** Hermes marks `site_ready` → Vuecra V4 Inbox claims → generates → POSTs back to `/delivered` with `site_url` → Hermes persists.

> **Port reconcile (RISK):** Vuecra docs assume `Hermes:8500`; current config uses `dashboard_port=55000`. **Pin the actual Hermes port as `HERMES_BASE_URL` in `CROSS-PROJECT-ENV.md` (single source of truth) before HI2** or callbacks 404.

### 4.3 Shared Infrastructure

- **LLM routing:** reuse Geronimo's 3-layer stack via `nim-router-mcp` HTTP with `tenant_id='hermes'` and a **separate daily budget cap**. Categorization / ICP / dedup-fuzzy run on **local Ollama T3 ($0, qwen2.5 on shared mesh)** to hold $0. Escalate to NIM tiers only for ambiguous classification.
- **agentmemory:** shared (already wired `:3111` / `:3141`), session-agnostic.
- **Ports:** Hermes internal range **8800–8810** (see §5).

---

## 5. Contabo Migration + Cohabitation

**Target:** Contabo VPS 30 (8 vCPU / 24 GB / 200 GB) **cohabiting Bolseye + Geronimo**. Hermes 2.0 runs as Docker services on the **same `geronimo-net` bridge (172.28.0.0/16)** to reuse Postgres / NATS / agentmemory / nim-router with **no new public surface**.

### 5.1 What migrates (from GCP)
- Prospect data (DB rows) → into shared Postgres, new schemas `hermes_prospects` + `cnpj_cuiaba` (NOT a new instance).
- Daemon + pipeline + brain + MCP services → Docker on `geronimo-net`.
- Env / secrets → shared `CROSS-PROJECT-ENV.md` (`HERMES_INTERNAL_TOKEN`, base URLs, feature flags).
- **PC keeps** source + dashboard host only.

### 5.2 Port allocation (3 projects)
Geronimo uses 8700 app ports; 5432/6379/4222/8222 internal; 11434 Tailscale.

| Service | Port | Visibility |
|---|---|---|
| hermes-api | 8800 | internal |
| hermes-discovery-mcp | 8801 | internal |
| hermes-enrich-mcp | 8802 | internal |
| hermes-handoff-mcp | 8803 | internal |
| self-hosted Overpass | 12345 | internal only |
| (reserved) | 8804–8810 | internal |

**Reuse:** Postgres 5432 (new schemas), NATS 4222 (subjects `geronimo.in.hermes.*`), nim-router (`tenant_id='hermes'`), Ollama via `OLLAMA_PC_URL` mesh, agentmemory `:3141`. cloudflared stays outbound-only; ufw only SSH 22; no new public inbound.

### 5.3 Resource limits (24 GB total — Geronimo + Bolseye already resident)
- **Overpass is the hog:** Brazil DB expands ~4-5× the .pbf (~8 GB disk) + ~6-8 GB RAM under load. Set `mem_limit: 8g`; conservative `OVERPASS_RATE_LIMIT / OVERPASS_TIME / OVERPASS_SPACE`. **Fallback if memory tight: load Mato-Grosso-only extract instead of full Brazil .pbf.**
- **CNPJ Postgres:** Cuiabá-filtered subset only (tens of GB on 200 GB disk), **NOT** full Brazil universe.
- Discovery/enrich workers: 1-2 GB each. **Hard cap concurrent scrape workers** (per-domain limiter via generalized `core/limiter.py`). Monitor via `observability.py`.

### 5.4 Frozen-LinkedIn
- `FEATURE_LINKEDIN=off` env gate in `server.py` blocks **all** cobaia/warmup/stealth launches.
- Daemon **P0 COBAIA + P2 SEQUENCE skipped** when flag off.
- `linkedin/`, `linkedin/lab/`, `dashboard/components/cobaia_*.js`, `api/cobaia.py`, `api/lab.py` **preserved (zero deletion)** but unreachable.
- **Patchright/Playwright browser binaries stay VM-ONLY** (guardrail: NEVER install on PC). In 2.0 the only browser need is Patchright T2 website-scrape — runs on Contabo VM, not PC.

### 5.5 The 2 gaps resolved in clean Contabo setup
- **R5-PHASE3:** resolved during clean Contabo provisioning (fresh service definitions on `geronimo-net`, no legacy GCP cruft).
- **Sentry token:** set as proper env secret in `CROSS-PROJECT-ENV.md` during cutover; `observability.py` reads from env, no hardcoded token.

### 5.6 Phased migration + rollback + cutover
1. **(a)** Stand up Overpass Docker + verify Cuiabá queries.
2. **(b)** Load CNPJ Cuiabá subset → shared Postgres.
3. **(c)** Wire discovery/enrich MCPs behind gateway.
4. **(d)** Flip `FEATURE_LINKEDIN=off`; re-map daemon priorities; **flag-off smoke test**.
5. **(e)** Ship Vuecra HI1 schema + HI2 endpoints.
6. **(f)** Wire Geronimo NATS handoff.

**Rollback:** per-stage via feature flags. Each stage independently revertible (flag off / unregister MCP / drop schema). **Cutover:** keep GCP read-only until Contabo proves a full discovery→handoff round-trip, then decommission GCP.

---

## 6. Roadmap H2-F0 .. H2-F8

| Phase | Goal | Scope | Effort | Depends on | Model |
|---|---|---|---|---|---|
| **H2-F0** Foundation + Freeze | Prove engine still boots clean post-freeze | `FEATURE_LINKEDIN=off`; skip daemon P0/P2; hide `cobaia_*.js`; add `source_type`+cnpj columns; pin Contabo ports 8800-8810 in CROSS-PROJECT-ENV.md; **flag-off smoke test** | 1-2d | — | Sonnet |
| **H2-F1** Overpass Discovery Backbone | Unlimited $0 24/7 discovery | Docker `wiktorn/overpass-api` + Geofabrik brazil .pbf + minute diffs (mem_limit 8g); `scripts/discovery_overpass.py` → Prospect schema; wire into `core/pipeline.py` discovery stage (drop Google Places dep); daemon P4 multi-source. **VERIFY:** N Cuiabá POIs ingested + deduped | 3-4d | F0 | Sonnet |
| **H2-F2** CNPJ Authority + Enrich | Brazil's best free structured layer | Load RF quarterly dump Cuiabá subset (5103403 + target CNAE) → Postgres `hermes_cnpj`; `scripts/enrich_cnpj.py` + BrasilAPI validation; **DEDUP/MERGE golden-record** step (fuzzy name+address+phone+CNPJ); daemon P3; register `mcps/hermes-enrich` | 3-5d | F1 | Sonnet |
| **H2-F3** Contact-Enrich (website) | Fill OSM contact gap | `scripts/scrape_website.py` (curl_cffi T1, Patchright T2 VM-only) parsing schema.org JSON-LD + regex +55 65 phones/emails/wa.me/og-social; per-domain limiter (generalize `core/limiter.py`); runs in P3 after CNPJ | 2-3d | F2 | Sonnet |
| **H2-F4** Categorize + ICP + Qualify | Score leads 0-100 | `classify_prospect` via local Ollama (CNAE→industry/ICP); extend `web_audit.py` + PageSpeed Insights qualifier; daemon P5; new `dedup_merge` intent | 2-3d | F3 | Opus (scoring logic) / Sonnet |
| **H2-F5** Vuecra Handoff (HI1+HI2) | Unblock Vuecra V4 Inbox | `migrations/006_vuecra_stages.py` + stages; `GET /api/vuecra/queue` + claim/delivered/failed + WS `site.*` with X-Internal-Token + idempotency. **VERIFY:** full round-trip | 3-4d | F4 | Sonnet |
| **H2-F6** Geronimo Handoff (NATS) | Push qualified leads | `mcps/hermes-geronimo` (POST /handoff, handoff_jobs, retries); coordinate Geronimo `POST /api/v1/qualified_leads` + NATS + `hermes-leads-router` consumer; `handoff_decision` intent gate; Tailscale transport | 3-4d | F4 + Geronimo team | Opus (cross-project contract) |
| **H2-F7** Market Intelligence | Proactive signals | `brain/market_analyzer.py` aggregates CNAE density + situação churn + new-reg velocity per vertical → `market_signal` events; daemon P6b; Market-Intel dashboard page (heat by category/region); rule-based first, LLM optional | 3-4d | F2 | Sonnet |
| **H2-F8** Hardening + Observability | Production-ready 24/7 | extend `observability.py` for scraper/source health + per-source cost; Source-health dashboard panel; agentmemory persistence of golden records + signals; per-stage flag rollback verified; load-test Overpass under 24/7 daemon | 2-3d | F1-F7 | Sonnet |

**Critical path:** F0 → F1 → F2 → F3 → F4 → (F5 ∥ F6 ∥ F7) → F8. F5/F6/F7 parallelizable after F4. **Total ~24-32 days** solo-founder.

---

## 7. Decisions for Owner + Risks

### 7.1 Open product decisions
1. **First source order confirmed?** Overpass → CNPJ → website. (Recommended; locked unless owner objects.)
2. **Full Brazil .pbf vs Mato-Grosso-only?** Decide based on Contabo RAM headroom at F1 (MG-only is safer at 24 GB shared).
3. **Knowledge-base schema:** golden-record fields + `source_type` array + `market_signals` — approve before F2 dedup/merge.
4. **Handoff trigger threshold:** what score gates Geronimo handoff (e.g. score ≥ 60 + audit_done)? And Vuecra site_ready (e.g. has_website=false OR score ≥ 70)?
5. **Geronimo lead-ingest API:** coordinate or stub? F6 blocks on Geronimo shipping `POST /api/v1/qualified_leads`.

### 7.2 Top risks + mitigations

| Risk | Mitigation |
|---|---|
| **Overpass RAM/disk OOM** on shared 24 GB (Geronimo+Bolseye resident) | `mem_limit 8g`, conservative OVERPASS_RATE/TIME/SPACE; **MG-only extract** if tight |
| **OSM contact-tag fill is LOW in Cuiabá (~40%)** — mom-and-pop sparse | Website-scrape (F3) + CNPJ (F2) are **MANDATORY**, not optional, to reach contactability. Set expectations. |
| **LGPD** — processing PII (QSA names, phones, emails) + reselling leads | Lawful basis (legitimate-interest B2B prospecting, defensible in BR); opt-out; no sensitive data storage; route handoffs through Geronimo `constitution_gates` PII redact; attribute OSM (ODbL) on display |
| **Port/base-URL mismatch** (Vuecra assumes 8500, config 55000) | Pin one canonical port in CROSS-PROJECT-ENV.md **before** HI2 |
| **Geronimo lead-ingest API doesn't exist yet** | F6 cross-project dependency — coordinate or stub `hermes-leads-router` |
| **$0 fragility** — temptation to add Google Maps for reviews | Hold the line: PageSpeed + own-site schema.org `aggregateRating` cover review signal legally; Google scraping needs paid proxies (breaks $0) + ToS + civil risk |
| **Frozen-LinkedIn regressions** — flag must gate ALL entry points | Verify with flag-off smoke test in F0; gate daemon P0/P2 + `api/cobaia.py` + `api/lab.py` + dashboard |
| **Solo-founder scope creep** — 9 phases ambitious; Overture/Foursquare/Apple tempting | DEFER all multi-vendor enrichment (Apollo/RocketReach break $0). Overpass+CNPJ+website trio is sufficient for Cuiabá. |
