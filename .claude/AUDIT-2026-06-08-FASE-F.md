# Hermes Cloud Studio — Re-auditoria 2026-06-08 (Delta Fase F)

> **Re-auditoria incremental** após DEEP-AUDIT 2026-06-08 (Fases A→D fechadas + E.1+E.2 XSS).
> Fonte canônica: este arquivo + PLAN.md atualizado. AUDIT.md original (2026-06-07) mantido pra histórico.

---

## Contexto absorvido

- **Fase A** (security): 3/3 PASS — auth fail-closed PC+VM, WS token, internal endpoints
- **Fase B** (robustness): 5/5 PASS — SQLite busy_timeout, asyncio spawn, persistência runtime_state/campaign_runs, dispatch error preservation, logging vs silent except
- **Fase C** (config+arch): 6/6 PASS — pydantic-settings central, IP VM via env, ollama_router, pipeline dedupe, split monolitos PC+VM (server.py 3685→251, hermes_api_v2.py 2015→98)
- **Fase D** (infra): 4/4 PASS — psutil supervision, session monitor 3-fail streak, slowapi rate-limit restart, sync versioning + conflict detection
- **Fase E.1** Email channel: PASS — SMTP Gmail + warmup 14d + working hours + retry transient
- **Fase E.2** XSS DOMPurify: PASS — vendor local 3.2.4 allowlist tags+attrs
- **LinkedIn lab E2E** APROVADO 2026-06-07: 5 perfis cobaia visitados sem ban. Conta `milgrauz.exe@gmail.com` viva
- **Zero outreach real** ainda — só baseline lab. Nenhuma campanha contra conta Caio executada
- **MCP `hermes-control`** TS operacional, 16 tools
- **Workflows existentes**: `deep-audit.js` (172 findings), `li-anti-detection.js` (8 patches confirmados)
- **Skills/agents/commands locais**: 5 skills + 3 subagents + 8 slash commands

## Diagnóstico estratégico (delta)

1. **Gap backend↔frontend** — 93 rotas PC + 51 VM expostas, mas dashboard SPA usa fração disso. Owner tem que ir no terminal pra muitas ações que deveriam ser cliques. **Bloqueia operação no-code.**
2. **Cobaia viva mas ociosa** — lab provou stealth funciona, mas warmup 14d não foi iniciado. Sem horas de uso real, próximo passo (conta Caio) é cego.
3. **"Cérebro" do Hermes inexistente** — daemon orquestra prioridades fixas P1-P7, mas não há classifier/router de intent. Owner não consegue conversar com Hermes em linguagem natural pra disparar ação cross-channel.
4. **Auto-skill loop = meta-recursão pendente** — Hermes não evolui sozinho. Sem isso, owner é gargalo permanente pra criar novas skills.
5. **MCP discovery zero** — 1 MCP custom (hermes-control) + 1 externo (agentmemory). Ecossistema explodiu em 2025-26 (browser-use, playwright Anthropic, github, slack, gmail, exa, firecrawl). Cada um pode acelerar fluxo específico.

## Próxima fase

### Fase F — "Hermes Operacional + Self-Evolving" (6-8 semanas)

Foco: tirar Hermes do estado "engine pronta, sem volante" pra "operador no-code orquestrando frota". **Decomposição em 9 chapters** (expandido pós estudo profundo 2026-06-08 — adicionados F.8 Observability + F.9 Pipeline Studio):

#### F.1 — Backend↔Frontend Gap Audit (1 sessão)
- Inventário automatizado: parsing `api/*.py` + `vm_api/routes.py` → lista 144 rotas
- Grep `dashboard/app.js` → mapa rotas consumidas vs órfãs
- Output: `.claude/FRONTEND-GAP.md` ranking por impacto UX (alto = ação freq via CLI hoje)
- Decidir top 10 features a expor

#### F.2 — Mission Control Real-Time Upgrade (2-3 sessões)
- Polir `dashboard/control` (Mission Control já existe stub)
- Activity Orbit expandida: tile por subsistema (LinkedIn / Email / Scraper / Audit / Daemon / Tunnel)
- Cada tile: status live (WS), última ação, próxima ação agendada, botão pause/resume
- Live tail de logs (server-sent events ou WS rolling buffer)
- Indicadores visuais saudável/warning/erro com cores claras
- Persist user prefs (collapsed sections, refresh rate)

#### F.3 — Lab Cockpit (2 sessões)
- Página `dashboard/lab` nova
- UI pra rodar `linkedin/lab/lab_runner.py` sem CLI
- Botões: `fingerprint baseline`, `login fresh`, `viewer test`
- Live screenshot polling (artifacts/*/screenshots/)
- Visualizar compliance score + delta vs baseline
- Lista de runs históricos com diff fingerprint
- API: `/api/lab/runs`, `/api/lab/start`, `/api/lab/{run_id}/artifacts`

#### F.4 — Auto-Skill Loop W3 (2-3 sessões — meta-recursivo)
- Workflow `hermes-skill-forge.js`
- Pipeline: lê activity DB 30d → classify intents recorrentes via Ollama → propõe N skills YAML → lab-test em sandbox → submete dashboard pra aprovação
- Nova tabela `skill_proposals` (PC) com diff visual
- UI: página `/skills/proposals` com YAML preview + accept/reject buttons
- Accept → sync VM `~/.hermes/skills/` automático
- Reject → log motivo, feedback pra próximo loop

#### F.5 — MCP Discovery + Integration (1 research + 2-3 integração)
- **Research**: survey MCPs públicos com ROI alto pra Hermes:
  - `@anthropic-ai/mcp-playwright` (browser real)
  - `@modelcontextprotocol/server-github` (PRs/issues)
  - `@modelcontextprotocol/server-sqlite` (query hermes_local.db)
  - `mcp-server-firecrawl` (crawl enrichment)
  - `mcp-server-exa` (semantic search)
  - `mcp-server-slack` / `mcp-gmail` (notificação)
  - `browser-use` (DOM automation reforçada)
- **Custom propostos**:
  - `linkedin-lab` MCP (test_flow, capture_trace, fingerprint_compare)
  - `prospect-enricher` MCP (CNPJ Receita + perfil público LI)
  - `ollama-router` MCP expõe roteador atual via MCP pra outros clientes
- Decidir 2-3 pra integrar/desenvolver primeiro

#### F.6 — Cérebro Hermes: Orchestration Layer (3-4 sessões)
- Decisão arquitetural: classifier intent (qwen2.5:3b) → tool router → execute
- Novo módulo `core/brain.py`: chat → intent_classify → tool_dispatch → response stream
- Tools registry: agrega skills/pipelines/MCPs/endpoints sob namespace único
- UI: chat na dashboard, cada resposta tem cards de ações executadas (com link pro log/artifact)
- Suporte multi-turn com `_brain_context_id`
- Plumbing WS: stream tokens + action events
- Persistir conversas em `brain_sessions` table

#### F.7 — Cobaia Live Ops (1 sessão + monitor contínuo)
- Plano warmup 14d documentado com gates diários
- Daemon auto-executa: dia 0-6 só lurking (views), dia 7-13 ramp connects, dia 14+ outreach
- Métricas: acceptance_rate (PATCH-014 já implementado), reply_rate, ban_probability
- Stop gates: burned_flag, compliance<70, acceptance<40%
- Daily Telegram report
- Dashboard página `/cobaia` com timeline + métricas

#### F.8 — Cost & Performance Observability (NOVO — 2 sessões)
- **Cost tracking** por LLM call (Claude/OpenRouter/Ollama) — agrega tokens + USD estimado por chapter de pipeline
- **Performance dashboard** — latência p50/p95/p99 por endpoint PC+VM, throughput por loop, slow queries SQLite
- **Error inbox visual** — substitui "checar logs SSH" — agrega erros últimas 24h por subsistema, triage (new/seen/resolved), permalink pro trace
- **Audit trail decisões cérebro** (acoplado a F.6) — cada decisão Brain.decide() registrada com inputs+output+rationale, navegável temporal
- API: `/api/observability/{costs,perf,errors,decisions}`
- Dashboard `/observability` com 4 tabs

#### F.9 — Pipeline Studio Visual (NOVO — 3-4 sessões)
- **Pipeline builder visual** — alternativa zero-code ao YAML/código pra criar pipelines novas
- Decisão design: form-driven structured (cards de step) vs canvas drag-drop. Owner solo + 11 páginas vanilla → **form-driven é mais rápido de construir + mantém**
- **Step library** — cada skill + pipeline existente + MCP tool + endpoint vira step disponível
- **Live execution monitor** — cada step com status, output, timing, error inline
- **Template gallery** — clone-and-modify pipelines existentes
- **A/B test pipelines** — rodar 2 variantes paralelas com mesma fonte, comparar métricas
- API: `/api/pipeline-studio/{steps,templates,execute,monitor}`
- Tabela `pipeline_drafts` (rascunhos sem publicar) + `pipeline_runs` (histórico execução granular por step)
- Dashboard `/pipeline-studio` substitui parcialmente `/pipeline` legado

---

## Regra inviolável: Test pre+post em código maduro (NOVO)

Toda task Fase F que toque código MADURO exige:
1. `pre_test`: capture estado atual (smoke concreto, não grep)
2. Aplica mudança
3. `post_test`: re-run smoke + diff esperado
4. **`validate_implementation.py --phase A B C D E` antes E depois** — confirma 20/22 ainda PASS

**Áreas MADURAS** (qualquer toque = regression gate):
- `core/{state,models,ai,pipeline,limiter}.py` + `core/brain.py` (futuro)
- `loops/*` (6 loops PC)
- `api/*` (10+ routers PC pós-MERGED-011)
- `vm_api/routes.py` (VM consolidado)
- `linkedin/{stealth,human,limiter,account_profile,preflight,stealth_compliance,ollama_router}.py`
- `channels/email/*` (recém-maduro E.1)
- `daemon/orchestrator.py`

Falha em assert prévio → REVERT mandatório. Nada de "cosmético, deixa quieto".

## Skills locais propostas (novas .claude/skills/)

| Skill | Trigger | O que faz | Chapter |
|---|---|---|---|
| `hermes-frontend-gap` | "audit frontend" | Parse API routes + grep app.js → ranking gaps | F.1 |
| `hermes-skill-forge` | "propor skill", "skill forge" | Bootstrap YAML + sync VM + ativa | F.4 |
| `hermes-mcp-survey` | "survey mcps", "mcp research" | Lista MCPs candidatos + estima ROI | F.5 |
| `hermes-brain-test` | "testar brain", "intent X" | Smoke test classifier+router fora do chat real | F.6 |
| `hermes-cobaia-status` | "como tá cobaia", "warmup status" | Snapshot warmup day + métricas + próxima ação | F.7 |

## Subagents custom (novos .claude/agents/)

| Agent | Quando usar | Diferencial | Chapter |
|---|---|---|---|
| `frontend-ux-reviewer` | UI nova entregue | Reviewer com lente "owner solo no-code" (Caio persona) | F.2/F.3 |
| `mcp-integrator` | Integrar MCP novo | Conhece padrão hermes-control TS, evita reinventar plumb | F.5 |
| `brain-prompt-engineer` | Tunear classifier/router intent | Conhece taxonomia Hermes (channels, pipelines, skills) | F.6 |
| `warmup-coach` | Dúvida warmup LI | Conhece PATCH-007/008/014 + janelas operacionais | F.7 |

## Slash commands (novos .claude/commands/)

- `/hermes-frontend-gap` — roda skill F.1
- `/hermes-skill-propose` — disparar workflow W3 manualmente
- `/hermes-mcp-discover` — research MCP candidatos
- `/hermes-brain` — chat one-shot via brain pra teste
- `/hermes-cobaia` — status warmup + próxima ação

## Workflows candidatos (novos)

| Workflow | Objetivo | Estimativa tokens | Prioridade |
|---|---|---|---|
| `frontend-gap-sweep` | Parser routes + grep frontend + ranking UX impact | 30-50k | F.1 |
| `hermes-skill-forge` | Lê activity → propõe skills → lab-test → submete | 200-300k | F.4 |
| `mcp-discovery-survey` | Pesquisa MCPs 2026 + estima ROI + decide roadmap | 80-120k | F.5 |
| `brain-intent-coverage` | Multi-lens: testa 50 prompts típicos contra router, mede acerto | 150-200k | F.6 |
| `cobaia-warmup-coach` | Daily check: verifica day, propõe ação, gera relatório | 20-40k/dia | F.7 |

## MCPs

### Já em uso
- `agentmemory` (escopo isolated, agent_id hermes-cloud-studio)
- `hermes-control` (16 tools, TS)

### Pra integrar (públicos, alta ROI)
| MCP | Pra quê | Esforço | Chapter |
|---|---|---|---|
| `@modelcontextprotocol/server-github` | PRs, issues, code review | baixo | F.5 |
| `@modelcontextprotocol/server-sqlite` | Query `hermes_local.db` natural language | baixo | F.5 |
| `mcp-server-firecrawl` | Enrich prospect via crawl | médio (custo) | F.5 |
| `playwright-mcp` Anthropic | Claude controla browser pra debug LI | baixo | F.5 |
| `mcp-server-exa` ou `brave-search` | Pesquisa LI detection updates | baixo | F.5 |

### A desenvolver (custom novos)
| MCP | Tools principais | Esforço | ROI | Chapter |
|---|---|---|---|---|
| `linkedin-lab` | test_flow, fingerprint_compare, capture_trace | 3-5 dias | Alto | F.5+F.3 |
| `prospect-enricher` | enrich_cnpj, enrich_linkedin_url | 3-4 dias | Médio | F.5 |
| `ollama-router-mcp` | expor router existente | 1-2 dias | Baixo (interno) | F.5 |
| `hermes-brain-mcp` | orchestration via MCP pra clientes externos | 5-7 dias | Alto (futuro) | F.6 |

## Cowork — quando faz sentido

**Continuar ignorando** até:
- Sócio comercial entrar (Linear/Notion)
- Telegram bridge dor real (subprocess `claude -p` virar gargalo)
- Hermes precisar postar/ler em ferramentas terceiras (Gmail, Calendar, Notion)

## Pendências conhecidas / dívidas técnicas

- 🟡 **Channels WhatsApp + Instagram** — pendentes (deferidos por design: 30d Email primeiro)
- 🟡 **`vm_api/routes.py`** — 1 router monolítico (decisão pragmática). Split por domínio quando dor real
- 🟡 **`_extract_profile_data`** — nome/headline vazios (LinkedIn DOM mudou, selectors precisam update)
- 🟡 **VM-GPU migration** — proposta no AUDIT v1, ainda não executada. Aguarda decisão financeira owner
- 🟡 **Telegram bridge** — `subprocess claude -p` funciona mas frágil; futuro via MCP brain
- 🟢 Tech-debt secundário: 11 sqlite3.connect bare no daemon/orchestrator.py + 4 em linkedin/* (não usam db_utils._connect)
- 🟢 `hermes_desktop.py` deprecated mas ainda no repo
- 🟢 `Hermes Cloud Studio/` subfolder vazia (deletar)

## Diferenças vs AUDIT v1 (2026-06-07)

| Aspecto | v1 | v2 |
|---|---|---|
| Foco | Stealth LinkedIn + cross-channel basics | Operacionalização + UX no-code + orquestrador |
| Camadas | Skills + agents + commands | + workflows + MCPs novos + UI cockpit |
| Output | Plano técnico backend | Plano UX-first com backend já solidificado |
| Risco principal | Detecção LinkedIn | Owner gargalo operacional (sem no-code) |

---

**Próximo passo executável**: começar F.1 (frontend gap audit) — fundação pras outras 6 chapters.
