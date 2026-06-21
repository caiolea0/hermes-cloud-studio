# Hermes 2.0 — Audit Intelligence Research (4 Brains)
**Sealed**: 2026-06-21
**Scope**: 4 audit "brains" for the Hermes prospecting pipeline (Cuiaba/Brazil SMBs). $0-first, anti-snake-oil. Synthesized from 8 research reports + 4 per-brain syntheses.

> **Reading rule**: every claim below is tagged. **FACT** = directly measured/observed, reproducible, cite verbatim. **ESTIMATE** = real method, but multiplies an unmeasured assumption — ship as a RANGE with assumptions visible. **GUESS** = no measured input — NEVER present as a number.

---

## 0. TL;DR (plain language, non-technical owner)

| Brain | $0? | How solid? | Top tool / repo |
|---|---|---|---|
| **1. Audit WITH site** | YES — 100% free, runs now on VM | SOLID. Numbers are measured (speed in ms, security, missing features). Only the written verdict is AI. | **PageSpeed Insights API** (free Google key) + **GoogleChrome/lighthouse** |
| **2. Audit WITHOUT site** | YES — free scrapers + free SERP tiers | SOLID for what's observed (followers, reviews, photos, found-or-not). Honest caveat: scraping breaks platform ToS; data sometimes absent (itself a finding). | **gosom/google-maps-scraper** (no API key) + **Serper.dev** (2,500 free) |
| **3. Estimate current revenue** | YES for inputs — but only as a RANGE | WEAKEST. Inputs (reviews/followers) are fact. Turning them into R$ multiplies 2 guesses (review-rate %, average ticket). Confidence ~30-40% absolute, ~70% relative-vs-competitor. NO free source gives real BR revenue. | **gosom** (review velocity) + custom **pandas** model + **CNPJ porte** (Receita) |
| **4. Project revenue uplift** | PARTIAL | RISKY. Only one empirical anchor exists (Luca/HBS Yelp study: +1 star ≈ +5-9% revenue, US restaurants). Everything else is parameterized assumption. Ship as min-median-max scenarios with every premise shown. | **Luca/HBS study** anchor + **pandas** scenarios + **PSI delta** |

**One sentence for the owner**: brains 1 and 2 produce hard, defensible facts you can put in front of a prospect today, for $0. Brains 3 and 4 produce honest RANGES with the math exposed — credible if you show the assumptions, snake-oil if you crave a single number. Lead every pitch with the FACTS (brains 1-2 + relative-vs-competitor), attach the R$ ranges with disclaimers.

---

## 1. Brain 1 — Audit company WITH site

### Free tools + repos (ready code) + what each measures

| Pillar | Tool / repo | Measures | Cost |
|---|---|---|---|
| **Performance** | Google PageSpeed Insights API v5 | Lighthouse score + Core Web Vitals lab (LCP/INP/CLS/FCP/TBT/SI), opportunities — 1 call | Free 25k/day, 240/min. 1 free Google Cloud key |
| Performance | GoogleChrome/lighthouse (self-hosted npm) | Same engine, unlimited runs, custom throttling, mobile emulation | Free, Apache-2.0. Node 22+ on VM |
| Performance (field) | CrUX API | Real-user CWV (origin+URL) | Free 150 qpm, same key. Often EMPTY for low-traffic SMBs |
| **SEO — structured data** | scrapinghub/extruct | JSON-LD / microdata / RDFa / OpenGraph in one call (LocalBusiness/Organization schema = local-SEO gap) | Free BSD, pure Python |
| SEO — sitemap/robots | eliasdabbas/advertools | sitemap_to_df + robotstxt_to_df | Free MIT |
| SEO — on-page | BeautifulSoup4 + requests | title/meta/H1/alt/canonical/OG, length checks | Free MIT |
| **Tech stack** | s0md3v/wappalyzer-next | CMS/framework/version (old WordPress/Wix, outdated jQuery, no analytics/pixel) | Free GPL-3.0. Playwright on VM |
| **Security/trust** | nabla-c0d3/sslyze | cert chain, expiry days, TLS version, known vulns | Free AGPL |
| Security | santoru/shcheck | HTTP security headers (CSP/HSTS/XFO) | Free |
| Security (cross-check) | testssl.sh | TLS second opinion | Free GPLv2 |
| **Conversion/UX** | custom BS4 over Playwright-rendered HTML | presence/absence of WhatsApp (wa.me), tel:, mailto:, `<form>`, CTA (pt-BR verbs) — **this is the core IP, no off-the-shelf tool does it** | Free |
| Accessibility | dequelabs/axe-core or pa11y | WCAG violations[] with impact + rule + nodes | Free |
| Content | adbar/trafilatura | body word count, thin-content, readability | Free Apache/GPL |

**Scaffolds to lift**: Dingan2218/SEOAUDIT (check logic + PDF), rkonstadinos/python-based-seo-audit-tool (pt-BR recommendation templates), ngstcf/ai-seo-auditor (the extract→LLM architecture — matches Hermes exactly).

### The output: a real problem-list, NOT a vague score
Concrete sales ammunition: *"no WhatsApp button, no contact form, viewport missing = breaks on mobile, 14 axe accessibility violations, footer says © 2019, jQuery 1.11 outdated, SSL cert expires in 12 days, LCP 6.8s on mobile (Google flags >2.5s), no LocalBusiness schema."* Each finding → a severity + a plain-PT sentence. The product is the SENTENCE, not the JSON.

### Honesty: hard-fact vs subjective
- **FACT** (cite directly): Lighthouse/CWV ms (lab, reproducible), cert days-to-expiry, TLS version, schema present y/n (binary), viewport meta present y/n (absent = definitively not mobile-optimized), axe violation count, **presence** of a conversion element (if selector matches, it exists), body word count, missing H1/meta description, horizontal scroll at 375px.
- **ESTIMATE**: freshness only as a COMPOSITE (© 2019 alone auto-updates and lies; combine with jQuery 1.11 + no viewport).
- **GUESS / DANGER**:
  1. **ABSENCE of WhatsApp/widget via static HTML = common FALSE POSITIVE** — JS-injected float buttons need headless render first. **ALWAYS render-then-parse the conversion layer** or you destroy credibility in the pitch.
  2. axe catches only ~30-50% of WCAG — say "at least N issues", never "fully accessible".
  3. CrUX field data absent for SMBs — NEVER show lab as if it were real-user; label synthetic vs real.
  4. CrUX API has no Brazil filter (only CrUX BigQuery `country='br'` does).

---

## 2. Brain 2 — Audit company WITHOUT site

### Free tools/repos (Google Business + social + reviews + reputation BR)

| Dimension | Tool / repo | Returns | Cost |
|---|---|---|---|
| **GBP existence + completeness + competitor pack (WORKHORSE)** | gosom/google-maps-scraper (Go, MIT, ~4.4k★, no API key) | name/address/phone/website/rating/review_count/per-star/hours/lat-lng/category, ~120 places/min; `-extra-reviews` ≈ 300 reviews w/ timestamps. CLI+Docker+REST+WebUI, has a Claude Code skill | Free (scrape). VM only |
| **Findability / local-pack (LOWEST ToS RISK)** | Serper.dev | structured Google Maps/Local JSON + local-pack position. Google never sees your scraper | 2,500 free one-time, then ~$1/1k |
| Findability backups | SerpApi (250/mo, 50/hr), serpstack (100/mo) | same | Free tiers |
| **Instagram** | instaloader (MIT, 12.1k★) ANONYMOUS mode | followers, mediacount→frequency, post timestamps, likes/comments→engagement | Free, low risk single-prospect |
| IG fallback (rate-limited) | subzeroid/instagrapi | richer fields, REQUIRES LOGIN — disposable account ONLY | Free, high ban risk |
| **Facebook** | kevinzg/facebook-scraper (MIT, 3.2k★) | followers/about, post frequency, engagement, no API key | Free |
| FB fallback | shaikhsajid1111/facebook_page_scraper (Selenium) | JSON/CSV | Free |
| **Map cross-check** | Overpass API / OpenStreetMap | is the business even mapped? | Free, no key |
| **Reviews + sentiment (BR)** | LeIA (rafjaa, VADER-pt, CPU-instant) / pysentimiento (BERTabaporu, SOTA PT) | pt-BR review sentiment | Free, local |
| Reputation (BR-specific) | ReclameAqui internal JSON API (iosearch/iosite raichu) | reputation score, complaint counts, response/resolution rate | Free, undocumented |
| No-code visual deliverable | Localo / GMBapi / GMB Radar free tiers | geo-grid heatmap screenshot | Free tiers |

### ToS / scraping-risk reality (honest)
Google Maps / IG / FB **all forbid scraping in their ToS** — this is **contract breach, not a crime** (hiQ v. LinkedIn supports public-data scraping legality). Enforcement is technical: temp IP bans (15-60 min); **IG account suspension is the one genuinely costly outcome**. Mitigation: low volume (one prospect at a time), 2-5s randomized delays, rotate UA, prefer a Brazilian residential IP, isolate any logged-in IG to a throwaway. **SERP APIs are the safest vector** (Google never sees you). **All browser scrapers run on the VM, never the PC** (project guardrail). For single-prospect audits the footprint is tiny and risk is low.

### The output: "digital gap vs competitors"
One normalized record: `{gbp_exists, completeness_0_100, local_pack_rank, ig_followers, ig_post_freq_per_wk, ig_engagement_rate, fb_followers, fb_last_post_age, competitor_median_*}`. Pitch line: *"You have 11 reviews and 4 photos; the top 3 barbearias in your bairro have 180+ reviews and 40+ photos. You don't appear in the Google map when someone searches 'barbearia Cuiaba'. Your last Instagram post was 8 months ago."* The strongest pitch when truly absent everywhere: **"you do not exist online."**

### Honesty
- **FACT** (cite directly): GBP existence, photo count, review count + rating + per-star, hours y/n, phone/address, appears-in-local-pack at a given query+location, IG/FB followers, post count, last-post date, presence on OSM. Read straight off live listings.
- **ESTIMATE** (label the sample): engagement rate over last ~12 posts; completeness 0-100 is YOUR weighted checklist, not a Google score; local-pack GRID rank is point-dependent (report "sampled at N points", not absolute).
- **GUESS / don't oversell**: "claimed vs unclaimed" often not exposed — don't assert when ambiguous; Reels play counts not always exposed (note as gap, never fabricate); competitor set = "top N for query Q", NEVER "all competitors".

---

## 3. Brain 3 — Estimate current revenue

### BR free data sources
- **NOT AVAILABLE free (set owner expectations)**: Receita Federal per-firm revenue, MEI/Simples declared faturamento, Serasa credit-bureau revenue bands, paid footfall (Placer.ai). **No $0 source gives true BR SMB revenue.**
- **What IS free**:
  - **CNPJ `porte` / Simples bracket** (Receita Federal open CNPJ data, e.g. via free ReceitaWS/BrasilAPI/minhareceita) → company SIZE class (MEI / ME / EPP) = a legal revenue CEILING band, not actual revenue. **FACT but coarse** (MEI ≤ R$81k/yr; ME ≤ R$360k; EPP ≤ R$4.8M).
  - **Google Maps review_count + rating + per-star + review TIMESTAMPS** (gosom) → **review velocity** (reviews/month) = best free demand proxy. **FACT (the count); ESTIMATE (the demand inference).**
  - **GBP category** → drives the ticket assumption (barbearia vs restaurante vs oficina).
  - **IG/FB followers + post frequency** → secondary scale signal.
  - **Competitor set (same query)** → relative rank (the defensible output).
  - Sector benchmarks: **SEBRAE / IBGE** publish sector-level averages (ticket, margins) — useful as a documented assumption band, NOT firm-specific.

### The proxy model (review-count → revenue range)
`reviews/month` (FACT from timestamps) × `review-rate assumption` (~1-5% of customers leave a review — NOT measured) → `customers/month` × `category average ticket` (assumed BRL) → **revenue RANGE**. Every multiplier is configurable and printed in the output. Cross-check the ceiling against CNPJ `porte`. Core IP = a small pandas model; trivial to write.

### HONESTY — estimate-with-range, state confidence
- **FACT (~80%, directly observed)**: review_count, rating, per-star, review timestamps → reviews/month, IG/FB followers, post frequency, GBP category, CNPJ porte band.
- **ESTIMATE (~30-40% absolute confidence)**: absolute BRL = product of TWO guesses (review-rate % + average ticket). The Luca/HBS Yelp study supports that reviews CORRELATE with revenue and rating moves revenue (~5-9%/star) but gives NO absolute BRL formula for a BR SMB. Wide error bars.
- **RELATIVE rank (~70%, fact-shaped)**: *"bottom quartile review velocity; 1/5 the reviews of the category leader."* **Lead with THIS.**
- **GUESS (FORBIDDEN as a number)**: any single point figure like "voce fatura R$45k/mes".
- **Anti-snake-oil rule**: ship a transparent range with every multiplier exposed; anchor credibility on the relative-vs-competitor facts and the CNPJ size band; explicitly tell the owner no free source gives true revenue.

---

## 4. Brain 4 — Project revenue uplift (the sales clincher)

### Sector uplift benchmarks (with sources — honest about strength)
- **ONLY empirical anchor in the research**: **Michael Luca (HBS), "Reviews, Reputation, and Revenue: The Case of Yelp.com"** → +1 star ≈ **+5-9% revenue**. Caveat: US restaurants — applying to BR multi-sector SMBs is **EXTRAPOLATION**, declare it as such.
- **Mobile-fix uplift**: derive a MEASURED input — PSI mobile delta (current vs potential CWV) + CrUX BigQuery `country='br'` as the only $0 BR-segmented CWV benchmark. The ms delta is FACT; "X ms faster = +Y sales" needs the business's conversion rate (unknown).
- **Ranking uplift**: local-pack position (Serper, FACT) × CTR-by-position curve (third-party data, not the prospect's) = ESTIMATE.
- **GBP creation / channels**: no $0 BR-specific benchmark exists in the research — this is the weakest chain.

### Defensible projection method (conservative / likely / optimistic)
Hybrid extract-then-score: deterministic pandas measures the inputs → produces **min-median-max** scenarios → Claude writes the narrative with every premise visible. Example: *"Assuming average ticket R$X and 3% conversion, fixing mobile (LCP 6.8s→2.4s, measured) projects +R$A to +R$C/month (median R$B)."* **Never a single cravado number.**

### HONESTY + ethics (BR consumer law, no overpromise)
- **FACT (input layer)**: review_count, local-pack position, followers, PSI mobile score, CWV delta, numeric gap vs competitor median.
- **ESTIMATE (acceptable IF exposed)**: review→customer multiplier (1-10%, unmeasured); star→R$ via Luca coefficient (US, extrapolated); rank→traffic via CTR curve; mobile-fix→sales via ticket+conversion (unknown for the prospect).
- **GUESS (FORBIDDEN)**: "site novo = +R$Z faturamento" with zero measured input from the business.
- **GOLDEN RULE**: always a range + the premise ("assuming ticket R$X and 3% conversion"). Hide the premises → lose credibility at the prospect's first question. Show them → it becomes a trust tool.
- **Ethics / CDC (BR)**: no guaranteed-result claims (Codigo de Defesa do Consumidor forbids misleading advertising); frame as "estimated potential", document assumptions, default to the **conservative** scenario for the headline.
- **Weakest link**: no $0 BR-specific ticket/conversion-by-sector source — fill via SEBRAE/IBGE sector benchmark, ask the prospect, or leave editable.

---

## 5. How the 4 brains combine into ONE prospect dossier

### The end artifact (per company)
```
PROSPECT DOSSIER
├─ identity: name, CNPJ, porte band, category, bairro, Cuiaba/VG
├─ brain_routing: has_site? → Brain1 ; else → Brain2  (both if partial)
├─ Brain1 (if site): perf_score, cwv{lcp,inp,cls}, seo_findings[],
│    tech_stack[], security{tls,cert_days,headers}, conversion{whatsapp,form,cta},
│    a11y_violations, problem_list[] (severity + pt-BR sentence)
├─ Brain2 (always useful): gbp{exists,completeness,reviews,rating,photos},
│    local_pack_rank, ig{followers,freq,engagement,last_post}, fb{...},
│    osm_present, reputation{reclameaqui}, competitor_median_*, gap_summary[]
├─ Brain3: revenue_range_low/median/high, confidence, assumptions[],
│    relative_rank_vs_competitors  ← LEAD WITH THIS
└─ Brain4: uplift_scenarios[{intervention, conservative, likely, optimistic, premises[]}]
```
**The story**: facts first (broken site / invisible on Google / dead Instagram) → relative gap vs competitors (the persuasive, defensible core) → honest revenue range → projected uplift per intervention, conservative headline.

### How it feeds Geronimo (sales) + Vuecra (site)
- **Geronimo (sales/outreach)**: consumes `problem_list[]` + `gap_summary[]` + `relative_rank` + conservative uplift line → personalized pt-BR opener ("notei que voce nao aparece no Google pra 'X Cuiaba' e seus 3 concorrentes tem 180+ reviews...").
- **Vuecra (site builder)**: consumes Brain1 `problem_list[]` + Brain2 `gbp/social gaps` as the brief for what the new site/presence must fix → closes the loop (audit finds the gap, Vuecra builds the fix, Geronimo sells it).

---

## 6. The $0 audit tech-stack (consolidated)

### Final shortlist
**Cross-cutting**: Python + pandas (calc/ranges), hybrid extract-then-score architecture (deterministic metrics → Claude narrative), Playwright/Patchright **on VM only**.

**Brain 1 (with site)**: PageSpeed Insights API v5 + GoogleChrome/lighthouse + CrUX API · extruct + advertools + BeautifulSoup4 · s0md3v/wappalyzer-next · sslyze + shcheck (+ testssl.sh) · axe-core/pa11y · trafilatura · custom conversion-detector (BS4 over rendered HTML).

**Brain 2 (no site)**: gosom/google-maps-scraper (workhorse) + Serper.dev (findability) · instaloader (anon) · kevinzg/facebook-scraper · Overpass/OSM · LeIA/pysentimiento (if review text) · ReclameAqui internal API · Localo/GMBapi (visual).

**Brain 3 (revenue)**: gosom (review velocity) + pandas proxy model + CNPJ porte (BrasilAPI/ReceitaWS) + SEBRAE/IBGE sector benchmarks + competitor pull.

**Brain 4 (uplift)**: Luca/HBS coefficient + pandas scenarios + PSI mobile delta + CrUX BigQuery `country='br'` + Serper local-pack rank.

### Genuinely free vs has limits
- **Truly $0, unlimited-ish**: lighthouse self-hosted, extruct, advertools, BS4, sslyze, shcheck, testssl.sh, trafilatura, axe/pa11y, instaloader (anon), kevinzg/facebook-scraper, Overpass, LeIA/pysentimiento, pandas, gosom (compute-bound, no quota).
- **Free with a key**: PSI API (25k/day), CrUX API (150 qpm), CrUX BigQuery (1TB/mo) — **one free Google Cloud key for all three**.
- **Finite free tiers (cache + reuse!)**: Serper.dev 2,500 one-time, SerpApi 250/mo, serpstack 100/mo. Reuse ONE Cuiaba category pull for target + competitors.
- **Free but ToS/ban risk**: all scrapers (gosom, instaloader, FB, ReclameAqui) — low at single-prospect volume, VM-only.
- **Not free at all**: real per-firm BR revenue (Receita declared, Serasa, Placer.ai) — does not exist at $0.

---

## 7. Open decisions + what's still uncertain (honest)

**Owner must decide**:
1. **Single-prospect on-demand vs batch lead-gen?** Batch sharply raises ToS/ban risk and burns finite SERP tiers → changes whether self-hosted (unlimited, higher detection) or SERP-API (capped, safe) is primary.
2. **Output format**: machine JSON for Hermes pitch-gen only, or also a client-facing PDF / geo-grid heatmap screenshot? (The converting product is the pt-BR SENTENCE, not the JSON.)
3. **GPL contamination**: Hermes ships closed? wappalyzer-next (GPL-3.0) and trafilatura (GPL/Apache) → call as arms-length CLI subprocess, don't import as lib.
4. **Revenue/uplift posture**: ranges-only with visible premises (research-supported) or a single number for the pitch (snake-oil risk the research will NOT back)? Conservative vs optimistic default scenario?
5. **Ticket + conversion by sector**: no $0 BR-specific source found — SEBRAE/IBGE generic benchmark, ask the prospect, or editable input?
6. **IG fallback**: allow a disposable throwaway IG for instagrapi, or strictly anonymous-only (accept some profiles partially missing)?
7. **Residential BR IP/proxy for the VM** or is the VM's IP acceptable? Affects ban risk + findability location accuracy.
8. **Google Cloud key**: confirm it exists / who provisions it. It is the ONLY external account the whole stack needs.

**Research gaps (need more digging)**:
- **roi-projection (Brain 4) is under-researched** — no dedicated thread; only the Luca anchor + inputs borrowed from brains 1-2. The input→R$ conversion chain (CTR curves, BR sector ticket/conversion) needs its own research pass.
- **Revenue calibration**: no ground-truth validation. Worth tracking 5-10 prospects where real revenue later surfaces, to calibrate multipliers above guess-level.
- **CrUX BigQuery `country='br'`**: only $0 path to BR-segmented field CWV but needs GCP+SQL setup — confirm it's worth the effort vs lab-only.
- **CNPJ porte → revenue**: porte gives a legal ceiling band, NOT actual revenue — don't overstate its precision.
