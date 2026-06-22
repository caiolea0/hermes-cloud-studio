# Hermes 2.0 — Marketing Audit + Revenue Projection: Viability ($0, real)
**Sealed**: 2026-06-21
**Context**: Caio, solo founder, Cuiaba/MT Brazil, $0-first self-hosted Contabo. Hermes audits local businesses to sell marketing+automation (Geronimo) + sites (Vuecra). Owner demands REAL data with REAL estimates — NO mock, NO fabricated precision. Audit = sales ammunition + a revenue projection that closes deals.

> **Hard guardrail repeated everywhere below**: every number ships tagged `[FACT]` or `[EST faixa, n=, fonte]`. A scrape/parse from a public source = FACT. A modeled multiplier = ESTIMATE-with-range. Anything invented = FORBIDDEN. The tag IS the credibility that closes the deal and survives pushback.

---

## 0. TL;DR verdict table (plain language)

| # | Dimension | Feasible $0? | The one tool to use | FACT vs ESTIMATE honesty |
|---|-----------|--------------|---------------------|--------------------------|
| 1 | **Presence / Social / Ads** | **solid-free** | Meta Ad Library (public web) + Google Ads Transparency Center | FACT: which networks, ads running yes/no, the literal creative images, page age, follower count. EST: posting cadence (visible window only), ad spend (NEVER a fact), reach. |
| 2 | **SEO / Position** | **with-limits** | Lighthouse CLI (tech, unlimited) + Serper free 2.5k then self-host scraper (rank) | FACT: rank snapshot, local-pack occupancy, Lighthouse scores, CrUX field CWV, on-page tags. EST: search volume, lost-clicks, revenue-at-stake. |
| 3 | **Competitive** | **with-limits** | Overpass+Google Maps (set) + Meta/Google ad-presence + PageSpeed | FACT: rating, review_count, GBP claimed, ads running, PageSpeed, SERP rank. EST: keyword/backlink counts, DA, click-share. FORBIDDEN: SimilarWeb/Ubersuggest traffic for local (>50% error). |
| 4 | **Keyword Volume** | **with-limits (see §1)** | DataForSEO search_volume/live ($1 free = ~20k kw EXACT) | FACT: EXACT integers from DataForSEO; Google Ads API = RANGES only on no-spend acct. All volumes are modeled (~±20-40%). |
| 5 | **AdWords Competition** | **with-limits** | Google Keyword Planner (geo Cuiaba, skip campaign = $0) | FACT: CPC top-of-page range BRL, Competition L/M/H, who advertises now + ad longevity. EST: exact volume (ranges), effective CPC, competitor spend (FORBIDDEN as fact). |
| 6 | **Organic Strategy** | **solid-free** | Google Places Details (10k/mo free) + PageSpeed + reuse on-disk scorers | FACT: GMB rating/reviews/hours/photos, Lighthouse, schema/NAP. EST: GMB views proxy, projected leads (benchmark bands). FORBIDDEN: LLM-generated stats (Ollama prose-only). |
| 7 | **Revenue Data / Pricing** | **with-limits (per niche)** | gosom/google-maps-scraper + iFood __NEXT_DATA__ price waterfall | FACT: real prices where public (food 70-90%, beauty 30-50%, retail 10-20%), review_count, popular_times. EST: niche-median ticket, demand from reviews band. |
| 8 | **Revenue Projection** | **with-limits (see §1)** | 5-factor model on $0 data, 3 scenarios | EST by definition — but FACT-anchored + every multiplier visible + cited. NEVER a single "you'll make R$X" promise. |

**One-line read**: Technical/factual layers (1,3,6 + tech-half of 2) are genuinely solid-free and devastating ammunition on their own. The two hard ones (keyword-volume, revenue-projection) are doable but are ESTIMATES — credibility comes from honest ranges, not fake precision.

---

## 1. The two hard ones (be brutally honest)

### 1A. Keyword volume free — REAL absolute monthly volume, $0?

**Final answer: YES, you can get EXACT $0 absolute volume — but only via one loophole, and even "exact" is a model.**

- **Best method: DataForSEO `keywords_data/google_ads/search_volume/live`.** Signup (no card) = **$1 free credit**. Endpoint costs **$0.05 per REQUEST**, and one request carries **up to 1000 keywords**. So **$1 ≈ 20 requests ≈ up to 20,000 keywords pulled FREE**, returning EXACT integers (e.g. `368000`, not `"100K-1M"`), with `location_name="Brazil"` + `language_code="pt"`, plus 12-month trend + CPC + competition. DataForSEO sources it from their own high-spend Google Ads MCC — that's how you get exact numbers WITHOUT running your own ads. After $1, min top-up $50 (= 50k more batches = effectively unlimited for a solo founder). **Batch 1000 kw/request and cache in Postgres** — sloppy 1-kw-per-request burns the credit 1000x faster.
- **Why NOT the official Google Ads API for exact**: free + 15k ops/day, BUT a no-spend account returns **BUCKETED RANGES** ("1K-10K"), not integers. Exact requires ~$5-10/day live ad spend. This is an account-tier rule, not a code bug. Use it only if you accept ranges.
- **Free-forever manual cross-check**: Keyword Surfer / Glimpse Chrome extensions = exact volume in SERP, Brazil supported, no account — perfect for sanity-checking a headline number before it goes in a deck. Not cleanly scriptable.
- **Google Trends = RELATIVE only (0-100)**, never absolute. pytrends ARCHIVED Apr 2025, 429-blocks fast. Use ONLY for seasonality storytelling.

**Honesty ceiling**: ALL volumes (even Google's own) are modeled estimates; treat any single number as **±20-40%**. Long-tail local terms ("pizzaria delivery cuiaba") often return 0/no-data even when real demand exists — triangulate from the head term + relative split, label as modeled, never invent a figure. **In decks: say "roughly 800-1,300/mo", not "1,047".**

### 1B. Revenue projection — credible R$ range, $0?

**Final answer: YES, a DEFENSIBLE range — never a single number. The projection is an ESTIMATE by definition; its credibility is the visible arithmetic.**

**The exact 5-factor formula (per channel, per keyword set):**
```
Monthly_uplift = Demand × Capture × Conversion × Ticket × Close
```
1. **DEMAND** = sum of monthly search volume for top 10-20 local keywords (from §1A). *Cuiaba metro ~660k pop → volumes are SMALL (tens-hundreds/mo, not thousands). This is the #1 reality check that kills inflated promises.*
2. **CAPTURE** = incremental CTR from current→target position. Organic CTR curve (FirstPageSage 2024-26): pos1=39.8%, pos2=18.7%, pos3=10.2%, pos4=7.2%, pos5=5.1%, pos7=3.0%, pos10=1.6%. **UPLIFT = (CTR_target − CTR_current)**, only the delta you create. Google Ads: pos1=7.94%, pos2=4.55%, pos3=2.55% (avg 3.17%).
3. **CONVERSION** = visitors→leads. BR sector benchmarks (Neotrust/Ebit 2024): ecommerce 1.65%, alimentacao 3.8%, saude 3.2%, beleza 2.9%, moda 1.9%, SERVICOS 4.02%; desktop 2.8% vs mobile 1.2%. Local "near me": 28% of nearby searches → purchase — apply ONLY to genuine local-intent terms.
4. **TICKET** = the business's OWN average ticket. **ASK THEM — never guess.** Most impactful + most business-specific input.
5. **CLOSE** (services only) = lead→client rate, owner-supplied (typ 15-30%).

**Range = 3 scenarios, every premise in a one-page table:**
- **Conservative**: bottom-of-range volume, modest gain (pos8→pos4), low-end conversion, worst-month ticket, low close.
- **Likely**: midpoint volume, realistic 3-6mo gain (pos8→pos3), median conversion, avg ticket.
- **Optimistic**: high volume, pos1-2, top-quartile conversion, peak ticket.
Present `R$ X – R$ Y – R$ Z /mo` with EVERY cell shown so the prospect can challenge any input. **That defensibility IS the close.**

**Confidence**: MEDIUM. Each FACT input (rank, ads, reviews, scores) is high-confidence; each multiplier (CTR curve, conversion, close) is a cited benchmark with real variance. The OUTPUT is honestly a band, not a forecast. **Confidence is HIGH that the range is defensible; LOW that any single point inside it is "the" number — so never present a point.**

---

## 2. Per-dimension build recipe

### Dim 1 — Presence / Social / Ads (solid-free)
**Pipeline (all VM/Contabo, Playwright/Patchright VM-only — NEVER browser binaries on PC):**
1. **Social detection** `[FACT]`: requests+BeautifulSoup on homepage/footer → regex facebook/instagram/linkedin/tiktok/youtube/wa.me. Cross-check GBP page. Link on own site = hard fact they have it.
2. **Cadence/content** `[FACT count, EST cadence]`: IG public page JSON (followers_count, posts_count, last ~12 timestamps→posts/wk RANGE over stated window); FB Page Transparency tab (created date, name changes, country, admins = gold, 100% public). Throttle 1/5s, expect IG breaks every 2-4wk (doc_id rotation), parse GraphQL not HTML.
3. **Ads (the closer)** `[FACT]`: **Meta Ad Library** `facebook.com/ads/library?country=BR&ad_type=all&active_status=active&q=BRAND` via Playwright GraphQL interception → creative image/video URLs (downloadable from Meta CDN), start date, active status, platforms, copy, count. **Google Ads Transparency** `adstransparency.google.com/?region=BR` by bare domain → all creatives, format, run dates. (`pip install Google-Ads-Transparency-Scraper`.)
4. **Audit+projection**: scorecard networks present/absent + cadence vs benchmark (<2/wk = dormant) + ads count + creative screenshots. Absence in ad library = NOT running paid ads = itself a FACT/selling point.
**Outputs**: `{network: present, handle}`, follower/post counts, ad creatives + count, page age. **AVOID official Meta API** (BR commercial = political-only, 5-10d verification, no creative downloads — public web gives MORE for $0).

### Dim 2 — SEO / Position (with-limits)
**(A) Technical SEO = 100% free, unlimited, zero legal risk:**
1. `npx lighthouse <url> --output=json --only-categories=performance,seo,accessibility,best-practices --form-factor=mobile` `[FACT]` — official replacement for dead Mobile-Friendly Test.
2. PageSpeed Insights API (25k/day free) `[FACT]` — second source + field data.
3. CrUX API (150 q/min free) `[FACT]` — REAL user CWV when it exists (absence for low-traffic local = itself a finding).
4. Fetch HTML (httpx+selectolax) → title/meta/H1/canonical/robots/sitemap/hreflang/OG `[FACT binary]`.
5. JSON-LD parse OR SchemaCheck REST `[FACT]`.
**(B) Positioning = free-with-limits:** Serper free 2,500 credits (no card) with `gl=br, hl=pt-br, location="Cuiaba, State of Mato Grosso, Brazil"` → organic rank + local-pack top-3 `[FACT snapshot]`. After credits: self-host gosom/google-maps-scraper (pack) + Playwright SERP script (organic). Log to Postgres = rank tracker. Throttle hard (few q/min, jittered), ToS-gray.
**Outputs**: per-site scorecard + rank history. **EST**: volume×CTR-curve×Caio-ticket → lost-clicks band.

### Dim 3 — Competitive (with-limits)
1. **Set**: Nominatim geocode → Overpass (no key) same-niche in Cuiaba bbox → dedupe with Google Maps category search (Maps = authoritative for BR interior). Rank by review_count.
2. **Reviews/presence** `[FACT]`: Playwright Maps profile → rating, review_count, photos, GBP claimed, hours. Warm session (google.com→cookies→nav), 1 profile/15-30s, persist cookies, VM not PC. 10-biz volume survives without paid proxy; fallback Apify ~40 free / Outscraper free tier.
3. **Ads** `[FACT]`: Meta Ad Library + Google Ads Transparency presence per competitor.
4. **Tech** `[FACT]`: PageSpeed scores + SSL/viewport/title/schema/WhatsApp-CTA.
5. **Rank** `[FACT]` who's in 3-pack/organic; **`[EST]`** keyword/backlink counts (Semrush 1/day, Ubersuggest 3/day, Moz DA).
6. **Synthesis**: comparison matrix (rows=target+competitors), color-code gaps. **FORBIDDEN**: SimilarWeb/Ubersuggest traffic counts for local (>50% error) → use review_count+velocity+ad presence as demand proxy.

### Dim 5 — AdWords Competition (with-limits)
1. **Anchor** `[FACT]`: Google Keyword Planner, Expert Mode, **skip campaign creation, NEVER activate = $0**. Per keyword geo-Cuiaba/MT + PT: CPC top-of-page low/high range BRL (what advertisers REALLY pay), Competition L/M/H, volume (FAIXAS).
2. **Names** `[FACT]`: Google Ads Transparency (script: faniAhmed/GoogleAdsTransparencyScraper — note: last release Jul 2023, may need patch, keep UI fallback) + Meta Ad Library UI. **Ad longevity = strongest persuasion** (nobody pays 6+mo ads at a loss).
3. **Saturation** `[FACT snapshot]`: manual SERP spot-check geo-Cuiaba, count 4-top/3-bottom ad slots. 5-10 kw by hand; NO 24/7 crawler. Batch fallback: SearchAPI/Scrape.do free credits (1000, no card).
4. **Cross-check** `[EST]`: WordStream/MediaSpearhead for order-of-magnitude only (US data, never the BR number).
**FORBIDDEN**: exact # advertisers (Google gives only L/M/H), competitor monthly spend.

### Dim 6 — Organic Strategy (solid-free)
1. **Collect**: Overpass (discovery) + **Google Places Details** (rating, review_count+text, hours, category, photos, business_status, website — 10k Essentials events/mo free ≈ 300+ audits, field-mask to stay in Essentials SKU) `[FACT]` + PageSpeed `[FACT]` + httpx HTML for JSON-LD/NAP/H1 `[FACT]`.
2. **Score** (deterministic, LLM-free, reproducible): port on-disk `local_seo_scorer.py` (`C:\Users\cleao\.claude\skills\logo-architect\external-skills\0-shiv-secondstep\skills\local-seo-claude\scripts\`) + `geo_checker.py` (`C:\Users\cleao\.agent\antigravity-awesome-skills\skills\geo-fundamentals\scripts\`). **Reweight to Whitespark 2026**: GBP 32, on-page 19, reviews 16, links 15, behavioral 8, citations 7, personalization 3.
3. **Strategy**: RULES decide WHAT (template per gap+niche). **Ollama (Qwen3) re-writes bullets to PT-BR prose ONLY — never generates facts/numbers** (anti-hallucination guardrail; all numbers injected from steps 1-2).
4. **Projection** `[EST band]`: GMB views (insights or review-volume proxy) × benchmark conversion bands (calls 5-8% / home-svc 10-15%, directions 3-5% / food 7-10%, clicks 4-7%) × Caio ticket → LOW-MID-HIGH, every multiplier cited (e.g. 50+ reviews = 266% Local-Pack odds, Whitespark/BrightLocal 2026).

### Dim 7 — Revenue Data / Pricing (with-limits, per niche)
**Price waterfall (stop at first hit):** `[FACT where found]`
1. iFood `__NEXT_DATA__` JSON (food, 70-90%) + Google GBP Menu/Services.
2. schema.org via `extruct` Product>Offer.price (~10-20% non-ecom).
3. HTML BRL regex `R\$\s?\d{1,3}(\.\d{3})*(,\d{2})` near product names.
4. IG/FB caption + Tesseract OCR (`-l por`) on price-table images.
5. pdfplumber (text PDF) / Tesseract `--psm 4` (image cardapio).
6. **Fallback `[EST n=, range]`**: niche-median table (scrape 15-30 peers once → median + p25/p75).
**Demand (band, never point):** gosom/google-maps-scraper (no key, review_count + popular_times) → reviews ≈ 1-3% of transactions → `LOW(reviews/0.03)–HIGH(reviews/0.01)`; popular_times × hours × served/hr = capacity ceiling. Keyword volume = market context only.
**Niche hit-rates (honest)**: food HIGH, beauty/services MEDIUM, retail LOW-MEDIUM, image-only-IG LOW. **TRAP**: pytrends archived — do not build demand on it.

---

## 3. The consolidated $0 stack

| Tool / repo | Use | Status | URL |
|---|---|---|---|
| Meta Ad Library (public web) | Active ads + downloadable creatives, BR | truly-free, no login | https://www.facebook.com/ads/library |
| FB Page Transparency tab | Page age, name changes, admins | truly-free | https://www.facebook.com/help/323314944866264 |
| Google Ads Transparency Center | Ads by domain/name, region=BR | truly-free | https://adstransparency.google.com/?region=BR |
| faniAhmed/GoogleAdsTransparencyScraper | Script the above | free, scrape-risk (Jul-2023 release) | https://github.com/faniAhmed/GoogleAdsTransparencyScraper |
| Lighthouse CLI | Tech SEO/perf/a11y, unlimited | truly-free, self-host | https://developer.chrome.com/docs/lighthouse/overview |
| PageSpeed Insights API | Lighthouse-as-service + field | truly-free 25k/day | https://developers.google.com/speed/docs/insights/v5/get-started |
| CrUX API | Real field CWV | truly-free 150 q/min | https://developer.chrome.com/docs/crux/api/ |
| Serper | SERP + local pack, geo Cuiaba | free-tier 2.5k then paid | https://serper.dev |
| SchemaCheck | Structured-data validate | truly-free REST | https://www.schemacheck.dev/ |
| gosom/google-maps-scraper | Maps: reviews, popular_times, no key | free, self-host, scrape-risk | https://github.com/gosom/google-maps-scraper |
| christophebe/serp | Organic SERP scrape | free, self-host, scrape-risk | https://github.com/christophebe/serp |
| Overpass API (OSM) | Local business discovery | truly-free, no key | https://overpass-api.de/api/interpreter |
| Nominatim | Geocode anchor | truly-free, no key | https://nominatim.openstreetmap.org |
| Google Places API (Details) | GMB rating/reviews/hours | free-tier 10k/mo, **account+billing card on file** | https://developers.google.com/maps/documentation/places/web-service/usage-and-billing |
| DataForSEO search_volume/live | EXACT BR volume | $1 free (no card) ≈ 20k kw, then $50 min | https://docs.dataforseo.com/v3/keywords_data-google_ads-search_volume-live/ |
| Google Keyword Planner | CPC range + competition, geo | free, **account-needed** (skip campaign=$0) | https://ads.google.com/home/tools/keyword-planner/ |
| Keyword Surfer / Glimpse | Volume cross-check in SERP | truly-free, manual ext | https://surferseo.com/keyword-surfer-extension/ |
| extruct | schema.org price extract | truly-free OSS | https://github.com/scrapinghub/extruct |
| Tesseract + pytesseract | OCR menu/price images | truly-free | https://github.com/tesseract-ocr/tesseract |
| pdfplumber | Text-PDF menu prices | truly-free | https://github.com/jsvine/pdfplumber |
| iFood __NEXT_DATA__ | Restaurant menu+prices | free DIY, scrape-risk (ToS gray) | https://github.com/KenzoBH/Web-Scraping-and-EDA-iFood |
| Playwright / Patchright | Headless GraphQL interception | free, **VM-ONLY** | (in Hermes VM stack) |
| Ollama (Qwen3) | PT-BR prose rewrite ONLY | free, self-host VM | https://ollama.com |
| local_seo_scorer.py / geo_checker.py | Deterministic scoring | on-disk, $0 | (paths in §2 Dim 6) |
| SearchAPI / Scrape.do | SERP batch fallback | free-tier 1000, no card | https://www.searchapi.io/ |
| Apify / Outscraper | Maps review fallback | free-tier | https://apify.com/compass/crawler-google-places |
| Semrush / Ubersuggest / Moz | Keyword/DA EST cross-check | free-tier (1-3/day) | https://www.semrush.com |

**Truly-free + unlimited self-host**: Lighthouse, Overpass, Nominatim, extruct, Tesseract, pdfplumber, gosom scraper, Ollama, on-disk scorers, Playwright (VM).
**Free-tier-limit**: PageSpeed 25k/day, CrUX 150/min, Places 10k/mo, Serper 2.5k once, DataForSEO $1, Scrape.do 1000.
**Account-needed**: Keyword Planner (Google Ads acct), Places (billing card on file even at $0), DataForSEO.
**Scrape-risk (ToS-gray, throttle, expect breakage)**: Meta/Google ad scrapers, IG, Google Maps, iFood, SERP scrapers.

---

## 4. The dossier output (per business)

**A. Identity & Presence** `[FACT]` — name, address, category, GBP claimed?, website?, SSL?, mobile-responsive?, networks present/absent map.
**B. Reputation** `[FACT]` — GMB rating, review_count, photo count, review velocity, response behavior; vs top-3 competitors `[FACT]`.
**C. Advertising** `[FACT]` — running Meta ads? count + creatives (screenshots) + start dates + longevity; running Google ads? formats; OR "zero ads running" (a selling fact). Competitor ad gap.
**D. Findability / SEO** `[FACT]` Lighthouse perf/SEO/a11y + CWV, schema/NAP/title status, organic rank + local-pack occupancy snapshot; `[EST]` keyword volume (DataForSEO/ranges), CPC range (KP), lost-clicks band.
**E. Pricing & Demand** `[FACT]` real prices where public (source-tagged), review_count, popular_times; `[EST]` niche-median ticket (n=, range), demand band from reviews/capacity.
**F. Revenue Projection** `[EST band]` — 5-factor model, conservative/likely/optimistic R$/mo, every multiplier cited, ticket+close owner-supplied. Headline = the gap ("you run 0 ads, competitor runs 12; you're page 2; closing this targets R$X-R$Y/mo").

---

## 5. Honesty + ethics

- **FACT (state verbatim, screenshot as proof)**: anything scraped/parsed from a public source at a point in time — networks, ads running + creatives, page age, follower/review counts, ratings, Lighthouse/CWV, on-page tags, SERP rank snapshot, real published prices, CPC ranges from KP, ad longevity. Always note rank/counts are point-in-time snapshots.
- **ESTIMATE-with-range (label "estimativa", show band + assumption + source)**: posting cadence, ad spend (NEVER a fact for commercial ads), reach, search volume (modeled, ±20-40%), lost-clicks, conversion/close multipliers, niche-median ticket, demand-from-reviews, the entire revenue projection.
- **MUST NOT claim**: exact commercial ad spend in R$, a promised "you'll make R$X" point number, follower/engagement for networks not actually fetched, SimilarWeb/Ubersuggest traffic for local sites, exact # of advertisers, any LLM-generated statistic, a no-data term filled with an invented number.
- **BR CDC (Codigo de Defesa do Consumidor)**: projections are estimates/expectations, never guarantees of result — frame as "potential/estimated under stated assumptions". Don't disparage named competitors with unverifiable claims; only state observable public facts about them (their ads run, their review_count) — those are defensible. Respect each source's ToS posture (scraping public ad-transparency data is low-risk; Maps/IG/iFood are ToS-gray — throttle, VM-only, low volume).

---

## 6. Open decisions for owner

1. **DataForSEO**: spend the $1 free credit now to prove EXACT-volume pipeline at literal $0, then decide on the $50 top-up once it's earning? (Recommended yes.)
2. **Places API billing card**: accept putting a card on file (stays $0 under 10k/mo) for real GMB data, or stay pure-scrape via gosom (no card, but ToS-gray)? This is the ONE non-pure-free dependency.
3. **Niche priority**: lead with FOOD (highest price + demand coverage, iFood) for the first Hermes audits? Which Cuiaba verticals first for Geronimo vs Vuecra?
4. **Ticket & close-rate inputs**: build the per-niche table from owner knowledge now (required input for §1B) — which niches does Caio have real numbers for today?
5. **Rank-tracker cadence**: how often to re-scrape rank/ads (weekly?) given scrape-risk + throttle budget?
6. **Maintenance budget**: accept that IG/Meta/Maps scrapers break every 2-4 weeks (DOM/doc_id rotation) and need patching — who/when?
