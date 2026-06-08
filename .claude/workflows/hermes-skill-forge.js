// hermes-skill-forge.js — Auto-Skill Loop W3 do Hermes
//
// Workflow autonomo que analisa activity_log + outcomes recentes, identifica
// padroes recorrentes (PME Cuiaba responde X dia/horario, hook Y converte mais,
// CTA Z gera mais reply) e PROPÕE skills YAML novas/atualizadas pra owner aprovar.
//
// Diferente do generation manual: roda ciclico (cron), respeita cooldown 24h
// por (subsystem, skill_family) pra evitar spam de proposals, valida cada
// proposal via verify multi-lens (3 lentes: pattern_strength, owner_value,
// safety_risk) antes de gravar em .claude/proposed-skills/.
//
// Output:
// - .claude/proposed-skills/{timestamp}-{slug}.yaml (skill candidata)
// - .claude/proposed-skills/{timestamp}-{slug}.md (justificativa + evidencias)
// - .claude/skill-forge-state.json (cooldown tracker + ultima execucao)
// - Notifica owner via WS event 'skill_proposal' (consumida pelo Mission Control F.2)
//
// Custo estimado: 60-200k tokens output por ciclo (variavel — depende quantos
// padroes detectados + quantas familias passam do cooldown). Roda max 1x/dia.

export const meta = {
  name: "hermes-skill-forge",
  description:
    "Auto-skill loop W3 — analisa activity_log Hermes, detecta padroes recorrentes em outcomes (replies, deals, bans evitados), propoe skills YAML novas/atualizadas, valida via 3-lens verify, respeita cooldown 24h por familia. Output: .claude/proposed-skills/*.yaml + .md pra owner aprovar via Mission Control.",
  phases: [
    { title: "GateCooldown", detail: "Le skill-forge-state.json, filtra familias dentro do cooldown 24h" },
    { title: "Sample", detail: "Le activity_log + outcomes ultimos 30d, agrupa por familia (subsystem + outcome_type)" },
    { title: "DetectPatterns", detail: "5 agents paralelos: 1 por familia elegivel (linkedin_message, linkedin_connect, email_warmup, daemon_decision, scraper_qualify)" },
    { title: "ProposeSkills", detail: "Pra cada padrao significativo (n>=10, effect_size>=0.15): gera skill YAML candidata" },
    { title: "Verify", detail: "3 lentes independentes por proposal: pattern_strength, owner_value, safety_risk" },
    { title: "Persist", detail: "Grava aprovadas em .claude/proposed-skills/ + atualiza cooldown state + emit WS event" },
  ],
};

const HERMES_ROOT = "D:/dev-projects/main/hermes-cloud-studio";
const PROPOSED_DIR = `${HERMES_ROOT}/.claude/proposed-skills`;
const STATE_PATH = `${HERMES_ROOT}/.claude/skill-forge-state.json`;
const DB_PATH = `${HERMES_ROOT}/hermes_local.db`;
const COOLDOWN_HOURS = 24;
const MIN_SAMPLE_SIZE = 10;
const MIN_EFFECT_SIZE = 0.15;
const MAX_PROPOSALS_PER_CYCLE = 5;

// ====================== SCHEMAS ======================

const FAMILY_PATTERNS_SCHEMA = {
  type: "object",
  properties: {
    family: { type: "string", description: "linkedin_message | linkedin_connect | email_warmup | daemon_decision | scraper_qualify" },
    sample_size: { type: "integer", description: "Numero de eventos analisados" },
    window_days: { type: "integer" },
    patterns: {
      type: "array",
      items: {
        type: "object",
        properties: {
          id: { type: "string", description: "PAT-XXX sequencial dentro da familia" },
          title: { type: "string", description: "Padrao em 1 frase ex: 'PME Cuiaba responde 3x mais entre 19h-21h ter/qui'" },
          dimension: {
            type: "string",
            enum: ["timing", "hook_style", "cta_format", "icp_segment", "channel_mix", "follow_up_cadence", "subject_line", "rate_envelope"],
          },
          baseline_metric: { type: "string", description: "Ex: 'reply rate medio 6.2%'" },
          observed_metric: { type: "string", description: "Ex: 'reply rate 18.7% quando enviado ter/qui 19-21h pra ICP comercio_local'" },
          effect_size: { type: "number", description: "Lift relativo (observed/baseline - 1). Ex: 2.0 = 200% mais. Min 0.15 pra propor." },
          evidence_count: { type: "integer", description: "N de eventos que sustentam o padrao. Min 10." },
          counter_evidence: { type: "string", description: "Casos em que o padrao NAO se sustentou (sanity check anti-cherry-pick)" },
          suggested_skill_action: {
            type: "string",
            enum: ["create_new_skill", "patch_existing_skill", "deprecate_existing_skill", "tighten_limiter", "loosen_limiter"],
          },
          target_skill_file: { type: "string", description: "Ex: 'skills/linkedin-connection-sender.yaml' se patch_existing; vazio se create_new" },
        },
        required: ["id", "title", "dimension", "effect_size", "evidence_count", "suggested_skill_action"],
      },
    },
  },
  required: ["family", "sample_size", "patterns"],
};

const SKILL_PROPOSAL_SCHEMA = {
  type: "object",
  properties: {
    slug: { type: "string", description: "kebab-case curto, ex: 'linkedin-twilight-tue-thu'" },
    title: { type: "string" },
    family: { type: "string" },
    pattern_id: { type: "string", description: "Referencia ao PAT-XXX que motivou" },
    action: { type: "string", enum: ["create_new_skill", "patch_existing_skill", "deprecate_existing_skill", "tighten_limiter", "loosen_limiter"] },
    target_path: { type: "string", description: "Caminho final relativo ao projeto. Ex: skills/linkedin-twilight-tue-thu.yaml" },
    yaml_content: { type: "string", description: "Conteudo COMPLETO YAML da skill candidata (formato compativel com skills/*.yaml existentes — name, description, trigger, steps, guardrails)" },
    rationale_md: { type: "string", description: "Markdown justificativa: baseline vs observado, sample size, effect size, contra-evidencias, riscos, plano de rollback" },
    expected_impact: { type: "string", description: "Estimativa ganho ex: 'reply rate +12pp se ICP comercio_local' " },
    rollback_plan: { type: "string", description: "Como reverter se metricas piorarem em 7d" },
    requires_owner_review: { type: "boolean", description: "Se action toca rate-limit/auth/anti-deteccao = TRUE obrigatorio" },
  },
  required: ["slug", "title", "family", "action", "target_path", "yaml_content", "rationale_md", "requires_owner_review"],
};

const VERDICT_SCHEMA = {
  type: "object",
  properties: {
    lens: { type: "string", enum: ["pattern_strength", "owner_value", "safety_risk"] },
    valid: { type: "boolean" },
    confidence: { type: "string", enum: ["low", "medium", "high"] },
    reasoning: { type: "string", description: "2-5 frases concretas, cite numeros do pattern + nome de arquivo se aplicavel" },
    blockers: { type: "array", items: { type: "string" } },
    suggestions: { type: "array", items: { type: "string" } },
  },
  required: ["lens", "valid", "confidence", "reasoning"],
};

// ====================== PHASE 1 — GATE COOLDOWN ======================
phase("GateCooldown");
log("Le skill-forge-state.json + filtra familias dentro do cooldown 24h");

const stateRaw = await readFileOptional(STATE_PATH);
const state = stateRaw
  ? JSON.parse(stateRaw)
  : { last_cycle: null, cooldowns: {}, history: [] };

const now = Date.now();
const ALL_FAMILIES = [
  "linkedin_message",
  "linkedin_connect",
  "email_warmup",
  "daemon_decision",
  "scraper_qualify",
];

const eligibleFamilies = ALL_FAMILIES.filter((fam) => {
  const lastRun = state.cooldowns?.[fam];
  if (!lastRun) return true;
  const hoursSince = (now - lastRun) / (1000 * 60 * 60);
  if (hoursSince < COOLDOWN_HOURS) {
    log(`Family ${fam} em cooldown (ultimo run ha ${hoursSince.toFixed(1)}h, < ${COOLDOWN_HOURS}h) — SKIP`);
    return false;
  }
  return true;
});

if (eligibleFamilies.length === 0) {
  log("Todas familias em cooldown. Encerrando ciclo sem propor nada.");
  return {
    cycle_skipped: true,
    reason: "all families in cooldown",
    next_eligible_at: Math.min(...Object.values(state.cooldowns || {}).map((t) => t + COOLDOWN_HOURS * 3600 * 1000)),
    proposals: 0,
  };
}

log(`Familias elegiveis (cooldown OK): ${eligibleFamilies.join(", ")}`);

// ====================== PHASE 2 — SAMPLE ACTIVITY LOG ======================
phase("Sample");
log("Lendo activity_log + outcomes dos ultimos 30d via SQLite");

const sampleAgent = await agent(
  `Leia o DB SQLite em ${DB_PATH} (read-only). Extraia amostras agregadas por familia para os ultimos 30 dias.

Familias elegiveis: ${eligibleFamilies.join(", ")}.

Tarefa: pra cada familia elegivel, rode queries READ-ONLY que devolvam:
- activity_log: ultimos 30d filtrado por subsystem matching a familia
  * linkedin_message → subsystem='linkedin' AND action IN ('message_sent','message_replied','message_read')
  * linkedin_connect → subsystem='linkedin' AND action IN ('connect_sent','connect_accepted','connect_ignored')
  * email_warmup → subsystem='email' AND action IN ('email_sent','email_replied','email_bounced','email_marked_spam')
  * daemon_decision → subsystem='daemon' AND action LIKE 'decision_%'
  * scraper_qualify → subsystem='scraper' AND action IN ('lead_qualified','lead_rejected')

Pra cada familia retorne:
{
  family: "...",
  sample_size: <int>,
  window_days: 30,
  raw_events: [<max 200 eventos amostrados representativamente — incluir timestamp, action, outcome, target_id, metadata JSON>],
  outcome_summary: {
    success_count, failure_count, neutral_count,
    baseline_success_rate,
    breakdown_by_hour, breakdown_by_weekday, breakdown_by_icp_segment, breakdown_by_hook (se aplicavel)
  }
}

Se familia tem <${MIN_SAMPLE_SIZE} eventos no periodo: marcar sample_size baixo + raw_events vazio (sera filtrada na fase seguinte).

NUNCA execute INSERT/UPDATE/DELETE. Use sqlite3 CLI ou python sqlite3 read-only mode.
Caminho DB: ${DB_PATH}.

Retorne JSON com array { samples: [...] }.`,
  {
    phase: "Sample",
    label: "sample-activity-log",
    schema: {
      type: "object",
      properties: {
        samples: {
          type: "array",
          items: {
            type: "object",
            properties: {
              family: { type: "string" },
              sample_size: { type: "integer" },
              window_days: { type: "integer" },
              raw_events: { type: "array", items: { type: "object" } },
              outcome_summary: { type: "object" },
            },
            required: ["family", "sample_size"],
          },
        },
      },
      required: ["samples"],
    },
  }
);

const samples = (sampleAgent?.samples ?? []).filter(
  (s) => eligibleFamilies.includes(s.family) && s.sample_size >= MIN_SAMPLE_SIZE
);

log(`Sample: ${samples.length}/${eligibleFamilies.length} familias com >= ${MIN_SAMPLE_SIZE} eventos (elegiveis pra detecao)`);

if (samples.length === 0) {
  log("Nenhuma familia com amostra suficiente. Encerrando sem propor.");
  state.last_cycle = now;
  await writeFile(STATE_PATH, JSON.stringify(state, null, 2));
  return { cycle_skipped: true, reason: "insufficient samples", proposals: 0 };
}

// ====================== PHASE 3 — DETECT PATTERNS ======================
phase("DetectPatterns");
log(`Fan-out: ${samples.length} agents paralelos (1 por familia)`);

const familyPatterns = await parallel(
  samples.map((sample) => () =>
    agent(
      `Voce e analista de padroes operacionais Hermes. Familia: ${sample.family}.

DATA RECEBIDA:
${JSON.stringify(sample, null, 2).slice(0, 25000)}

OBJETIVO: identificar padroes RECORRENTES, ESTATISTICAMENTE SIGNIFICATIVOS, ACIONAVEIS.

CRITERIOS RIGIDOS (descarte padrao que falhar):
- evidence_count >= ${MIN_SAMPLE_SIZE}
- effect_size >= ${MIN_EFFECT_SIZE} (lift de pelo menos 15% sobre baseline)
- counter_evidence preenchido (se nao houver contra-casos, padrao e ruido)
- dimension entre: timing | hook_style | cta_format | icp_segment | channel_mix | follow_up_cadence | subject_line | rate_envelope

PROIBIDO:
- Cherry-picking (citar so casos que confirmam)
- Padroes que exigem expandir rate-limit linkedin (zona MADURA — owner ja calibrou em B/D)
- Padroes que sugerem bypass anti-deteccao (zona MADURA — STEALTH-PATCHES.md owns)
- Padroes baseados em <10 eventos
- Padroes generalistas sem corte ("enviar mais cedo funciona" — falta segmento)

PRA CADA PADRAO VALIDO, sugerir suggested_skill_action:
- create_new_skill: padrao novo, sem skill existente cobrindo
- patch_existing_skill: melhoria de skill ja em skills/*.yaml (citar arquivo)
- deprecate_existing_skill: skill atual contradiz padrao
- tighten_limiter: padrao mostra ban/spam quando passa de X — REQUER REVIEW OWNER
- loosen_limiter: padrao mostra ganho ao relaxar — REQUER REVIEW OWNER

Maximo 4 padroes por familia. Qualidade > quantidade.

Retorne via FAMILY_PATTERNS_SCHEMA.`,
      {
        phase: "DetectPatterns",
        schema: FAMILY_PATTERNS_SCHEMA,
        label: `detect:${sample.family}`,
      }
    )
  )
);

const allPatterns = familyPatterns
  .filter(Boolean)
  .flatMap((fp) =>
    (fp.patterns ?? [])
      .filter(
        (p) =>
          p.evidence_count >= MIN_SAMPLE_SIZE &&
          p.effect_size >= MIN_EFFECT_SIZE &&
          p.counter_evidence
      )
      .map((p) => ({ ...p, family: fp.family }))
  );

log(`DetectPatterns: ${allPatterns.length} padroes brutos passaram nos filtros estatisticos`);

if (allPatterns.length === 0) {
  log("Nenhum padrao significativo. Atualizando cooldown e encerrando.");
  for (const fam of samples.map((s) => s.family)) {
    state.cooldowns[fam] = now;
  }
  state.last_cycle = now;
  await writeFile(STATE_PATH, JSON.stringify(state, null, 2));
  return { cycle_skipped: false, proposals: 0, reason: "no significant patterns" };
}

// Ranking: prioriza maior effect_size * log(evidence_count). Top MAX_PROPOSALS_PER_CYCLE.
allPatterns.sort((a, b) => {
  const scoreA = a.effect_size * Math.log(a.evidence_count + 1);
  const scoreB = b.effect_size * Math.log(b.evidence_count + 1);
  return scoreB - scoreA;
});
const topPatterns = allPatterns.slice(0, MAX_PROPOSALS_PER_CYCLE);

log(`Top ${topPatterns.length} padroes selecionados pra virar proposal`);

// ====================== PHASE 4 — PROPOSE SKILLS ======================
phase("ProposeSkills");
log(`Gerando ${topPatterns.length} proposals de skill em paralelo`);

const proposals = await parallel(
  topPatterns.map((pattern) => () =>
    agent(
      `Voce e arquiteto de skills Hermes. Baseado no PADRAO abaixo, gere uma SKILL YAML CANDIDATA.

PADRAO:
${JSON.stringify(pattern, null, 2)}

REFERENCIA — formato YAML das skills existentes em ${HERMES_ROOT}/skills/:
- linkedin-connection-sender.yaml
- linkedin-engagement.yaml
- linkedin-post-generator.yaml
- linkedin-profile-researcher.yaml
- linkedin-trend-monitor.yaml
- weekly-mission-planner.yaml

OBRIGATORIO no YAML candidato:
- name: kebab-case unico
- description: 1-2 frases descrevendo quando disparar
- trigger: condicao concreta (cron, event, manual, hour-of-day)
- steps: lista de acoes ordenadas (referencias a subsystem + action existentes — NAO inventar API nova)
- guardrails: lista de proibicoes (ex: 'nunca exceder limiter atual', 'so dispara em working hours', 'cooldown 24h por target')
- metrics: como medir sucesso (ex: 'reply_rate@7d > baseline + 10pp')

PRA action='patch_existing_skill': yaml_content deve ser DIFF logico (NAO arquivo completo) — describar o que muda + onde + porque.

PRA action='tighten_limiter' ou 'loosen_limiter': requires_owner_review=TRUE obrigatorio. target_path aponta pra core/limiter.py ou linkedin/limiter.py — yaml_content vira proposta de patch + justificativa numerica.

PRA action='deprecate_existing_skill': yaml_content e markdown explicando porque + qual skill substitui (se houver).

Rationale_md deve ter:
- # Padrao detectado
- ## Numeros (baseline, observado, effect_size, sample_size, window)
- ## Contra-evidencia (porque NAO e ruido)
- ## Risco se aplicar
- ## Rollback plan
- ## Owner review checklist (se requires_owner_review)

Retorne via SKILL_PROPOSAL_SCHEMA. slug em kebab-case curto, target_path absoluto-relativo (skills/foo.yaml).`,
      {
        phase: "ProposeSkills",
        schema: SKILL_PROPOSAL_SCHEMA,
        label: `propose:${pattern.id}:${pattern.family}`,
      }
    )
  )
);

const validProposals = proposals.filter(
  (p) => p && p.slug && p.yaml_content && p.rationale_md
);

log(`ProposeSkills: ${validProposals.length}/${topPatterns.length} proposals geradas com sucesso`);

if (validProposals.length === 0) {
  log("Nenhuma proposal valida. Encerrando.");
  for (const fam of samples.map((s) => s.family)) {
    state.cooldowns[fam] = now;
  }
  state.last_cycle = now;
  await writeFile(STATE_PATH, JSON.stringify(state, null, 2));
  return { cycle_skipped: false, proposals: 0, reason: "all proposals failed schema" };
}

// ====================== PHASE 5 — VERIFY MULTI-LENS ======================
phase("Verify");
log("Cada proposal validada por 3 lentes independentes: pattern_strength, owner_value, safety_risk");

const lenses = [
  {
    name: "pattern_strength",
    prompt: (p) =>
      `Lente PATTERN_STRENGTH. Avalie esta proposta de skill:
${JSON.stringify({ slug: p.slug, family: p.family, action: p.action, rationale_md: p.rationale_md, expected_impact: p.expected_impact }, null, 2)}

PERGUNTAS:
1. O padrao detectado realmente sustenta a skill proposta? (rationale cita numeros concretos?)
2. effect_size declarado e plausivel dado evidence_count? (ex: lift 200% com n=12 e estatisticamente fragil)
3. Counter-evidence foi honestamente endereçada ou e excusa?
4. Skill proposta ataca o padrao certo ou e tangencial?

valid=FALSE se: rationale_md sem numeros, evidence_count<10 mesmo declarando alto, contra-evidencia ausente ou trivial, ou padrao nao mapeia 1:1 pra skill.

Seja CETICO. Default valid=false em duvida.`,
  },
  {
    name: "owner_value",
    prompt: (p) =>
      `Lente OWNER_VALUE. Avalie esta proposta:
${JSON.stringify({ slug: p.slug, action: p.action, target_path: p.target_path, expected_impact: p.expected_impact, requires_owner_review: p.requires_owner_review }, null, 2)}

CONTEXTO OWNER: cleao opera Hermes solo, prioriza B2B PME Cuiaba, ja tem 6 skills LinkedIn ativas em skills/*.yaml.

PERGUNTAS:
1. Essa skill resolve dor REAL do owner ou e otimizacao academica?
2. Owner consegue entender + aprovar em <3min lendo rationale_md?
3. Expected_impact e mensuravel ou wishful thinking?
4. Ja existe skill cobrindo isso (sobreposicao com as 6 atuais)?
5. Se patch_existing: diff e cirurgico ou reescrita disfarcada?

valid=FALSE se: ganho marginal (<5pp em metrica owner valoriza), duplica skill existente, ou rationale nao explica em portugues claro pra owner aprovar.`,
  },
  {
    name: "safety_risk",
    prompt: (p) =>
      `Lente SAFETY_RISK. Avalie esta proposta:
${JSON.stringify({ slug: p.slug, family: p.family, action: p.action, target_path: p.target_path, yaml_content: (p.yaml_content || "").slice(0, 3000), requires_owner_review: p.requires_owner_review, rollback_plan: p.rollback_plan }, null, 2)}

GUARDRAILS HERMES (NUNCA VIOLAR):
- core/state.py, loops/sync.py, api/dashboard.py, core/limiter.py = MADURO (owner ja calibrou em Fases A/B/D)
- linkedin/limiter.py warm-up 14d e SAGRADO — afrouxar = risco ban conta Caio
- linkedin/stealth.py e human.py = MADURO — STEALTH-PATCHES.md owns
- Ban LinkedIn = nuclear (conta unica owner)
- Email reputation dominio = critico (warmup 14d)

PERGUNTAS:
1. Skill toca zona MADURA? Se sim: requires_owner_review=TRUE? rollback_plan concreto (nao "reverter via git")?
2. Pode causar regressao em Fases A-E (validate_implementation.py 20/22 PASS)?
3. Se action=loosen_limiter: aumenta risco ban? Sample size justifica?
4. Se action=tighten_limiter: pode parar pipeline producao?
5. Rollback_plan tem trigger objetivo (ex: 'se reply_rate cair >5pp em 7d') ou e generico?

valid=FALSE se: toca zona MADURA sem owner_review flag, rollback_plan vago, ou risco ban/reputation >> ganho esperado.

Seja PARANOICO. Default valid=false em duvida.`,
  },
];

const verifiedProposals = await parallel(
  validProposals.map((proposal) => () =>
    parallel(
      lenses.map((l) => () =>
        agent(l.prompt(proposal), {
          phase: "Verify",
          schema: VERDICT_SCHEMA,
          label: `verify:${proposal.slug}:${l.name}`,
        })
      )
    ).then((verdicts) => {
      const valids = verdicts.filter(Boolean).filter((v) => v.valid);
      return {
        proposal,
        verdicts: verdicts.filter(Boolean),
        confirmed: valids.length >= 2,
        score: valids.length,
        blockers_aggregated: verdicts
          .filter(Boolean)
          .flatMap((v) => v.blockers ?? []),
      };
    })
  )
);

const confirmed = verifiedProposals.filter((v) => v && v.confirmed);
const rejected = verifiedProposals.filter((v) => v && !v.confirmed);

log(`Verify: ${confirmed.length}/${verifiedProposals.length} proposals confirmadas (>=2 lentes valid)`);

// ====================== PHASE 6 — PERSIST ======================
phase("Persist");
log(`Gravando ${confirmed.length} proposals em ${PROPOSED_DIR}`);

await ensureDir(PROPOSED_DIR);

const timestamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
const persistedFiles = [];

for (const v of confirmed) {
  const p = v.proposal;
  const baseName = `${timestamp}-${p.slug}`;
  const yamlPath = `${PROPOSED_DIR}/${baseName}.yaml`;
  const mdPath = `${PROPOSED_DIR}/${baseName}.md`;

  // YAML candidato (skill proposta)
  await writeFile(yamlPath, p.yaml_content);

  // Markdown justificativa + verdicts
  let md = `# Skill Proposal — ${p.title}\n\n`;
  md += `- **Slug**: \`${p.slug}\`\n`;
  md += `- **Family**: ${p.family}\n`;
  md += `- **Action**: ${p.action}\n`;
  md += `- **Target**: \`${p.target_path}\`\n`;
  md += `- **Requires owner review**: ${p.requires_owner_review ? "SIM" : "Nao"}\n`;
  md += `- **Verify score**: ${v.score}/3 lentes\n`;
  md += `- **Pattern ID**: ${p.pattern_id || "(n/a)"}\n\n`;
  md += `## Expected impact\n\n${p.expected_impact || "(nao declarado)"}\n\n`;
  md += `## Rationale\n\n${p.rationale_md}\n\n`;
  md += `## Rollback plan\n\n${p.rollback_plan || "(faltando — owner exigir antes de aplicar)"}\n\n`;
  md += `## Verify verdicts\n\n`;
  for (const verdict of v.verdicts) {
    md += `### Lens ${verdict.lens || "?"} — ${verdict.valid ? "OK" : "FAIL"} (${verdict.confidence})\n\n`;
    md += `${verdict.reasoning}\n\n`;
    if (verdict.blockers?.length) {
      md += `**Blockers**:\n`;
      for (const b of verdict.blockers) md += `- ${b}\n`;
      md += `\n`;
    }
    if (verdict.suggestions?.length) {
      md += `**Sugestoes**:\n`;
      for (const s of verdict.suggestions) md += `- ${s}\n`;
      md += `\n`;
    }
  }
  md += `\n---\n\n_Gerado por workflow \`hermes-skill-forge\` em ${new Date().toISOString()}._\n`;

  await writeFile(mdPath, md);
  persistedFiles.push({ yaml: yamlPath, md: mdPath, slug: p.slug });
}

// Tambem persiste lista de rejeitadas pra auditoria (sem yaml — so md)
if (rejected.length > 0) {
  const rejectedMdPath = `${PROPOSED_DIR}/${timestamp}-REJECTED.md`;
  let rmd = `# Rejected proposals (cycle ${timestamp})\n\n`;
  rmd += `${rejected.length} proposals nao passaram em >=2 lentes.\n\n`;
  for (const v of rejected) {
    rmd += `## ${v.proposal.slug} (score ${v.score}/3)\n\n`;
    rmd += `- Family: ${v.proposal.family} · Action: ${v.proposal.action}\n\n`;
    for (const verdict of v.verdicts.filter((x) => !x.valid)) {
      rmd += `- **FAIL ${verdict.lens || "?"}**: ${verdict.reasoning}\n`;
    }
    rmd += `\n`;
  }
  await writeFile(rejectedMdPath, rmd);
  persistedFiles.push({ md: rejectedMdPath, slug: "REJECTED" });
}

// Atualiza cooldown state — TODAS familias amostradas entram em cooldown
// (mesmo as que nao geraram proposal aprovada, pra evitar re-analise imediata).
for (const fam of samples.map((s) => s.family)) {
  state.cooldowns[fam] = now;
}
state.last_cycle = now;
state.history = (state.history || []).slice(-20); // mantem 20 ciclos
state.history.push({
  timestamp: now,
  families_sampled: samples.map((s) => s.family),
  patterns_detected: allPatterns.length,
  proposals_generated: validProposals.length,
  proposals_confirmed: confirmed.length,
  proposals_rejected: rejected.length,
  files: persistedFiles.map((f) => f.yaml || f.md),
});

await writeFile(STATE_PATH, JSON.stringify(state, null, 2));

// Emit WS event 'skill_proposal' pra Mission Control F.2 consumir
// (best-effort — se backend down, NAO falhar o ciclo)
try {
  if (confirmed.length > 0) {
    await emitWS("skill_proposal", {
      cycle: timestamp,
      count: confirmed.length,
      slugs: confirmed.map((v) => v.proposal.slug),
      requires_review_count: confirmed.filter((v) => v.proposal.requires_owner_review).length,
      proposed_dir: PROPOSED_DIR,
    });
    log(`WS event 'skill_proposal' emitido (${confirmed.length} proposals)`);
  }
} catch (e) {
  log(`WS emit falhou (nao-bloqueante): ${e?.message || e}`);
}

log(`Persist: ${confirmed.length} YAMLs + ${confirmed.length} MDs gravados. ${rejected.length} rejeitadas registradas.`);

return {
  cycle_skipped: false,
  cycle_id: timestamp,
  families_analyzed: samples.map((s) => s.family),
  patterns_detected: allPatterns.length,
  proposals_generated: validProposals.length,
  proposals_confirmed: confirmed.length,
  proposals_rejected: rejected.length,
  proposed_dir: PROPOSED_DIR,
  state_path: STATE_PATH,
  files: persistedFiles,
  next_eligible_at: now + COOLDOWN_HOURS * 3600 * 1000,
};

// ====================== HELPERS ======================

async function readFileOptional(path) {
  try {
    return await readFile(path);
  } catch {
    return null;
  }
}
