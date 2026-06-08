// linkedin-anti-detection-sweep
// Workflow multi-agent que cruza pesquisa web 2025-2026 com codigo stealth atual
// e produz patches priorizados em STEALTH-PATCHES.md
//
// Custo estimado: 80-150k tokens output (4 phases, ~12 agent calls)

export const meta = {
  name: "linkedin-anti-detection-sweep",
  description:
    "Pesquisa tecnicas deteccao LinkedIn 2025-26 + le codigo stealth atual + sintese cross-source + verify multi-lens. Output: STEALTH-PATCHES.md priorizado.",
  phases: [
    { title: "Research", detail: "3 agents paralelos: web research deteccao recente" },
    { title: "Read", detail: "3 agents paralelos: ler stealth.py, human.py, limiter.py" },
    { title: "Synthesize", detail: "Cruza research vs codigo, ranking gaps por severidade" },
    { title: "Verify", detail: "Cada gap top-N verificado por 3 lentes independentes" },
    { title: "Output", detail: "Escreve STEALTH-PATCHES.md com plano executavel" },
  ],
};

const HERMES_ROOT = "D:/dev-projects/main/hermes-cloud-studio";

const FINDING_SCHEMA = {
  type: "object",
  properties: {
    findings: {
      type: "array",
      items: {
        type: "object",
        properties: {
          title: { type: "string", description: "Nome curto da tecnica/gap" },
          category: {
            type: "string",
            enum: ["fingerprint", "behavior", "network", "session", "rate", "challenge"],
          },
          source: { type: "string", description: "URL/paper/observacao" },
          summary: { type: "string", description: "1-3 frases tecnicas" },
          severity: { type: "string", enum: ["critical", "high", "medium", "low"] },
        },
        required: ["title", "category", "summary", "severity"],
      },
    },
  },
  required: ["findings"],
};

const CODE_GAP_SCHEMA = {
  type: "object",
  properties: {
    file: { type: "string" },
    gaps: {
      type: "array",
      items: {
        type: "object",
        properties: {
          area: { type: "string", description: "Funcao/patch/limite especifico" },
          current_behavior: { type: "string" },
          weakness: { type: "string", description: "Como pode ser detectado" },
          improvement_hint: { type: "string", description: "Direcao da correcao" },
        },
        required: ["area", "weakness"],
      },
    },
  },
  required: ["file", "gaps"],
};

const PATCH_SCHEMA = {
  type: "object",
  properties: {
    patches: {
      type: "array",
      items: {
        type: "object",
        properties: {
          id: { type: "string", description: "PATCH-001 etc" },
          title: { type: "string" },
          category: { type: "string" },
          target_file: { type: "string" },
          severity: { type: "string", enum: ["critical", "high", "medium", "low"] },
          effort: { type: "string", enum: ["S", "M", "L"] },
          description: { type: "string" },
          implementation_sketch: { type: "string", description: "Pseudo-codigo ou diff guidance" },
          test_plan: { type: "string", description: "Como verificar em lab" },
          sources: { type: "array", items: { type: "string" } },
        },
        required: ["id", "title", "target_file", "severity", "effort", "description"],
      },
    },
    summary: { type: "string", description: "Resumo executivo 3-5 frases" },
  },
  required: ["patches", "summary"],
};

const VERDICT_SCHEMA = {
  type: "object",
  properties: {
    valid: { type: "boolean" },
    confidence: { type: "string", enum: ["low", "medium", "high"] },
    reasoning: { type: "string" },
    caveats: { type: "array", items: { type: "string" } },
  },
  required: ["valid", "confidence", "reasoning"],
};

// =================== PHASE 1 — RESEARCH ===================
phase("Research");
log("Fan-out: 3 angulos de pesquisa web sobre deteccao LinkedIn 2025-2026");

const researchPrompts = [
  `Pesquise tecnicas RECENTES (2024-2026) que o LinkedIn usa pra detectar bots/automacao em contas Free.
Foco em: fingerprint browser (canvas, WebGL, audio, fonts, hardware), comportamento (mouse entropy, typing biometrics, scroll patterns), network (TLS JA3/JA4, HTTP/2 fingerprint, IP reputation), session (cookie age, persistence), challenge flow (captcha/verify email/phone).
Use WebSearch + WebFetch em fontes tecnicas: blogs CreepJS, fingerprintjs, Patchright issues recentes, papers academicos, threads X/Reddit de devs LinkedIn scraping.
NAO especule — so reporte achados com fonte verificavel.
Retorne findings via tool call.`,

  `Pesquise contornos ATUAIS conhecidos (2024-2026) pra bypass deteccao LinkedIn: bibliotecas (camoufox, puppeteer-extra-stealth, undetected-chromedriver, Patchright), tecnicas de simulacao humana (Bezier mouse, Fitts's Law typing, dwell time distributions), residential proxy strategies, account warm-up best practices, session rotation tactics.
Foco em o que FUNCIONA em 2026, nao papers antigos.
Use WebSearch + WebFetch.
Retorne findings com sources verificaveis.`,

  `Pesquise como o LinkedIn especificamente penaliza/bloqueia automacao em conta Free: rate limits efetivos observados (views/connects/messages por dia/semana), red flags conhecidos (login burst, no-mouse navigation, perfect timing), warning signs antes do ban (CAPTCHAs, email verify, profile restrictions, slowdown), e tempo medio entre primeiro warning e ban definitivo.
Use WebSearch focado em casos reais 2024-2026.
Retorne findings categorizados por severidade.`,
];

const research = await parallel(
  researchPrompts.map((p) => () => agent(p, { phase: "Research", schema: FINDING_SCHEMA }))
);

const allFindings = research
  .filter(Boolean)
  .flatMap((r) => r.findings ?? [])
  .filter((f) => f.title && f.summary);

log(`Research: ${allFindings.length} findings coletados de ${research.filter(Boolean).length}/3 angulos`);

// =================== PHASE 2 — READ CODE ===================
phase("Read");
log("Fan-out: leitura targeted de stealth.py, human.py, limiter.py");

const codeFiles = [
  {
    file: `${HERMES_ROOT}/linkedin/stealth.py`,
    focus:
      "11 patches JS anti-deteccao: webdriver, chrome obj, plugins, languages, platform, hardware, permissions, WebGL, canvas, WebRTC, Function.toString. Compare com findings de fingerprint research.",
  },
  {
    file: `${HERMES_ROOT}/linkedin/human.py`,
    focus:
      "Mouse Bezier, typing Fitts, reading simulation (35% scroll/30% pause/20% mouse/15% nada), overshoot 12%. Compare com findings de behavior research.",
  },
  {
    file: `${HERMES_ROOT}/linkedin/limiter.py`,
    focus:
      "Rate limiter SQLite WAL, warm-up 14d, working hours, 30min cooldown entre campaigns, break apos N acoes. Compare com findings de rate research.",
  },
];

const codeGaps = await parallel(
  codeFiles.map((cf) => () =>
    agent(
      `Leia ${cf.file} completo. Identifique gaps tecnicos: ${cf.focus}
Para cada gap: area especifica (linha/funcao), comportamento atual, fraqueza (como pode ser detectado), hint de melhoria (direcao, nao implementacao).
Seja TECNICO e ESPECIFICO. Nada de "poderia ser melhorado".
Retorne via schema.`,
      { phase: "Read", schema: CODE_GAP_SCHEMA }
    )
  )
);

log(`Read: ${codeGaps.filter(Boolean).length}/3 arquivos analisados`);

// =================== PHASE 3 — SYNTHESIZE ===================
phase("Synthesize");
log("Sintese: cruza research findings com code gaps -> patches priorizados");

const synthesisInput = {
  research_findings: allFindings,
  code_gaps: codeGaps.filter(Boolean),
};

const patchProposal = await agent(
  `Voce e um especialista anti-deteccao LinkedIn. Voce recebeu:
1) Pesquisa atualizada 2024-2026 sobre tecnicas de deteccao LinkedIn (research_findings)
2) Analise tecnica do codigo stealth atual do Hermes (code_gaps)

INPUT:
${JSON.stringify(synthesisInput, null, 2).slice(0, 30000)}

Tarefa: produzir lista PRIORIZADA de patches concretos. Para cada patch:
- ID sequencial PATCH-XXX
- Title curto
- Category (fingerprint/behavior/network/session/rate/challenge)
- target_file (caminho absoluto)
- Severity (critical = bloqueador atual, high = arrisco alto, medium/low)
- Effort S/M/L (horas)
- Description (problema + solucao em 3-5 frases tecnicas)
- implementation_sketch (pseudo-codigo ou diff guidance, NAO codigo final)
- test_plan (como verificar em lab mode sem queimar conta real)
- sources (URLs/observacoes que justificam)

Priorize gaps que aparecem em MULTIPLAS fontes. Critical primeiro. Maximo 15 patches.
Output via schema PATCH_SCHEMA.`,
  { phase: "Synthesize", schema: PATCH_SCHEMA, label: "synthesize-patches" }
);

const patches = patchProposal?.patches ?? [];
log(`Synthesize: ${patches.length} patches propostos`);

// =================== PHASE 4 — VERIFY ===================
phase("Verify");
log("Verify multi-lens: cada patch validado por 3 lentes independentes");

const lenses = [
  {
    name: "correctness",
    prompt: (p) =>
      `Lente CORRECTNESS. Avalie o patch:\n${JSON.stringify(p, null, 2)}\n\nA tecnica proposta realmente resolve a deteccao descrita? Ha falhas logicas no implementation_sketch? Default valid=false se ha duvida tecnica. Seja cetico.`,
  },
  {
    name: "feasibility",
    prompt: (p) =>
      `Lente FEASIBILITY. Avalie o patch:\n${JSON.stringify(p, null, 2)}\n\nO effort estimado (${p.effort}) e realista? O Patchright/Python/Playwright suporta isso sem hack pesado? Ha dependencias instavel? Default valid=false se implementacao tem risco alto.`,
  },
  {
    name: "risk",
    prompt: (p) =>
      `Lente RISK. Avalie o patch:\n${JSON.stringify(p, null, 2)}\n\nAplicar esse patch pode QUEBRAR fluxos LinkedIn existentes? Pode causar deteccao pior (overshoot stealth)? O test_plan cobre os riscos? Default valid=false se risco > beneficio.`,
  },
];

const verifiedPatches = await parallel(
  patches.map((p) => () =>
    parallel(lenses.map((l) => () =>
      agent(l.prompt(p), { phase: "Verify", schema: VERDICT_SCHEMA, label: `verify:${p.id}:${l.name}` })
    )).then((verdicts) => {
      const valids = verdicts.filter(Boolean).filter((v) => v.valid);
      return {
        patch: p,
        verdicts: verdicts.filter(Boolean),
        confirmed: valids.length >= 2,
        score: valids.length,
      };
    })
  )
);

const confirmed = verifiedPatches.filter(Boolean).filter((v) => v.confirmed);
log(`Verify: ${confirmed.length}/${patches.length} patches confirmados (>=2 lentes valid)`);

// =================== PHASE 5 — OUTPUT ===================
phase("Output");
log("Escrevendo STEALTH-PATCHES.md");

const today = "2026-06-07";
let md = `# Hermes — Anti-Detection Patches (${today})\n\n`;
md += `Gerado por workflow \`linkedin-anti-detection-sweep\`.\n`;
md += `${confirmed.length} patches confirmados de ${patches.length} propostos. ${allFindings.length} findings de pesquisa em ${research.filter(Boolean).length} angulos.\n\n`;
md += `## Resumo executivo\n\n${patchProposal?.summary ?? "(sem resumo)"}\n\n`;
md += `## Patches confirmados (>=2 lentes valid)\n\n`;

const sevOrder = { critical: 0, high: 1, medium: 2, low: 3 };
confirmed.sort((a, b) => (sevOrder[a.patch.severity] ?? 9) - (sevOrder[b.patch.severity] ?? 9));

for (const v of confirmed) {
  const p = v.patch;
  md += `### ${p.id} — ${p.title}\n\n`;
  md += `- **Severity**: ${p.severity} · **Effort**: ${p.effort} · **Category**: ${p.category}\n`;
  md += `- **Target**: \`${p.target_file}\`\n`;
  md += `- **Verify score**: ${v.score}/3 lentes\n\n`;
  md += `**Descricao**: ${p.description}\n\n`;
  if (p.implementation_sketch) md += `**Sketch**:\n\`\`\`\n${p.implementation_sketch}\n\`\`\`\n\n`;
  if (p.test_plan) md += `**Test plan (lab)**: ${p.test_plan}\n\n`;
  if (p.sources?.length) md += `**Sources**: ${p.sources.join(" · ")}\n\n`;
  md += `**Lentes**:\n`;
  for (const verdict of v.verdicts) {
    md += `- ${verdict.valid ? "OK" : "FAIL"} (${verdict.confidence}): ${verdict.reasoning}\n`;
  }
  md += `\n---\n\n`;
}

const rejected = verifiedPatches.filter(Boolean).filter((v) => !v.confirmed);
if (rejected.length > 0) {
  md += `## Patches rejeitados (< 2 lentes valid)\n\n`;
  for (const v of rejected) {
    md += `- **${v.patch.id}** — ${v.patch.title} (score ${v.score}/3)\n`;
    for (const verdict of v.verdicts.filter((x) => !x.valid)) {
      md += `  - FAIL: ${verdict.reasoning}\n`;
    }
  }
  md += `\n`;
}

md += `## Research findings (raw)\n\n`;
for (const f of allFindings.slice(0, 30)) {
  md += `- **[${f.severity}/${f.category}]** ${f.title} — ${f.summary}${f.source ? ` _(${f.source})_` : ""}\n`;
}

return {
  patches_confirmed: confirmed.length,
  patches_total: patches.length,
  findings: allFindings.length,
  markdown: md,
  output_path: `${HERMES_ROOT}/.claude/STEALTH-PATCHES.md`,
};
