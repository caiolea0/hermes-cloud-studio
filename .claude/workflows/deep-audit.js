// deep-audit.js — Auditoria multi-dimensional do Hermes Cloud Studio
//
// Investiga TODO o projeto (não só LinkedIn anti-detection como o workflow anterior).
// 8 dimensões fan-out paralelas → sintese → multi-lens verify → output priorizado.
//
// Custo estimado: 1.5-2.5M tokens output (8+3 dimensões + verify pipeline).

export const meta = {
  name: "hermes-deep-audit",
  description:
    "Auditoria deep multi-dimensional Hermes: arquitetura, backend bugs, channels stubs, daemon, stealth residual, skills, DB, MCP, tunnel, security, performance. Verify multi-lens. Output: DEEP-AUDIT-{date}.md priorizado.",
  phases: [
    { title: "Discover", detail: "8 agents paralelos: arquitetura, backend, channels, daemon, stealth residual, skills, DB, MCP" },
    { title: "CrossCut", detail: "3 agents: tunnel resilience, security, performance" },
    { title: "Synthesize", detail: "Cruza findings cross-area, prioriza" },
    { title: "Verify", detail: "Cada finding alto-prioritario verificado por 3 lentes" },
    { title: "Output", detail: "DEEP-AUDIT-2026-06-08.md priorizado" },
  ],
};

const HERMES_ROOT = "D:/dev-projects/main/hermes-cloud-studio";

const FINDINGS_SCHEMA = {
  type: "object",
  properties: {
    area: { type: "string", description: "Nome da dimensão" },
    findings: {
      type: "array",
      items: {
        type: "object",
        properties: {
          id: { type: "string", description: "FIND-XXX sequencial" },
          title: { type: "string", description: "Resumo curto" },
          category: {
            type: "string",
            enum: ["bug", "security", "performance", "missing-feature", "tech-debt", "race-condition", "deps", "doc", "scalability"],
          },
          severity: { type: "string", enum: ["critical", "high", "medium", "low"] },
          file: { type: "string", description: "Caminho relativo ao projeto + linha se aplicavel" },
          summary: { type: "string", description: "2-4 frases técnicas explicando" },
          evidence: { type: "string", description: "Quote de código ou observação concreta" },
          fix_hint: { type: "string", description: "Direção da correção, NÃO solução completa" },
        },
        required: ["id", "title", "category", "severity", "summary"],
      },
    },
  },
  required: ["area", "findings"],
};

const VERDICT_SCHEMA = {
  type: "object",
  properties: {
    valid: { type: "boolean" },
    confidence: { type: "string", enum: ["low", "medium", "high"] },
    reasoning: { type: "string" },
    caveats: { type: "array", items: { type: "string" } },
    revised_severity: { type: "string", enum: ["critical", "high", "medium", "low"] },
  },
  required: ["valid", "confidence", "reasoning"],
};

// ====================== PHASE 1 — DISCOVER (8 paralelos) ======================
phase("Discover");
log("Fan-out: 8 dimensões em paralelo");

const dimensions = [
  {
    key: "architecture",
    prompt: `Audite ARQUITETURA do Hermes Cloud Studio em ${HERMES_ROOT}.

Leia: ${HERMES_ROOT}/CLAUDE.md, ${HERMES_ROOT}/.claude/GUARDRAILS.md, ${HERMES_ROOT}/.claude/AUDIT.md, ${HERMES_ROOT}/README.md.

Avalie:
- Coerência da topologia PC + VM + external services como documentada vs realidade do código
- Boundary clarity (o que executa onde, o que orquestra vs executa)
- Acoplamentos não-explícitos entre componentes
- Decisões arquiteturais que viraram tech-debt
- Falta de abstrações importantes (config global, error handling, etc)

Retorne findings via schema. Foque em problemas reais, não estilísticos.`,
  },
  {
    key: "backend-bugs",
    prompt: `Audite ${HERMES_ROOT}/server.py (3300+ linhas) e ${HERMES_ROOT}/hermes_api_v2.py (1860 linhas).

Procure especificamente:
- Race conditions nos 5 background loops (sync_loop 60s, linkedin_sync_loop 10s, linkedin_scheduler_loop 30s, linkedin_health_monitor_loop adaptive, linkedin_session_monitor_loop 1h)
- Auth gaps (WebSocket /ws sem auth confirmado; checar outros endpoints /api/internal/*)
- SQL injection em endpoints que aceitam filtros usuário (/api/prospects?city=X, /api/activities?type=X)
- Exception handling silencioso (bare except, except Exception sem log)
- Resource leaks (httpx clients não fechados, subprocesses órfãos)
- Cookie/state inconsistency entre os 5 loops

Não cobrir LinkedIn anti-detection (outro agent faz). Foco em backend Python.
Use Read + Grep targeted. Retorne findings via schema.`,
  },
  {
    key: "channels-stubs",
    prompt: `Audite ${HERMES_ROOT}/channels/ — pastas Email, Instagram, WhatsApp são stubs (__init__.py vazios).

Avalie:
- O que falta pra cada channel virar funcional (seguir padrão linkedin/ — config + limiter + human + sender)
- Quais channels têm rate-limit mais permissivo (WhatsApp Business, Email SMTP, Instagram Graph API) — priorizar
- Riscos de implementação por canal (Instagram banimento conta, WhatsApp Business approval, Email deliverability)
- Skills YAML que seriam necessárias por canal
- Como o daemon orchestrator P1-P7 integraria

Não implementar nada — só auditar a lacuna e propor sequência. Retorne via schema.`,
  },
  {
    key: "daemon",
    prompt: `Audite ${HERMES_ROOT}/daemon/orchestrator.py — HermesDaemon loop 24/7 com prioridades P1-P7.

Avalie:
- Edge cases: o que acontece se duas prioridades disparam simultâneo
- Circuit breaker (5 erros = 10min pause) — gaps de cobertura
- State persistence em daemon_state table — riscos de corrupção
- Working hours logic — handling de timezone, DST, weekends
- Recovery após restart (estado in-memory vs SQLite)
- Broadcasts WS — race com sync_loop
- Como decide quando rodar P1 vs P2 vs P3 (algoritmo de seleção)

Retorne findings via schema.`,
  },
  {
    key: "stealth-residual",
    prompt: `Audite gaps RESIDUAIS de anti-detecção LinkedIn pós-aplicação dos 3 patches reduzidos.

Pre-context: estão aplicados em ${HERMES_ROOT}/linkedin/:
- PATCH-008 reduzido: account_profile.py com burned_flag + sticky_session_id + assert_not_burned gate
- PATCH-013 corrigido: window.chrome stub (timeOrigin lazy, Object.freeze loadTimes/csi, ALPN h2, runtime.connect retorna Port async)
- PATCH-014: limiter.py acceptance_rate guard d-14..d-7 + cooldown 7d
- Preflight + stealth_compliance gates em stealth.py
- Locale pt-BR + WebGL ANGLE/Vulkan/SwiftShader

Leia ${HERMES_ROOT}/linkedin/stealth.py + ${HERMES_ROOT}/linkedin/human.py + ${HERMES_ROOT}/linkedin/limiter.py + ${HERMES_ROOT}/.claude/STEALTH-PATCHES.md.

Identifique:
- Gaps remanescentes (PATCH-001/002/004/005/007/009/011/012 do workflow anterior — quais ainda valem aplicar)
- Riscos novos introduzidos pelas mudanças (overshoot stealth)
- Falta de testes de regressão
- Integração entre os 3 patches (conflitos?)
- Pendente: connector.py + engager.py chamando record_invite_sent (PATCH-014 part 2)

Retorne findings via schema.`,
  },
  {
    key: "skills-yaml",
    prompt: `Audite as 6 skills YAML em ${HERMES_ROOT}/skills/.

Para cada: linkedin-post-generator, linkedin-profile-researcher, linkedin-connection-sender, linkedin-engagement, linkedin-trend-monitor, weekly-mission-planner.

Avalie:
- System prompt — qualidade (specificity, output constraints, tone)
- Model assignment (deepseek-chat:free, qwen3:8b, minimax-m1:free, nemotron-70b:free) — adequação ao task
- Input schema — completude
- Triggers — overlapping? buracos?
- Falta de skills críticas (ex: profile-decision-maker que classifica accept/reject; reply-generator pra responder DMs)
- Inconsistências (ex: sem acentos vs hardcoded ASCII)
- Versionamento — todas v1, sem evolution path

Use Read em alguns YAMLs pra basear achados. Retorne via schema.`,
  },
  {
    key: "database",
    prompt: `Audite bancos SQLite do Hermes em ${HERMES_ROOT}/linkedin_data/rate_limits.db (e migration scripts em ${HERMES_ROOT}/migrations/ se existir).

Schema relevante (de limiter.py + account_profile.py):
- rate_actions, warmup_state, session_state, pending_invites (PATCH-014), acceptance_cooldown (PATCH-014)
- AccountProfile JSON em linkedin_data/account_profiles/

Avalie:
- Índices ausentes em queries hot (rate_actions WHERE account, timestamp; pending_invites range)
- WAL mode — múltiplos writers conflito?
- Migration strategy — schema evolutions, downgrade safety
- Backup strategy — None? (risco de perda total se VM cai)
- Foreign keys / constraints faltando
- Tipos de coluna mal escolhidos (REAL vs INTEGER timestamps)
- Bloat (rate_actions cresce sem limpeza)

Use Read em linkedin/limiter.py + linkedin/account_profile.py pro schema.
Retorne findings via schema.`,
  },
  {
    key: "mcp-completude",
    prompt: `Audite o MCP ${HERMES_ROOT}/mcps/hermes-control/ (TypeScript, 16 tools) vs a API real do Hermes (server.py + hermes_api_v2.py).

Avalie:
- Tools cobertas (16 atuais: hermes_status, list_prospects, daemon_state/control, li_health/rate_limits/campaigns, activities, pipeline_list/execute, scraper_status/start, audit_start, skills_list/toggle, server_restart)
- Endpoints da API que NÃO têm tool MCP (gap)
- Tools com schema incompleto (Zod fields que poderiam ser melhor tipados)
- Error handling — onde fetch falha, como tool retorna ao Claude
- Falta de tools de DB query read-only (mencionado no roadmap)
- Falta de deploy_vm tool (mencionado no roadmap)
- Falta de streaming/SSE pra campanhas em tempo real

Leia ${HERMES_ROOT}/mcps/hermes-control/src/index.ts.
Retorne findings via schema.`,
  },
];

const discoveries = await parallel(
  dimensions.map((d) => () =>
    agent(d.prompt, {
      phase: "Discover",
      label: `discover:${d.key}`,
      schema: FINDINGS_SCHEMA,
    })
  )
);

const allFindings = discoveries
  .filter(Boolean)
  .flatMap((d) => d.findings || []);
log(`Discover: ${allFindings.length} findings de ${discoveries.filter(Boolean).length}/${dimensions.length} dimensões`);

// ====================== PHASE 2 — CROSS-CUT (3 paralelos) ======================
phase("CrossCut");
log("Cross-cuts: tunnel resilience, security, performance");

const crosscuts = [
  {
    key: "tunnel-resilience",
    prompt: `Audite resiliência do tunnel sistema PC-VM em ${HERMES_ROOT}/scripts/tunnel_supervisor.py + ${HERMES_ROOT}/linkedin/preflight.py + ${HERMES_ROOT}/socks5_proxy.py.

Tunnel é INEGOCIÁVEL — sem ele LinkedIn = ban instantâneo.

Edge cases:
- PC sleep/hibernate — task scheduler restart funciona?
- SSH session timeout (default 5min) — ServerAliveInterval setado mas testado?
- Network flap (Wi-Fi reconnect) — recovery automático?
- DNS failure pro VM — fallback?
- Múltiplos supervisor instances rodando (idempotência)
- Restart logic exponential backoff — caps respeitados?
- Egress IP changes (Caio muda de rede residencial) — supervisor detecta?
- Preflight gate falhou — quanto tempo até supervisor consertar?
- VM reboot — tunnel reverso re-estabelece sozinho?

Retorne findings via schema.`,
  },
  {
    key: "security",
    prompt: `Security review do Hermes Cloud Studio. Foco em:

1. Secrets handling: .env tem HERMES_AUTH_TOKEN, OPENROUTER_API_KEY, LINKEDIN_LAB_PASSWORD, TELEGRAM_BOT_TOKEN. Avalie:
   - Logs vazam tokens? (grep server.py + hermes_api_v2.py)
   - Rotation strategy — N/A?
   - .env committado? (.gitignore cobre mas verificar)

2. Auth gaps confirmados:
   - WebSocket /ws sem auth
   - /api/internal/* endpoints só checa origem ou aceita qualquer POST?

3. Network surface:
   - hermes_api_v2.py :8420 — exposed na VM publica? (firewall GCP)
   - Cloudflare tunnel hermes.caioleo.com — auth nessa exposição?
   - SOCKS5 proxy :55081 — bind 127.0.0.1 ok (validar)

4. Code injection:
   - subprocess.Popen com user input em pipeline.py? scraper start params?
   - SQL strings interpolated?

5. AccountProfile burned_flag — bypass via manual edit do JSON?

Use Grep targeted pra cada item. Retorne via schema.`,
  },
  {
    key: "performance",
    prompt: `Performance audit do Hermes:

1. PC backend server.py: 5 loops simultâneos
   - sync_loop 60s — quantos requests/min pra VM
   - linkedin_sync_loop 10s — overhead se VM lento
   - polling tax total estimado

2. SQLite WAL — múltiplos readers OK, mas writer único:
   - rate_actions INSERT a cada ação (high frequency)
   - índices garantem query <100ms?

3. Photo cache (photo_cache/) — limpeza? cresce indefinidamente?

4. Browser/Patchright cost na VM: cada launch_persistent_context = browser process
   - GC entre runs?
   - Memory leak em sessões longas?

5. WebSocket broadcast — fanout pra N clientes simultâneos
   - bottleneck conhecido em FastAPI WS?

6. Dashboard SPA vanilla — render performance com 1000+ prospects na tabela?

Use Read + Grep pra evidence. Retorne via schema.`,
  },
];

const crossFindings = await parallel(
  crosscuts.map((c) => () =>
    agent(c.prompt, {
      phase: "CrossCut",
      label: `crosscut:${c.key}`,
      schema: FINDINGS_SCHEMA,
    })
  )
);

allFindings.push(...crossFindings.filter(Boolean).flatMap((c) => c.findings || []));
log(`CrossCut: total findings agora ${allFindings.length}`);

// ====================== PHASE 3 — SYNTHESIZE ======================
phase("Synthesize");
log("Sintese cross-area, prioriza top findings");

const synthInput = {
  all_findings_compact: allFindings.map((f) => ({
    id: f.id,
    area: f.area || "unknown",
    title: f.title,
    category: f.category,
    severity: f.severity,
    file: f.file,
    summary: (f.summary || "").slice(0, 250),
  })),
};

const synthesis = await agent(
  `Você é um arquiteto senior. Recebeu ${allFindings.length} findings de 11 dimensões do Hermes Cloud Studio.

INPUT:
${JSON.stringify(synthInput, null, 2).slice(0, 25000)}

Tarefa:
1. Identificar findings DUPLICADOS ou que se sobrepõem entre dimensões — mergear.
2. Identificar findings que são SINTOMAS de causa-raiz comum — agrupar com cause label.
3. Ranking final: top 20 findings por (severity × impacto-cross-area). Critical primeiro.
4. Para cada finding TOP-20, output:
   - id original (ou novo MERGED-XXX se merge)
   - title, category, severity (revisada se necessário)
   - file
   - rationale do ranking (1-2 frases)
   - cross_area_links (outros find_ids que reforçam ou conectam)

Output via schema FINDINGS_SCHEMA com area="SYNTHESIS-TOP20".`,
  { phase: "Synthesize", label: "synth-top20", schema: FINDINGS_SCHEMA }
);

const top20 = (synthesis?.findings || []).slice(0, 20);
log(`Synthesize: ${top20.length} top findings selecionados`);

// ====================== PHASE 4 — VERIFY (multi-lens) ======================
phase("Verify");
log(`Verify: ${top20.length} findings × 3 lentes = ${top20.length * 3} agents`);

const lenses = [
  {
    name: "evidence",
    prompt: (f) =>
      `Lente EVIDENCE. Finding:\n${JSON.stringify(f, null, 2)}\n\nLeia o arquivo/seção em ${HERMES_ROOT}/${f.file || "(não especificado)"} (se file presente). Confirme: a evidência citada existe REALMENTE no código atual? Ou foi alucinação do auditor? Default valid=false se NÃO conseguir verificar evidência concreta. Sé cético.`,
  },
  {
    name: "impact",
    prompt: (f) =>
      `Lente IMPACT. Finding:\n${JSON.stringify(f, null, 2)}\n\nA severity (${f.severity}) é justificada? Cenários reais: se este finding ficar SEM fix por 3 meses, qual o dano real? Sé cético em "critical" — só vale se o sistema quebra. Revise severity se necessário (campo revised_severity).`,
  },
  {
    name: "fixability",
    prompt: (f) =>
      `Lente FIXABILITY. Finding:\n${JSON.stringify(f, null, 2)}\n\nO fix_hint é viável? Quanto custa (effort S/M/L)? Tem dependência de outro finding pra ser corrigido primeiro? Há risco de regressão? Default valid=true se fix é claro. valid=false se fix_hint é vago ou impossível.`,
  },
];

const verified = await parallel(
  top20.map((f) => () =>
    parallel(
      lenses.map((l) => () =>
        agent(l.prompt(f), {
          phase: "Verify",
          label: `verify:${f.id}:${l.name}`,
          schema: VERDICT_SCHEMA,
        })
      )
    ).then((verdicts) => {
      const valids = verdicts.filter(Boolean).filter((v) => v.valid);
      const revisedSev = verdicts
        .filter(Boolean)
        .map((v) => v.revised_severity)
        .filter(Boolean);
      return {
        finding: f,
        verdicts: verdicts.filter(Boolean),
        confirmed: valids.length >= 2,
        score: valids.length,
        revised_severity: revisedSev[0] || f.severity,
      };
    })
  )
);

const confirmed = verified.filter(Boolean).filter((v) => v.confirmed);
log(`Verify: ${confirmed.length}/${top20.length} confirmados (>=2 lentes valid)`);

// ====================== PHASE 5 — OUTPUT ======================
phase("Output");
log("Escrevendo DEEP-AUDIT-2026-06-08.md");

let md = `# Hermes Cloud Studio — Deep Audit (2026-06-08)\n\n`;
md += `> Gerado por workflow \`hermes-deep-audit\`. Investigação multi-dimensional pós-implementação dos 3 patches stealth reduzidos.\n\n`;
md += `**Findings totais**: ${allFindings.length} (de 11 dimensões: arquitetura, backend, channels, daemon, stealth residual, skills YAML, database, MCP, tunnel resilience, security, performance)\n`;
md += `**Top 20 sintetizados**: ${top20.length}\n`;
md += `**Confirmados (>=2 lentes valid)**: ${confirmed.length}\n\n`;
md += `---\n\n`;

md += `## Top findings confirmados\n\n`;

const sevOrder = { critical: 0, high: 1, medium: 2, low: 3 };
confirmed.sort(
  (a, b) =>
    (sevOrder[a.revised_severity] ?? 9) - (sevOrder[b.revised_severity] ?? 9)
);

for (const v of confirmed) {
  const f = v.finding;
  md += `### ${f.id} — ${f.title}\n\n`;
  md += `- **Severity**: ${v.revised_severity} ${f.severity !== v.revised_severity ? `(originalmente ${f.severity})` : ""}\n`;
  md += `- **Category**: ${f.category}\n`;
  md += `- **File**: \`${f.file || "(transversal)"}\`\n`;
  md += `- **Verify score**: ${v.score}/3 lentes\n\n`;
  md += `**Resumo**: ${f.summary || "(sem resumo)"}\n\n`;
  if (f.evidence) md += `**Evidência**: \`\`\`\n${f.evidence.slice(0, 600)}\n\`\`\`\n\n`;
  if (f.fix_hint) md += `**Fix hint**: ${f.fix_hint}\n\n`;
  md += `**Lentes**:\n`;
  for (const verdict of v.verdicts) {
    md += `- ${verdict.valid ? "OK" : "FAIL"} (${verdict.confidence}): ${(verdict.reasoning || "").slice(0, 400)}\n`;
  }
  md += `\n---\n\n`;
}

// Rejeitados
const rejected = verified.filter(Boolean).filter((v) => !v.confirmed);
if (rejected.length) {
  md += `## Findings rejeitados (< 2 lentes valid)\n\n`;
  for (const v of rejected) {
    md += `- **${v.finding.id}** ${v.finding.title} (score ${v.score}/3)\n`;
    for (const verdict of v.verdicts.filter((x) => !x.valid)) {
      md += `  - FAIL: ${(verdict.reasoning || "").slice(0, 250)}\n`;
    }
  }
  md += `\n`;
}

// Discoveries raw por área
md += `## Discoveries por área (raw)\n\n`;
const grouped = {};
for (const f of allFindings) {
  const a = f.area || "unknown";
  if (!grouped[a]) grouped[a] = [];
  grouped[a].push(f);
}
for (const area of Object.keys(grouped).sort()) {
  md += `### ${area} (${grouped[area].length} findings)\n`;
  for (const f of grouped[area].slice(0, 20)) {
    md += `- **[${f.severity || "?"}]** ${f.id || ""} ${f.title || ""} (${f.category || ""})\n`;
  }
  md += `\n`;
}

return {
  total_findings: allFindings.length,
  top20: top20.length,
  confirmed: confirmed.length,
  rejected: rejected.length,
  markdown: md,
  output_path: `${HERMES_ROOT}/.claude/DEEP-AUDIT-2026-06-08.md`,
};
