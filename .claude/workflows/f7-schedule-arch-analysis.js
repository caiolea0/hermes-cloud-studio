// f7-schedule-arch-analysis.js — Análise meticulosa decisão schedule infra F.7
//
// Trigger: descoberta F.3.4 2026-06-10 (daemon/orchestrator.py sem APScheduler nem cron).
// PLAN.md F.7 ganhou bloco "🚨 DECISÃO ARQUITETURAL PENDENTE" com 8 alternativas placeholder.
// Este workflow analisa profundamente cada uma + síntese + recommendation + plano F.7 concreto.
//
// Output: .claude/F7-SCHEDULE-ARCH-DECISION.md (main) + PLAN.md F.7 patch suggestion
// Custo estimado: ~500-600k tokens (48 agents). Background — owner sai PC.

export const meta = {
  name: "f7-schedule-arch-analysis",
  description: "Análise profunda decisão schedule infra F.7 (APScheduler vs crontab VM vs 6 alternativas). 8 opções × 4 lentes adversarial + síntese + concrete F.7 implementation plan + migration checklist. Output: .claude/F7-SCHEDULE-ARCH-DECISION.md",
  phases: [
    { title: "Context Absorb", detail: "5 agents paralelos: daemon state + APScheduler 2026 + deps + F.7 tasks 2/3/4 + cross-platform" },
    { title: "Alternative Deep Dive", detail: "8 agents paralelos — 1 por opção (A-H) com pseudo-code + integration + migration + failure mode + obs hooks" },
    { title: "Adversarial Verify", detail: "4 lentes × 8 alternativas pipeline — regression/complexity/cross-platform/future-proof" },
    { title: "Synthesis Recommendation", detail: "1 agent: rank 8 opções + PRIMARY/FALLBACK/LONG-TERM tiers + F.7 implementation plan + migration checklist + risk mitigation" },
    { title: "Artifact Generation", detail: "2 agents paralelos: F7-SCHEDULE-ARCH-DECISION.md + PLAN.md F.7 patch suggestion" }
  ]
};

const HERMES_ROOT = "D:/dev-projects/main/hermes-cloud-studio";

const ALTERNATIVES = [
  { id: "A", name: "Linux crontab VM", note: "F.3.4 pattern, zero dep, standalone scripts" },
  { id: "B", name: "APScheduler in-process daemon", note: "Add dependency, integrate daemon main loop, async-friendly" },
  { id: "C", name: "FastAPI BackgroundTasks", note: "Built-in, per-request lifecycle" },
  { id: "D", name: "asyncio.create_task + sleep loop", note: "Zero dep, pattern manual" },
  { id: "E", name: "Celery + Redis", note: "Production-grade, distributed, heavy" },
  { id: "F", name: "MCP scheduled-tasks", note: "Externo daemon, MCP gateway F.5 dep" },
  { id: "G", name: "systemd timers Linux", note: "VM Linux nativo, cross-process" },
  { id: "H", name: "Daemon main loop time-check", note: "Zero dep, acoplado loop principal" }
];

// ============ SCHEMAS ============

const CONTEXT_FRAGMENT_SCHEMA = {
  type: "object",
  properties: {
    fragment_id: { type: "string" },
    summary: { type: "string" },
    findings: { type: "array", items: { type: "object", properties: { topic: { type: "string" }, detail: { type: "string" }, source: { type: "string" } }, required: ["topic", "detail"] } },
    constraints: { type: "array", items: { type: "string" } },
    integration_hooks: { type: "array", items: { type: "string" } }
  },
  required: ["fragment_id", "summary", "findings"]
};

const ALTERNATIVE_DEEP_DIVE_SCHEMA = {
  type: "object",
  properties: {
    option_id: { type: "string" },
    option_name: { type: "string" },
    implementation_pseudo_code: { type: "string" },
    integration_points: { type: "array", items: { type: "object", properties: { file: { type: "string" }, change: { type: "string" }, mature_zone_touch: { type: "boolean" } } } },
    pros: { type: "array", items: { type: "string" } },
    cons: { type: "array", items: { type: "string" } },
    migration_steps: { type: "array", items: { type: "string" } },
    failure_mode_recovery: { type: "string" },
    observability_hooks: { type: "string" },
    test_strategy: { type: "string" },
    f7_sessions_impact: { type: "string" },
    dependencies_required: { type: "array", items: { type: "string" } },
    cross_platform_support: { type: "string", enum: ["PC", "VM", "PC+VM", "VM_only", "PC_only"] },
    estimated_complexity_score: { type: "integer", minimum: 1, maximum: 10 }
  },
  required: ["option_id", "option_name", "implementation_pseudo_code", "integration_points", "pros", "cons", "migration_steps", "failure_mode_recovery"]
};

const VERDICT_SCHEMA = {
  type: "object",
  properties: {
    option_id: { type: "string" },
    lens: { type: "string", enum: ["regression_risk", "complexity_roi", "cross_platform", "future_proof"] },
    valid: { type: "boolean" },
    confidence: { type: "string", enum: ["low", "medium", "high"] },
    reasoning: { type: "string" },
    blockers: { type: "array", items: { type: "string" } },
    suggestions: { type: "array", items: { type: "string" } },
    score: { type: "integer", minimum: 1, maximum: 10 }
  },
  required: ["option_id", "lens", "valid", "confidence", "reasoning"]
};

const RECOMMENDATION_SCHEMA = {
  type: "object",
  properties: {
    primary_option: { type: "string" },
    primary_rationale: { type: "string" },
    fallback_option: { type: "string" },
    fallback_rationale: { type: "string" },
    long_term_option: { type: "string" },
    long_term_rationale: { type: "string" },
    rank_table: { type: "array", items: { type: "object", properties: { option_id: { type: "string" }, total_score: { type: "integer" }, lens_breakdown: { type: "object" } } } },
    f7_tasks_2_3_4_implementation_plan: { type: "string" },
    migration_checklist: { type: "array", items: { type: "string" } },
    risk_mitigation: { type: "array", items: { type: "string" } },
    success_criteria: { type: "array", items: { type: "string" } },
    rollback_plan: { type: "string" }
  },
  required: ["primary_option", "primary_rationale", "f7_tasks_2_3_4_implementation_plan", "migration_checklist"]
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
log("Fan-out 5 agents paralelos: daemon state + APScheduler ecosystem + Hermes deps + F.7 tasks + cross-platform");

const contextFragments = await parallel([
  () => agent(
    `Você é o DAEMON STATE FRAGMENT investigator pra workflow f7-schedule-arch-analysis Hermes.

OBJETIVO: capturar estado ATUAL daemon/orchestrator.py (PC) + hermes_api_v2.py (VM) pra entender:
- Async patterns existentes (spawn() MERGED-015 from F.2 — onde + como usado)
- Main loop structure (P1-P7 priority queue mentioned em CLAUDE.md)
- State management (DB writes? in-memory? both?)
- Error recovery patterns (try/except logging?)
- Lifecycle hooks FastAPI lifespan
- Integration com tasks scheduled futuras

Read em ${HERMES_ROOT}:
- daemon/orchestrator.py (full read)
- core/state.py linhas com spawn() + run_in_executor + background tasks
- server.py lifespan + startup events
- hermes_api_v2.py (VM) lifespan + sync loops

Output schema CONTEXT_FRAGMENT. fragment_id="daemon_state". Liste 5-8 findings concretos + 3-5 constraints + 3-5 integration_hooks pra schedule infra futura.`,
    { label: "ctx:daemon_state", phase: "Context Absorb", schema: CONTEXT_FRAGMENT_SCHEMA }
  ),
  () => agent(
    `Você é o APSCHEDULER ECOSYSTEM 2026 researcher.

OBJETIVO: status atual APScheduler 4.x (2026) + alternatives ecosystem pra async Python scheduling.

WebSearch + WebFetch:
1. APScheduler 4.x release status (estável? beta? async support?)
2. AsyncIOScheduler usage pattern com FastAPI lifespan
3. Alternatives: rocketry, schedule (sync only), arq (Redis), prefect (heavy), taskiq
4. Compatibility Python 3.12+ (Hermes stack)
5. Production-grade async scheduler 2026 — qual community recomenda?
6. SQLAlchemy job store APScheduler — persistência cross-restart
7. Trigger types (interval, cron, date) + custom
8. Observability hooks (OpenTelemetry, Sentry integration?)

Output CONTEXT_FRAGMENT. fragment_id="apscheduler_ecosystem_2026". Liste 6-10 findings (releases, patterns, gotchas, comparison alternatives) + 3-5 constraints (Python version, async compat, persistence) + integration_hooks pra Hermes FastAPI lifespan integration.`,
    { label: "ctx:apscheduler_2026", phase: "Context Absorb", schema: CONTEXT_FRAGMENT_SCHEMA }
  ),
  () => agent(
    `Você é o HERMES DEPS investigator.

OBJETIVO: catálogo completo Python deps Hermes (PC + VM) + identificar conflicts/sinergias pra schedule infra adoption.

Read em ${HERMES_ROOT}:
- requirements.txt (PC)
- pyproject.toml se existir
- setup.py se existir
- .env.example pra config patterns
- Cross-check: SSH VM ~/requirements.txt OR similar (mentioned em CLAUDE.md ou GUARDRAILS)

Output CONTEXT_FRAGMENT. fragment_id="hermes_deps". Liste:
- 10-20 deps atuais relevantes (fastapi version, asyncio patterns, slowapi, pydantic-settings, sqlite stuff)
- Conflicts potenciais APScheduler add (ex: SQLAlchemy duplicate, redis dependency Celery, etc)
- Sinergias (já tem httpx? slowapi rate limit que serve modelo de injection?)
- Constraints adicionar deps (size requirements.txt, deploy VM, Python 3.12 compat)
- Integration hooks (lifespan FastAPI já estabelecido em server.py + hermes_api_v2.py)`,
    { label: "ctx:hermes_deps", phase: "Context Absorb", schema: CONTEXT_FRAGMENT_SCHEMA }
  ),
  () => agent(
    `Você é o F.7 TASKS investigator.

OBJETIVO: extrair requirements EXATOS das Tasks 2/3/4 F.7 (Métricas coletor + Stop gates + Daily Telegram report) + qualquer outra task F.7 que precise schedule infra.

Read em ${HERMES_ROOT}:
- .claude/PLAN.md seção F.7 inteira (bullet bloco recente "🚨 DECISÃO ARQUITETURAL PENDENTE" também)
- .claude/IMPLEMENTATION-PLAN-FASE-F.md seção F.7 (se exists)
- .claude/AUDIT-2026-06-08-FASE-F.md F.7 referências

Pra cada task scheduled F.7:
- Frequency exata (1h? 30min? 19h diário?)
- State shared com daemon? (escreve cobaia_daily_metrics? lê linkedin/limiter state?)
- Idempotência (se rodar 2x mesmo minuto = OK?)
- Error recovery (next run retry? alert imediato?)
- Cross-task deps (Task 3 stop gate depende Task 2 métricas?)
- Latency tolerance (Telegram 19h = acceptable 19:01? 30min stop gate = acceptable 30min05?)
- Coupling daemon main loop (intercepts P1-P7? paralelo?)
- Persistence requirement (job state cross-restart? task history?)

Output CONTEXT_FRAGMENT. fragment_id="f7_tasks_requirements". Liste 4-6 tasks + requirements completos cada + 3-5 constraints arquiteturais derivados + integration_hooks Telegram bridge existing.`,
    { label: "ctx:f7_tasks", phase: "Context Absorb", schema: CONTEXT_FRAGMENT_SCHEMA }
  ),
  () => agent(
    `Você é o CROSS-PLATFORM CONSTRAINTS investigator.

OBJETIVO: mapear quais schedule alternatives funcionam onde (PC Windows, VM Linux, Tauri spawned subprocesses, MCP Gateway F.5 future).

Read em ${HERMES_ROOT}:
- CLAUDE.md (arquitetura PC + VM detalhada)
- GUARDRAILS.md ("🏗️ Arquitetura" + "🔧 Deps por máquina")
- README.md se contém deploy info

Pra cada componente:
- PC Windows (Hermes.exe Tauri spawned subprocesses): qual schedule alternatives compatible? Windows Task Scheduler? Daemon Python? Crontab via WSL?
- VM Linux (hermes_api_v2.py, daemon, scrapers, lab_runner): nativos systemd timers, crontab. APScheduler in-process OK?
- Tauri lifecycle: spawned subprocesses morrem com app close? scheduled tasks devem persistir?
- MCP Gateway F.5 future: scheduled MCP tools possible? VM-side?
- Cobaia LinkedIn (F.7 main consumer): scheduled tasks rodam APENAS VM (linkedin/* vive VM only per GUARDRAILS)

Output CONTEXT_FRAGMENT. fragment_id="cross_platform_constraints". Liste 5-8 findings (deployment topology, platform-specific alternatives, lifecycle constraints) + 3-5 constraints (cobaia VM only, Tauri lifecycle, future MCP integration) + integration_hooks (preflight tunnel check pattern existing).`,
    { label: "ctx:cross_platform", phase: "Context Absorb", schema: CONTEXT_FRAGMENT_SCHEMA }
  )
]);

const contextBundle = contextFragments.filter(Boolean).reduce((acc, frag) => {
  acc[frag.fragment_id] = frag;
  return acc;
}, {});
const contextJson = JSON.stringify(contextBundle, null, 2);

log(`Context absorbed: ${Object.keys(contextBundle).length} fragments. Total findings: ${Object.values(contextBundle).reduce((s, f) => s + (f.findings?.length || 0), 0)}`);

// ============ PHASE 2: ALTERNATIVE DEEP DIVE ============
phase("Alternative Deep Dive");
log("Fan-out 8 agents paralelos — 1 por opção A-H com pseudo-code + integration + migration");

const alternativeDeepDives = await parallel(ALTERNATIVES.map(opt => () => agent(
  `Você é o DEEP DIVE investigator pra opção ${opt.id}) ${opt.name} (${opt.note}).

CONTEXTO COMPLETO (não re-investigar, use como verdade):
${contextJson.slice(0, 60000)}

OBJETIVO: produzir análise técnica PROFUNDA + IMPLEMENTÁVEL pra opção ${opt.name} aplicada a F.7 (Cobaia Live Ops Tasks 2/3/4 — métricas 1h, stop gate 30min, Telegram 19h diário).

Liste:

1. **Implementation pseudo-code** (~30-80 linhas Python/bash) — código real-ish que owner Claude da sessão F.7 poderia adaptar diretamente. Mostre:
   - Setup/init (FastAPI lifespan? subprocess? cron entry?)
   - 3 scheduled tasks F.7 registered (métricas, stop_gate, telegram)
   - Error handling pattern
   - Shutdown gracefull

2. **Integration points** — lista files que precisariam touch:
   - file: caminho relativo
   - change: o que muda concretamente
   - mature_zone_touch: true/false (daemon/orchestrator.py + core/state.py + hermes_api_v2.py + linkedin/limiter.py são MADURO per GUARDRAILS)

3. **Pros real-world** (4-6 itens) — porque essa opção é boa F.7 específico

4. **Cons real-world** (4-6 itens) — limitações + dores conhecidas

5. **Migration steps** (5-10 steps) — do estado atual (zero scheduled tasks) ao steady-state F.7

6. **Failure mode + recovery** — o que acontece se task crashar? supervisor restart? worker pool? manual?

7. **Observability hooks** — como Sentry MCP F.5 prep + Cost & Performance F.8 vão se beneficiar? job duration tracking? failure rate?

8. **Test strategy** — como smoke test essa scheduled task antes prod? mock time? fast-forward?

9. **f7_sessions_impact** — quantas sessões F.7 ADICIONA vs base estimate 5? +0? +1? +2?

10. **dependencies_required** — Python packages, OS tools, infra (Redis? Docker?)

11. **cross_platform_support** — PC/VM/PC+VM/VM_only/PC_only

12. **estimated_complexity_score** 1-10 (1=trivial, 10=Celery+infra+devops)

Output ALTERNATIVE_DEEP_DIVE_SCHEMA. Seja TÉCNICO E CONCRETO — owner Claude vai usar isso pra implementar F.7.`,
  { label: `deepdive:${opt.id}`, phase: "Alternative Deep Dive", schema: ALTERNATIVE_DEEP_DIVE_SCHEMA }
)));

const validDeepDives = alternativeDeepDives.filter(Boolean);
log(`Deep dives done: ${validDeepDives.length}/8 alternatives`);

const deepDivesJson = JSON.stringify(validDeepDives, null, 2);

// ============ PHASE 3: ADVERSARIAL VERIFY (4 lenses × 8 alternatives pipeline) ============
phase("Adversarial Verify");
log("Pipeline 8 alternativas × 4 lentes — regression/complexity/cross-platform/future-proof. Aceita >=3/4 valid.");

const LENSES = [
  {
    key: "regression_risk",
    prompt_fn: (dd) => `Você é o REGRESSION RISK lens — adversarial verifier opção ${dd.option_id}) ${dd.option_name}.

DEEP DIVE FULL:
${JSON.stringify(dd, null, 2)}

CONTEXT (daemon state + Hermes deps):
${JSON.stringify({daemon: contextBundle.daemon_state, deps: contextBundle.hermes_deps}, null, 2).slice(0, 30000)}

ÁREAS MADURAS Hermes Fase F (touch = regression-test gate INVIOLÁVEL):
- daemon/orchestrator.py, hermes_api_v2.py, core/state.py, server.py, linkedin/limiter.py, linkedin/account_profile.py, core/ai.py, loops/*

SUA POSIÇÃO: skeptical defender. Default valid=FALSE se uncertain.

Avalie:
1. Quantos files MADUROS essa opção touch? Cada touch = regression risk + pre/post test obrigatório + reviewer.
2. Backward compat: scheduled task crash quebra daemon main loop (P1-P7)?
3. State coupling: scheduled task escreve em DB compartilhada — race condition vs daemon?
4. Restart safety: app restart enquanto task running — task state recuperável?
5. validate phase A B C D E provavelmente regredir (estimativa: zero/pouco/médio/alto)?

Score 1-10 (1=zero regression risk, 10=catastrophic).
Retorne VERDICT. valid=true APENAS se todos checks acima OK + score ≤4.`
  },
  {
    key: "complexity_roi",
    prompt_fn: (dd) => `Você é o COMPLEXITY/ROI lens — adversarial verifier opção ${dd.option_id}) ${dd.option_name}.

DEEP DIVE FULL:
${JSON.stringify(dd, null, 2)}

CONTEXT (F.7 tasks requirements):
${JSON.stringify(contextBundle.f7_tasks_requirements, null, 2).slice(0, 20000)}

SUA POSIÇÃO: skeptical realist. Hermes é owner-solo no-code project. Over-engineering = sin.

Avalie:
1. estimated_complexity_score (já fornecido) vs ROI F.7 (3 scheduled tasks confirmed) — balance certo?
2. f7_sessions_impact razoável vs base 5 sessões? +2 sessões pra schedule infra acceptable?
3. Dependencies novas: APScheduler 1 package vs Celery+Redis 5+ services — quanto cabe owner solo manter?
4. Learning curve owner Claude da sessão F.7 — sintaxe familiar (asyncio nativo) OR exótica (Celery decorators)?
5. Yagni — F.7 tem 3 tasks, opção justifica enterprise-grade infra? OR over-engineered?
6. Lock-in risk: trocar de schedule infra depois (F.future) — quão custoso?

Score 1-10 (1=zero overhead complexity, 10=infra heavy enterprise).
Retorne VERDICT. valid=true APENAS se complexity proporcional ao ROI F.7 + score ≤6.`
  },
  {
    key: "cross_platform",
    prompt_fn: (dd) => `Você é o CROSS-PLATFORM lens — adversarial verifier opção ${dd.option_id}) ${dd.option_name}.

DEEP DIVE FULL:
${JSON.stringify(dd, null, 2)}

CONTEXT (cross-platform constraints):
${JSON.stringify(contextBundle.cross_platform_constraints, null, 2).slice(0, 20000)}

ÁREAS Hermes: PC Windows (Hermes.exe Tauri) + VM Linux (linkedin/lab/scrapers/cobaia VM-only per GUARDRAILS).

SUA POSIÇÃO: skeptical realist about deployment topology.

Avalie:
1. cross_platform_support declarado (PC/VM/PC+VM/VM_only/PC_only) cobre necessidades F.7?
2. F.7 cobaia tasks vivem VM-only (linkedin/* per GUARDRAILS) — opção compatible VM Linux?
3. Daemon PC (mission control real-time) também precisa schedule? OR só VM cobaia?
4. Tauri lifecycle (Hermes.exe close = subprocess die) — scheduled task persiste?
5. Future MCP Gateway F.5 — opção compatible MCP-side scheduled invocations?
6. Owner pode trabalhar com Hermes desligado (laptop fechado) — VM-side schedule continua?

Score 1-10 (1=universal compat, 10=PC-only OR VM-only with caveats).
Retorne VERDICT. valid=true APENAS se cross-platform cobre F.7 needs + score ≤5.`
  },
  {
    key: "future_proof",
    prompt_fn: (dd) => `Você é o FUTURE-PROOF lens — adversarial verifier opção ${dd.option_id}) ${dd.option_name}.

DEEP DIVE FULL:
${JSON.stringify(dd, null, 2)}

CONTEXT F.7+ chapters seguintes:
- F.8 Cost & Performance Observability (vai instrumentar TODOS scheduled tasks pra cost/perf metrics)
- F.9 Pipeline Studio Visual (pipeline scheduled runs?)
- F.future MCP Gateway scheduled tools

SUA POSIÇÃO: skeptical futurist. Quer maximizar reuse cross-chapters sem rebuild.

Avalie:
1. F.8 Observability — opção expõe job metrics natively (duration, fail rate, runs count)? OR precisa wrapper custom?
2. F.9 Pipeline Studio — pipelines scheduled runs reuse essa infra? OR build separate?
3. F.future MCP scheduled-tasks server — opção compose com MCP gateway naturally?
4. F.6 Brain decision audit — Brain pode disparar scheduled task? observability decisão→agendamento?
5. Migration path: F.7 vai usar X, F.8 add observability over X, F.9 add UI builder sobre X — opção suporta crescimento?
6. Standard ecosystem trajectory 2026+ — opção é o que comunidade Python async vai usar nos próximos 2 anos?

Score 1-10 (1=future-proof multi-chapter, 10=throwaway F.7 only).
Retorne VERDICT. valid=true APENAS se opção sustenta F.7+F.8+F.9 reuse + score ≤5.`
  }
];

const verifiedAlternatives = await pipeline(
  validDeepDives,
  dd => parallel(LENSES.map(lens => () => agent(lens.prompt_fn(dd), {
    label: `verify:${dd.option_id}:${lens.key}`,
    phase: "Adversarial Verify",
    schema: VERDICT_SCHEMA
  }))).then(verdicts => {
    const valid = verdicts.filter(Boolean);
    const validCount = valid.filter(v => v.valid).length;
    const totalScore = valid.reduce((s, v) => s + (v.score || 0), 0);
    const accepted = validCount >= 3;
    const lensBreakdown = valid.reduce((acc, v) => { acc[v.lens] = { valid: v.valid, score: v.score, confidence: v.confidence }; return acc; }, {});
    return {
      ...dd,
      verdicts: valid,
      verdict_summary: { valid_count: validCount, total: valid.length, accepted, total_score: totalScore, lens_breakdown: lensBreakdown },
      blockers_aggregated: valid.flatMap(v => v.blockers || []),
      suggestions_aggregated: valid.flatMap(v => v.suggestions || [])
    };
  })
);

const validVerified = verifiedAlternatives.filter(Boolean);
const acceptedAlternatives = validVerified.filter(v => v.verdict_summary?.accepted);
log(`Verified: ${acceptedAlternatives.length}/${validVerified.length} alternatives accepted (>=3/4 lenses valid)`);

const verifiedJson = JSON.stringify(validVerified, null, 2);

// ============ PHASE 4: SYNTHESIS RECOMMENDATION ============
phase("Synthesis Recommendation");
log("1 agent synth: rank 8 opções + PRIMARY/FALLBACK/LONG-TERM tiers + F.7 implementation plan + migration");

const recommendation = await agent(
  `Você é o RECOMMENDATION SYNTHESIZER pra workflow f7-schedule-arch-analysis.

INPUTS:
1. Context bundle (5 fragments): ${contextJson.slice(0, 40000)}

2. 8 alternativas com verdicts + scores: ${verifiedJson.slice(0, 80000)}

OBJETIVO: produzir recommendation FINAL F.7 schedule infra. Decisão arquitetural durável que owner Claude da sessão F.7 vai seguir SEM ambiguity.

Tarefas:

1. **Rank table 8 opções** — total_score (sum lens scores INVERSO, lower=better) + lens_breakdown each.

2. **Primary option** — recomendação principal. Justificativa rationale 3-5 frases concretas referenciando Hermes deps + F.7 tasks + cross-platform.

3. **Fallback option** — se Primary tiver blocker imprevisto durante F.7 implementação, fallback safe. Rationale.

4. **Long-term option** — opção pra eventually migrar (F.future quando justify), pode ser diferente de Primary.

5. **F.7 Tasks 2/3/4 implementation plan** — concreto, código-implementável:
   - Task 2 (métricas 1h coletor): pseudo-code adaptado Primary option
   - Task 3 (stop gates 30min check): pseudo-code adaptado
   - Task 4 (Telegram 19h daily): pseudo-code adaptado
   - Lifecycle integration FastAPI lifespan
   - Error handling unified pattern
   - Observability hooks F.8 prep

6. **Migration checklist** — 8-12 steps concretos, ordenados, do estado atual (zero scheduled tasks) ao F.7 steady-state:
   - Dependency add (requirements.txt)
   - Infra setup (config, dirs, permissions)
   - Code integration (daemon, lifespan, lifespan)
   - DB migrations (job persistence se relevante)
   - Smoke test (mock time, fast-forward)
   - Deploy VM (scp + systemd OR crontab OR similar)
   - Validate (run task 1x manual, verify state effect)
   - Rollback ready (git revert + DB revert)

7. **Risk mitigation** — pra cada blocker top-3 aggregated cross-verdicts, mitigation concreta.

8. **Success criteria F.7** — 5-8 critérios mensuráveis (e.g., "1h metric task ran without skip for 24h", "stop gate triggered when compliance<70 in <60s", "Telegram 19h daily delivery 7d streak").

9. **Rollback plan** — se Primary option implementado e mostrar problema produção F.7+, como reverter sem perder warmup state cobaia.

Output RECOMMENDATION_SCHEMA. Seja DECISIVO — owner Claude vai seguir essa recommendation. Cite option_id (A-H) explicit. NÃO ambiguity.`,
  { label: "synthesis:recommendation", phase: "Synthesis Recommendation", schema: RECOMMENDATION_SCHEMA }
);

log(`Recommendation synthesized. Primary: ${recommendation?.primary_option}. Fallback: ${recommendation?.fallback_option}. Long-term: ${recommendation?.long_term_option}.`);

const recommendationJson = JSON.stringify(recommendation, null, 2);

// ============ PHASE 5: ARTIFACT GENERATION ============
phase("Artifact Generation");
log("Fan-out 2 agents paralelos: F7-SCHEDULE-ARCH-DECISION.md (main) + PLAN.md patch suggestion");

const artifacts = await parallel([
  () => agent(
    `Gere ${HERMES_ROOT}/.claude/F7-SCHEDULE-ARCH-DECISION.md (DECISÃO FINAL arquitetural schedule infra F.7).

INPUTS (use tudo, não cortar):
- Context bundle: ${contextJson.slice(0, 40000)}
- 8 alternativas verified: ${verifiedJson.slice(0, 70000)}
- Recommendation: ${recommendationJson}

ESTRUTURA OBRIGATÓRIA (~8-12k chars):

# F.7 Schedule Infrastructure — Decisão Arquitetural Final

## 1. Context (origem decisão)
Descoberta F.3.4 2026-06-10 + memory cross-ref + PLAN.md F.7 bloco "🚨 DECISÃO ARQUITETURAL PENDENTE".

## 2. Sumário Executivo
- Primary recommendation: <option_id>) <option_name>
- Rationale 2-3 frases
- F.7 sessions impact: base 5 → real X
- Dependencies novas: list

## 3. 8 Alternativas Avaliadas
Tabela rank com 8 rows:
| Rank | Option | Total Score | Regression | Complexity | Cross-Platform | Future-Proof | Accepted (≥3/4) |

## 4. Análise Detalhada Primary Option
Implementation pseudo-code + integration points + migration steps + failure recovery + observability hooks + test strategy + dependencies + cross-platform support.

## 5. F.7 Tasks 2/3/4 Implementation Plan
Pseudo-code Python concreto, owner Claude pode copy-paste-adapt:
- Task 2 (métricas 1h coletor)
- Task 3 (stop gates 30min check)
- Task 4 (Telegram 19h daily report)
- FastAPI lifespan integration
- Error handling unified pattern
- Observability hooks F.8 prep

## 6. Migration Checklist
8-12 steps ordenados implementação F.7 schedule infra do zero ao steady-state.

## 7. Fallback Option
Se Primary tiver blocker imprevisto F.7 — fallback safe + rationale + migration path Primary → Fallback.

## 8. Long-term Option
Opção pra eventually migrar (F.future), rationale + trigger condições migrate.

## 9. Risk Mitigation
Top-5 blockers cross-verdicts + mitigation concreta cada.

## 10. Success Criteria F.7 (5-8 critérios mensuráveis)

## 11. Rollback Plan
Se Primary problemático produção, como reverter sem perder warmup state cobaia.

## 12. Cross-References
- F.3.4 discovery commit c3c24d3
- Memory mem_mq7fh8qa + mem_mq7eyrio
- PLAN.md F.7 bloco "🚨 DECISÃO ARQUITETURAL PENDENTE"
- This workflow run output

## 13. Approval Checklist (owner DEVE marcar antes F.7 session)
- [ ] Owner leu sumário executivo + rationale Primary
- [ ] Owner confirma dependencies novas acceptable (requirements.txt impact)
- [ ] Owner aceita f7_sessions_impact (+N sessões vs base 5)
- [ ] Owner ciente fallback option se Primary falhar

Output ARTIFACT_SPEC com filename="F7-SCHEDULE-ARCH-DECISION.md", full_path="${HERMES_ROOT}/.claude/F7-SCHEDULE-ARCH-DECISION.md", content=markdown completo, replaces_existing=false.

CRITICAL: documento DEFINITIVO. Owner DEVE conseguir decidir F.7 schedule infra apenas lendo isso, sem voltar ao workflow runs. Inclua TODO contexto necessário.`,
    { label: "gen:decision_md", phase: "Artifact Generation", schema: ARTIFACT_SPEC_SCHEMA }
  ),
  () => agent(
    `Gere PATCH SUGGESTION PLAN.md F.7 section atualização (substituir bloco "🚨 DECISÃO ARQUITETURAL PENDENTE" placeholder com decisão real).

INPUTS:
- Recommendation: ${recommendationJson}
- PLAN.md current F.7 bloco placeholder existe linhas ~388-420 (após "Done criteria F.7")

OUTPUT: ARTIFACT_SPEC com filename="PLAN-F7-PATCH-SUGGESTION.md", full_path="${HERMES_ROOT}/.claude/PLAN-F7-PATCH-SUGGESTION.md", content=instruções patch concretas + diff sugerido + git command exato.

Estrutura PATCH (~2-3k chars):

# PLAN.md F.7 Patch Suggestion (post f7-schedule-arch-analysis)

## Bloco a substituir
Texto atual placeholder "🚨 DECISÃO ARQUITETURAL PENDENTE — Schedule Infrastructure" + 8 alternativas table + 5 critérios + tentativa recommendation default.

## Bloco novo (replace por)
"### Schedule Infrastructure — Decisão Final (workflow f7-schedule-arch-analysis 2026-06-10)

**Primary**: <option_id>) <option_name> — <rationale>
**Fallback**: <option_id>) <option_name> — <trigger fallback condition>
**Long-term migration**: <option_id>) <option_name> — <trigger condition>

**F.7 Tasks 2/3/4 implementation**: ver .claude/F7-SCHEDULE-ARCH-DECISION.md sections 5-6 (pseudo-code + migration checklist).

**Dependencies novas**: <list>
**F.7 sessions impact**: base 5 → <X> sessões reais
**Success criteria**: ver .claude/F7-SCHEDULE-ARCH-DECISION.md section 10

**Rollback plan**: ver .claude/F7-SCHEDULE-ARCH-DECISION.md section 11"

## Git command (sequence, sem code block markdown pra evitar template literal conflict)
- Owner aplica manualmente (revisão crítica antes commit)
- Step 1: Read .claude/F7-SCHEDULE-ARCH-DECISION.md completo
- Step 2: Approval checklist section 13 marcado
- Step 3: Edit .claude/PLAN.md substitui bloco placeholder
- Step 4: git add .claude/PLAN.md
- Step 5: git commit message: docs(plan) F.7 schedule infra decisão final
- Step 6: git push origin master

## Instruções owner Claude da sessão F.7
ANTES iniciar F.7 sessão dedicada:
1. Read .claude/F7-SCHEDULE-ARCH-DECISION.md (completo, decisão arquitetural)
2. Confirm PLAN.md F.7 bloco "Schedule Infrastructure" reflete decisão (não placeholder antigo)
3. Confirm requirements.txt tem dependencies novas (se Primary requer)
4. Use F.7 Tasks 2/3/4 implementation plan section 5 como base, NÃO improvisar

Output ARTIFACT_SPEC schema.`,
    { label: "gen:plan_patch", phase: "Artifact Generation", schema: ARTIFACT_SPEC_SCHEMA }
  )
]);

const validArtifacts = artifacts.filter(Boolean);
log(`Artifacts generated: ${validArtifacts.length}/2`);

// ============ RETURN ============
const summary = {
  workflow: "f7-schedule-arch-analysis",
  phase_target: "F.7",
  context_fragments: Object.keys(contextBundle).length,
  alternatives_analyzed: validDeepDives.length,
  alternatives_accepted_by_verify: acceptedAlternatives.length,
  primary_recommendation: recommendation?.primary_option,
  fallback_recommendation: recommendation?.fallback_option,
  long_term_recommendation: recommendation?.long_term_option,
  artifacts_generated: validArtifacts.length,
  total_verifications: validVerified.reduce((s, v) => s + (v.verdicts?.length || 0), 0)
};

log(`F.7 schedule arch analysis complete. Primary: ${recommendation?.primary_option}. Artifacts ready: ${validArtifacts.length}.`);

return {
  summary,
  artifacts: validArtifacts,
  recommendation,
  alternatives_verified: validVerified,
  context_bundle: contextBundle
};
