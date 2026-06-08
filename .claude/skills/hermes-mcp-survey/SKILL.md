---
name: hermes-mcp-survey
description: Survey deterministico do landscape MCP relevante ao Hermes — gera/atualiza .claude/MCP-LANDSCAPE.md com top public MCPs (Playwright, GitHub, FastMCP, ContextForge Gateway, Sentry, Postgres Pro, Omnisearch, Firecrawl, AgentMail, Apollo, Hunter, Exa, WhatsApp Business, Slack, Notion), ROI por chapter F.x, effort, alignment com guardrails (Caio sagrada, zero API paga, VM-only) e shortlist priorizado pra F.5 (gateway+wrappers custom hermes-linkedin/prospects/skills). Trigger "mcp survey", "mcp landscape", "auditar mcps", "/hermes-mcp-survey".
---

# /hermes-mcp-survey — Survey MCP landscape pro Hermes

## Quando disparar
- Antes de planejar/abrir fase F.5 (MCP wrappers + gateway)
- Quando aparecer MCP novo relevante (mensal: re-rodar pra refresh)
- Quando owner pergunta "tem MCP pra X?"
- Antes de adicionar dependencia MCP nova ao stack — confirmar nao duplica capability ja coberta

## Pre-requisitos
- Repo Hermes em D:/dev-projects/main/hermes-cloud-studio
- .claude/PHASE-F-STUDY-SYNTHESIS.md existente (contexto guardrails F)
- Acesso WebSearch + WebFetch (refresh stars/versao)

## Procedimento deterministico (5 passos)

### Passo 1 — Carregar baseline catalog
Ler `.claude/mcp-survey/catalog.json` (inventario curado abaixo). Se nao existir, criar a partir do template embarcado nesta skill (secao "Catalog baseline" no fim do doc).

### Passo 2 — Refresh metadata (opcional, se flag --refresh)
Pra cada MCP do catalog:
- WebFetch repo URL → extrai stars atuais, ultimo release, license
- Compara com snapshot anterior — flagga drift (>20% stars, breaking change major)
- Atualiza catalog.json com `last_checked: <ISO date>`

### Passo 3 — Score ROI por chapter F.x
Pra cada MCP, calcular score 0-10 = soma ponderada:
- **chapter_alignment** (peso 4): match com F.2/F.3/F.4/F.5/F.6/F.7/F.8/F.9 explicito = 4, tangencial = 2, sem = 0
- **guardrail_safe** (peso 3): nao toca conta Caio = 3, isolavel cobaia = 2, requer Caio = 0
- **cost_zero** (peso 2): self-hosted/free tier suficiente = 2, free limitado = 1, paid = 0
- **effort_low** (peso 1): low = 1, medium = 0.5, high = 0

### Passo 4 — Gerar relatorio `.claude/MCP-LANDSCAPE.md`
6 secoes:
1. **§1 Top 15 MCPs catalogados** — tabela markdown [nome, repo, stars, license, last_release, tools_count, score, chapter_destino]
2. **§2 ROI matrix por chapter F.x** — tabela 8x15 (chapters x MCPs) com cell value = score
3. **§3 Shortlist F.5 fundacao** — 3-5 MCPs obrigatorios pra F.5 com justificativa 2 linhas
4. **§4 Wrappers custom necessarios** — hermes-linkedin (skill lab), hermes-prospects (DB read+state mutations), hermes-skills (auto-skill loop F.4) — define escopo/tools de cada
5. **§5 Gateway architecture** — porque ContextForge MCP Gateway eh obrigatorio (multiplex auth/rate-limit/audit), deploy plan VM
6. **§6 Anti-recomendacoes** — MCPs que parecem util mas DUPLICAM/CONFLITAM (ex: Exa standalone vs Omnisearch, Playwright MCP pra conta Caio)

### Passo 5 — Sanity asserts + persistencia
- Assert: shortlist F.5 inclui FastMCP + ContextForge Gateway + GitHub MCP (obrigatorios verificados em PHASE-F-STUDY-SYNTHESIS)
- Assert: nenhum MCP shortlist tem `guardrail_safe == 0` (Caio sagrada)
- Salvar catalog.json refresh em `.claude/mcp-survey/catalog.json`
- Log em `.claude/mcp-survey/run-history.jsonl` (1 linha por exec)

## Outputs

```
.claude/MCP-LANDSCAPE.md            # relatorio principal markdown
.claude/mcp-survey/catalog.json     # catalog persistente refresh-avel
.claude/mcp-survey/run-history.jsonl # log execucoes
```

## Output esperado (formato canonico)

```
HERMES MCP SURVEY — {YYYY-MM-DD HH:MM}

Catalog : {N} MCPs avaliados ({M} refresh metadata, {K} drift detectado)
Shortlist F.5 : FastMCP + ContextForge Gateway + GitHub MCP + Sentry + Postgres Pro
Wrappers custom : hermes-linkedin, hermes-prospects, hermes-skills
Anti-recomendacoes : {X} MCPs flagados (ver §6)

Top 5 por score :
- {nome} score {N}/10 — {chapter} — {1 linha justificativa}
- ...

Acao sugerida proxima fase :
- F.5.task_1 : deploy ContextForge Gateway na VM
- F.5.task_2 : wrappers FastMCP 3 servers (linkedin/prospects/skills)
- F.5.task_3 : integrar Sentry + Postgres Pro read-only via gateway
- F.5.task_4 : GitHub MCP OAuth scope-filtered pra F.4 auto-skill loop
```

## Catalog baseline (top 15 MCPs Hermes-relevant)

| nome | repo | stars | tools_count | chapter | guardrail_safe | cost_zero | effort | score |
|------|------|------:|------------:|---------|---------------:|----------:|--------|------:|
| FastMCP 3.0 | jlowin/fastmcp | high | framework | F.5 fundacao | 3 | 2 | low | 9.0 |
| ContextForge Gateway | IBM/mcp-context-forge | 3500+ | gateway | F.5 fundacao | 3 | 2 | medium | 8.5 |
| GitHub MCP Server | github/github-mcp-server | high | 7+ | F.4 PR-deploy | 3 | 2 | medium | 8.5 |
| Microsoft Playwright MCP | microsoft/playwright-mcp | high | 8 | F.5+li-lab cobaia | 2 | 2 | low | 7.5 |
| Sentry MCP Server | getsentry/sentry-mcp | high | 7 | F.4 auto-disable + F.7 | 3 | 2 | low | 8.5 |
| Postgres MCP Pro | crystaldba/postgres-mcp | high | 8 | F.6 Brain.decide() | 3 | 2 | low | 8.5 |
| MCP Omnisearch | spences10/mcp-omnisearch | medium | multi-provider | F.7 ICP discovery | 3 | 1.5 | low | 7.5 |
| Firecrawl MCP | firecrawl/firecrawl-mcp-server | 5200+ | 6 | F.7 ICP enrich | 3 | 1 | low | 7.0 |
| AgentMail MCP | mcp.agentmail.to | hosted | 7 | F.7 email cobaia | 2 | 0.5 | medium | 5.5 |
| Apollo.io MCP (Inferensys) | Inferensys/apollo-io-mcp | medium | 27 | F.7 enrich B2B | 2 | 0.5 | medium | 5.0 |
| Hunter.io MCP | hunter-io/hunter-mcp | medium | 6 | F.7 email hygiene | 3 | 1.5 | low | 7.0 |
| Exa MCP | exa-labs/exa-mcp-server | medium | 5 | coberto Omnisearch | 3 | 1.5 | low | 5.0 (skip standalone) |
| WhatsApp Business MCP | nakulben/whatsapp-business | low | 5 | F.7 outreach BR | 2 | 0.5 | medium | 5.5 |
| Slack MCP Server | slack oficial | hosted | 8 | F.4 alertas (cond) | 3 | 1 | low | 6.0 |
| Notion MCP | makenotion/notion-mcp-server | 4200+ | 7 | F.4/F.7 owner notes (opc) | 3 | 1.5 | low | 6.5 |

## Wrappers custom (F.5 escopo)

### hermes-linkedin MCP (FastMCP 3.0)
- `linkedin_status()` — health + warmup day + rate-limits hoje
- `linkedin_pause(reason, ttl_min)` — pause subsystem, log motivo
- `linkedin_visited_today()` — lista perfis visitados (auditoria)
- `linkedin_dryrun_comment(post_id, text)` — simula sem postar
- **Auth**: JWT audience=hermes-linkedin, scope=read|write split
- **Rate-limit**: herdado slowapi singleton MERGED-016

### hermes-prospects MCP (FastMCP 3.0)
- `prospects_search(filters)` — read DB com filtros (stage, score)
- `prospects_get(id)` — full record + sequence state
- `prospects_resolve_conflict(id, decision)` — mutate state.conflicts
- `proposals_mark_sent(id, channel)` — mutate proposals.sent_at
- **Auth**: scope=read default, scope=write requer audience=hermes-orchestrator
- **DB**: usa db_utils._connect() singleton — NUNCA bypass

### hermes-skills MCP (FastMCP 3.0)
- `skill_list()` — inventario skills atuais + status (enabled/disabled/disabled_reason)
- `skill_propose(yaml_spec)` — abre PR no GitHub via GitHub MCP, retorna PR URL
- `skill_disable(name, reason)` — auto-disable F.4 criterio 5+ erros
- `skill_run_history(name, limit)` — ultimas N execucoes + score
- **Auth**: scope=write requer audience=hermes-meta + 2FA owner approval flow

## Gateway architecture (F.5 fundacao)

```
              ┌────────────────────────────────────────┐
              │ Hermes Brain (Claude API)              │
              └────────────┬───────────────────────────┘
                           │ MCP protocol (1 endpoint)
              ┌────────────▼───────────────────────────┐
              │ ContextForge MCP Gateway (VM :8600)    │
              │ - OAuth 2.1 JWT validation             │
              │ - Rate limit per-tool                  │
              │ - OpenTelemetry tracing → Sentry       │
              │ - Audit log → DB hermes_mcp_audit      │
              │ - TOON compression                     │
              └─┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬─────┘
                │  │  │  │  │  │  │  │  │  │  │  │
                ▼  ▼  ▼  ▼  ▼  ▼  ▼  ▼  ▼  ▼  ▼  ▼
              hermes-linkedin  hermes-prospects  hermes-skills
              GitHub MCP       Sentry MCP        Postgres MCP Pro
              Omnisearch       Firecrawl         Hunter.io
              Playwright (cobaia only)           AgentMail (cond)
```

## Anti-padroes
- NUNCA expor 15 MCPs direto ao Brain — sempre via gateway
- NUNCA usar Playwright MCP na conta Caio (fragmentado, sem stealth) — cobaias only
- NUNCA duplicar capability (ex: instalar Exa standalone se Omnisearch ja inclui)
- NUNCA adicionar MCP SaaS pago sem owner approval explicito (guardrail "zero API paga alem Claude Max")
- NUNCA dar scope=write a MCP sem audience JWT validation
- NUNCA pular sanity asserts — shortlist F.5 SEM FastMCP+Gateway+GitHub = survey falhou

## Validacao end-to-end
```powershell
# trigger skill
# espera: .claude/MCP-LANDSCAPE.md gerado <90s
Test-Path .claude/MCP-LANDSCAPE.md
Test-Path .claude/mcp-survey/catalog.json
Get-Content .claude/MCP-LANDSCAPE.md | Select-String "Shortlist F.5"
Get-Content .claude/MCP-LANDSCAPE.md | Select-String "ContextForge"
Get-Content .claude/MCP-LANDSCAPE.md | Select-String "FastMCP"
Get-Content .claude/MCP-LANDSCAPE.md | Select-String "GitHub MCP"
```

## Done criteria
- `.claude/MCP-LANDSCAPE.md` existe com 6 secoes
- Shortlist F.5 inclui FastMCP + ContextForge + GitHub MCP (asserts hard)
- Nenhum MCP shortlist com guardrail_safe=0
- catalog.json refresh ou criado
- run-history.jsonl appended
- Skill re-executavel idempotente (overwrite seguro)
