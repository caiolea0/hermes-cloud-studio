# Hermes Cloud Studio — Auditoria 2026-06-07

## Contexto absorvido

- Sistema autônomo de prospecção B2B + LinkedIn 24/7. PC (Tauri+FastAPI :8500) orquestra, VM GCP (:8420) executa pesado
- Stack: Tauri 2.0 (Rust) + FastAPI + SQLite WAL + Patchright + OpenRouter/Ollama + AgentMemory MCP
- 11 páginas dashboard SPA vanilla, 5 loops background, daemon orchestrator P1-P7
- 6 skills YAML LinkedIn (deepseek/qwen/nemotron/minimax) sincronizadas PC↔VM
- 11 patches anti-detecção LinkedIn + simulação humana (Bezier, Fitts) + rate limiter SQLite com warm-up 14d
- Estágio embrionário: testes só on-demand, nenhum bem-sucedido por detecção LinkedIn
- Channels Email/WA/IG são stubs (`__init__.py` vazios). `intelligence/`, `task_queue/` vazios
- Bug conhecido: `time.time()` sem `import time` em `server.py:698,722`
- WS `/ws` sem auth — confia em same-origin
- `.claude/` praticamente vazio (só launch.json)

## Diagnóstico estratégico

1. **Detecção LinkedIn = gargalo único.** Zero testes bem-sucedidos. Bloqueia 90% do roadmap. Sem resolver, resto vira teatro.
2. **Silos cross-channel.** Daemon tem P1-P7 mas só LinkedIn implementado. "Hermes 24/7" hoje é "LinkedIn 24/7" no melhor caso.
3. **Skills estáticas sem feedback loop.** Hermes não evolui sozinho — meta de "criar próprias skills" exige camada de auto-reflexão inexistente.
4. **Risco infraestrutura.** Migração pra VM GPU este mês precisa planejamento ou vira refactor caótico.

## Fases recomendadas

- **Fase 1 (sem 1-2)** — Sobrevivência LinkedIn. Endurecer stealth/human/limiter via workflow multi-agent + lab mode pra testar sem queimar conta.
- **Fase 2 (sem 3-6)** — Cross-channel real (Email/WA/IG) + auto-skill loop (Hermes propõe próprias skills via workflow semanal).
- **Fase 3 (sem 7-10)** — Convergência: pipeline único prospect→audit→proposta→site→entrega. Painel real-time consolidado.
- **Paralelo a Fase 1** — Migração VM GPU (RunPod/Lambda/Vast/Hetzner).

## Skills locais propostas (.claude/skills/)

| Skill | Trigger | O que faz | Fase |
|---|---|---|---|
| `hermes-status` | "status hermes", "como tá" | Agrega PC+VM+LI health+daemon state+últimos erros num só report | 1 |
| `hermes-deploy` | "deploy VM", "sync VM" | SSH dry-run → rsync seletivo → restart → health check → rollback | 1 |
| `hermes-li-lab` | "testar flow X", "lab" | Patchright headful local perfil descartável, captura trace+screenshots, classifica detecção | 1 |
| `hermes-bug-hunt` | "varrer bugs hermes" | Code-review focado em race conditions (5 loops!), auth gaps (WS!), bug `time.time()` | 1 |
| `hermes-stealth-audit` | "audit stealth" | Lê stealth/human/limiter + logs, compara com técnicas 2026, patches priorizados | 1 |
| `hermes-skill-forge` | "criar skill X" | Bootstrap YAML schema correto, model recommendation, sync VM, ativa | 2 |
| `hermes-channel-impl` | "implementar channel Y" | Gera channel completo seguindo padrão LinkedIn (config+limiter+human+sender) | 2 |
| `hermes-pipeline-design` | "novo pipeline X" | Desenha pipeline cross-channel com gates, fallbacks, métricas | 2 |
| `hermes-db-query` | "query db hermes" | Wrapper SQL read-only contra `hermes_local.db` + VM via SSH | 2 |

## Subagents custom (.claude/agents/)

| Agent | Quando usar | Diferencial | Fase |
|---|---|---|---|
| `linkedin-detection-researcher` | Pesquisar técnicas detecção 2025-26 | WebSearch+WebFetch focado LinkedIn bot detection, fingerprint papers | 1 |
| `linkedin-flow-debugger` | Campanha travou/falhou | Lê logs VM + trace Patchright + DB state + correlaciona health/rate-limit | 1 |
| `vm-deploy-verifier` | Após deploy VM | SSH, checa services, hits endpoints, valida DB schema, reporta diff | 1 |
| `pipeline-architect` | Pipeline cross-channel novo | Conhece daemon P1-P7, gates, rate-limits — desenha sem conflitar | 2 |
| `skill-yaml-validator` | Antes commit skill | Schema check + model availability OpenRouter + cross-check triggers | 2 |
| `hermes-meta-strategist` | Decisões grandes | Contexto CLAUDE.md+roadmap, propõe trade-offs | 2 |

## Slash commands (.claude/commands/)

- `/hermes-status` — snapshot saúde
- `/hermes-deploy [target]` — sync seletivo PC→VM
- `/hermes-restart [service]` — restart serviço específico
- `/hermes-li-lab <flow>` — testa flow em lab
- `/hermes-skill-new <nome>` — bootstrap YAML
- `/hermes-pipeline-new <obj>` — pipeline cross-channel
- `/hermes-bug-hunt` — code-review focado
- `/hermes-stealth-check` — audit anti-detecção

## Workflows candidatos (agent teams)

| Workflow | Objetivo | Estimativa tokens | Prioridade |
|---|---|---|---|
| `linkedin-anti-detection-sweep` | 4 agents paralelos (web research + ler stealth+human+limiter) → síntese → multi-lens verify → patches concretos | 80-150k | 🔥 Crítica |
| `cross-channel-implementation` | 3 worktrees paralelos: email/wa/ig completos seguindo padrão LinkedIn + adversarial review | 200-300k | Fase 2 |
| `hermes-self-skill-loop` | Meta: lê activity 30d → identifica padrões → propõe N skills YAML → lab-testa → submete dashboard | 100-200k | Fase 2 (semanal P7) |
| `vm-gpu-migration-planner` | Checklist + scripts + dry-run RunPod/Lambda/Vast/Hetzner GPU | 40-60k | Paralelo Fase 1 |

## MCPs

### Já em uso
- `agentmemory` — escopo isolated, agent_id `hermes-cloud-studio`, Ollama qwen3:8b

### Faltam (instalar/conectar)

| MCP | Pra quê | Esforço |
|---|---|---|
| playwright (Anthropic) | Claude controlar browser direto pra testar LI flows | baixo |
| sqlite | Query `hermes_local.db` sem código | baixo |
| github | Issues, PRs, commits | baixo |
| filesystem (escopado VM via SSH) | Ver arquivos VM sem subprocess | médio |
| brave-search / exa | Pesquisa LinkedIn detection focada | baixo |
| firecrawl | Crawl perfis públicos pra enrich prospects | médio (custo) |

### A desenvolver (custom)

| MCP | Tools principais | Esforço | ROI |
|---|---|---|---|
| **`hermes-control`** 🔥 | list_prospects, daemon_state, li_health, query_db, deploy_vm, pipeline_create, campaign_start | 2-3 dias | Altíssimo — Claude controla Hermes via linguagem natural |
| **`linkedin-lab`** | test_flow, run_stealth_patch, fingerprint_compare, capture_trace | 3-5 dias | Alto — desbloqueia Fase 1 |
| **`ollama-router`** | generate(prompt, model_hint), list_available, benchmark | 2 dias | Médio — alinha objetivo GPU VM |
| **`prospect-enricher`** | enrich_by_cnpj, enrich_by_url | 3-4 dias | Médio — fase 3 |

## Cowork — quando faz sentido

**Ignorar agora.** Cowork não controla apps locais nem o stack Tauri/FastAPI/Patchright. Ativar quando:
- Sócio entrar (Linear/Notion pra tracking comercial)
- Telegram bridge atual (subprocess `claude -p`) começar a doer
- Precisar conectar Gmail/Calendar pra prospects responderem

## Pendências conhecidas / bugs / dívidas

- 🔴 **`server.py:698,722`** — `time.time()` sem `import time`, risco runtime
- 🟡 **WS `/ws` sem auth** — confia em same-origin, gap de segurança
- 🟡 **`channels/email|instagram|whatsapp`** — só `__init__.py`, stubs vazios
- 🟡 **`intelligence/`, `task_queue/`** — pastas vazias, intenção futura sem código
- 🟡 **`hermes_desktop.py`** — deprecated mas no repo
- 🟢 Commits pendentes de sessões anteriores (lembrar owner ao fim)
- 🟢 `Hermes Cloud Studio/` subfolder vazia (ignorar/deletar)
