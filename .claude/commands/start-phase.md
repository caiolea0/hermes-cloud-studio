---
description: Inicia fase do IMPLEMENTATION-PLAN com pré-requisitos automatizados + persistência (A-F)
argument-hint: "<A|B|C|D|E|F>"
---
Leia `.claude/HOW-TO-START-PHASE.md` no projeto. Execute os 7 pré-requisitos em paralelo, reporte baseline da `python scripts/validate_implementation.py --phase $1`, aguarde confirmação do owner antes de mexer em código.

## Lógica por fase

### Fases A-E (comportamento padrão)
- Ler `.claude/HOW-TO-START-PHASE.md` integral
- Ler `.claude/IMPLEMENTATION-PLAN.md` seção da fase `$1`
- Rodar 7 pré-requisitos em paralelo (env, deps, tunnel, services, git status, validate baseline, memory recall)
- Reportar baseline:
  - `python scripts/validate_implementation.py --phase $1` (exit code + counts)
  - Estado git (branch, dirty files)
  - Serviços UP/DOWN
- Persistência durável: PLAN.md + TaskCreate + memory_save + mark_chapter
- AGUARDAR confirmação do owner antes de tocar código

### Fase F (adicional — código maduro)
SE `$1 == "F"`:
- Ler TAMBÉM em paralelo:
  - `.claude/AUDIT-FASE-F.md` (auditoria do estado atual)
  - `.claude/IMPLEMENTATION-PLAN-FASE-F.md` (plano específico fase F)
  - `.claude/PHASE-F-STUDY-SYNTHESIS.md` (síntese estudo prévio)
- ALERTAS obrigatórios pra reportar ao owner ANTES de aprovação:
  - **Regression-test gate**: fase F mexe em código maduro → todo patch precisa passar regression suite ANTES + DEPOIS. Sem isso, NÃO mergear.
  - **Pre/post test obrigatório**: cada mudança em módulo maduro (stealth.py, human.py, limiter.py, hermes_api_v2.py, daemon/) exige:
    - Snapshot comportamento ANTES (test run + métricas baseline)
    - Snapshot DEPOIS (test run + métricas)
    - Diff metrics → owner aprova ou reverte
  - **UI empowerment meta**: fase F entrega controle visual ao owner — toda feature backend precisa ter contraparte UI no dashboard (toggle, slider, status indicator). Backend-only patches em fase F = scope incompleto.
- Persistência: além do padrão, criar chapter "Phase F — Maduro hardening" e memory_save type="architecture" com escopo da fase.

## Output esperado
```
PHASE: $1
BASELINE:
  validate_implementation: <exit_code> (<pass>/<total>)
  git: <branch> [<dirty_count> dirty]
  services: <up_list> | DOWN: <down_list>
  memory_recall: <N hits>
PREREQUISITES: <7/7 OK | failures listed>
[F only] GATES:
  - regression-test gate: <armed|missing>
  - pre/post snapshot policy: <enforced>
  - UI empowerment check: <covered|gap>
NEXT: aguardando GO do owner
```

NÃO tocar código até owner responder GO.
