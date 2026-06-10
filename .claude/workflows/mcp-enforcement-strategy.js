// mcp-enforcement-strategy.js — Análise meticulosa enforcement uso MCPs cross-chapter F.5+
//
// Trigger: descoberta 2026-06-10 que F.5 entrega 8 MCPs mas F.6/F.7/F.4/F.9 não obrigam uso
// explícito. Risk: MCPs "ficarem na gaveta", deps pagas (Apollo/Hunter) zero ROI.
//
// Output: .claude/MCP-ENFORCEMENT-STRATEGY.md (recommendation + 6 fixes per chapter +
// workflow recurrent mcp-coverage-audit.js design + dashboard widget F.8 spec)
// Custo estimado: ~400-500k tokens (32 agents). Background.

export const meta = {
  name: "mcp-enforcement-strategy",
  description: "Análise meticulosa enforcement uso MCPs cross-chapter (F.5 entrega 8, F.6/F.7/F.4/F.9 risco esquecer na gaveta). 7 estratégias × 4 lentes adversarial + síntese + 6 fixes per chapter + workflow recurrent audit + dashboard widget design. Output: .claude/MCP-ENFORCEMENT-STRATEGY.md",
  phases: [
    { title: "Context Absorb", detail: "4 agents paralelos: F.5 deliverables + F.6 ToolRegistry + F.7/F.4/F.9 MCP usage refs + industry patterns 2026" },
    { title: "Strategy Deep Dive", detail: "7 agents paralelos — 1 por estratégia enforcement (hard requirement chapter, coverage tracker F.8, recurrent audit workflow, dashboard visualization, deactivation policy, mandatory usage minimums, owner notification system)" },
    { title: "Adversarial Verify", detail: "4 lentes × 7 estratégias pipeline — owner_friction/observability/cost_roi/maintenance_burden" },
    { title: "Synthesis Recommendation", detail: "1 agent: combo estratégias winning + 6 fixes specific PLAN.md per chapter + workflow recurrent design + dashboard widget spec" },
    { title: "Artifact Generation", detail: "2 agents paralelos: MCP-ENFORCEMENT-STRATEGY.md (main) + PLAN.md patches suggestion" }
  ]
};

const HERMES_ROOT = "D:/dev-projects/main/hermes-cloud-studio";

const STRATEGIES = [
  { id: "S1", name: "Hard requirement chapter done_criteria", note: "F.7 Task 6 Hunter OBRIGATÓRIA, F.4 Auto-Skill primeira proposal 2+ MCPs, F.9 step library all MCPs" },
  { id: "S2", name: "Coverage tracker F.8 mcp_calls table", note: "Postgres MCP query tool name + calls 24h/7d/30d + last_used + chapter owner" },
  { id: "S3", name: "Recurrent audit workflow mensal", note: "mcp-coverage-audit.js cron 1º dia mês — output MCP-COVERAGE-{YYYY-MM}.md zombie list" },
  { id: "S4", name: "Dashboard widget /observability/mcp-coverage", note: "Visual tab F.8 — owner vê inventário + status active/zombie + actions integrate/deactivate" },
  { id: "S5", name: "Deactivation policy 60d zero calls", note: "Workflow audit recommendation auto: 60d zero = remove from gateway OR document why kept" },
  { id: "S6", name: "Mandatory usage minimums per MCP", note: "Apollo: ≥10 calls/mês ou downgrade free. Hunter: ≥5 calls/semana ou skip integration" },
  { id: "S7", name: "Owner notification telemetria semanal", note: "Telegram weekly: 'MCP X 3 calls esta semana (vs 12 média) — investigar?'" }
];

const CONTEXT_FRAGMENT_SCHEMA = {
  type: "object",
  properties: {
    fragment_id: { type: "string" },
    summary: { type: "string" },
    findings: { type: "array", items: { type: "object", properties: { topic: { type: "string" }, detail: { type: "string" } }, required: ["topic", "detail"] } },
    gaps_identified: { type: "array", items: { type: "string" } },
    requirements_for_enforcement: { type: "array", items: { type: "string" } }
  },
  required: ["fragment_id", "summary", "findings"]
};

const STRATEGY_DEEP_DIVE_SCHEMA = {
  type: "object",
  properties: {
    strategy_id: { type: "string" },
    strategy_name: { type: "string" },
    implementation_pseudo_code: { type: "string" },
    integration_points: { type: "array", items: { type: "object", properties: { chapter: { type: "string" }, change: { type: "string" } } } },
    pros: { type: "array", items: { type: "string" } },
    cons: { type: "array", items: { type: "string" } },
    owner_friction_score: { type: "integer", minimum: 1, maximum: 10 },
    observability_value_score: { type: "integer", minimum: 1, maximum: 10 },
    cost_roi_score: { type: "integer", minimum: 1, maximum: 10 },
    maintenance_burden_score: { type: "integer", minimum: 1, maximum: 10 },
    dependencies_required: { type: "array", items: { type: "string" } },
    sessions_impact: { type: "string" }
  },
  required: ["strategy_id", "strategy_name", "implementation_pseudo_code", "pros", "cons"]
};

const VERDICT_SCHEMA = {
  type: "object",
  properties: {
    strategy_id: { type: "string" },
    lens: { type: "string", enum: ["owner_friction", "observability", "cost_roi", "maintenance_burden"] },
    valid: { type: "boolean" },
    confidence: { type: "string", enum: ["low", "medium", "high"] },
    reasoning: { type: "string" },
    blockers: { type: "array", items: { type: "string" } },
    suggestions: { type: "array", items: { type: "string" } }
  },
  required: ["strategy_id", "lens", "valid", "confidence", "reasoning"]
};

const RECOMMENDATION_SCHEMA = {
  type: "object",
  properties: {
    primary_combo: { type: "array", items: { type: "string" } },
    primary_combo_rationale: { type: "string" },
    fix_per_chapter: { type: "object", properties: {
      F5: { type: "string" }, F6: { type: "string" }, F7: { type: "string" },
      F4: { type: "string" }, F8: { type: "string" }, F9: { type: "string" }
    } },
    recurrent_workflow_design: { type: "string" },
    dashboard_widget_spec: { type: "string" },
    success_criteria: { type: "array", items: { type: "string" } },
    rollback_plan: { type: "string" }
  },
  required: ["primary_combo", "primary_combo_rationale", "fix_per_chapter"]
};

const ARTIFACT_SPEC_SCHEMA = {
  type: "object",
  properties: {
    filename: { type: "string" },
    full_path: { type: "string" },
    content: { type: "string" },
    replaces_existing: { type: "boolean" }
  },
  required: ["filename", "full_path", "content"]
};

// ============ PHASE 1: CONTEXT ABSORB ============
phase("Context Absorb");
log("Fan-out 4 agents paralelos");

const contextFragments = await parallel([
  () => agent(
    `Você é o F.5 DELIVERABLES investigator pra workflow mcp-enforcement-strategy Hermes.

Read em ${HERMES_ROOT}:
- .claude/PLAN.md seção F.5 "MCP Gateway + Discovery + Custom MCPs" completa
- .claude/AUDIT-2026-06-08-FASE-F.md F.5 referências
- .claude/PHASE-F-STUDY-SYNTHESIS.md MCP ecosystem section (top 10 públicos + 3 customs)

Extraia:
- Lista exata 8 MCPs F.5 vai entregar (5 públicos + 3 customs)
- ROI declarado por MCP (qual chapter consome)
- Custos (free vs paid)
- Tools dentro cada MCP custom (linkedin/prospects/skills)
- F.5 done_criteria atual

Output CONTEXT_FRAGMENT. fragment_id="f5_deliverables". gaps_identified deve listar coisas que F.5 docs NÃO cobrem (ex: "sem coverage tracker", "sem deactivation policy").`,
    { label: "ctx:f5_deliverables", phase: "Context Absorb", schema: CONTEXT_FRAGMENT_SCHEMA }
  ),
  () => agent(
    `Você é o F.6 BRAIN TOOL REGISTRY investigator.

Read ${HERMES_ROOT}/.claude/PLAN.md seção F.6 "Cérebro Hermes Brain orchestrator" + AUDIT-FASE-F + PHASE-F-STUDY-SYNTHESIS F.6 section.

Extraia:
- Como Brain.tools.invoke() é planejado integrar MCPs via gateway
- ToolRegistry namespace pattern
- Brain.decide() how chooses qual MCP usar
- Audit trail brain_decisions table fields
- Done criteria F.6

Output CONTEXT_FRAGMENT. fragment_id="f6_brain_registry". requirements_for_enforcement deve listar o que F.6 precisa fazer pra forçar coverage MCPs cross-chapter.`,
    { label: "ctx:f6_brain", phase: "Context Absorb", schema: CONTEXT_FRAGMENT_SCHEMA }
  ),
  () => agent(
    `Você é o F.7/F.4/F.9 MCP USAGE REFS investigator.

Read ${HERMES_ROOT}/.claude/PLAN.md seções F.7 (Cobaia Live Ops), F.4 (Auto-Skill Loop), F.9 (Pipeline Studio) — extraia TODAS menções a MCPs específicos (Hunter, Apollo, Omnisearch, Firecrawl, GitHub MCP, Postgres MCP Pro, Playwright MS, hermes-linkedin/prospects/skills).

Pra cada chapter, identifique:
- Quantas MCPs específicos mencionados?
- São requirements HARD (done_criteria block) OR soft (nice-to-have)?
- Done criteria atual cobre uso explicit?
- Onde owner Claude poderia "esquecer" usar MCP?

Output CONTEXT_FRAGMENT. fragment_id="f7_f4_f9_mcp_usage". gaps_identified deve listar MCPs mencionados mas sem hard requirement.`,
    { label: "ctx:chapter_mcp_refs", phase: "Context Absorb", schema: CONTEXT_FRAGMENT_SCHEMA }
  ),
  () => agent(
    `Você é o INDUSTRY PATTERNS researcher MCP coverage enforcement 2026.

WebSearch + WebFetch:
1. Como LangChain/LlamaIndex tracking tool usage stats? Coverage dashboards?
2. Anthropic MCP server telemetry padrão (OpenTelemetry hooks)?
3. Cursor IDE MCP usage analytics — owner notification quando tool ficar idle?
4. Production patterns enforcement uso APIs externas (Apollo/Hunter no DevTools dashboards comuns)?
5. SaaS coverage tracking — Datadog/PostHog API usage telemetry padrões 2026
6. Hard requirements vs soft suggestions — quando enforcement viola autonomy AI agent?
7. Deactivation policies registry zombie (ms-clarity / npm deprecation thresholds)

Output CONTEXT_FRAGMENT. fragment_id="industry_patterns_2026". findings devem citar 5-8 patterns concretos + sources.`,
    { label: "ctx:industry_patterns", phase: "Context Absorb", schema: CONTEXT_FRAGMENT_SCHEMA }
  )
]);

const contextBundle = contextFragments.filter(Boolean).reduce((acc, f) => { acc[f.fragment_id] = f; return acc; }, {});
const contextJson = JSON.stringify(contextBundle, null, 2);
log(`Context: ${Object.keys(contextBundle).length} fragments`);

// ============ PHASE 2: STRATEGY DEEP DIVE ============
phase("Strategy Deep Dive");
log("Fan-out 7 agents paralelos — 1 por estratégia");

const deepDives = await parallel(STRATEGIES.map(s => () => agent(
  `Você é o DEEP DIVE investigator pra estratégia ${s.id}) ${s.name} (${s.note}).

CONTEXTO COMPLETO: ${contextJson.slice(0, 50000)}

OBJETIVO: análise técnica + implementável pra estratégia ${s.name} aplicada a F.5+ ecosystem MCPs Hermes.

Liste:
1. Implementation pseudo-code (~30-60 linhas) — código real-ish owner Claude pode adaptar
2. Integration points: chapter (F.5/F.6/F.7/F.4/F.8/F.9) + change concreto cada
3. Pros real-world (4-6)
4. Cons (4-6)
5. owner_friction_score 1-10 (1=zero atrito, 10=owner odeia)
6. observability_value_score 1-10 (1=nada visível, 10=dashboard rich)
7. cost_roi_score 1-10 (1=baixo ROI cost, 10=alto ROI)
8. maintenance_burden_score 1-10 (1=zero manutenção, 10=high maintenance)
9. dependencies_required: list
10. sessions_impact: F.X +N sessões OR F.X NEW sub-session

Output STRATEGY_DEEP_DIVE_SCHEMA. TÉCNICO E CONCRETO.`,
  { label: `deepdive:${s.id}`, phase: "Strategy Deep Dive", schema: STRATEGY_DEEP_DIVE_SCHEMA }
)));

const validDeepDives = deepDives.filter(Boolean);
const deepDivesJson = JSON.stringify(validDeepDives, null, 2);
log(`Deep dives: ${validDeepDives.length}/7`);

// ============ PHASE 3: ADVERSARIAL VERIFY ============
phase("Adversarial Verify");
log("Pipeline 7 estratégias × 4 lentes");

const LENSES = [
  { key: "owner_friction", prompt_fn: (dd) => `Lens OWNER FRICTION estratégia ${dd.strategy_id}) ${dd.strategy_name}. Score declarado: ${dd.owner_friction_score}/10. Hermes é solo no-code owner. Avalie: friction cabe owner? OR exige micromanage cada decisão? Default valid=false se uncertain. Retorne VERDICT.` },
  { key: "observability", prompt_fn: (dd) => `Lens OBSERVABILITY estratégia ${dd.strategy_id}. Score: ${dd.observability_value_score}/10. F.8 vai construir observability — esta estratégia ALAVANCA F.8 dashboards OR isolada? Retorne VERDICT.` },
  { key: "cost_roi", prompt_fn: (dd) => `Lens COST/ROI estratégia ${dd.strategy_id}. Score: ${dd.cost_roi_score}/10. Apollo $50/mês + Hunter $49/mês são custos reais. Estratégia previne waste? Justifica overhead próprio? Retorne VERDICT.` },
  { key: "maintenance_burden", prompt_fn: (dd) => `Lens MAINTENANCE estratégia ${dd.strategy_id}. Score: ${dd.maintenance_burden_score}/10. Owner solo — manutenção contínua quem faz? Workflow recurrent precisa intervenção mensal? Retorne VERDICT.` }
];

const verifiedStrategies = await pipeline(
  validDeepDives,
  dd => parallel(LENSES.map(lens => () => agent(lens.prompt_fn(dd) + ` Strategy full: ${JSON.stringify(dd, null, 2)}`, {
    label: `verify:${dd.strategy_id}:${lens.key}`,
    phase: "Adversarial Verify",
    schema: VERDICT_SCHEMA
  }))).then(verdicts => {
    const valid = verdicts.filter(Boolean);
    const validCount = valid.filter(v => v.valid).length;
    return {
      ...dd,
      verdicts: valid,
      verdict_summary: { valid_count: validCount, total: valid.length, accepted: validCount >= 3 }
    };
  })
);

const acceptedStrategies = verifiedStrategies.filter(Boolean).filter(v => v.verdict_summary?.accepted);
log(`Verified: ${acceptedStrategies.length}/${verifiedStrategies.length} strategies accepted >=3/4`);

const verifiedJson = JSON.stringify(verifiedStrategies, null, 2);

// ============ PHASE 4: SYNTHESIS ============
phase("Synthesis Recommendation");

const recommendation = await agent(
  `Você é o SYNTHESIZER mcp-enforcement-strategy.

INPUTS:
- Context: ${contextJson.slice(0, 30000)}
- 7 estratégias verified: ${verifiedJson.slice(0, 70000)}

Produzir recommendation FINAL combinando 2-4 estratégias winning (NÃO 1 só — coverage exige multi-camada).

Tarefas:
1. primary_combo: 2-4 strategy_ids combinados (ex: ["S1", "S2", "S3"])
2. primary_combo_rationale: 4-6 frases por que essa combinação
3. fix_per_chapter: pra cada chapter F.5/F.6/F.7/F.4/F.8/F.9, recomendação concreta diff/patch PLAN.md
4. recurrent_workflow_design: detalhar workflow mcp-coverage-audit.js (frequency, output format, integration F.8)
5. dashboard_widget_spec: dashboard tab /observability/mcp-coverage detalhado (UI components, data source, refresh rate)
6. success_criteria: 5-8 critérios mensuráveis (ex: "Apollo usage >10 calls/mês por 3 meses consecutivos")
7. rollback_plan: se enforcement causar fricção owner intolerável, como reverter

Output RECOMMENDATION_SCHEMA. Decisivo, cite strategy_ids.`,
  { label: "synthesis:recommendation", phase: "Synthesis Recommendation", schema: RECOMMENDATION_SCHEMA }
);

log(`Primary combo: ${(recommendation?.primary_combo || []).join(" + ")}`);

const recJson = JSON.stringify(recommendation, null, 2);

// ============ PHASE 5: ARTIFACT GENERATION ============
phase("Artifact Generation");

const artifacts = await parallel([
  () => agent(
    `Gere ${HERMES_ROOT}/.claude/MCP-ENFORCEMENT-STRATEGY.md (~8-12k chars, 10 sections).

INPUTS:
- Context: ${contextJson.slice(0, 30000)}
- Strategies verified: ${verifiedJson.slice(0, 50000)}
- Recommendation: ${recJson}

Sections obrigatórias:
1. Context (problema "MCPs na gaveta")
2. Sumário Executivo (primary combo + rationale 1 parágrafo + impact)
3. 7 Estratégias Avaliadas (rank table)
4. Análise Detalhada Primary Combo
5. Fix per Chapter (PLAN.md patches específicos F.5/F.6/F.7/F.4/F.8/F.9 — copy-paste-adapt)
6. Workflow Recurrent Design (mcp-coverage-audit.js spec completa)
7. Dashboard Widget Spec (/observability/mcp-coverage F.8 — UI components + data + refresh)
8. Success Criteria mensuráveis (5-8)
9. Rollback Plan
10. Cross-references + Approval Checklist owner

Output ARTIFACT_SPEC. filename=MCP-ENFORCEMENT-STRATEGY.md, path=${HERMES_ROOT}/.claude/, replaces=false.`,
    { label: "gen:enforcement_md", phase: "Artifact Generation", schema: ARTIFACT_SPEC_SCHEMA }
  ),
  () => agent(
    `Gere ${HERMES_ROOT}/.claude/PLAN-MCP-ENFORCEMENT-PATCH.md (~3-5k chars).

Patch instructions específicos pra PLAN.md chapters F.5/F.6/F.7/F.4/F.8/F.9 substituir done_criteria vagos por hard requirements MCP coverage.

INPUT: ${recJson}

Estrutura:
- Per chapter (F.5/F.6/F.7/F.4/F.8/F.9): bloco "antes" (texto atual approx) + bloco "depois" (texto novo)
- Git command sequence aplicar manual
- Approval checklist owner antes commit

Output ARTIFACT_SPEC. filename=PLAN-MCP-ENFORCEMENT-PATCH.md, path=${HERMES_ROOT}/.claude/.`,
    { label: "gen:plan_patch", phase: "Artifact Generation", schema: ARTIFACT_SPEC_SCHEMA }
  )
]);

const validArtifacts = artifacts.filter(Boolean);

return {
  summary: {
    workflow: "mcp-enforcement-strategy",
    context_fragments: Object.keys(contextBundle).length,
    strategies_analyzed: validDeepDives.length,
    strategies_accepted: acceptedStrategies.length,
    primary_combo: recommendation?.primary_combo,
    artifacts_generated: validArtifacts.length
  },
  artifacts: validArtifacts,
  recommendation,
  strategies_verified: verifiedStrategies,
  context_bundle: contextBundle
};
