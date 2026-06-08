---
name: hermes-frontend-gap
description: Auditoria deterministica do gap backend-frontend Hermes. Cruza inventario AST de rotas FastAPI (PC api/*.py + VM vm_api/routes.py + shells server.py/hermes_api_v2.py) com consumo real do dashboard (dashboard/app.js fetch+WS+hash routes) e produz .claude/FRONTEND-GAP.md ranking top 10 endpoints orfaos priorizados por impacto UX. Re-rodavel apos cada fase F.2-F.9 pra medir progresso. Trigger "audit frontend", "frontend gap", "gap audit backend", "mapear endpoints", "/hermes-frontend-gap".
---

# /hermes-frontend-gap — Backend<>Frontend Gap Audit

## Quando disparar
- Inicio fase F (mapear o que owner faz hoje via CLI mas backend ja expoe)
- Apos cada fase F.2-F.9 fechar (recalcular orfaos restantes — termometro UX)
- Antes de propor nova API (cross-check se ja existe orfa similar)
- Owner pergunta "que botao falta no dashboard"
- PR review de codigo backend sem PR correspondente frontend (regra GUARDRAILS)

## Inputs
NENHUM — auto-discovery. Skill descobre:
- `api/*.py` (20 arquivos FastAPI PC backend)
- `vm_api/routes.py` (VM backend stealth)
- `server.py` + `hermes_api_v2.py` (shells legacy)
- `channels/*.py` + `ws_*.py` (eventos WS emitidos)
- `dashboard/app.js` (5429 linhas, 271 fetch calls ground truth)
- `dashboard/index.html` (hash routes)
- `.claude/PHASE-F-STUDY-SYNTHESIS.md` §2 (lista hardcoded 11 fantasmas pra sanity)

## Outputs
| Arquivo | Conteudo |
|---|---|
| `.claude/frontend-gap/routes.json` | Inventario completo: `[{method, path_full, router_file, line, function_name, auth_decorator, side: pc\|vm}]` |
| `.claude/frontend-gap/frontend-consumption.json` | Mapa: `{endpoint_pattern: [{file, line, snippet_20chars, kind: fetch\|ws\|hash}]}` |
| `.claude/frontend-gap/ws-events.json` | Eventos WS emitidos backend (`channels/*.py`) vs `socket.on()` em app.js |
| `.claude/frontend-gap/diff-vs-known.md` | Drift entre execucoes (qual endpoint mudou de bucket) |
| `.claude/FRONTEND-GAP.md` | Relatorio principal: §1 inventario, §2 consumo, §3 orfaos, §4 TOP 10, §5 Quick Wins, §6 Mission Control endpoints |

## Procedimento (3 passos deterministicos)

### Passo 1 — Parse AST routes PC+VM
```powershell
python .claude/skills/hermes-frontend-gap/scripts/parse_routes.py
```
- Usa `ast.parse()` em `api/*.py` + `vm_api/routes.py` + shells.
- Detecta `@router.get/post/put/delete/patch/websocket` + `APIRouter(prefix=...)` + `Depends(verify_token)/Depends(require_internal)`.
- Sanity hard: `assert len(routes) >= 140` (topology: 93 PC + 51 VM = 144). Se <140 = parser bugado, falha alto.

### Passo 2 — Grep consumo dashboard
```powershell
python .claude/skills/hermes-frontend-gap/scripts/grep_frontend.py
```
- Regex tolerante a path params: cobre template literal `` `/api/prospects/${id}` ``, concat `'/api/prospects/' + id`, helper `apiCall('/...')`, hash `#/prospects/:id`.
- Varre `channels/*.py` + `ws_*.py` extraindo `await ws_manager.broadcast(event_name, ...)` e cruza com `socket.on('event_name')` em app.js.
- Teste unitario inline: lista 8-10 padroes conhecidos do app.js que DEVEM match (falha alto se regex regrediu).
- Sanity: `assert total_consumos >= 200` (271 fetch ground truth ± ruido).

### Passo 3 — Diff + ranking + relatorio
```powershell
python .claude/skills/hermes-frontend-gap/scripts/rank_gaps.py
```
- Cruza `routes.json` x `frontend-consumption.json` → 3 buckets: **CONSUMED**, **ORPHAN**, **STUB-ONLY**.
- Heuristica score impacto UX:
  - Peso 3: POST/PATCH/DELETE (acao owner)
  - Peso 2: path `/daemon|/linkedin|/prospects` (alta freq diaria)
  - Peso 1: GET telemetria
  - Bonus +2: endpoint em lista hardcoded 11 fantasmas conhecidos
  - Bonus +1: auth_decorator = `verify_token` (UI publica) vs `require_internal` (loopback-only — UI NAO chama)
- Sanity hard: assert os 11 fantasmas de PHASE-F-STUDY-SYNTHESIS.md §2 aparecem em ORPHAN ou STUB-ONLY. Se faltar algum → raise + log diff explicito (qual fantasma, em qual bucket caiu).
- Gera `.claude/FRONTEND-GAP.md` com 6 secoes (ver abaixo).

## Formato canonico FRONTEND-GAP.md

```markdown
# Hermes Frontend Gap — gerado {YYYY-MM-DD HH:MM}
Baseline fase: {F.1|apos F.2|apos F.3|...}
Orfaos totais: {N} (era {M} na execucao anterior — delta {+/-X})

## §1 Inventario rotas backend ({N} total)
<details><summary>PC api/* ({X} rotas)</summary>
| Method | Path | Router | Line | Auth |
|---|---|---|---|---|
| GET | /api/daemon/state | api/daemon.py | 142 | verify_token |
...
</details>
<details><summary>VM vm_api/routes.py ({Y} rotas)</summary>...</details>

## §2 Mapa consumo dashboard
| Endpoint | Chamadas | Locais |
|---|---|---|
| /api/prospects | 18 | app.js:412, app.js:1893, ... |

## §3 Orfaos (backend exposto, zero consumo UI) — {N} endpoints
| Method | Path | Side | Auth | Justificativa orfandade |
|---|---|---|---|---|

## §4 TOP 10 priorizado
| Rank | Endpoint | Metodo | Side | UX gain | CLI hoje | WS needed | Owner pain (1-5) | Effort UI | Chapter destino |
|---|---|---|---|---|---|---|---|---|---|
| 1 | /api/daemon/timeline | GET | PC | Mission Control real-time replace `ssh vm 'tail -f /var/hermes/daemon.log'` | curl + tail SSH | true | 5 | M | F.2 |

## §5 Quick Wins UX (1 fetch + 1 toast)
- POST /api/prospects/{id}/resolve-conflict — botao "resolver conflito" linha 1247 list view

## §6 Mission Control endpoints (WS + streaming)
- GET /api/daemon/timeline → necessita canal WS `daemon_timeline_update` (atualmente broadcast inexistente)
- GET /api/daemon/decisions → WS `daemon_decision_made`
```

## Criterios de sucesso (sanity asserts)
- [ ] `routes.json` total >= 140 endpoints
- [ ] `frontend-consumption.json` total consumos >= 200
- [ ] `FRONTEND-GAP.md` contem string literal `TOP 10`
- [ ] `FRONTEND-GAP.md` contem os 11 fantasmas: `/api/daemon/timeline`, `/api/daemon/decisions`, `/api/daemon/state`, `/api/daemon/log`, `/api/daemon/channels`, `/api/prospects/{id}/resolve-conflict`, `/api/tasks/bulk`, `/api/stats`, `/api/linkedin/visited`, `/api/linkedin/comment/edit`, `/api/agent-zero/status`
- [ ] Tempo total execucao <90s end-to-end
- [ ] Zero modificacao em codigo MADURO (validate_implementation.py --phase A B C D E continua 20/22 PASS)

## Anti-padroes (NUNCA)
- NUNCA sobrescrever `FRONTEND-GAP.md` se sanity asserts falharem (rollback dos JSONs, preserva baseline anterior intacto)
- NUNCA modificar arquivos fora de `.claude/` durante execucao da skill (parser AST e grep sao READ-ONLY)
- NUNCA classificar endpoint com `Depends(require_internal)` como UX gap (loopback-only, UI nao chama por design)
- NUNCA pular o cross-check dos 11 fantasmas — se parser regredir, top-10 erra e fases F.2-F.9 priorizam mal
- NUNCA marcar como CONSUMED endpoint que so aparece em string literal de log/comentario (regex precisa estar em contexto `fetch(`, `apiCall(`, `new WebSocket(`)

## Tempo esperado
- Passo 1 (parse): 5-15s
- Passo 2 (grep): 10-25s
- Passo 3 (rank + markdown): 5-15s
- **Total: <60s tipico, <90s hard limit**

## Re-execucao recomendada
Apos cada fase F.x fechar:
```powershell
python .claude/skills/hermes-frontend-gap/scripts/parse_routes.py
python .claude/skills/hermes-frontend-gap/scripts/grep_frontend.py
python .claude/skills/hermes-frontend-gap/scripts/rank_gaps.py
```
`diff-vs-known.md` mostra exatamente quais endpoints saíram de ORPHAN → CONSUMED (vitorias da fase) e se algum CONSUMED virou ORPHAN (regressao UI).

## Estrutura skill
```
.claude/skills/hermes-frontend-gap/
  SKILL.md                          # este arquivo
  scripts/
    parse_routes.py                 # AST inventory PC+VM (~80 linhas)
    grep_frontend.py                # regex fetch+WS+hash em app.js (~90 linhas com WS cross-ref)
    rank_gaps.py                    # diff + scoring + markdown render (~170 linhas)
.claude/commands/
  hermes-frontend-gap.md            # slash command invoca esta skill
.claude/frontend-gap/               # outputs auto-criados
  routes.json
  frontend-consumption.json
  ws-events.json
  diff-vs-known.md
.claude/
  FRONTEND-GAP.md                   # relatorio principal owner-facing
```

## Permissions (settings.local.json)
Allowlist escopada (NAO wildcard `python *`):
```json
{
  "permissions": {
    "allow": [
      "Bash(python .claude/skills/hermes-frontend-gap/scripts/parse_routes.py)",
      "Bash(python .claude/skills/hermes-frontend-gap/scripts/grep_frontend.py)",
      "Bash(python .claude/skills/hermes-frontend-gap/scripts/rank_gaps.py)"
    ]
  }
}
```

## Defesa em profundidade — drift detection
Apos cada execucao, comparar `git diff --stat` esperando APENAS paths sob `.claude/`. Se outro path aparecer (api/, dashboard/, core/, loops/) = drift acidental, abortar + investigar. Esta verificacao roda no smoke_test da task_5 do chapter F.1 (PLAN.md).

## Integracao com chapters seguintes
- **F.2** Mission Control consome `/api/daemon/timeline|decisions|state|log|channels` — top 10 entrega lista priorizada de quais broadcasts WS criar primeiro.
- **F.4** Auto-skill loop consome `/api/skills/*` — top 10 sinaliza endpoints faltantes pra UI propor/aprovar skill.
- **F.5** Cobaia operations consome `/api/linkedin/visited|comment/edit|delete` — top 10 prioriza por freq CLI owner.
- **F.6** Brain orchestrator consome `/api/agent-zero/status|chat` + `/api/prospects/{id}/resolve-conflict` — top 10 mapeia substituicao de comandos manuais.
- **F.7** Cobaia Live Ops consome `/api/stats` + `/api/tasks/bulk` — top 10 entrega dashboard discovery+enrichment.

## Relacao com GUARDRAILS
Esta skill formaliza a regra GUARDRAILS.md ✅ SEMPRE:
> "Backend novo SEM consumo frontend = debito imediato → adicionar entrada em .claude/FRONTEND-GAP.md orfaos antes de merge"

PR review futuros: se diff toca `api/*.py` mas nao toca `dashboard/app.js`, reviewer roda `/hermes-frontend-gap` pra confirmar endpoint aparece em §3 orfaos com chapter destino atribuido.
