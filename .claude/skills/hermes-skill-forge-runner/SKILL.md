---
name: hermes-skill-forge-runner
description: Executor controlado de skills forjadas pelo Hermes Brain (Fase F.4 auto-skill loop). Roda skill candidata em sandbox isolado com dry-run obrigatorio antes de promover pra producao, captura metricas (latencia, exit code, side-effects detectados), persiste resultado em skill_runs table, decide promote/quarantine/disable via criterios objetivos. Use quando user diz "rodar skill X", "testar skill forjada", "promover skill", "dry-run skill", "forge runner", ou invocar /hermes-skill-forge-runner. Auto-disparado pelo Brain F.4 apos sintetizar skill nova.
---

# /hermes-skill-forge-runner — Executor controlado de skills forjadas

## F.4 Real Implementation Status

Esta skill cresce em fatias acopladas as 5 sub-sessoes F.4 (PLAN.md D1):

| Sub-sessao | Entrega                                                                                | Status     |
|------------|---------------------------------------------------------------------------------------|------------|
| **F.4.1**  | Backend `skill_proposals` + `skill_runs` tables + CRUD `/api/skills/proposals/*` + workflow `hermes-skill-forge.js` POST DB integration + SKILL.md F.4 real | **DONE**   |
| F.4.2      | GitHub MCP `create_pull_request` (branch `skill/proposal-{id}`) + Lab sandbox via `mcp.hermes-skills.test_skill_dryrun` + lab_test_result update         | PLANEJADO  |
| F.4.3      | UI `/skills/proposals` dashboard + Monaco editor read-only YAML + accept/reject modal owner                                                              | PLANEJADO  |
| F.4.4      | Sync VM auto on merge (webhook handler atomic transaction) + Sentry MCP cron quarantine signal (D6 success_rate < 0.5 last 10 runs)                       | PLANEJADO  |
| F.4.5      | Closeout F.4 + holistic reviewer + F.7 PREP                                                                                                              | PLANEJADO  |

Fluxo F.4 end-to-end (alvo F.4.5):
1. Workflow `hermes-skill-forge.js` cron daily 09h BRT → analise activity 30d → 3 candidatos paralelos
2. POST `/api/skills/proposals` (F.4.1) → `skill_proposals` row status=draft
3. Owner aprova via UI dashboard (F.4.3) → status=lab_running
4. Backend background dispatch `mcp.hermes-skills.test_skill_dryrun` (F.4.2) → status=lab_passed|lab_failed
5. Se lab_passed: `mcp.github.create_pull_request` branch skill/proposal-{id} (F.4.2) → status=pr_open
6. Owner reviewa PR no GitHub → manual merge → webhook (F.4.4) → status=pr_merged → sync VM `~/.hermes/skills/`
7. Cron daily analyzer (F.4.4) lê `skill_runs` last 24h → Sentry MCP errors → propose quarantine via Brain

## Proposito

Fase F.4 (auto-skill loop) sintetiza skills novas a partir de padroes observados (ex: "owner sempre faz X depois de Y → forjar skill X-after-Y"). Skill recem-forjada NAO pode ir direto pra producao — precisa de gate de validacao mecanizado. Esta skill e esse gate.

Fluxo:
1. Brain sintetiza candidata em `.claude/skills/_forge/<skill-name>/SKILL.md`
2. Runner valida YAML frontmatter + estrutura
3. Runner executa em **dry-run** (zero side-effects reais — mocks de fetch/db/ssh)
4. Runner executa em **shadow-run** (side-effects reais MAS em cobaia/sandbox, conta real INTOCADA)
5. Runner coleta metricas → decide: promote (`.claude/skills/`), quarantine (`.claude/skills/_quarantine/`), ou disable (raise alert)
6. Persiste tudo em `skill_runs` SQLite + memory_save

## Quando disparar

- Brain F.4 acabou de sintetizar skill nova → auto-trigger
- User diz: "rodar skill forjada X", "testar skill X", "promover skill X"
- User invoca: `/hermes-skill-forge-runner <skill-name> [--mode dry|shadow|promote] [--cobaia <id>]`
- Auditoria periodica: rodar em todas skills quarantined pra reavaliar

## Inputs

| Param | Tipo | Default | Descricao |
|-------|------|---------|-----------|
| `skill_name` | str (required) | — | Nome da skill (slug) em `.claude/skills/_forge/` |
| `mode` | enum | `dry` | `dry` (mocks tudo) \| `shadow` (cobaia real) \| `promote` (move pra prod) |
| `cobaia_id` | str | `cobaia-default` | ID prospect/conta sandbox pra shadow-run (NUNCA conta Caio) |
| `timeout_s` | int | 120 | Hard kill da execucao |
| `max_side_effects` | int | 50 | Limite de fetch/db-write/ssh — exceder = abort + quarantine |

## Outputs

- `.claude/skills/_forge_runs/<skill-name>-<timestamp>.json` — log completo (stdout, stderr, exit, latencia, side-effects)
- SQLite `skill_runs` table — historico agregado (skill_name, mode, verdict, latency_ms, errors, run_at)
- Decisao final printada: `PROMOTED` | `QUARANTINED` | `DISABLED` + justificativa
- memory_save tipo `workflow` com summary

## Procedimento determinístico

### Passo 0 — Pre-flight

```powershell
# Validar guardrails ANTES de tocar qualquer coisa
$skillPath = ".claude/skills/_forge/$skill_name"
if (-not (Test-Path "$skillPath/SKILL.md")) { throw "skill $skill_name nao existe em _forge/" }

# Garantir cobaia real != conta Caio
if ($mode -eq "shadow" -and ($cobaia_id -match "caio|cleao|owner")) {
    throw "GUARDRAIL VIOLATION: shadow-run NUNCA na conta owner"
}
```

### Passo 1 — Validar estrutura skill

Rodar `python .claude/skills/hermes-skill-forge-runner/scripts/validate_skill.py <skill-name>`:
- YAML frontmatter parseavel (name, description >= 50 chars, triggers explicitos)
- SKILL.md tem secoes: Quando disparar, Procedimento, Outputs
- Scripts em `scripts/` (se houver) tem shebang + sao executaveis
- Zero hardcoded paths owner (`C:/Users/cleao`, `cleao@`, `Caio`)
- Zero secrets inline (regex: `sk-`, `eyJ`, `BEGIN PRIVATE KEY`)

Falha aqui → quarantine imediato + log motivo.

### Passo 2 — Dry-run (sempre primeiro)

Executar skill com **wrapper de mocks**:

```python
# scripts/run_dry.py
import sys, json, time, subprocess
from unittest.mock import patch

# Mock todos side-effects perigosos
mocks = {
    'requests.post': lambda *a, **kw: MockResponse(200, {'mocked': True}),
    'requests.get': lambda *a, **kw: MockResponse(200, {'mocked': True}),
    'subprocess.run': lambda *a, **kw: MockProc(returncode=0),
    'sqlite3.connect': lambda *a, **kw: MockConn(),
    'paramiko.SSHClient': MockSSH,
}

start = time.time()
side_effects = []
with patch.multiple('requests', **{k.split('.')[1]: v for k,v in mocks.items() if k.startswith('requests')}):
    result = invoke_skill(skill_name, capture_side_effects=side_effects)
latency_ms = int((time.time() - start) * 1000)

verdict = {
    'mode': 'dry',
    'exit_code': result.returncode,
    'latency_ms': latency_ms,
    'side_effects_attempted': len(side_effects),
    'stdout_tail': result.stdout[-2000:],
    'stderr_tail': result.stderr[-2000:],
}
print(json.dumps(verdict))
```

Criterios PASS dry-run:
- exit_code == 0
- latency_ms < 30000 (30s)
- side_effects_attempted <= max_side_effects
- stderr sem palavras: `TRACEBACK`, `CRITICAL`, `BLOCKED`, `403`, `429`

Falha → quarantine + memory_save.

### Passo 3 — Shadow-run (opcional, so se mode=shadow ou promote)

Skill executa de verdade MAS:
- LinkedIn calls vao pra perfil cobaia (config `HERMES_COBAIA_LI_PROFILE`)
- Email envia pra inbox cobaia (config `HERMES_COBAIA_INBOX`)
- DB writes vao pra `hermes_shadow.db` (copia schema, dados descartaveis)
- SSH calls bloqueadas exceto `cobaia@cobaia-vm`

```powershell
$env:HERMES_RUN_MODE = "shadow"
$env:HERMES_COBAIA_ID = $cobaia_id
python .claude/skills/hermes-skill-forge-runner/scripts/run_shadow.py $skill_name
```

Criterios PASS shadow:
- Tudo do dry-run +
- Side-effects reais nao tocaram conta owner (audit: grep logs por `caio|cleao`)
- Cobaia survived (nenhum 403/429/cooldown disparado)
- Resultado semantico esperado aconteceu (skill define `expected_outcome` no frontmatter — ex: "1 row inserted in skill_proposals")

### Passo 4 — Decisao + persistencia

```python
# scripts/decide.py
def decide(dry_result, shadow_result=None, mode='dry'):
    if dry_result['exit_code'] != 0:
        return ('QUARANTINED', 'dry-run exit != 0')
    if dry_result['side_effects_attempted'] > MAX:
        return ('DISABLED', 'side-effects excedidos — risco loop infinito')
    if mode == 'dry':
        return ('READY-FOR-SHADOW', 'aprovada pra shadow-run manual')
    if shadow_result and shadow_result['cobaia_health'] == 'degraded':
        return ('QUARANTINED', 'cobaia degraded apos shadow')
    if mode == 'promote' and shadow_result['verdict'] == 'pass':
        # mover .claude/skills/_forge/X → .claude/skills/X
        return ('PROMOTED', 'shadow OK + promote solicitado')
    return ('READY-FOR-PROMOTE', 'shadow OK, aguarda owner promote')
```

Persistencia SQLite:
```sql
INSERT INTO skill_runs (skill_name, mode, verdict, latency_ms, side_effects, errors, run_at, cobaia_id)
VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?);
```

memory_save:
```
type: workflow
content: "hermes-skill-forge-runner: skill <name> verdict=<X> mode=<Y> latency=<Z>ms"
concepts: [hermes, phase-f4, skill-forge, <skill_name>, <verdict>]
files: [.claude/skills/_forge_runs/<name>-<ts>.json]
```

## Modos de execucao detalhados

### `--mode dry` (default, SEMPRE roda primeiro)
- Zero side-effects reais
- Tempo alvo: <30s
- Custo: zero
- Output: `READY-FOR-SHADOW` | `QUARANTINED` | `DISABLED`

### `--mode shadow` (cobaia real)
- Side-effects reais em sandbox isolado
- Tempo alvo: <120s
- Custo: 0-5 reqs LinkedIn cobaia (descartavel)
- Output: `READY-FOR-PROMOTE` | `QUARANTINED`
- Pre-req: dry-run da mesma skill passou nas ultimas 24h

### `--mode promote` (move pra producao)
- Roda dry + shadow + move arquivos
- Update `.claude/SKILLS-CATALOG.md` (auto-append entrada)
- Update `settings.local.json` permissions (se skill declara `requires_permissions`)
- Output: `PROMOTED` + commit auto `feat(skill): forge promote <name>`
- Pre-req: shadow-run passou + owner explicito (ou auto se Brain confidence >= 0.9)

## Criterios objetivos auto-disable

Skill vai pra `.claude/skills/_disabled/` se:
- 5+ runs com exit != 0 em janela 24h
- Side-effects > 2x media historica
- Sentry MCP reporta 3+ erros distintos correlacionados
- Cobaia ficou em cooldown LinkedIn apos shadow-run

## Outputs esperados (formato canonico)

```
HERMES SKILL FORGE RUNNER — {skill_name} — {mode}

Validacao estrutura : {OK|FAIL — <motivo>}
Dry-run             : exit={X} latency={Y}ms side-effects={Z}
Shadow-run          : {SKIPPED|OK|FAIL — <motivo>}
Cobaia health pos   : {ok|degraded|cooldown}

Verdict             : {PROMOTED|READY-FOR-PROMOTE|READY-FOR-SHADOW|QUARANTINED|DISABLED}
Justificativa       : {1 linha}

Arquivos:
- log: .claude/skills/_forge_runs/{name}-{ts}.json
- skill: .claude/skills/{_forge|_quarantine|_disabled}/{name}/

Proximo passo:
- {comando ou acao recomendada}
```

## Estrutura de arquivos da skill

```
.claude/skills/hermes-skill-forge-runner/
├── SKILL.md                          # este arquivo
├── scripts/
│   ├── validate_skill.py             # passo 1 — estrutura + secrets scan
│   ├── run_dry.py                    # passo 2 — execucao mockada
│   ├── run_shadow.py                 # passo 3 — execucao cobaia
│   ├── decide.py                     # passo 4 — verdict + move
│   └── lib/
│       ├── mocks.py                  # MockResponse, MockSSH, MockConn
│       ├── cobaia.py                 # config cobaia + audit owner-touch
│       └── persist.py                # SQLite skill_runs + memory_save
└── tests/
    ├── fixture_skill_good/           # skill exemplo que DEVE promote
    └── fixture_skill_bad/            # skill exemplo que DEVE quarantine
```

## Permissions necessarias (settings.local.json)

```json
{
  "permissions": {
    "allow": [
      "Bash(python .claude/skills/hermes-skill-forge-runner/scripts/*.py:*)",
      "Bash(python .claude/skills/hermes-skill-forge-runner/scripts/lib/*.py:*)"
    ]
  }
}
```

Scope estreito — NAO wildcard `python *`. Defesa em profundidade.

## Anti-padroes (NUNCA)

- NUNCA rodar `--mode shadow` ou `--mode promote` sem dry-run PASS recente (24h)
- NUNCA usar conta owner como cobaia — guardrail hard fail
- NUNCA promover skill com side_effects > max_side_effects (loop infinito risk)
- NUNCA pular validate_skill.py — skill com secret inline = leak
- NUNCA modificar `.claude/skills/` de uma skill em uso (verificar `skill_runs` last_used)
- NUNCA rodar 2 forge-runners em paralelo — race em SQLite `skill_runs`

## Integracao com chapters Fase F

| Chapter | Como integra |
|---------|--------------|
| F.1 | Le `.claude/FRONTEND-GAP.md` pra entender quais skills resolvem gaps top-10 |
| F.2 | Mission Control mostra `skill_runs` recentes + verdict (WS event `skill_run_complete`) |
| F.4 | **PRIMARIO** — Brain sintetiza skill → chama runner → consome verdict |
| F.5 | Workflow `linkedin-anti-detection-sweep` pode usar runner pra testar patches stealth em cobaia |
| F.6 | Brain.decide() consulta `skill_runs` last 7d antes de propor skill nova (evita re-forjar quarantined) |
| F.7 | Cobaia live ops e o sandbox de shadow-run — runner depende cobaia VM ativa |

## Sanity check pos-instalacao

```powershell
# 1. Skill responde a trigger
# (invocar via Claude Code: "rodar skill forjada test-fixture")

# 2. Scripts executam
python .claude/skills/hermes-skill-forge-runner/scripts/validate_skill.py --self-test

# 3. SQLite table criada
python -c "import sqlite3; c=sqlite3.connect('hermes.db'); c.execute('SELECT 1 FROM skill_runs LIMIT 1'); print('OK')"

# 4. Fixture good promove, fixture bad quarantina
python .claude/skills/hermes-skill-forge-runner/scripts/run_dry.py fixture_skill_good
python .claude/skills/hermes-skill-forge-runner/scripts/run_dry.py fixture_skill_bad
```

## Tempo de execucao esperado

| Mode | Alvo | Hard timeout |
|------|------|--------------|
| dry | <30s | 60s |
| shadow | <120s | 180s |
| promote | <150s | 240s |

Se exceder timeout: abort + quarantine + log `TIMEOUT_EXCEEDED`.

## Re-execucao e idempotencia

- Re-rodar `--mode dry` na mesma skill: OK, sobrescreve log mais recente, mantem historico SQLite
- Re-rodar `--mode promote` em skill ja promovida: no-op + warning
- Skill quarantined pode ser re-testada apos owner editar — runner detecta hash mudou e permite novo dry-run
- `skill_runs` table NUNCA truncada — historico permanente pra analise drift

## Rollback

Se skill promovida revelar bug em producao:
```powershell
# Move de volta pra quarantine + flag disabled
python .claude/skills/hermes-skill-forge-runner/scripts/decide.py --rollback <skill_name> --reason "<motivo>"
```

Rollback:
1. Move `.claude/skills/<name>/` → `.claude/skills/_quarantine/<name>-rollback-<ts>/`
2. Remove entrada de `SKILLS-CATALOG.md`
3. Insert row `skill_runs (verdict='ROLLBACK', errors=<motivo>)`
4. memory_save tipo `bug` com root cause
5. Notifica Brain pra NAO re-forjar skill identica nas proximas 7d

## Exemplo de uso end-to-end

```
> /hermes-skill-forge-runner auto-reply-portuguese --mode dry

HERMES SKILL FORGE RUNNER — auto-reply-portuguese — dry

Validacao estrutura : OK
Dry-run             : exit=0 latency=2341ms side-effects=3
Shadow-run          : SKIPPED (mode=dry)
Cobaia health pos   : n/a

Verdict             : READY-FOR-SHADOW
Justificativa       : dry-run limpo, sem side-effects suspeitos

Arquivos:
- log: .claude/skills/_forge_runs/auto-reply-portuguese-20260608-1430.json
- skill: .claude/skills/_forge/auto-reply-portuguese/

Proximo passo:
- /hermes-skill-forge-runner auto-reply-portuguese --mode shadow --cobaia cobaia-li-001
```

```
> /hermes-skill-forge-runner auto-reply-portuguese --mode promote --cobaia cobaia-li-001

HERMES SKILL FORGE RUNNER — auto-reply-portuguese — promote

Validacao estrutura : OK
Dry-run             : exit=0 latency=2102ms side-effects=3
Shadow-run          : OK — 1 reply enviado pra cobaia, semantica esperada (PT-BR, <500 chars, sem links)
Cobaia health pos   : ok (sem cooldown, rate-limit 12/70)

Verdict             : PROMOTED
Justificativa       : dry+shadow PASS, owner solicitou promote

Arquivos:
- log: .claude/skills/_forge_runs/auto-reply-portuguese-20260608-1445.json
- skill: .claude/skills/auto-reply-portuguese/ (movida de _forge/)
- catalog: .claude/SKILLS-CATALOG.md atualizado
- commit: feat(skill): forge promote auto-reply-portuguese

Proximo passo:
- Skill ativa em producao. Monitorar via /hermes-status nas proximas 24h.
```

## Slash command

Arquivo: `.claude/commands/hermes-skill-forge-runner.md`

```markdown
---
description: Executor controlado de skills forjadas pelo Brain (dry-run obrigatorio antes de promover)
---

Roda a skill `hermes-skill-forge-runner` com os argumentos passados.

Uso:
- `/hermes-skill-forge-runner <skill-name>` — dry-run default
- `/hermes-skill-forge-runner <skill-name> --mode shadow --cobaia <id>` — testa em sandbox
- `/hermes-skill-forge-runner <skill-name> --mode promote` — move pra producao apos dry+shadow

Anti-padroes:
- Nunca passar cobaia=owner (guardrail hard fail)
- Nunca `--mode promote` sem dry+shadow PASS recente
```

## Veredicto integration (Brain F.6)

Brain consulta antes de re-forjar:
```sql
SELECT verdict, COUNT(*) as n
FROM skill_runs
WHERE skill_name = ? AND run_at > datetime('now', '-7 days')
GROUP BY verdict;
```

Se ultima verdict = QUARANTINED ou DISABLED → Brain NAO re-forja por 7d. Logica vive em `core/brain/skill_proposer.py` (Chapter F.4).
