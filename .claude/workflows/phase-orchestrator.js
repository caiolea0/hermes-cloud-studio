// phase-orchestrator.js — Gera plano executável durável + skill /start-phase F + artefatos pra Fase F
//
// Reusável pra fases UX/feature futuras (G, H...). Input: AUDIT-XXX.md. Output: planejamento durável.
// Custo estimado: 1.2-1.5M tokens (64-68 agents). Autônomo (sem checkpoint pause).

export const meta = {
  name: "phase-orchestrator",
  description: "Decompõe Fase F (9 chapters) em plano executável: IMPLEMENTATION-PLAN-FASE-F + VALIDATION-CHECKLIST + harness extension + skill /start-phase F + skills/agents/workflows companion. Adversarial verify 4 lentes. Completeness critic. Pre+post test gate em codigo maduro.",
  phases: [
    { title: "Context Absorb", detail: "5 agents paralelos: state+topology+pattern+expectations+MCP landscape" },
    { title: "Chapter Decomposition", detail: "9 agents paralelos — 1 por F.1-F.9, schema CHAPTER_PLAN" },
    { title: "Coherence", detail: "1 synth — cruza deps, conflitos GUARDRAILS, reorder, grafo Mermaid" },
    { title: "Adversarial Verify", detail: "4 lentes × 9 chapters pipeline — regression/realism/guardrails/ui-empowerment, aceita >=3/4" },
    { title: "Artifact Generation", detail: "12 agents paralelos — plan+checklist+harness+howto+command+5skills+4subagents+3workflows+3specs" },
    { title: "Completeness Critic", detail: "1 agent revisa tudo + contingent additional generation se gap" },
    { title: "Synthesis Persist", detail: "Main loop: PLAN+GUARDRAILS+TASKs+memory" }
  ]
};

const HERMES_ROOT = "D:/dev-projects/main/hermes-cloud-studio";

const CHAPTERS = [
  { id: "F.1", title: "Backend↔Frontend Gap Audit", type: "research+ui" },
  { id: "F.2", title: "Mission Control Real-Time + Design System Polish", type: "ui" },
  { id: "F.3", title: "Lab Cockpit no-code", type: "ui+backend" },
  { id: "F.4", title: "Auto-Skill Loop W3", type: "architectural+ui" },
  { id: "F.5", title: "MCP Discovery + Integration + Gateway", type: "research+backend" },
  { id: "F.6", title: "Cérebro Hermes (brain.py + tools.py + decision replay)", type: "architectural" },
  { id: "F.7", title: "Cobaia Live Ops (warmup 14d real)", type: "ops" },
  { id: "F.8", title: "Cost & Performance Observability", type: "ui+backend" },
  { id: "F.9", title: "Pipeline Studio Visual", type: "ui+backend" }
];

// ========== SCHEMAS ==========

const CONTEXT_STATE_SCHEMA = {
  type: "object",
  properties: {
    fase_a_e_status: { type: "string" },
    findings_pass: { type: "integer" },
    findings_total: { type: "integer" },
    mature_zones: { type: "array", items: { type: "string" } },
    chapters_pending: { type: "array", items: { type: "string" } },
    guardrails_summary: { type: "string" },
    key_decisions_recorded: { type: "array", items: { type: "string" } }
  },
  required: ["fase_a_e_status", "findings_pass", "mature_zones", "guardrails_summary"]
};

const PROJECT_TOPOLOGY_SCHEMA = {
  type: "object",
  properties: {
    pc_components: { type: "array", items: { type: "string" } },
    vm_components: { type: "array", items: { type: "string" } },
    external_services: { type: "array", items: { type: "string" } },
    mcps_active: { type: "array", items: { type: "string" } },
    dashboard_pages: { type: "array", items: { type: "string" } },
    critical_files: { type: "array", items: { type: "object", properties: { path: { type: "string" }, role: { type: "string" } } } }
  },
  required: ["pc_components", "vm_components", "mcps_active", "dashboard_pages"]
};

const EXISTING_PATTERN_SCHEMA = {
  type: "object",
  properties: {
    implementation_plan_structure: { type: "string" },
    validation_assert_types: { type: "array", items: { type: "string" } },
    harness_capabilities: { type: "string" },
    finding_format: { type: "string" },
    phase_workflow: { type: "string" },
    artifact_persistence_pattern: { type: "string" }
  },
  required: ["implementation_plan_structure", "validation_assert_types", "harness_capabilities"]
};

const EXPECTATIONS_MAP_SCHEMA = {
  type: "object",
  properties: {
    explicit_desires: { type: "array", items: { type: "string" } },
    implicit_desires: { type: "array", items: { type: "string" } },
    constraints: { type: "array", items: { type: "string" } },
    success_metrics: { type: "array", items: { type: "string" } },
    risks_to_avoid: { type: "array", items: { type: "string" } }
  },
  required: ["explicit_desires", "constraints"]
};

const MCP_LANDSCAPE_SCHEMA = {
  type: "object",
  properties: {
    public_mcps_top: { type: "array", items: { type: "object", properties: {
      name: { type: "string" }, repo: { type: "string" }, tools: { type: "array", items: { type: "string" } },
      roi_for_hermes: { type: "string" }, effort: { type: "string", enum: ["low", "medium", "high"] },
      chapter_alignment: { type: "string" }
    } } },
    custom_mcps_to_build: { type: "array", items: { type: "object", properties: {
      name: { type: "string" }, tools: { type: "array", items: { type: "string" } },
      rationale: { type: "string" }, priority: { type: "string", enum: ["critical", "high", "medium"] }
    } } },
    framework_recommended: { type: "string" },
    gateway_pattern_notes: { type: "string" },
    risk_warnings: { type: "array", items: { type: "string" } }
  },
  required: ["public_mcps_top", "custom_mcps_to_build", "framework_recommended"]
};

const CHAPTER_PLAN_SCHEMA = {
  type: "object",
  properties: {
    chapter: { type: "string" },
    title: { type: "string" },
    classification: { type: "string", enum: ["ui", "backend", "architectural", "research", "ops", "ui+backend", "research+ui", "architectural+ui", "research+backend"] },
    ui_empowerment_score: { type: "integer", minimum: 1, maximum: 10 },
    estimated_sessions: { type: "integer" },
    tasks: { type: "array", items: { type: "object", properties: {
      id: { type: "string" }, title: { type: "string" },
      files_touched: { type: "array", items: { type: "string" } },
      files_created: { type: "array", items: { type: "string" } },
      mature_zone_touch: { type: "boolean" },
      pre_test: { type: "string" },
      post_test: { type: "string" },
      regression_phases_to_revalidate: { type: "array", items: { type: "string", enum: ["A", "B", "C", "D", "E"] } },
      smoke_test: { type: "string" },
      visual_proof: { type: "string" },
      done_criteria: { type: "array", items: { type: "string" } }
    }, required: ["id", "title", "mature_zone_touch", "done_criteria"] } },
    apis_new: { type: "array", items: { type: "object", properties: { method: { type: "string" }, path: { type: "string" }, purpose: { type: "string" } } } },
    apis_to_expose: { type: "array", items: { type: "string" } },
    ui_pages_new: { type: "array", items: { type: "object", properties: { page: { type: "string" }, components: { type: "array", items: { type: "string" } }, ws_events: { type: "array", items: { type: "string" } } } } },
    db_migrations: { type: "array", items: { type: "string" } },
    dependencies_on_chapters: { type: "array", items: { type: "string" } },
    risk_assessment: { type: "string" },
    done_criteria_chapter: { type: "array", items: { type: "string" } }
  },
  required: ["chapter", "title", "classification", "tasks", "done_criteria_chapter"]
};

const COHERENCE_SCHEMA = {
  type: "object",
  properties: {
    dependency_graph_mermaid: { type: "string" },
    execution_order_recommended: { type: "array", items: { type: "string" } },
    parallel_groups: { type: "array", items: { type: "array", items: { type: "string" } } },
    detected_conflicts: { type: "array", items: { type: "object", properties: { type: { type: "string" }, chapters: { type: "array", items: { type: "string" } }, resolution: { type: "string" } } } },
    guardrails_violations: { type: "array", items: { type: "string" } },
    refactoring_recommendations: { type: "array", items: { type: "string" } }
  },
  required: ["dependency_graph_mermaid", "execution_order_recommended"]
};

const VERDICT_SCHEMA = {
  type: "object",
  properties: {
    chapter: { type: "string" },
    lens: { type: "string", enum: ["regression_risk", "estimation_realism", "guardrails_compliance", "ui_empowerment"] },
    valid: { type: "boolean" },
    confidence: { type: "string", enum: ["low", "medium", "high"] },
    reasoning: { type: "string" },
    blockers: { type: "array", items: { type: "string" } },
    suggestions: { type: "array", items: { type: "string" } }
  },
  required: ["chapter", "lens", "valid", "confidence", "reasoning"]
};

const ARTIFACT_SPEC_SCHEMA = {
  type: "object",
  properties: {
    filename: { type: "string" },
    full_path: { type: "string" },
    content: { type: "string" },
    replaces_existing: { type: "boolean" },
    depends_on_chapter_plans: { type: "boolean" }
  },
  required: ["filename", "full_path", "content"]
};

const COMPLETENESS_SCHEMA = {
  type: "object",
  properties: {
    gaps_detected: { type: "array", items: { type: "object", properties: {
      gap_type: { type: "string" }, description: { type: "string" },
      severity: { type: "string", enum: ["critical", "high", "medium", "low"] },
      suggested_artifact: { type: "string" }
    } } },
    coverage_assessment: { type: "string" },
    additional_artifacts_needed: { type: "boolean" },
    additional_artifacts_specs: { type: "array", items: { type: "string" } }
  },
  required: ["gaps_detected", "coverage_assessment", "additional_artifacts_needed"]
};

// ====================== PHASE 1 — CONTEXT ABSORB ======================
phase("Context Absorb");
log("Fan-out: 5 agents paralelos absorvendo contexto");

const contextInputs = [
  {
    label: "context-state",
    schema: CONTEXT_STATE_SCHEMA,
    prompt: `Você é o context absorber pra workflow phase-orchestrator do Hermes Cloud Studio em ${HERMES_ROOT}.

Leia EXAUSTIVAMENTE estes arquivos:
- ${HERMES_ROOT}/.claude/GUARDRAILS.md (TODAS as regras invioláveis, especialmente Fase F e regression-test gate)
- ${HERMES_ROOT}/.claude/PLAN.md (estado durável, todos 20 chapters executados, 9 chapters Fase F propostos)
- ${HERMES_ROOT}/.claude/AUDIT-2026-06-08-FASE-F.md (proposta Fase F com 9 chapters)
- ${HERMES_ROOT}/.claude/validation-report.json (status real findings PASS/FAIL)

Extraia:
1. Status real Fases A-E (PASS/FAIL count por fase)
2. Lista COMPLETA áreas MADURAS que exigem regression-test gate
3. Chapters Fase F pendentes (F.1 a F.9)
4. Decisões arquiteturais já tomadas (core/state.py split, channels/email padrão, ollama_router, etc)
5. Regras GUARDRAILS críticas que afetam decomposição (PC vs VM, fail-closed auth, etc)

Retorne JSON conforme CONTEXT_STATE_SCHEMA. SEM truncar mature_zones e key_decisions_recorded — lista completa.`
  },
  {
    label: "project-topology",
    schema: PROJECT_TOPOLOGY_SCHEMA,
    prompt: `Você mapeia topologia técnica do Hermes Cloud Studio em ${HERMES_ROOT}.

Leia:
- ${HERMES_ROOT}/CLAUDE.md (mapa completo PC/VM/dashboard/skills)
- ${HERMES_ROOT}/.mcp.json (MCPs ativos)
- ${HERMES_ROOT}/.env.example (config vars)

Extraia:
1. Componentes PC (Tauri, server.py, dashboard SPA, etc)
2. Componentes VM (hermes_api_v2.py, daemon, linkedin/, gosom_scraper, Ollama)
3. External services (OpenRouter, Cloudflare Tunnel, Telegram, Google Places, AgentMemory)
4. MCPs atualmente conectados via .mcp.json
5. 11 páginas dashboard SPA (control, dashboard, prospects, proposals, audit, pipeline, tasks, skills, memory, missions, claude, linkedin — sim, 12 contando linkedin)
6. Arquivos críticos com tamanho/papel (server.py 251 pós-split, core/state.py, daemon/orchestrator.py, etc)

Retorne JSON conforme PROJECT_TOPOLOGY_SCHEMA.`
  },
  {
    label: "existing-pattern",
    schema: EXISTING_PATTERN_SCHEMA,
    prompt: `Você analisa o padrão de implementação Fases A-E pra workflow phase-orchestrator do Hermes em ${HERMES_ROOT}.

Leia EXAUSTIVAMENTE:
- ${HERMES_ROOT}/.claude/IMPLEMENTATION-PLAN.md (estrutura completa: análise+solução+test+persistência por finding)
- ${HERMES_ROOT}/.claude/VALIDATION-CHECKLIST.md (formato dos asserts grep)
- ${HERMES_ROOT}/scripts/validate_implementation.py (harness — quais tipos de assert suporta hoje, como extender)
- ${HERMES_ROOT}/.claude/HOW-TO-START-PHASE.md (roteiro fases existente)
- ${HERMES_ROOT}/.claude/commands/start-phase.md

Reporta:
1. Estrutura canônica IMPLEMENTATION-PLAN (seções por finding: contexto+análise+solução+test+persistência)
2. Tipos de assert atualmente suportados pelo harness (grep_present, file_exists, etc — ler script)
3. Como harness pode ser estendido pra suportar Fase F (asserts UI_VISIBLE, WS_SUBSCRIBED, ENDPOINT_CONSUMED_IN_APP_JS, REGRESSION_PHASE_X_PASS, SCREENSHOT_MATCH)
4. Formato de finding MERGED-XXX (vs novo formato Chapter F.x.task_Y)
5. Workflow real (start-phase: read GUARDRAILS+PLAN+IMPL+CHECKLIST → memory_smart_search → validate baseline → implement → validate per-finding → commit → memory_save → PLAN update)
6. Padrão persistência durável (PLAN + tasks + memory + chapters + commits)

Retorne JSON conforme EXISTING_PATTERN_SCHEMA.`
  },
  {
    label: "expectations-map",
    schema: EXPECTATIONS_MAP_SCHEMA,
    prompt: `Você sintetiza expectativas do owner (Caio Leão, designer/estrategista solo Cuiabá-MT) sobre Fase F.

Leia OBRIGATORIAMENTE:
- ${HERMES_ROOT}/.claude/PHASE-F-STUDY-SYNTHESIS.md (seção 6 EXPECTATIVAS OWNER)
- ${HERMES_ROOT}/.claude/AUDIT-2026-06-08-FASE-F.md (toda proposta)
- ${HERMES_ROOT}/.claude/PLAN.md (chapters F.1-F.9 + critério de regressão)

Extraia:
1. Desejos EXPLÍCITOS (no-code UI, real-time WS, cérebro orquestrador, MCP discovery, auto-skill, pipelines configuráveis interativos bonitos monitoráveis)
2. Desejos IMPLÍCITOS (revenue PMF, escala solo, conta Caio sagrada, zero API paga extra além Claude, VM-GPU pendente)
3. Restrições INVIOLÁVEIS (20/22 PASS preservado, GUARDRAILS, pre+post test em maduro)
4. Métricas sucesso (acceptance rate, reply rate, ban probability, latência endpoints, custo tokens)
5. Riscos cataclísmicos (ban LinkedIn conta real, regressão silenciosa Fases A-D, complexidade ingerencial solo)

Retorne JSON conforme EXPECTATIONS_MAP_SCHEMA.`
  },
  {
    label: "mcp-landscape",
    schema: MCP_LANDSCAPE_SCHEMA,
    prompt: `Você é o MCP landscape researcher pra Hermes Cloud Studio (B2B sales automation + LinkedIn outreach + Brazil PMEs).

Leia PRIMEIRO:
- ${HERMES_ROOT}/.claude/PHASE-F-STUDY-SYNTHESIS.md (seção 4 MCP ECOSYSTEM 2026 — top 10 já identificados)
- ${HERMES_ROOT}/.mcp.json (MCPs já conectados: agentmemory + hermes-control)

DEPOIS faça WebSearch+WebFetch live pra:
1. Verificar status MAIS RECENTE dos top 10 MCPs públicos listados (stars atualizadas, last commit, releases recentes)
2. Buscar MCPs RELEASED 2026 Q1 que não estavam no estudo (linkedin oficial? meta business mcp? whatsapp business mcp? notion mcp? gmail oficial?)
3. Verificar FastMCP 3.0 versão atual e novos features
4. Padrões MCP Gateway 2026 — projetos referência (mcp-gateway oss?)
5. Workflows MCP composition referência (mcp-agent Swarms, LangGraph patterns)

Retorne JSON conforme MCP_LANDSCAPE_SCHEMA. SEM cortar — quero contexto pleno pra F.5 + F.6.

Foco em ROI específico Hermes: cada MCP deve resolver dor explícita (replace CLI, integrar canal, evolucionar skill, monitor cobaia, observability).`
  }
];

const [contextState, projectTopology, existingPattern, expectationsMap, mcpLandscape] = await parallel(
  contextInputs.map(input => () => agent(input.prompt, {
    label: input.label,
    phase: "Context Absorb",
    schema: input.schema
  }))
);

log(`Context absorved. Mature zones: ${(contextState?.mature_zones || []).length}. Public MCPs surveyed: ${(mcpLandscape?.public_mcps_top || []).length}. Custom MCPs candidate: ${(mcpLandscape?.custom_mcps_to_build || []).length}.`);

const contextBundle = {
  state: contextState,
  topology: projectTopology,
  pattern: existingPattern,
  expectations: expectationsMap,
  mcp: mcpLandscape
};
const contextJson = JSON.stringify(contextBundle, null, 2);

// ====================== PHASE 2 — CHAPTER DECOMPOSITION ======================
phase("Chapter Decomposition");
log("Fan-out: 9 agents paralelos — 1 por chapter F.1 a F.9");

const chapterPlans = await parallel(CHAPTERS.map(ch => () => agent(
  `Você é domain expert pro chapter ${ch.id} (${ch.title}) classificação=${ch.type} da Fase F do Hermes Cloud Studio.

CONTEXTO COMPLETO (use isso como verdade — NÃO re-investigue):
${contextJson}

Sua TAREFA: decompor o chapter ${ch.id} em CHAPTER_PLAN executável.

Leia complementar:
- ${HERMES_ROOT}/.claude/AUDIT-2026-06-08-FASE-F.md (seção ${ch.id})
- ${HERMES_ROOT}/.claude/PHASE-F-STUDY-SYNTHESIS.md (relevante pro chapter)
- Read targeted no codebase pra entender estado atual (NÃO leia mais que 3-5 arquivos)

REGRAS HARD:
1. Cada task: 1 sessão de trabalho (~2-4h, 50-150k tokens). Se task > 1 sessão, QUEBRE em sub-tasks.
2. \`mature_zone_touch: true\` quando files_touched intersecta áreas MADURAS (lista em contextState.mature_zones). NESSE CASO:
   - pre_test OBRIGATÓRIO: comando concreto que captura estado (smoke test, NÃO grep)
   - post_test OBRIGATÓRIO: comando que valida estado pós-mudança
   - regression_phases_to_revalidate: lista [A,B,C,D,E] que esse touch pode regredir
3. \`visual_proof\` OBRIGATÓRIO pra tasks UI: URL preview + screenshot esperado descrito
4. \`done_criteria\` por task: 3-5 bullets concretos (não "tá funcionando")
5. \`ui_empowerment_score\` 1-10: quanto esse chapter substitui ação CLI por UI no-code (10=tudo via botão, 1=nada muda UX)
6. Respeitar GUARDRAILS: PC vs VM, fail-closed auth, ollama_router pra LLM, db_utils._connect pra SQLite, channels/ pattern pra novos canais
7. Reuso > reescrita: PipelineRunner, OllamaRouter, ChannelState, WS broadcast são ouro. Reusar massivamente.

SPECIFIC GUIDANCE PRO CHAPTER ${ch.id}:
${ch.id === "F.1" ? `- Output principal: .claude/FRONTEND-GAP.md ranking 11+ endpoints fantasma + top 10 gaps UX
- Skill auxiliar: hermes-frontend-gap (parser + grep + report)
- Sem mudança código backend; só análise + report
- Quick win (1 sessão). Fundação pras outras chapters.` : ""}
${ch.id === "F.2" ? `- Mission Control: Timeline+Decisions WS live (hoje polling-only)
- Design system polish: tokens consistentes, notification toast system, error inbox visual, dark mode polish, micro-interactions
- Tile por subsistema (LinkedIn/Email/Scraper/Audit/Daemon/Tunnel) com pause/resume + live status
- Expor api/daemon/* (5 endpoints fantasma — OURO!)
- mature_zone_touch: SIM (loops/, api/daemon.py se ainda existir, dashboard/app.js — não é maduro mas é grande)` : ""}
${ch.id === "F.3" ? `- Nova página dashboard/lab com botões fingerprint/login/viewer
- Live screenshot polling (artifacts/*/screenshots/)
- Compliance score + delta baseline
- APIs novas: /api/lab/{runs,start,artifacts}
- Backend: orquestra ssh remoto pra rodar lab_runner.py na VM, polling artifacts
- mature_zone_touch: NÃO (cria novo, não toca maduro)` : ""}
${ch.id === "F.4" ? `- Workflow .claude/workflows/hermes-skill-forge.js (W3)
- Tabela skill_proposals (campos do schema na SYNTHESIS)
- UI /skills/proposals com YAML diff + accept/reject/edit+test-lab buttons
- Lab sandbox: snapshot DB prod, wipe IDs, 10+ fixtures + injection tests
- 7d A/B post-deploy + auto-disable se métrica ruim
- mature_zone_touch: SIM (channels/email/* talvez, skills runtime VM)
- Cooldown 1x/dia max propose, cost_budget_per_day no schema YAML
- VISUAL DIFF obrigatório antes accept` : ""}
${ch.id === "F.5" ? `- Workflow .claude/workflows/mcp-discovery-survey.js (recurrente — research vivo)
- Integrar top 5 públicos: Playwright MS + Firecrawl + Postgres MCP Pro + Apollo + Hunter (ou conforme mcpLandscape final)
- Desenvolver hermes-linkedin-mcp custom (CRÍTICO — moat técnico, FastMCP 3.0 Python)
- MCP Gateway pattern: hermes-mcp-gateway pra não expor 15 MCPs direto
- Allowlist + sandboxed por MCP. Validator tool descriptions (2026 CVE prevention)
- mature_zone_touch: SIM (vm_api/routes.py se MCP server hospedado VM, linkedin/* se hermes-linkedin-mcp wraps)` : ""}
${ch.id === "F.6" ? `- core/brain.py NOVO (Brain.decide + classify + evaluate_result)
- core/tools.py NOVO (ToolRegistry — skills + MCPs + pipelines + endpoints sob namespace único)
- daemon/orchestrator.py REFATOR: decide_next_action delega pra brain.decide
- Decision replay: tabela brain_decisions com inputs+output+rationale, navegável temporal
- Chat dashboard com cards de ações executadas + multi-turn _brain_context_id
- WS stream tokens + action events
- Integrar Agent Zero como decision maker (não fallback)
- mature_zone_touch: SIM (CRÍTICO — daemon/orchestrator, core/state, core/ai, linkedin/ollama_router)
- REGRESSION TESTS exaustivos. Quebrar isso = quebrar Hermes 24/7.` : ""}
${ch.id === "F.7" ? `- Documenta plano warmup 14d em .claude/COBAIA-WARMUP-PLAN.md
- daemon/orchestrator.py adiciona day-aware execução: d0-6 lurking só, d7-13 ramp connects, d14+ outreach
- Métricas: acceptance_rate (PATCH-014 ✓), reply_rate (novo), ban_probability (proxy: cooldowns+challenges streak)
- Stop gates: burned_flag (✓), compliance<70 (✓), acceptance<40% (✓), CHALLENGES_24H>2 (novo)
- Daily Telegram report 19h cobaia summary
- Dashboard /cobaia: timeline visual day-by-day + métricas live + manual pause
- mature_zone_touch: SIM (daemon/orchestrator, linkedin/limiter, linkedin/account_profile)` : ""}
${ch.id === "F.8" ? `- Cost tracking: middleware FastAPI logs todo LLM call (provider+model+tokens_in+tokens_out+usd_estimate)
- Tabela llm_costs persiste
- Perf monitoring: middleware mede latência endpoint, slow SQL query log (>500ms), throughput por loop
- Error inbox: agrega exceptions log_loops + logger.exception() em tabela errors_inbox (status: new/seen/resolved)
- Audit trail Brain.decide() — acoplado F.6, tabela brain_decisions
- APIs: /api/observability/{costs,perf,errors,decisions}
- Dashboard /observability 4 tabs com charts (custos diários, latência p50/95/99, error count, decision timeline)
- mature_zone_touch: SIM (TODO loop, TODO endpoint maduro recebe middleware — risk regressão alta)
- USE MIDDLEWARE não touch direto em handlers maduros (preservação A-D crítica)` : ""}
${ch.id === "F.9" ? `- Pipeline builder VISUAL form-driven (decisão: NÃO canvas drag-drop. Owner solo 11 páginas vanilla, form é mais rápido construir + manter)
- Step library: cada skill + pipeline existente + MCP tool + endpoint vira step disponível, render como card
- Steps configuráveis: form com inputs do step + dropdown source (output do step anterior)
- Validação client-side antes submit
- Live execution monitor: cada step com status (pending/running/success/error), output preview, timing, error inline
- Template gallery: pipelines existentes viram templates clone-and-modify
- A/B test: rodar 2 variantes paralelas mesma fonte
- APIs: /api/pipeline-studio/{steps,templates,execute,monitor}
- Tabelas: pipeline_drafts (rascunhos sem publicar), pipeline_runs (histórico granular step-by-step)
- Dashboard /pipeline-studio (NOT replace /pipeline legado de uma vez — coexiste, /pipeline vira "Quick Run", /pipeline-studio é o builder)
- WS events: pipeline_step_started, pipeline_step_completed, pipeline_step_failed
- mature_zone_touch: SIM (core/pipeline.py, api/pipelines.py, daemon/orchestrator P3-P5)` : ""}

OUTPUT: JSON CHAPTER_PLAN_SCHEMA. Schema completo, sem truncar.`,
  { label: `decompose:${ch.id}`, phase: "Chapter Decomposition", schema: CHAPTER_PLAN_SCHEMA }
)));

log(`Decomposed ${chapterPlans.filter(Boolean).length}/${CHAPTERS.length} chapters`);

const chapterPlansJson = JSON.stringify(chapterPlans.filter(Boolean), null, 2);

// ====================== PHASE 3 — COHERENCE ======================
phase("Coherence");
log("Synthesis: cruza dependências, conflitos GUARDRAILS, reorder");

const coherence = await agent(
  `Você é o coherence synthesizer do workflow phase-orchestrator do Hermes Cloud Studio.

INPUT — chapter plans completos (9 chapters Fase F):
${chapterPlansJson}

CONTEXT BUNDLE (state+topology+pattern+expectations+mcp):
${contextJson}

Sua TAREFA:

1. **Grafo dependências** entre os 9 chapters. Exemplo: F.1 (gap audit) é fundação pra F.2, F.3, F.4, F.8, F.9. F.6 (brain.py) pode invalidar workflows W3 de F.4 se não coordenado.

2. **Ordem execução recomendada** (linear ou paralelo). Considere:
   - Quais chapters podem rodar em paralelo (sem touch áreas compartilhadas)?
   - Quais EXIGEM ordem (F.5 MCP integration deve estar pronto antes F.6 brain.py registrar tools)?
   - Sessão dedicada vs múltiplas sessões intercaladas

3. **Detecta conflitos**:
   - DOIS chapters touch mesmo arquivo maduro simultaneamente (race risk Fases A-D)
   - DUPLICATA: F.x e F.y propõem mesmo endpoint/UI/tabela
   - INCOMPATÍVEL: F.x assume estado que F.y elimina

4. **Validações GUARDRAILS** cross-chapter:
   - Algum chapter viola PC-vs-VM topology?
   - Algum touch áreas maduras SEM pre_test/post_test definido?
   - Algum chapter assume API externa paga (proibido)?

5. **Refatoring recommendations** se algum chapter melhoraria com decomposição diferente.

Retorne JSON COHERENCE_SCHEMA com dependency_graph_mermaid (sintaxe Mermaid graph TD válida).`,
  { label: "coherence-synth", phase: "Coherence", schema: COHERENCE_SCHEMA }
);

const coherenceJson = JSON.stringify(coherence, null, 2);
log(`Coherence done. Execution order: ${(coherence?.execution_order_recommended || []).join(" → ")}. Conflicts: ${(coherence?.detected_conflicts || []).length}.`);

// ====================== PHASE 4 — ADVERSARIAL VERIFY ======================
phase("Adversarial Verify");
log("Pipeline: 4 lentes × 9 chapters. Aceita >=3/4 lentes valid.");

const LENSES = [
  {
    key: "regression_risk",
    prompt_fn: (cp) => `Você é o REGRESSION RISK lens — adversarial verifier do chapter ${cp.chapter} (${cp.title}) Fase F Hermes.

CHAPTER PLAN:
${JSON.stringify(cp, null, 2)}

ÁREAS MADURAS Fase F protegidas (qualquer touch exige pre+post test + regression validate):
${JSON.stringify(contextState?.mature_zones || [], null, 2)}

SUA POSIÇÃO: SKEPTIC. Default valid=false se uncertain. Procure razões pra REFUTAR.

Avalie:
1. Toda task que touch maduro tem pre_test E post_test concretos (não placeholder)?
2. regression_phases_to_revalidate lista TODAS fases que esse touch pode regredir?
3. Algum touch implícito a maduro que a task NÃO documentou (ex: importar de core/state.py = mature touch)?
4. As mudanças em vm_api/routes.py têm migration SSH documentada (esquema PC+VM coerente)?
5. Schemas DB novos têm migration idempotente PC+VM se relevante?
6. Risk concreto: cite finding MERGED-XXX específico que pode regredir e como detectar via validate --phase X.

Retorne VERDICT_SCHEMA. lens="regression_risk". valid=true APENAS se todos checks acima OK. blockers=lista issues concretos.`
  },
  {
    key: "estimation_realism",
    prompt_fn: (cp) => `Você é o ESTIMATION REALISM lens — adversarial verifier do chapter ${cp.chapter} (${cp.title}) Fase F Hermes.

CHAPTER PLAN:
${JSON.stringify(cp, null, 2)}

SUA POSIÇÃO: REALISTIC SKEPTIC. Default valid=false se uncertain.

Avalie:
1. Cada task é executável em 1 sessão (2-4h, 50-150k tokens)? Se task >5 arquivos novos + DB migration + UI nova + API nova = provavelmente over-scoped, refute.
2. estimated_sessions realista? F.6 (brain.py + tools.py + agent integration + decision replay + chat contextual) em 3-4 sessões é otimista — desafie.
3. Done criteria são CONCRETOS e mensuráveis ou genéricos ("tá funcionando")?
4. Pipeline Studio F.9 (form builder + step library + live monitor + templates + A/B): 3-4 sessões realista? Owner solo, vanilla JS, 276KB app.js já complexo.
5. F.5 + F.6 deps: F.5 pronto antes F.6 = serial = +2 semanas. Documentado?
6. F.4 com lab sandbox snapshot DB prod + 10+ fixtures + injection tests + 7d A/B: subestimado?

Retorne VERDICT_SCHEMA. lens="estimation_realism". suggestions=como fatiar se over-scoped.`
  },
  {
    key: "guardrails_compliance",
    prompt_fn: (cp) => `Você é o GUARDRAILS COMPLIANCE lens — adversarial verifier do chapter ${cp.chapter} (${cp.title}) Fase F Hermes.

CHAPTER PLAN:
${JSON.stringify(cp, null, 2)}

GUARDRAILS SUMMARY (do contextState):
${contextState?.guardrails_summary || "[não disponível, leia .claude/GUARDRAILS.md]"}

Regras invioláveis a verificar:
- PC vs VM topology (linkedin/, daemon/ rodam VM; server.py PC; nada cruza)
- Fail-closed auth (HERMES_AUTH_TOKEN, HERMES_INTERNAL_TOKEN, HERMES_VM_AUTH_TOKEN — não bypass)
- WS /ws auth via ?token= obrigatório (não confia same-origin)
- spawn() pra asyncio tasks (não bare create_task)
- db_utils._connect() pra SQLite novo (WAL + busy_timeout 30s)
- ollama_router.route(task, prompt) — nunca httpx direto pra :11434
- channels/ pattern: config.py + limiter.py + sender.py paralelo a linkedin/
- Regression-test gate (pre+post em touch maduro)
- Zero API externa paga além Claude Max

Avalie chapter contra TODAS regras. Refute se viola QUALQUER uma.

Retorne VERDICT_SCHEMA. lens="guardrails_compliance". blockers=violações concretas com regra+task afetada.`
  },
  {
    key: "ui_empowerment",
    prompt_fn: (cp) => `Você é o UI EMPOWERMENT lens — adversarial verifier do chapter ${cp.chapter} (${cp.title}) Fase F Hermes.

CHAPTER PLAN:
${JSON.stringify(cp, null, 2)}

EXPECTATIVAS OWNER (extraídas):
${JSON.stringify(expectationsMap?.explicit_desires || [], null, 2)}

Owner solo, quer ZERO CLI, UI MUITO MAIS CAPAZ, pipelines configuráveis interativos bonitos 100% monitoráveis real-time, cérebro orquestrador despacha ferramentas e Claude Code orquestra PC.

SUA POSIÇÃO: skeptical advocate da UX. Refute se chapter não eleva UX significativamente.

Avalie:
1. ui_empowerment_score declarado (1-10) confere com tasks? Score 8+ exige: UI nova ou major upgrade + WS real-time + sem CLI requerido + visualmente polished.
2. Ações que owner faria CLI hoje ficam disponível via botão? Liste 3 ações concretas.
3. Real-time WS events declarados pra cada UI nova? Polling >10s é "bonus", não primary.
4. Visual proof claro pra cada task UI (screenshot esperado, page URL, key interactions)?
5. Notification/feedback loop pro owner (toast, sound, badge)?
6. Para chapter de research/architecture (F.5, F.6): output deve INCLUIR UI que torne MCPs visíveis + brain reasoning visível, senão owner fica cego.

Retorne VERDICT_SCHEMA. lens="ui_empowerment". suggestions=como elevar UX se score baixo.`
  }
];

const verifiedChapters = await pipeline(
  chapterPlans.filter(Boolean),
  cp => parallel(LENSES.map(lens => () => agent(lens.prompt_fn(cp), {
    label: `verify:${cp.chapter}:${lens.key}`,
    phase: "Adversarial Verify",
    schema: VERDICT_SCHEMA
  }))).then(verdicts => {
    const valid = verdicts.filter(Boolean);
    const validCount = valid.filter(v => v.valid).length;
    const accepted = validCount >= 3;
    return {
      ...cp,
      verdicts: valid,
      verdict_summary: { valid_count: validCount, total: valid.length, accepted },
      blockers_aggregated: valid.flatMap(v => v.blockers || []),
      suggestions_aggregated: valid.flatMap(v => v.suggestions || [])
    };
  })
);

const acceptedChapters = verifiedChapters.filter(Boolean).filter(c => c.verdict_summary?.accepted);
const rejectedChapters = verifiedChapters.filter(Boolean).filter(c => !c.verdict_summary?.accepted);

log(`Verified. Accepted: ${acceptedChapters.length}/${verifiedChapters.length}. Rejected (need revision): ${rejectedChapters.length}.`);
if (rejectedChapters.length > 0) {
  log(`Rejected chapters: ${rejectedChapters.map(c => c.chapter).join(", ")}. Blockers will be embedded in IMPLEMENTATION-PLAN as warnings.`);
}

const verifiedChaptersJson = JSON.stringify(verifiedChapters, null, 2);

// ====================== PHASE 5 — ARTIFACT GENERATION ======================
phase("Artifact Generation");
log("Fan-out: 12 agents paralelos — IMPLEMENTATION-PLAN + 11 outros artefatos durables");

const ARTIFACTS = [
  {
    label: "implementation-plan",
    prompt: `Gere .claude/IMPLEMENTATION-PLAN-FASE-F.md seguindo padrão de ${HERMES_ROOT}/.claude/IMPLEMENTATION-PLAN.md (Fases A-E).

INPUT chapter plans verificados (9 chapters):
${verifiedChaptersJson}

COHERENCE:
${coherenceJson}

CONTEXT (mature_zones, guardrails):
${contextJson}

ESTRUTURA OBRIGATÓRIA do markdown:
1. Header: # Hermes Cloud Studio — Implementation Plan Fase F (9 Chapters)
2. Convenções desta sessão (anti-patterns proibidos — copiar do A-E)
3. Sumário ordem execução + paralelismo + grafo Mermaid (do coherence)
4. PRA CADA chapter (F.1 a F.9):
   - ## Chapter F.x — Title
   - Estimated sessions + classification + ui_empowerment_score
   - Dependencies
   - **Contexto** (1-2 paragraph por que chapter existe)
   - **Solução** (alto nível, arquitetura)
   - **Tasks** (lista detalhada com files, pre/post test se aplicável, smoke, visual_proof, done_criteria)
   - **APIs novas + DB migrations**
   - **UI nova** (pages, components, ws events)
   - **Regression-test gate** (se mature_zone_touch=true em qualquer task)
   - **Done criteria** chapter inteiro
   - **Risk assessment + blockers identified by verify** (se rejected ou parcial)
5. Apêndice: regression-test runbook (validate --phase A B C D E antes/depois)

NÃO truncar. Markdown completo, mantém formato canônico.

Retorne ARTIFACT_SPEC_SCHEMA com filename="IMPLEMENTATION-PLAN-FASE-F.md", full_path="${HERMES_ROOT}/.claude/IMPLEMENTATION-PLAN-FASE-F.md", content=markdown completo.`
  },
  {
    label: "validation-checklist",
    prompt: `Gere .claude/VALIDATION-CHECKLIST-FASE-F.md seguindo padrão de ${HERMES_ROOT}/.claude/VALIDATION-CHECKLIST.md.

INPUT chapter plans verificados:
${verifiedChaptersJson}

NOVOS TIPOS DE ASSERT pra Fase F (extender harness):
- grep_present(file, pattern) — existente
- file_exists(path) — existente
- ui_visible(page_url, css_selector) — NOVO
- ws_subscribed(event_name, source_file) — NOVO (grep app.js por handleWSEvent + event)
- endpoint_consumed(api_path, source=app.js|MCP) — NOVO (grep app.js por path)
- regression_phase_pass(phase_letter) — NOVO (re-run validate_implementation.py --phase X)
- table_exists(db, table) — NOVO (sqlite query)
- screenshot_match(page_url, baseline_path) — NOVO (preview_screenshot + manual diff)
- workflow_exists(path) — NOVO (file_exists + has valid meta export)
- mcp_registered(name) — NOVO (grep .mcp.json)
- skill_exists(name) — NOVO (file_exists + valid YAML schema)
- subagent_exists(name) — NOVO (file_exists .claude/agents/name.md)

ESTRUTURA do checklist:
1. Header explicação tipos assert
2. PRA CADA chapter F.x:
   - ### Chapter F.x
   - Lista bullets de asserts por task com tipo + parâmetros

Retorne ARTIFACT_SPEC com filename="VALIDATION-CHECKLIST-FASE-F.md", path=${HERMES_ROOT}/.claude/, content=completo.`
  },
  {
    label: "harness-extension",
    prompt: `Gere patch pra ${HERMES_ROOT}/scripts/validate_implementation.py adicionando suporte aos novos assert types da Fase F.

INPUT: tipos novos descritos em VALIDATION-CHECKLIST-FASE-F.md (ui_visible, ws_subscribed, endpoint_consumed, regression_phase_pass, table_exists, screenshot_match, workflow_exists, mcp_registered, skill_exists, subagent_exists).

ATUAL harness (resumo do EXISTING_PATTERN):
${existingPattern?.harness_capabilities || "Read script directly"}

OUTPUT: arquivo .claude/HARNESS-EXTENSION-PATCH.md (NÃO patch git direto — documento que orienta humano a aplicar com instruções).

Estrutura:
1. Introdução: o que estende e por quê
2. Por tipo novo de assert:
   - Pseudo-código Python da função check_<type>(args)
   - Exemplo de uso no CHECKLIST
   - Limitações + testabilidade
3. Como integrar ao validate_implementation.py existente (qual função adicionar onde)
4. Comando pra rodar Fase F: \`python scripts/validate_implementation.py --phase F\`
5. Lista findings dummy iniciais Fase F (F.1.1, F.1.2, ..., F.9.N) com tipos asserts mapeados

Retorne ARTIFACT_SPEC com filename="HARNESS-EXTENSION-PATCH.md", path=${HERMES_ROOT}/.claude/, content=completo.`
  },
  {
    label: "how-to-start-update",
    prompt: `Gere .claude/HOW-TO-START-PHASE.md ATUALIZADO adicionando seção Fase F. Mantém A-E intactas.

LEIA atual: ${HERMES_ROOT}/.claude/HOW-TO-START-PHASE.md

ADICIONA nova seção "### Fase F — Operacional + Self-Evolving":

- Tempo estimado: ${verifiedChapters.reduce((sum, c) => sum + (c.estimated_sessions || 0), 0)} sessões
- Tokens estimados (síntese)
- Sequência OBRIGATÓRIA dos chapters (vem de coherence.execution_order_recommended)
- Cuidados específicos Fase F:
  * Regression-test gate INVIOLÁVEL (pre+post em maduro)
  * UI MUITO MAIS CAPAZ — meta zero-CLI
  * WS real-time prioridade vs polling
  * MCP gateway pattern (não expor direto)
  * Brain.py vs daemon — manter separação infra/decisão
- Pra cada chapter F.x:
  * Tempo
  * Tokens
  * Sequência tasks (ordem)
  * Cuidados específicos
  * Risco principal
- Modificar prompt universal:
  * Suporta {A|B|C|D|E|F}
  * Pra F: extra steps — read AUDIT-2026-06-08-FASE-F.md + IMPLEMENTATION-PLAN-FASE-F.md + PHASE-F-STUDY-SYNTHESIS.md
  * Validate baseline: \`python scripts/validate_implementation.py --phase F\`
  * Pra cada task que touch maduro: pre_test BEFORE + post_test AFTER + validate --phase A B C D E PRESERVA 20/22 PASS

Retorne ARTIFACT_SPEC com filename="HOW-TO-START-PHASE.md", path=${HERMES_ROOT}/.claude/, content=arquivo COMPLETO (A-E intacto + nova seção F).`
  },
  {
    label: "start-phase-command",
    prompt: `Gere .claude/commands/start-phase.md atualizado.

ATUAL:
---
description: Inicia fase do IMPLEMENTATION-PLAN com pré-requisitos automatizados + persistência
argument-hint: "<A|B|C|D|E>"
---
Leia \`.claude/HOW-TO-START-PHASE.md\` no projeto. Execute os 7 pré-requisitos em paralelo, reporte baseline da \`python scripts/validate_implementation.py --phase $1\`, aguarde confirmação do owner antes de mexer em código.

NOVO: suporta F + lógica condicional:
- Pra A-E: comportamento atual
- Pra F: adicionalmente reads AUDIT-FASE-F + IMPLEMENTATION-PLAN-FASE-F + PHASE-F-STUDY-SYNTHESIS, alert sobre regression-test gate, mention pre/post test obrigatório em maduro, mention UI empowerment meta

Retorne ARTIFACT_SPEC com filename="start-phase.md", path=${HERMES_ROOT}/.claude/commands/, content=arquivo completo (frontmatter + corpo).`
  },
  {
    label: "skill-frontend-gap",
    prompt: `Gere skill .claude/skills/hermes-frontend-gap/SKILL.md.

Padrão SKILL.md observar em existentes:
- ${HERMES_ROOT}/.claude/skills/hermes-status/
- ${HERMES_ROOT}/.claude/skills/hermes-deploy/

FUNÇÃO da skill: rodar gap audit backend↔frontend. Inputs: nenhum. Outputs: .claude/FRONTEND-GAP.md ranking.

Implementação:
1. Parse api/*.py + vm_api/routes.py: grep @router. methods + paths
2. Grep dashboard/app.js: extrair paths em fetch/apiCall/apiRequest
3. Cross-reference: rotas backend não consumidas frontend
4. Ranking por impacto: ALTO se cobre ação CLI frequente
5. Output .claude/FRONTEND-GAP.md tabela + recommendations

Trigger: "audit frontend", "frontend gap", "/hermes-frontend-gap"

Retorne ARTIFACT_SPEC com filename="SKILL.md", path=${HERMES_ROOT}/.claude/skills/hermes-frontend-gap/, content=completo.`
  },
  {
    label: "skill-mcp-survey",
    prompt: `Gere skill .claude/skills/hermes-mcp-survey/SKILL.md.

FUNÇÃO: research recurrente ecosystem MCP 2026. Inputs: nenhum (ou tópico opcional). Outputs: .claude/MCP-SURVEY-{date}.md.

Padrão similar a hermes-frontend-gap (procedimento determinístico SKILL.md).

Implementação:
1. WebSearch MCPs lançados últimos 90 dias
2. WebFetch top releases (stars >500, commits últimos 30d)
3. Cross-reference com Hermes needs (LinkedIn, B2B sales, browser, LLM ops, observability)
4. Filtrar por security (CVEs, allowlist, validator descriptions)
5. Output ranking + recommendations integrar/desenvolver

Trigger: "survey mcps", "mcp research", "/hermes-mcp-survey"

Retorne ARTIFACT_SPEC com filename="SKILL.md", path=${HERMES_ROOT}/.claude/skills/hermes-mcp-survey/, content=completo.`
  },
  {
    label: "skill-skill-forge",
    prompt: `Gere skill .claude/skills/hermes-skill-forge-runner/SKILL.md.

FUNÇÃO: manual trigger workflow hermes-skill-forge.js (W3). Bridge entre owner e workflow auto-skill loop.

Implementação:
1. Read tabela skill_proposals via SSH SQLite query (rate_limits.db ou equivalente)
2. Lista pending proposals
3. Owner escolhe ação: run-workflow / accept-proposal / reject / view-diff
4. Run workflow: invoke .claude/workflows/hermes-skill-forge.js
5. Accept proposal: POST /api/skill-proposals/{id}/deploy
6. Reject: PATCH status=rejected
7. Reportar status pós-ação

Trigger: "skill forge", "propor skill", "/hermes-skill-forge"

Retorne ARTIFACT_SPEC com filename="SKILL.md", path=${HERMES_ROOT}/.claude/skills/hermes-skill-forge-runner/, content=completo.`
  },
  {
    label: "skill-brain-test",
    prompt: `Gere skill .claude/skills/hermes-brain-test/SKILL.md.

FUNÇÃO: smoke test cérebro Hermes (core/brain.py) fora do chat real. Útil pra calibrar classifier+router + debugging F.6.

Implementação:
1. Inputs: prompt de teste + categories esperadas
2. Call Brain.classify(text, categories, context) via /api/brain/test endpoint
3. Compare output vs expected
4. Test multi-turn: send 3 prompts seguidos com _brain_context_id
5. Test tool dispatch: solicite "list prospects Cuiabá" e verifica que Brain rotou pra ToolRegistry.invoke("list_prospects")
6. Report coverage % intents corretos

Trigger: "testar brain", "test cérebro", "/hermes-brain-test"

Retorne ARTIFACT_SPEC com filename="SKILL.md", path=${HERMES_ROOT}/.claude/skills/hermes-brain-test/, content=completo.`
  },
  {
    label: "skill-cobaia-status",
    prompt: `Gere skill .claude/skills/hermes-cobaia-status/SKILL.md.

FUNÇÃO: snapshot warmup status + próxima ação cobaia. Operacionalização F.7.

Implementação:
1. Query linkedin_data/account_profiles/milgrauz_exe.json (sticky_session_id, burned_flag, dia atual warmup)
2. Query linkedin_data/rate_limits.db: warmup_state + acceptance_cooldown
3. Calcula day-since-start
4. Cita PATCH-014 acceptance rate atual (vs threshold 40%)
5. Próxima ação programada pelo daemon (dia X = lurking vs connect vs outreach)
6. Stop gates status (burned, compliance, acceptance, challenges_24h)
7. Telegram report mais recente
8. Recomendação owner: pause/continue/intervir

Trigger: "como tá cobaia", "warmup status", "/hermes-cobaia"

Retorne ARTIFACT_SPEC com filename="SKILL.md", path=${HERMES_ROOT}/.claude/skills/hermes-cobaia-status/, content=completo.`
  },
  {
    label: "subagent-frontend-ux-reviewer",
    prompt: `Gere subagent .claude/agents/frontend-ux-reviewer.md.

Padrão observar em existentes: ${HERMES_ROOT}/.claude/agents/linkedin-detection-researcher.md

PERSONA: UX reviewer com lente "owner solo no-code" — Caio persona. Designer/estrategista Cuiabá, prefere bonito + funcional + zero fricção. Sem tolerância pra polling stale, botões fantasma, navegação confusa.

CAPABILITIES (tools allowed): Read, Glob, Grep, preview_* tools (Claude Preview), mas NÃO Edit/Write (review only).

USO: invocado em F.2, F.3, F.4 UI, F.7 UI, F.8 UI, F.9 UI delivery. Critique pages novas/modificadas. Output: review com severity (must-fix, should-fix, nice-to-have).

CHECKLIST do reviewer:
- WS real-time vs polling stale
- Visual consistency com design system
- Loading states presentes
- Error states presentes
- Empty states presentes
- Notification feedback (toast/badge)
- Mobile breakpoints (futuro)
- Accessibility básico (contraste, focus visible)

Retorne ARTIFACT_SPEC com filename="frontend-ux-reviewer.md", path=${HERMES_ROOT}/.claude/agents/, content=completo.`
  },
  {
    label: "subagent-mcp-integrator",
    prompt: `Gere subagent .claude/agents/mcp-integrator.md.

PERSONA: MCP integrator expert. Conhece padrão hermes-control TS (FastMCP wrapper Python ou node MCP SDK), .mcp.json schema, OAuth 2.1 / stdio / streamable HTTP transports.

CAPABILITIES: Read, Glob, Grep, Bash (npm install, pip install, fastmcp run), Edit (mcps/<name>/), WebFetch (docs MCP), WebSearch.

USO: F.5 integração MCPs públicos (Playwright, Firecrawl, Postgres Pro, Apollo, Hunter, GitHub, Slack, Omnisearch) + desenvolvimento custom (hermes-linkedin-mcp, hermes-prospects-mcp, hermes-skills-mcp).

PROCEDURE:
1. Survey: ler MCP-INTEGRATION-PLAN.md
2. Pra cada MCP a integrar: validate package na fonte (github + npm/pypi), check security (CVE, validator), estimate tokens/cost se LLM-backed
3. Setup: criar entry em .mcp.json + env vars + scripts setup
4. Test: MCP Inspector smoke
5. Document: mcps/<name>/README.md (tools list + exemplos invocação)
6. Gateway pattern: registrar atrás de hermes-mcp-gateway se aplicável

Retorne ARTIFACT_SPEC com filename="mcp-integrator.md", path=${HERMES_ROOT}/.claude/agents/, content=completo.`
  },
  {
    label: "subagent-brain-prompt-engineer",
    prompt: `Gere subagent .claude/agents/brain-prompt-engineer.md.

PERSONA: tune classifier+router intent do core/brain.py. Conhece taxonomia Hermes (channels LinkedIn/Email/WA/IG, pipelines discovery/audit/outreach/enrich, skills 6 LinkedIn + auto-propostas, MCPs registered, endpoints PC+VM).

CAPABILITIES: Read, Glob, Grep, Edit (core/brain.py), Bash (python -m linkedin.brain.test). NO WebFetch (foca codebase).

USO: F.6 calibragem + iteração. Multi-turn: classifier confunde "ver prospects" com "audit prospect"? Tune system prompt + categories taxonomy.

PROCEDURE:
1. Read core/brain.py + core/tools.py + tabela brain_decisions (últimas 100)
2. Identifica intents misclassified
3. Categoriza padrão de erro (genérico vs especifico)
4. Propõe: ajuste system prompt classifier, ajuste categories taxonomy, ajuste tool descriptions
5. Validate via hermes-brain-test skill (smoke 50 prompts)
6. Iterate até accuracy >85%

Retorne ARTIFACT_SPEC com filename="brain-prompt-engineer.md", path=${HERMES_ROOT}/.claude/agents/, content=completo.`
  }
];

const artifactSpecs = await parallel(ARTIFACTS.map(a => () => agent(a.prompt, {
  label: `gen:${a.label}`,
  phase: "Artifact Generation",
  schema: ARTIFACT_SPEC_SCHEMA
})));

const validArtifacts = artifactSpecs.filter(Boolean);
log(`Generated ${validArtifacts.length}/${ARTIFACTS.length} artifacts`);

// ====================== PHASE 6 — COMPLETENESS CRITIC ======================
phase("Completeness Critic");
log("Revising end-to-end coverage. Detecting gaps.");

const generatedArtifactsList = validArtifacts.map(a => `- ${a.filename} (${a.full_path})`).join("\n");

const completeness = await agent(
  `Você é o COMPLETENESS CRITIC do workflow phase-orchestrator. Sua TAREFA: identificar GAPS no que foi gerado.

EXPECTATIVAS OWNER (must serve):
${JSON.stringify(expectationsMap, null, 2)}

CHAPTER PLANS verified (9 chapters):
${verifiedChaptersJson}

ARTEFATOS GERADOS na Phase 5:
${generatedArtifactsList}

PERGUNTA CENTRAL: Owner solo, quer rodar Hermes 24/7 SEM mexer no terminal. Os artefatos gerados são SUFICIENTES pra ele:
1. Abrir /start-phase F e ter roteiro claro?
2. Implementar 9 chapters sem perder contexto entre sessões?
3. Validar cada chapter sem regredir A-D?
4. Ter UI no-code completa pós Fase F?
5. Operar cobaia warmup sem CLI?
6. Auto-evoluir Hermes via skill loop?
7. Monitorar custo+performance+errors real-time?
8. Construir/clonar pipelines via builder visual?
9. Integrar MCPs externos + custom sem pesquisa adicional?
10. Cérebro orquestrador documentado e testável?

PROCURE GAPS:
- Artefato faltando (ex: PIPELINE-STUDIO-SPEC.md proposta no design original mas não gerada?)
- Documentação owner-facing (README Fase F? quickstart guide?)
- Migrations DB consolidadas?
- Decisão design system tokens documentada?
- Plano deployment VM pra MCPs custom?
- Quickstart pra novos chapters em sessões futuras?

Retorne COMPLETENESS_SCHEMA. Se additional_artifacts_needed=true, list em additional_artifacts_specs (descrição cada artefato faltante).`,
  { label: "completeness-critic", phase: "Completeness Critic", schema: COMPLETENESS_SCHEMA }
);

log(`Completeness assessment: ${completeness?.coverage_assessment || "unknown"}. Gaps detected: ${(completeness?.gaps_detected || []).length}. Additional artifacts needed: ${completeness?.additional_artifacts_needed}`);

let additionalArtifacts = [];
if (completeness?.additional_artifacts_needed && (completeness.additional_artifacts_specs || []).length > 0) {
  log(`Spawning Phase 5.5: generating ${completeness.additional_artifacts_specs.length} additional artifacts`);
  additionalArtifacts = await parallel(completeness.additional_artifacts_specs.map((spec, idx) => () => agent(
    `Você gera artefato adicional Fase F do Hermes solicitado por Completeness Critic.

SPEC: ${spec}

CONTEXTO:
- Hermes root: ${HERMES_ROOT}
- Chapter plans: ${verifiedChaptersJson.slice(0, 30000)}...
- MCP landscape: ${JSON.stringify(mcpLandscape, null, 2).slice(0, 10000)}...

Gere o artefato completo conforme spec. NÃO truncar. Mantém formato consistente com artefatos Fase F existentes.

Retorne ARTIFACT_SPEC_SCHEMA com filename + full_path + content. Inferir path apropriado (.claude/, mcps/, scripts/, docs/).`,
    { label: `gen-additional:${idx}`, phase: "Completeness Critic", schema: ARTIFACT_SPEC_SCHEMA }
  )));
  log(`Additional artifacts generated: ${additionalArtifacts.filter(Boolean).length}`);
}

// ====================== PHASE 7 — SYNTHESIS PERSIST ======================
phase("Synthesis Persist");
log("Return data — main loop persists files + updates PLAN/GUARDRAILS/TASKS/memory");

const allArtifacts = [...validArtifacts, ...additionalArtifacts.filter(Boolean)];

const summary = {
  workflow: "phase-orchestrator",
  generated_at_iso: "RUNTIME_STAMP",
  phase_target: "F",
  chapters_decomposed: chapterPlans.filter(Boolean).length,
  chapters_accepted_by_verify: acceptedChapters.length,
  chapters_rejected_by_verify: rejectedChapters.length,
  rejected_chapter_ids: rejectedChapters.map(c => c.chapter),
  artifacts_generated_main: validArtifacts.length,
  artifacts_generated_additional: additionalArtifacts.filter(Boolean).length,
  artifacts_total: allArtifacts.length,
  total_estimated_sessions: verifiedChapters.reduce((sum, c) => sum + (c.estimated_sessions || 0), 0),
  coherence_execution_order: coherence?.execution_order_recommended || [],
  coherence_parallel_groups: coherence?.parallel_groups || [],
  detected_conflicts: (coherence?.detected_conflicts || []).length,
  completeness_assessment: completeness?.coverage_assessment || "unknown",
  gaps_detected: (completeness?.gaps_detected || []).length
};

log(`Workflow complete. ${allArtifacts.length} artifacts ready for main-loop persistence. Estimated total Fase F effort: ${summary.total_estimated_sessions} sessions.`);

return {
  summary,
  artifacts: allArtifacts,
  chapter_plans: verifiedChapters,
  coherence,
  completeness,
  context_bundle: contextBundle
};
