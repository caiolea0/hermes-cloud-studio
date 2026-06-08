# Como começar cada fase em sessão dedicada

> Procedimento canônico **idêntico** para A, B, C, D, E. Persistência embutida.
> Use ESTE arquivo como roteiro. Não improvise — desvios = bugs invisíveis.

---

## Prompt universal (copiar-colar no início de QUALQUER fase)

Abre Claude Code em `D:\dev-projects\main\hermes-cloud-studio` e cola:

```
Vamos começar a Fase {A|B|C|D|E} do IMPLEMENTATION-PLAN do Hermes Cloud Studio.

PRÉ-REQUISITOS OBRIGATÓRIOS (executar nesta ordem, NÃO PULAR):

1. Read .claude/GUARDRAILS.md  — internalizar 🚫 NUNCA + ✅ SEMPRE
2. Read .claude/PLAN.md         — estado atual do projeto
3. Read .claude/IMPLEMENTATION-PLAN.md (seção da Fase {X})  — escopo da fase
4. Read .claude/VALIDATION-CHECKLIST.md (findings dessa fase) — asserts a satisfazer
5. memory_smart_search "hermes phase {X} implementation"
6. Verificar tunnel: `python scripts/tunnel_supervisor.py --status` deve retornar egress_residential=true
7. Baseline check: `python scripts/validate_implementation.py --phase {X}` — confirma quais findings ainda em FAIL

EXECUÇÃO:

Pra cada finding da fase (em ordem do IMPLEMENTATION-PLAN):
  a. mark_chapter "Phase {X}.{N} — MERGED-XXX"
  b. TaskCreate com descrição do finding
  c. Implementar conforme análise + solução documentadas
  d. Smoke test conforme plano de teste do finding
  e. `python scripts/validate_implementation.py --finding MERGED-XXX` deve PASS
  f. git add + git commit "fix(escope): MERGED-XXX — descrição curta"
  g. memory_save tipo bug/architecture com fix + arquivos tocados
  h. Update .claude/PLAN.md (marcar checkbox)
  i. Update .claude/GUARDRAILS.md se regra arquitetural nova
  j. TaskUpdate completed

Ao final da fase:
  - `python scripts/validate_implementation.py --phase {X}` MUST be 100% PASS
  - Se FAIL: NÃO fechar fase. Re-abrir findings + iterar.
  - git push
  - memory_save tipo workflow: resumo da fase, próximo movimento
  - Comunicar fim ao owner

Anti-padrões PROIBIDOS:
  ❌ Pular validação porque "óbvio que funciona"
  ❌ Commit que mexe em arquivo fora do escopo do finding atual
  ❌ Marcar finding completed sem PASS no script
  ❌ Implementar 2 findings no mesmo commit (exceto se tecnicamente acoplados)
  ❌ Pular memory_save / chapter mark / PLAN update

Comece executando os 7 pré-requisitos em paralelo (são todos read-only), reporte estado, depois aguarde minha confirmação antes de mexer em código.
```

Substituir `{X}` por `A`, `B`, `C`, `D`, ou `E`.

---

## Por fase — particularidades

### Fase A — Security Critical

**Tempo estimado**: 4-6h em 1 sessão dedicada
**Tokens**: ~50k
**Sequência**: A.1 (MERGED-002) → A.2 (MERGED-001) → A.3 (MERGED-003)

**Por quê essa ordem**: MERGED-002 (fail-closed AUTH_TOKEN) é prerequisito de A.2 e A.3 — sem auth funcional, WS auth e internal token são incompletos.

**Cuidados específicos**:
- Tauri precisa injetar HERMES_AUTH_TOKEN no env do subprocess server.py. Verificar `app/src-tauri/src/lib.rs` antes de commitar A.1
- WS auth no dashboard precisa também atualizar `linkedin_data/sessions/*.json` se houver cookie/token cacheado
- INTERNAL_TOKEN no .env requer **regenerar** os mesmos tokens no extension Chrome (recarregar)

**Risco principal**: dev local sem env var → server não sobe. Documentar no PLAN regenerar token com `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

### Fase B — State & Robustness

**Tempo estimado**: 3-5 dias em 2-3 sessões
**Tokens**: ~150k
**Sequência sugerida**:
1. B.1 MERGED-005 (busy_timeout) — quick win, melhora confiabilidade geral
2. B.3 MERGED-015 (asyncio spawn helper) — prerequisito de B.2
3. B.2 MERGED-004 (globals persistence) — depende de B.3
4. B.5 MERGED-016 (dispatch error preservation)
5. B.4 MERGED-007 (except: pass) — pode dividir em sub-sessões por arquivo

**Cuidados**:
- B.2 inclui SCHEMA migration (campaign_runs table) — deploy VM ou rodar migration manualmente
- B.4 NÃO fazer em 1 commit gigante. Por arquivo ou bloco lógico.

### Fase C — Architecture Consistency

**Tempo estimado**: 1-2 semanas em 3-5 sessões
**Tokens**: ~400k
**Sequência OBRIGATÓRIA** (cada um habilita o próximo):
1. C.1 MERGED-013 (Settings central pydantic-settings) — **TODO O RESTO depende**
2. C.2 MERGED-009 (IP VM via env) — refactor trivial após C.1
3. C.3 MERGED-008 (topologia enforce) — depende de C.1
4. C.4 MERGED-014 (Ollama router) — decisão estratégica do owner
5. C.6 MERGED-012 (pipeline dedupe) — extrai core/pipeline.py
6. C.5 MERGED-011 (split monolitos) — **iterativo, vários sub-commits**, por último

**Cuidados**:
- C.5 split: NÃO mover lógica num só commit. Mover APIRouter por domínio, smoke test cada.
- C.1 quebra deploy se .env não atualizado. Rodar antes em dev.
- C.4 depende da decisão estratégica VM-GPU migration (pode adiar)

### Fase D — Infra & Supervision

**Tempo estimado**: 3-5 dias em 1-2 sessões
**Tokens**: ~80k
**Sequência**:
1. D.1 MERGED-017 (subprocess scraper) — quick win
2. D.2 MERGED-018 (session monitor consecutive) — quick win
3. D.3 MERGED-020 (rate-limit restart) — quick win
4. D.4 MERGED-006 (sync versioning) — schema migration, requer mais cuidado

**Cuidados**:
- D.4 envolve coluna nova em tabela existente. Migration script obrigatório.

### Fase E — Features & Hardening

**Tempo estimado**: 1 sprint completo (~2-3 semanas)
**Tokens**: ~200k
**Estratégia**: implementar 1 channel por vez, testar 30 dias, próximo.

**Sequência**:
1. E.1.1 MERGED-010 Email (SMTP, simples, alto ROI)
2. E.1.2 MERGED-010 WhatsApp (Business API ou wppconnect — escolher antes)
3. E.1.3 MERGED-010 Instagram (Graph API — risco ban)
4. E.2 MERGED-019 XSS sanitization

**Cuidados**:
- Cada channel = mini-sprint. NÃO emparelhar.
- Skills YAML novas precisam ser sincronizadas pra VM (~/.hermes/skills/).
- Email: setup Gmail App Password antes (não senha conta).
- WhatsApp: decisão Business API (paga) vs wppconnect (free, risco ban) é estratégica owner.

---

## Quando atacar tudo em sessões consecutivas vs espaçadas

| Estratégia | Quando faz sentido |
|---|---|
| **Tudo em 1-2 semanas sprint-like** | Owner tem ~6h/dia dedicado |
| **1 fase por semana espaçada** | Owner trabalha part-time + cliente paralelo |
| **Só Fase A agora, resto adiar** | Outras prioridades estratégicas (ex: cliente novo, deadline) |

**Recomendação**: Fase A imediatamente (segurança não espera) + Fase B em até 2 semanas. Fases C/D/E podem espaçar conforme contexto.

---

## Validação cross-projeto

A skill `/audit-project` global (em `~/.claude/skills/audit-project/`) replica esse framework. Quando rodar `/audit-project` em outro projeto:
- Cria .claude/GUARDRAILS.md (Fase 0 obrigatória)
- Coleta findings
- **Não cria IMPLEMENTATION-PLAN automaticamente** — esse é manual por projeto (deep-audit workflow é opcional, custo alto)

Pra ter IMPLEMENTATION-PLAN em outro projeto, peça explicitamente: "rodar deep-audit no projeto X" depois.

---

## Atalho para sessões futuras

Salve este prompt como `.claude/commands/start-phase.md`:

```markdown
---
description: Inicia fase do IMPLEMENTATION-PLAN com pré-requisitos automatizados
argument-hint: "<A|B|C|D|E>"
---

Leia HOW-TO-START-PHASE.md no .claude/. Execute os 7 pré-requisitos em paralelo,
reporte baseline da validation `--phase $1`, aguarde confirmação owner antes de
mexer em código.
```

Daí basta digitar `/start-phase A` no Claude Code aberto no projeto.
