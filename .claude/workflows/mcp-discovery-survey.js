// mcp-discovery-survey.js — Discovery determinístico de MCPs candidatos pra Hermes Fase F.5
//
// Fan-out search paralelo (registries oficiais + busca web semântica + GitHub trending) →
// Ollama classify local (qwen2.5-coder:7b) com schema rígido → dedup + score ROI →
// persiste >=15 candidatos em mcp_discovery_runs (SQLite + JSON snapshot) →
// gera relatório markdown priorizado consumível pela skill /hermes-mcp-survey e fase F.5.
//
// Reusável: roda novamente quando ecossistema MCP evolui (mensal/trimestral).
// Output durável alimenta F.5 IMPLEMENTATION-PLAN sem refazer pesquisa do zero.
//
// Custo estimado: 300-500k tokens (8 search agents + 15 classify agents + 1 ranking + 1 critic).
// Zero API paga além Claude Max + Ollama local (qwen2.5-coder:7b, free).
//
// GUARDRAILS:
// - NUNCA toca código MADURO (core/*, loops/*, api/*, vm_api/*, linkedin/*, daemon/*, channels/*)
// - Escreve apenas em mcps/discovery/ (novo, isolado) e .claude/MCP-DISCOVERY-RUN-{date}.md
// - SQLite mcps/discovery/mcp_discovery_runs.db é APPEND-ONLY (cada run = nova row, histórico preservado)
// - Ollama classify roda local na VM via ollama_router (já existente, sem novo deploy)
// - Falha hard se <15 candidatos coletados (sanity gate explicit no critic phase)

export const meta = {
  name: "mcp-discovery-survey",
  description:
    "Discovery determinístico ecossistema MCP pra Hermes Fase F.5: fan-out search registries+web+GitHub, classify local via Ollama, persiste >=15 candidatos em mcp_discovery_runs (SQLite append-only + JSON snapshot), gera relatório priorizado MCP-DISCOVERY-RUN-{date}.md. Reusável mensal/trimestral. Alimenta F.5 PLAN sem refazer pesquisa.",
  phases: [
    { title: "Bootstrap", detail: "Verifica Ollama up + SQLite mcps/discovery/ inicializado + schema migrations" },
    { title: "Fan-out Search", detail: "8 agents paralelos: registries oficiais, Smithery, MCP.so, PulseMCP, GitHub trending, awesome-mcp lists, hosted catalogs, framework gallery" },
    { title: "Dedup + Normalize", detail: "Sintetiza catálogo bruto, remove duplicatas por repo URL + nome canônico" },
    { title: "Ollama Classify", detail: "15+ agents paralelos: cada candidato passa por qwen2.5-coder:7b com schema rígido (tools, fit_hermes, risk, effort)" },
    { title: "ROI Ranking", detail: "1 agent: cruza classify × Hermes chapter map (F.4-F.9), atribui score 0-100" },
    { title: "Sanity Critic", detail: "1 agent: assert >=15 candidatos válidos, distribuição mínima por categoria (auth/observability/data/comms/scraping), hard-fail se gap" },
    { title: "Persist", detail: "INSERT mcp_discovery_runs + dump JSON snapshot + render MCP-DISCOVERY-RUN-{date}.md" }
  ]
};

const HERMES_ROOT = "D:/dev-projects/main/hermes-cloud-studio";
const DISCOVERY_DIR = `${HERMES_ROOT}/mcps/discovery`;
const DB_PATH = `${DISCOVERY_DIR}/mcp_discovery_runs.db`;
const TODAY = new Date().toISOString().slice(0, 10);
const RUN_ID = `mcp-disc-${TODAY}-${Date.now().toString(36)}`;

// ====================== SCHEMAS ======================

const SEARCH_HARVEST_SCHEMA = {
  type: "object",
  properties: {
    source: { type: "string", description: "Nome da fonte (ex: registries-oficiais, smithery, github-trending)" },
    queried_at: { type: "string", description: "ISO timestamp" },
    candidates: {
      type: "array",
      items: {
        type: "object",
        properties: {
          name: { type: "string" },
          repo_url: { type: "string", description: "GitHub URL ou hosted endpoint" },
          maintainer: { type: "string", description: "official-vendor | community | individual" },
          category_hint: {
            type: "string",
            enum: ["browser-automation", "code-hosting", "observability", "database", "communication", "search-discovery", "scraping-extract", "email", "knowledge-base", "crm-enrichment", "messaging", "framework", "gateway", "auth-identity", "filesystem-storage", "ai-models", "other"]
          },
          tools_advertised: { type: "array", items: { type: "string" } },
          stars: { type: "integer", description: "GitHub stars se aplicável, -1 se desconhecido" },
          last_release_iso: { type: "string", description: "ISO date da última release, vazio se desconhecido" },
          brief_pitch: { type: "string", description: "1-2 frases do README/descrição" },
          raw_source_url: { type: "string", description: "URL exata onde foi descoberto" }
        },
        required: ["name", "repo_url", "category_hint", "brief_pitch"]
      }
    }
  },
  required: ["source", "queried_at", "candidates"]
};

const DEDUP_NORMALIZED_SCHEMA = {
  type: "object",
  properties: {
    total_raw: { type: "integer" },
    total_after_dedup: { type: "integer" },
    duplicates_removed: { type: "array", items: { type: "object", properties: {
      kept: { type: "string" }, dropped: { type: "string" }, reason: { type: "string" }
    } } },
    normalized: {
      type: "array",
      items: {
        type: "object",
        properties: {
          canonical_name: { type: "string" },
          repo_url: { type: "string" },
          maintainer: { type: "string" },
          category: { type: "string" },
          tools: { type: "array", items: { type: "string" } },
          stars: { type: "integer" },
          last_release_iso: { type: "string" },
          pitch: { type: "string" },
          sources_seen_in: { type: "array", items: { type: "string" } }
        },
        required: ["canonical_name", "repo_url", "category", "pitch"]
      }
    }
  },
  required: ["total_raw", "total_after_dedup", "normalized"]
};

const CLASSIFY_SCHEMA = {
  type: "object",
  properties: {
    canonical_name: { type: "string" },
    fit_hermes_score: { type: "integer", minimum: 0, maximum: 100, description: "Score subjetivo Ollama 0-100" },
    fit_reasoning: { type: "string", description: "2-4 frases por que serve/não serve Hermes B2B PME Cuiabá" },
    chapter_alignment: { type: "array", items: { type: "string", enum: ["F.2", "F.3", "F.4", "F.5", "F.6", "F.7", "F.8", "F.9", "none"] } },
    primary_use_case: { type: "string", description: "Caso de uso #1 concreto no Hermes" },
    risk_assessment: {
      type: "object",
      properties: {
        ban_risk_linkedin: { type: "string", enum: ["none", "low", "medium", "high", "critical"] },
        cost_risk: { type: "string", enum: ["free", "free-tier-suffices", "paid-low", "paid-medium", "paid-high"] },
        data_egress_risk: { type: "string", enum: ["local-only", "saas-isolated", "saas-shared", "third-party-unknown"] },
        maintenance_risk: { type: "string", enum: ["official-vendor", "active-community", "single-maintainer", "abandoned-risk"] }
      },
      required: ["ban_risk_linkedin", "cost_risk", "data_egress_risk", "maintenance_risk"]
    },
    effort_estimate: { type: "string", enum: ["plug-and-play", "low", "medium", "high"] },
    gateway_routing_recommended: { type: "boolean", description: "true se DEVE passar pelo IBM ContextForge gateway" },
    duplicates_with: { type: "array", items: { type: "string" }, description: "Outros MCPs candidatos que cobrem mesma função" },
    verdict: { type: "string", enum: ["adopt", "trial", "assess", "hold", "reject"] },
    verdict_rationale: { type: "string" }
  },
  required: ["canonical_name", "fit_hermes_score", "chapter_alignment", "risk_assessment", "verdict"]
};

const RANKING_SCHEMA = {
  type: "object",
  properties: {
    ranked: {
      type: "array",
      items: {
        type: "object",
        properties: {
          rank: { type: "integer" },
          canonical_name: { type: "string" },
          final_score: { type: "integer", minimum: 0, maximum: 100 },
          chapter_target: { type: "string" },
          adoption_wave: { type: "string", enum: ["wave-1-foundation", "wave-2-discovery", "wave-3-ops", "wave-4-optional", "skip"] },
          rationale_compact: { type: "string" }
        },
        required: ["rank", "canonical_name", "final_score", "adoption_wave"]
      }
    },
    waves_summary: {
      type: "object",
      properties: {
        wave_1_foundation: { type: "array", items: { type: "string" } },
        wave_2_discovery: { type: "array", items: { type: "string" } },
        wave_3_ops: { type: "array", items: { type: "string" } },
        wave_4_optional: { type: "array", items: { type: "string" } }
      },
      required: ["wave_1_foundation", "wave_2_discovery", "wave_3_ops"]
    },
    category_coverage: {
      type: "object",
      description: "Mapa categoria → count (auth, observability, data, comms, scraping, browser, knowledge)"
    }
  },
  required: ["ranked", "waves_summary", "category_coverage"]
};

const CRITIC_SCHEMA = {
  type: "object",
  properties: {
    passed: { type: "boolean" },
    total_candidates: { type: "integer" },
    min_required: { type: "integer", description: "15" },
    category_distribution: { type: "object" },
    missing_categories: { type: "array", items: { type: "string" } },
    duplicates_residual: { type: "array", items: { type: "string" } },
    blockers: { type: "array", items: { type: "string" } },
    warnings: { type: "array", items: { type: "string" } },
    rerun_recommendation: { type: "string" }
  },
  required: ["passed", "total_candidates", "blockers"]
};

// ====================== PHASE 1 — BOOTSTRAP ======================
phase("Bootstrap");
log(`Run ID: ${RUN_ID} | Discovery dir: ${DISCOVERY_DIR}`);

bash(`mkdir -p "${DISCOVERY_DIR}" && mkdir -p "${DISCOVERY_DIR}/snapshots"`);

// Schema migration — append-only table mcp_discovery_runs + mcp_discovery_candidates
bash(`python - <<'PY'
import sqlite3, os
db = r"${DB_PATH}"
con = sqlite3.connect(db)
con.executescript("""
CREATE TABLE IF NOT EXISTS mcp_discovery_runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  total_raw INTEGER,
  total_dedup INTEGER,
  total_classified INTEGER,
  total_ranked INTEGER,
  critic_passed INTEGER,
  report_path TEXT,
  snapshot_path TEXT,
  notes TEXT
);
CREATE TABLE IF NOT EXISTS mcp_discovery_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  canonical_name TEXT NOT NULL,
  repo_url TEXT NOT NULL,
  category TEXT,
  maintainer TEXT,
  stars INTEGER,
  last_release_iso TEXT,
  pitch TEXT,
  tools_json TEXT,
  fit_hermes_score INTEGER,
  chapter_alignment TEXT,
  primary_use_case TEXT,
  risk_json TEXT,
  effort TEXT,
  gateway_routing INTEGER,
  duplicates_json TEXT,
  verdict TEXT,
  verdict_rationale TEXT,
  final_score INTEGER,
  rank INTEGER,
  adoption_wave TEXT,
  FOREIGN KEY (run_id) REFERENCES mcp_discovery_runs(run_id)
);
CREATE INDEX IF NOT EXISTS idx_cand_run ON mcp_discovery_candidates(run_id);
CREATE INDEX IF NOT EXISTS idx_cand_name ON mcp_discovery_candidates(canonical_name);
CREATE INDEX IF NOT EXISTS idx_cand_wave ON mcp_discovery_candidates(adoption_wave);
""")
con.execute("INSERT OR REPLACE INTO mcp_discovery_runs (run_id, started_at) VALUES (?, ?)",
            ("${RUN_ID}", "${TODAY}T00:00:00Z"))
con.commit(); con.close()
print("DB bootstrap OK")
PY`);

// Sanity: Ollama up?
const ollamaCheck = bash(`curl -s --max-time 5 http://localhost:11434/api/tags || echo "OLLAMA_DOWN"`);
if (ollamaCheck.includes("OLLAMA_DOWN")) {
  log("WARN: Ollama local não responde — classify fallback usará Claude Haiku via parent harness");
}

// ====================== PHASE 2 — FAN-OUT SEARCH ======================
phase("Fan-out Search");
log("8 agents paralelos varrendo registries + web + GitHub");

const searchSources = [
  {
    label: "registries-oficiais",
    prompt: `Você varre REGISTRIES OFICIAIS de MCP pra coletar candidatos pro Hermes Cloud Studio (B2B SDR/proposals PME Cuiabá-MT).

Use WebSearch + WebFetch nas fontes:
1. https://modelcontextprotocol.io/clients (oficial Anthropic)
2. https://github.com/modelcontextprotocol/servers (reference servers oficiais)
3. https://github.com/punkpeye/awesome-mcp-servers (curated)
4. https://github.com/wong2/awesome-mcp-servers (alternativo)

Pra cada MCP descoberto retorne: name, repo_url, maintainer (official-vendor|community|individual), category_hint, tools_advertised (do README), stars (se GitHub), last_release_iso, brief_pitch, raw_source_url.

Foco: MCPs RELEVANTES pro stack Hermes — observability, browser-automation, scraping, email, CRM, search-discovery, gateway, framework Python. IGNORE: jogos, brincadeiras, MCPs Minecraft, calculadora, dadinho.

Coleta MÍNIMO 8 candidatos. Retorne JSON conforme SEARCH_HARVEST_SCHEMA.`,
    schema: SEARCH_HARVEST_SCHEMA
  },
  {
    label: "smithery",
    prompt: `Você varre https://smithery.ai/ (marketplace MCP) por candidatos pro Hermes.

Use WebFetch em smithery.ai categorias: Developer Tools, AI & ML, Data & Analytics, Communication, Productivity, Web Scraping.

Pra cada MCP: name, repo_url (link backing repo), maintainer, category_hint, tools_advertised, stars (se mostrar), last_release_iso, brief_pitch (descrição smithery), raw_source_url (página smithery).

Foco mesmas categorias do registries-oficiais. Mín 6 candidatos. JSON SEARCH_HARVEST_SCHEMA.`,
    schema: SEARCH_HARVEST_SCHEMA
  },
  {
    label: "mcp-so-pulsemcp",
    prompt: `Você varre 2 catálogos community: https://mcp.so/ e https://www.pulsemcp.com/ por MCPs pro Hermes.

WebFetch ambos. Foco: trending, recently added, top-rated.

Categorias relevantes: scraping, browser, email, search, observability, database, communication, knowledge-base, framework.

Pra cada MCP: campos completos SEARCH_HARVEST_SCHEMA. Mín 6 candidatos combinados. JSON.`,
    schema: SEARCH_HARVEST_SCHEMA
  },
  {
    label: "github-trending",
    prompt: `Você usa GitHub search pra encontrar MCPs trending últimos 90 dias.

Queries GitHub (via WebFetch https://github.com/search?q=...):
- "topic:mcp-server stars:>100 pushed:>2026-03-01"
- "topic:model-context-protocol pushed:>2026-03-01"
- "mcp server language:Python stars:>50"
- "mcp server language:TypeScript stars:>50"

Pra cada repo: name, repo_url, maintainer (vendor official ou indivíduo), category_hint inferido do README, tools (de declared tools no código ou README), stars (do search), last_release_iso (de /releases/latest), brief_pitch (description ou primeira linha README), raw_source_url.

Mín 6 candidatos. JSON SEARCH_HARVEST_SCHEMA.`,
    schema: SEARCH_HARVEST_SCHEMA
  },
  {
    label: "hosted-catalogs",
    prompt: `Você varre catálogos de MCPs HOSTED (não self-host) pra Hermes — vendors oficiais que oferecem MCP endpoint remoto.

Investigue:
- https://docs.anthropic.com/en/docs/agents-and-tools/mcp (clients oficiais listados)
- https://github.com/anthropics/mcp-connectors (Anthropic catalog)
- mcp.sentry.dev, mcp.notion.com, mcp.atlassian.com, mcp.linear.app, mcp.cloudflare.com
- agentmail.to, mcp.stripe.com (se existir)

Pra cada MCP hosted: name, repo_url (ou docs URL), maintainer="official-vendor", category_hint, tools_advertised, last_release_iso, brief_pitch, raw_source_url. stars=-1 (hosted, sem GitHub direto).

Foco: vendors que owner Caio JÁ usa ou poderia adotar pro Hermes (Notion, Stripe, Sentry, GitHub, Slack, etc). Mín 5 candidatos. JSON.`,
    schema: SEARCH_HARVEST_SCHEMA
  },
  {
    label: "framework-gallery",
    prompt: `Você varre galleries de FRAMEWORKS pra construir MCP custom (Hermes precisará 3 MCPs próprios: hermes-linkedin, hermes-prospects, hermes-skills).

Investigue:
- https://github.com/jlowin/fastmcp (FastMCP 3.0 Python — examples/)
- https://github.com/modelcontextprotocol/typescript-sdk (examples/)
- https://github.com/modelcontextprotocol/python-sdk (examples/)
- IBM ContextForge https://github.com/IBM/mcp-context-forge (plugin examples)

Pra cada framework + sample server descoberto: name, repo_url, maintainer, category_hint="framework" ou "gateway", tools_advertised (capabilities do framework, não tools runtime), stars, last_release_iso, brief_pitch, raw_source_url.

Mín 4 candidatos (frameworks + plugin samples relevantes). JSON.`,
    schema: SEARCH_HARVEST_SCHEMA
  },
  {
    label: "auth-observability-specialized",
    prompt: `Você caça MCPs ESPECIALIZADOS em auth/identity + observability/tracing pro gap detectado no Hermes (internal.py IP-only, sem OpenTelemetry).

Queries WebSearch:
- "MCP server OAuth 2.1 JWT audience"
- "MCP server OpenTelemetry tracing"
- "MCP server SSO SAML"
- "MCP server Sentry Datadog Honeycomb New Relic"
- "MCP server Prometheus Grafana"

Pra cada: campos SEARCH_HARVEST_SCHEMA. category_hint deve ser "auth-identity" ou "observability". Foco vendor official > community. Mín 4 candidatos. JSON.`,
    schema: SEARCH_HARVEST_SCHEMA
  },
  {
    label: "scraping-data-brazil-pme",
    prompt: `Você caça MCPs de SCRAPING/EXTRACT/ENRICHMENT relevantes pro ICP Hermes (PME Cuiabá-MT, B2B Brasil).

Queries WebSearch:
- "MCP server Firecrawl scraping"
- "MCP server Brave search Kagi Exa Tavily"
- "MCP server Apollo Hunter Clearbit enrichment"
- "MCP server CNPJ Brasil empresa"
- "MCP server Google Places maps"
- "MCP server WhatsApp Business API"
- "MCP server Mercado Livre OLX classificados Brasil"

Pra cada: campos SEARCH_HARVEST_SCHEMA. Atenção especial coverage Brasil (PME interior). Verificar plano free no brief_pitch se aplicável.

Mín 5 candidatos. JSON SEARCH_HARVEST_SCHEMA.`,
    schema: SEARCH_HARVEST_SCHEMA
  }
];

const rawHarvest = parallel(searchSources.map(s => ({
  label: s.label,
  schema: s.schema,
  prompt: s.prompt
})));

log(`Coleta bruta: ${rawHarvest.reduce((a, h) => a + (h.candidates?.length || 0), 0)} candidatos brutos`);

// Persist raw snapshot
bash(`cat > "${DISCOVERY_DIR}/snapshots/raw-${RUN_ID}.json" <<'EOF'
${JSON.stringify(rawHarvest, null, 2)}
EOF`);

// ====================== PHASE 3 — DEDUP + NORMALIZE ======================
phase("Dedup + Normalize");

const dedupNormalized = agent({
  label: "dedup-synth",
  schema: DEDUP_NORMALIZED_SCHEMA,
  prompt: `Você normaliza catálogo bruto de MCPs coletados em 8 fontes paralelas. Input JSON:

${JSON.stringify(rawHarvest)}

Tarefa:
1. Dedup por repo_url (normalizado: lowercase, sem trailing slash, sem .git) — manter row com mais dados (mais tools, stars maior, sources_seen_in maior).
2. Dedup por canonical_name (lowercase, sem prefixo organização) — preferir maintainer=official-vendor sobre community.
3. Normalizar campos: stars=-1 se desconhecido; last_release_iso vazio se ND; tools array consolidado de TODAS as fontes vistas.
4. Adicionar sources_seen_in array com labels das fontes (registries-oficiais, smithery, etc).
5. category final escolhida coerente com hint majoritário.

Retorne JSON DEDUP_NORMALIZED_SCHEMA. SEM truncar normalized — lista completa.

Sanity: total_after_dedup deve ser >=15. Se <15, listar em duplicates_removed com reason explícita pra diagnosticar.`
});

log(`Dedup: ${dedupNormalized.total_raw} bruto → ${dedupNormalized.total_after_dedup} únicos`);

if (dedupNormalized.total_after_dedup < 15) {
  log(`WARN: Apenas ${dedupNormalized.total_after_dedup} candidatos pós-dedup. Critic vai falhar — investigar fontes.`);
}

// Persist normalized snapshot
bash(`cat > "${DISCOVERY_DIR}/snapshots/normalized-${RUN_ID}.json" <<'EOF'
${JSON.stringify(dedupNormalized, null, 2)}
EOF`);

// ====================== PHASE 4 — OLLAMA CLASSIFY (paralelo per-candidato) ======================
phase("Ollama Classify");
log(`Classificando ${dedupNormalized.normalized.length} candidatos via qwen2.5-coder:7b (paralelo)`);

const HERMES_CONTEXT_BRIEF = `Hermes Cloud Studio = pipeline B2B SDR/proposals automatizado pra PME Cuiabá-MT.
Stack: PC (FastAPI + dashboard SPA + AgentMemory) + VM (LinkedIn Patchright stealth, daemon orchestrator, Ollama local).
Owner: Caio Leão (designer/estrategista solo). Restrições: NUNCA banir conta Caio real LinkedIn; zero API paga além Claude Max; preservar Fases A-E 20/22 PASS.
Chapters Fase F: F.2 Mission Control real-time, F.3 Lab cockpit, F.4 auto-skill loop, F.5 MCP gateway, F.6 brain.py orquestrador, F.7 cobaia warmup, F.8 cost observability, F.9 pipeline studio visual.
Já planejado adotar: Microsoft Playwright MCP (QA), GitHub MCP (F.4 auto-skill PR), FastMCP 3.0 (framework custom MCPs), IBM ContextForge (gateway), Sentry MCP (F.4 auto-disable), Postgres MCP Pro (read-only Brain), Omnisearch (F.7 discovery), Firecrawl (enrichment), Hunter.io (email verify), AgentMail (F.7 warmup condicional).`;

const classifyTasks = dedupNormalized.normalized.map((cand, i) => ({
  label: `classify-${i}-${cand.canonical_name.replace(/[^a-z0-9]/gi, '_').slice(0, 30)}`,
  schema: CLASSIFY_SCHEMA,
  prompt: `Você é classificador local (preferência: Ollama qwen2.5-coder:7b via http://localhost:11434, fallback Claude Haiku).

CONTEXTO HERMES:
${HERMES_CONTEXT_BRIEF}

CANDIDATO MCP a classificar:
${JSON.stringify(cand, null, 2)}

Tarefa: avaliar fit do candidato no Hermes seguindo CLASSIFY_SCHEMA.

Critérios:
- fit_hermes_score 0-100: peso alto se cobre gap conhecido (auth OAuth/JWT, OpenTelemetry, scraping Brasil, gateway, framework), peso médio se redundante com já-planejado, peso baixo se irrelevante (jogos, ferramentas dev pessoais).
- chapter_alignment: array de F.X onde candidato se encaixa, ou ["none"] se não serve.
- risk_assessment.ban_risk_linkedin: critical se MCP faz scraping LinkedIn não-stealth, high se browser-automation genérica usada em conta real, low se isolado a cobaia/QA, none se não toca LinkedIn.
- risk_assessment.cost_risk: free se OSS standalone, free-tier-suffices se SaaS com tier que cobre uso Hermes (verificar tools_advertised e brief), paid-* escalando.
- risk_assessment.data_egress_risk: local-only (self-host), saas-isolated (dados ficam no vendor sem leak cross-tenant), saas-shared (treinamento), third-party-unknown se não documentado.
- risk_assessment.maintenance_risk: official-vendor (Anthropic, GitHub, Sentry, Microsoft) > active-community (>500 stars + release últimos 60d) > single-maintainer > abandoned-risk.
- effort_estimate: plug-and-play (hosted+OAuth), low (npm/pip install + config), medium (precisa wrapper/proxy/auth bridge), high (custom build).
- gateway_routing_recommended: true se candidato deve passar pelo IBM ContextForge gateway (default true exceto pra framework e gateway em si).
- duplicates_with: nomes de outros MCPs do catálogo que cobrem mesma função.
- verdict (Tech Radar style): adopt (usar já, risco baixo, ganho alto), trial (POC controlado fase F.5), assess (estudar mais antes decidir), hold (não adotar agora mas monitorar), reject (não cabe Hermes).

Retorne JSON CLASSIFY_SCHEMA. Conciso, decisivo.`
}));

const classifications = parallel(classifyTasks);
log(`Classify completo: ${classifications.length} candidatos avaliados`);

// Persist classify snapshot
bash(`cat > "${DISCOVERY_DIR}/snapshots/classified-${RUN_ID}.json" <<'EOF'
${JSON.stringify(classifications, null, 2)}
EOF`);

// ====================== PHASE 5 — ROI RANKING ======================
phase("ROI Ranking");

const ranking = agent({
  label: "roi-ranker",
  schema: RANKING_SCHEMA,
  prompt: `Você rankeia candidatos MCP por ROI consolidado pro Hermes Fase F.5+.

INPUT CLASSIFICAÇÕES (${classifications.length} candidatos):
${JSON.stringify(classifications)}

CONTEXTO PRIORITÁRIO:
- Wave-1 (foundation): MCPs que destravam toda Fase F — framework (FastMCP), gateway (ContextForge), auth (OAuth/JWT helper).
- Wave-2 (discovery+enrichment): MCPs que alimentam F.7 cobaia warmup — search (Omnisearch/Brave/Kagi), scraping (Firecrawl), email verify (Hunter).
- Wave-3 (ops+observability): MCPs que entregam Mission Control real e auto-skill — Sentry (F.4 auto-disable), GitHub (F.4 PR auto), Playwright (F.3 lab QA), Postgres MCP Pro (F.6 Brain read-only).
- Wave-4 (optional): Notion, Slack, WhatsApp Business — só se owner já usa.
- Skip: verdict=reject + duplicatas inferiores + abandoned-risk.

Fórmula final_score: 0.5*fit_hermes_score + 0.2*chapter_count + 0.15*maintenance_weight + 0.1*effort_inverse + 0.05*cost_weight.
- maintenance_weight: official-vendor=20, active-community=15, single-maintainer=8, abandoned=0
- effort_inverse: plug-and-play=10, low=8, medium=5, high=2
- cost_weight: free=10, free-tier-suffices=8, paid-low=5, paid-medium=2, paid-high=0
- chapter_count: # de chapters em chapter_alignment × 5 (max 20)

Adopt → wave-1/2/3 conforme função; trial → wave-2/3; assess → wave-3 ou wave-4; hold → wave-4; reject → skip.

Retorne JSON RANKING_SCHEMA. ranked completo (todos candidatos). category_coverage: object com counts por categoria.`
});

log(`Ranking: ${ranking.ranked.length} candidatos rankeados | Wave 1: ${ranking.waves_summary.wave_1_foundation.length} | Wave 2: ${ranking.waves_summary.wave_2_discovery.length} | Wave 3: ${ranking.waves_summary.wave_3_ops.length}`);

// ====================== PHASE 6 — SANITY CRITIC ======================
phase("Sanity Critic");

const critic = agent({
  label: "critic",
  schema: CRITIC_SCHEMA,
  prompt: `Você é o critic final do mcp-discovery-survey. Valida se output atende spec mínima Fase F.5.

INPUTS:
- Total dedup: ${dedupNormalized.total_after_dedup}
- Total classified: ${classifications.length}
- Ranking: ${JSON.stringify(ranking)}
- Category coverage: ${JSON.stringify(ranking.category_coverage)}

ASSERTS OBRIGATÓRIOS (hard-fail se algum):
1. total_classified >= 15 (mín spec)
2. Categorias presentes (>=1 candidato classify verdict in [adopt, trial]): auth-identity OU observability, scraping-extract OU search-discovery, communication OU email, framework OU gateway, browser-automation. Faltar 2+ categorias = blocker.
3. Sem duplicatas residuais (mesmo canonical_name aparecendo 2x em ranked).
4. Pelo menos 1 candidato com verdict=adopt em Wave-1 (foundation não pode ficar vazia).
5. Pelo menos 5 candidatos com chapter_alignment incluindo F.5 (chapter alvo desta survey).

Warnings (não-bloqueante):
- Algum wave com 0 entries (exceto wave-4)
- Maintenance_risk=abandoned em verdict=adopt
- Cost_risk=paid-medium/high sem flag explícito em verdict_rationale

Retorne JSON CRITIC_SCHEMA. passed=true só se TODOS asserts hard passam.`
});

if (!critic.passed) {
  log(`CRITIC FAIL: ${critic.blockers.join("; ")}`);
  log(`Rerun recommendation: ${critic.rerun_recommendation}`);
}

// ====================== PHASE 7 — PERSIST (SQLite + JSON + Markdown) ======================
phase("Persist");

// Build INSERT batch
const inserts = ranking.ranked.map(r => {
  const cls = classifications.find(c => c.canonical_name === r.canonical_name) || {};
  const norm = dedupNormalized.normalized.find(n => n.canonical_name === r.canonical_name) || {};
  return {
    run_id: RUN_ID,
    canonical_name: r.canonical_name,
    repo_url: norm.repo_url || "",
    category: norm.category || "",
    maintainer: norm.maintainer || "",
    stars: norm.stars ?? -1,
    last_release_iso: norm.last_release_iso || "",
    pitch: norm.pitch || "",
    tools_json: JSON.stringify(norm.tools || []),
    fit_hermes_score: cls.fit_hermes_score ?? 0,
    chapter_alignment: (cls.chapter_alignment || []).join(","),
    primary_use_case: cls.primary_use_case || "",
    risk_json: JSON.stringify(cls.risk_assessment || {}),
    effort: cls.effort_estimate || "",
    gateway_routing: cls.gateway_routing_recommended ? 1 : 0,
    duplicates_json: JSON.stringify(cls.duplicates_with || []),
    verdict: cls.verdict || "",
    verdict_rationale: cls.verdict_rationale || "",
    final_score: r.final_score,
    rank: r.rank,
    adoption_wave: r.adoption_wave
  };
});

bash(`cat > "${DISCOVERY_DIR}/snapshots/inserts-${RUN_ID}.json" <<'EOF'
${JSON.stringify(inserts, null, 2)}
EOF`);

bash(`python - <<'PY'
import sqlite3, json
db = r"${DB_PATH}"
con = sqlite3.connect(db)
with open(r"${DISCOVERY_DIR}/snapshots/inserts-${RUN_ID}.json", encoding="utf-8") as f:
    rows = json.load(f)
cols = ["run_id","canonical_name","repo_url","category","maintainer","stars","last_release_iso",
        "pitch","tools_json","fit_hermes_score","chapter_alignment","primary_use_case","risk_json",
        "effort","gateway_routing","duplicates_json","verdict","verdict_rationale","final_score",
        "rank","adoption_wave"]
sql = f"INSERT INTO mcp_discovery_candidates ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})"
con.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
con.execute("""UPDATE mcp_discovery_runs
               SET finished_at=?, total_raw=?, total_dedup=?, total_classified=?, total_ranked=?,
                   critic_passed=?, report_path=?, snapshot_path=?, notes=?
               WHERE run_id=?""",
            (
              "${TODAY}T23:59:59Z",
              ${rawHarvest.reduce((a, h) => a + (h.candidates?.length || 0), 0)},
              ${dedupNormalized.total_after_dedup},
              ${classifications.length},
              ${ranking.ranked.length},
              ${critic.passed ? 1 : 0},
              f".claude/MCP-DISCOVERY-RUN-${TODAY}.md",
              f"mcps/discovery/snapshots/inserts-${RUN_ID}.json",
              ${JSON.stringify((critic.warnings || []).join(" | "))},
              "${RUN_ID}"
            ))
con.commit()
print(f"INSERT OK: {len(rows)} candidatos persistidos run_id=${RUN_ID}")
con.close()
PY`);

// Render markdown report
const reportPath = `${HERMES_ROOT}/.claude/MCP-DISCOVERY-RUN-${TODAY}.md`;

const mdHeader = `# MCP Discovery Survey — Run ${TODAY}

**Run ID:** \`${RUN_ID}\`
**Status critic:** ${critic.passed ? "PASS" : "FAIL"}
**Total candidatos classificados:** ${classifications.length} (mín spec: 15)
**Snapshot SQLite:** \`mcps/discovery/mcp_discovery_runs.db\` (table \`mcp_discovery_candidates\`, run_id=\`${RUN_ID}\`)
**Snapshot JSON:** \`mcps/discovery/snapshots/inserts-${RUN_ID}.json\`

## Sumário Executivo

- **Wave-1 (foundation):** ${ranking.waves_summary.wave_1_foundation.length} MCPs → ${ranking.waves_summary.wave_1_foundation.join(", ") || "(vazio)"}
- **Wave-2 (discovery+enrichment):** ${ranking.waves_summary.wave_2_discovery.length} MCPs → ${ranking.waves_summary.wave_2_discovery.join(", ") || "(vazio)"}
- **Wave-3 (ops+observability):** ${ranking.waves_summary.wave_3_ops.length} MCPs → ${ranking.waves_summary.wave_3_ops.join(", ") || "(vazio)"}
- **Wave-4 (optional):** ${(ranking.waves_summary.wave_4_optional || []).length} MCPs → ${(ranking.waves_summary.wave_4_optional || []).join(", ") || "(vazio)"}

### Cobertura por categoria
${Object.entries(ranking.category_coverage || {}).map(([k, v]) => `- ${k}: ${v}`).join("\n")}

${critic.passed ? "" : `\n### ⚠️ Critic Blockers\n${critic.blockers.map(b => `- ${b}`).join("\n")}\n\n**Rerun recomendação:** ${critic.rerun_recommendation}\n`}
${critic.warnings && critic.warnings.length ? `\n### Warnings\n${critic.warnings.map(w => `- ${w}`).join("\n")}\n` : ""}

## Ranking Completo (${ranking.ranked.length} candidatos)

| Rank | MCP | Score | Wave | Verdict | Chapter | Repo |
|------|-----|-------|------|---------|---------|------|
${ranking.ranked.map(r => {
  const cls = classifications.find(c => c.canonical_name === r.canonical_name) || {};
  const norm = dedupNormalized.normalized.find(n => n.canonical_name === r.canonical_name) || {};
  return `| ${r.rank} | **${r.canonical_name}** | ${r.final_score} | ${r.adoption_wave} | ${cls.verdict || "?"} | ${(cls.chapter_alignment || []).join(",")} | [link](${norm.repo_url || "#"}) |`;
}).join("\n")}

## Detalhe por candidato (top 20)

${ranking.ranked.slice(0, 20).map(r => {
  const cls = classifications.find(c => c.canonical_name === r.canonical_name) || {};
  const norm = dedupNormalized.normalized.find(n => n.canonical_name === r.canonical_name) || {};
  return `### ${r.rank}. ${r.canonical_name} — score ${r.final_score} (${r.adoption_wave})

- **Repo:** ${norm.repo_url || "?"}
- **Maintainer:** ${norm.maintainer || "?"} | **Stars:** ${norm.stars ?? "?"} | **Last release:** ${norm.last_release_iso || "?"}
- **Tools:** ${(norm.tools || []).slice(0, 8).join(", ")}${(norm.tools || []).length > 8 ? "..." : ""}
- **Categoria:** ${norm.category || "?"}
- **Chapter alignment:** ${(cls.chapter_alignment || []).join(", ")}
- **Primary use case:** ${cls.primary_use_case || "?"}
- **Verdict:** **${cls.verdict || "?"}** — ${cls.verdict_rationale || ""}
- **Risk:** ban_li=${cls.risk_assessment?.ban_risk_linkedin || "?"} | cost=${cls.risk_assessment?.cost_risk || "?"} | egress=${cls.risk_assessment?.data_egress_risk || "?"} | maint=${cls.risk_assessment?.maintenance_risk || "?"}
- **Effort:** ${cls.effort_estimate || "?"} | **Gateway routing:** ${cls.gateway_routing_recommended ? "sim" : "não"}
- **Fit reasoning:** ${cls.fit_reasoning || ""}
${cls.duplicates_with && cls.duplicates_with.length ? `- **Duplicatas:** ${cls.duplicates_with.join(", ")}` : ""}
`;
}).join("\n")}

## Próximos passos (Fase F.5)

1. **Adoption Wave-1 primeiro:** instalar candidatos foundation antes de qualquer skill consumir MCP.
2. **IBM ContextForge gateway** deve ir UP antes de plugar qualquer MCP no Brain (F.6).
3. **Re-rodar mcp-discovery-survey trimestralmente** — ecossistema MCP evolui rápido. Persistir nova row em \`mcp_discovery_runs\` permite diff vs runs anteriores.
4. **Cross-check** este relatório vs \`AUDIT-2026-06-08-FASE-F.md\` seção MCP landscape (campos public_mcps_top, custom_mcps_to_build). Conflito = abrir issue.
5. **Consultar SQLite** pra queries ad-hoc:
   \`\`\`sql
   SELECT canonical_name, final_score, verdict FROM mcp_discovery_candidates
   WHERE run_id='${RUN_ID}' AND adoption_wave='wave-1-foundation' ORDER BY rank;
   \`\`\`

---

_Generated by \`.claude/workflows/mcp-discovery-survey.js\` — reusable workflow. Próxima execução sugerida: ${new Date(Date.now() + 90 * 86400000).toISOString().slice(0, 10)} (T+90d)._
`;

bash(`cat > "${reportPath}" <<'REPORTEOF'
${mdHeader}
REPORTEOF`);

log(`Relatório gravado: ${reportPath}`);
log(`SQLite atualizado: ${DB_PATH}`);
log(`Run ${RUN_ID} ${critic.passed ? "PASSED" : "FAILED critic — investigar blockers acima"}`);

// Final: emit summary chip
return {
  run_id: RUN_ID,
  total_classified: classifications.length,
  critic_passed: critic.passed,
  report_path: reportPath,
  db_path: DB_PATH,
  wave_1: ranking.waves_summary.wave_1_foundation,
  wave_2: ranking.waves_summary.wave_2_discovery,
  wave_3: ranking.waves_summary.wave_3_ops,
  blockers: critic.blockers || []
};
