# PHASE F — QUICKSTART (Owner-Facing 1-Page)

> **Pra quem é**: owner solo (cleao) decidindo qual chapter F.x rodar AGORA.
> **Pra quem NÃO é**: agente Claude Code (esse usa `PHASE-F-CHAPTER-PLANS.md` + `HOW-TO-START-PHASE.md`).
> **Última atualização**: 2026-06-08 — pós Completeness Critic round.
> **Status global Fase F**: chapters F.1 a F.9 planejados, zero executado. Baseline regressão: `validate_implementation.py --phase A B C D E` = **20/22 PASS** (preservado em todas fases F).

---

## 1. Overview — 9 Chapters em 1 Tela

| # | Título | Classif. | UX score | Sessions | Depende | Output owner-visivel |
|---|--------|----------|----------|----------|---------|----------------------|
| **F.1** | Backend↔Frontend Gap Audit | research+ui | 3 | 1 | — | `.claude/FRONTEND-GAP.md` (mapa 144 rotas + top 10 fantasmas → prioriza F.2–F.9) |
| **F.2** | Mission Control Real-Time + Design System Polish | ui+backend | 9 | 5 | F.1 | Dashboard live: timeline daemon WS, subsystems pause/resume, toasts, dark mode, sem F5 |
| **F.3** | LinkedIn Lab Mode (cobaia descartável) | ui+backend | 7 | 3 | F.1 | Botão `Run Lab` → trace + screenshots + classificação detecção (antes de mexer conta Caio) |
| **F.4** | Auto-Skill Loop (Hermes propõe skill → PR → owner aprova UI) | backend+ui | 8 | 4 | F.1, F.2 | Inbox `Skills propostas` → diff + aprovar/reprovar 1-click, deploy via PR GitHub |
| **F.5** | MCP Gateway (ContextForge) + 3 MCPs Hermes Custom | backend+infra | 6 | 4 | F.1 | 1 endpoint MCP unificado VM, auth+rate-limit+audit, base pra F.6 |
| **F.6** | Cérebro Hermes (Brain.decide loop + Agent-Zero UI) | backend+ui | 9 | 6 | F.1, F.2, F.5 | Painel `Cérebro`: timeline decisões + chat orquestrador + override owner |
| **F.7** | Cobaia Live Ops (LinkedIn warmup + email + enrichment) | backend+ui | 8 | 5 | F.3, F.5 | Pipeline cobaia 14d: discovery → warmup → outreach controlado, dashboard live |
| **F.8** | Marketplace Skills + Telemetria Cross-Owner | backend+ui | 5 | 3 | F.4, F.6 | Owner vê skills de outros owners (anônimo), instala 1-click, opt-in telemetria |
| **F.9** | Hardening Produção + DR + Runbooks | infra+ops | 4 | 3 | TODAS anteriores | Backup automatizado, runbooks `/runbook deploy|rollback|incident`, SLO/SLI |

**Total realista**: 34 sessions (~6-8 semanas owner solo trabalhando 1-2 sessions/dia).
**Caminho crítico mínimo pra Mission Control owner-empowered**: F.1 → F.2 = **6 sessions** (~1.5 sem).
**Caminho crítico mínimo pra Hermes autônomo**: F.1 → F.2 → F.5 → F.6 = **16 sessions** (~3-4 sem).

---

## 2. Ordem Recomendada (default — 80% dos casos)

```
F.1  ──► F.2  ──► F.3  ──► F.4  ──► F.5  ──► F.6  ──► F.7  ──► F.8  ──► F.9
[1s]    [5s]    [3s]    [4s]    [4s]    [6s]    [5s]    [3s]    [3s]
```

**Por que essa ordem**:
1. **F.1 primeiro SEMPRE** — sem inventário backend↔frontend, F.2-F.9 priorizam errado e owner continua CLI-bound.
2. **F.2 antes de tudo** — destrava Mission Control real-time. Owner para de fazer SSH+curl pra ver estado daemon.
3. **F.3 antes de F.7** — testar flows LinkedIn em cobaia ANTES de tocar conta Caio sagrada.
4. **F.4 antes de F.6** — Hermes precisa do canal `propor skill → PR → aprovar` ANTES de virar agente decisor (F.6 emite skills via F.4).
5. **F.5 antes de F.6** — Brain.decide() consulta MCPs via gateway, nunca direto (risco audit/auth).
6. **F.7 depende F.3+F.5** — cobaia live precisa lab mode validado + MCPs prontos (Hunter/Firecrawl/AgentMail).
7. **F.8 e F.9 por último** — marketplace e hardening assumem fluxo Hermes maduro.

---

## 3. Decision Tree por Objetivo do Owner

### Objetivo A: "Quero parar de fazer `ssh vm curl /api/...` pra ver o que Hermes tá fazendo"
→ **F.1 → F.2** (6 sessions). Mission Control real-time + timeline daemon + pause/resume UI. Resto pode esperar.

### Objetivo B: "Quero testar flow LinkedIn novo SEM risco de ban na conta Caio"
→ **F.1 → F.3** (4 sessions). Skip F.2 se já tolera CLI. Lab mode standalone.

### Objetivo C: "Quero Hermes propondo melhorias sozinho e eu só aprovo"
→ **F.1 → F.2 → F.4** (10 sessions). Auto-skill loop precisa Mission Control pra aprovar visualmente.

### Objetivo D: "Quero Hermes 100% autônomo prospectando + orquestrando"
→ **F.1 → F.2 → F.5 → F.6** (16 sessions). Cérebro Hermes full loop. NÃO pular F.5 (gateway MCP) — Brain direto em 15 MCPs vira pesadelo audit.

### Objetivo E: "Quero validar tese cobaia (prospect→deal) antes de escalar"
→ **F.1 → F.3 → F.5 → F.7** (13 sessions). Lab + gateway + cobaia live ops. F.2 opcional se aceitar dashboard polling 10s.

### Objetivo F: "Quero deixar Hermes pronto pra outros owners (SaaS-like)"
→ **TUDO até F.9** (34 sessions). Marketplace + DR + runbooks são pré-req comercial.

### Objetivo G: "Só quero hardening prod, resto tá ok"
→ **F.9 standalone** (3 sessions). Pode rodar isolado — `dependencies_on_chapters: [TODAS]` é nominal (DR funciona sem F.2-F.8, perde só cobertura runbook).

---

## 4. Gates Entre Chapters (NUNCA pular)

Cada chapter fecha com **6 gates obrigatórios** antes do próximo arrancar:

| Gate | Critério | Comando verificação |
|------|----------|---------------------|
| **G1 — Regressão zero** | `validate_implementation.py --phase A B C D E` = 20/22 PASS preservado | `python scripts/validate_implementation.py --phase A B C D E --json` |
| **G2 — PLAN.md atualizado** | Chapter F.x marcado completo, bullets de entrega listados | `grep "^- \[x\] F.X" .claude/PLAN.md` |
| **G3 — Memory saved** | `memory_save` tipo workflow com summary chapter | Agentmemory `memory_smart_search "hermes phase F.X complete"` |
| **G4 — Chapter mark** | `mark_chapter "Phase F.X complete — <titulo>"` registrado | Verificável no transcript |
| **G5 — Commit git** | Commit prefixado conforme escopo: `docs(audit):` (F.1), `feat(ui):` (F.2/F.3), `feat(backend):` (F.4-F.7), `infra:` (F.5/F.9) | `git log --oneline -5` |
| **G6 — Smoke test owner** | Owner abre dashboard / roda comando do chapter e CONFIRMA visualmente que entrega funciona | Manual — owner valida |

**Gate especial F.2 → F.3**: WS broadcasts adicionados em loops/sync.py DEVEM passar `--phase D` (loops resilience) sem regredir, ALÉM dos 5 padrões.
**Gate especial F.4 → F.5**: Auto-skill loop DEVE ter ao menos 1 skill aprovada pelo owner via UI antes de F.5 começar (proves loop completo).
**Gate especial F.6 → F.7**: Brain.decide() rodando em modo `dry_run=true` por mínimo 48h antes de F.7 dar autonomia real cobaia.
**Gate especial F.7 → F.8**: Cobaia mínima 1 deal won + 0 bans LinkedIn em 14d antes de marketplace.

---

## 5. Total Realista (com buffer)

| Phase | Estimativa raw | Buffer 30% | Total |
|-------|---------------|------------|-------|
| F.1 | 1 | +0 | **1** |
| F.2 | 5 | +1 | **6** |
| F.3 | 3 | +1 | **4** |
| F.4 | 4 | +1 | **5** |
| F.5 | 4 | +1 | **5** |
| F.6 | 6 | +2 | **8** |
| F.7 | 5 | +1 | **6** |
| F.8 | 3 | +1 | **4** |
| F.9 | 3 | +1 | **4** |
| **TOTAL** | **34** | **+9** | **43 sessions** |

**Calendário owner solo realista** (1.5 sessions/dia média, descontando weekends parciais):
- Mínimo (Objetivo A, F.1+F.2): **~1 semana**
- Cérebro Hermes (Objetivo D, F.1→F.6): **~3 semanas**
- Full Fase F (TODOS): **~6-8 semanas**

**Riscos calendário**:
- F.2 pode estourar (5→8 sessions) se dashboard/app.js precisar refactor maior — owner avalia após F.2 sessão 3.
- F.6 é o mais incerto — Brain.decide() loop pode exigir +2 sessions de tuning prompts.
- F.5 ContextForge gateway tem learning curve — primeira instalação pode comer 1 sessão extra.

---

## 6. Quick Reference — Como Iniciar Cada Chapter

```bash
# Owner roda no Claude Code, dentro D:/dev-projects/main/hermes-cloud-studio:
/start-phase F.1   # → Lê PLAN.md F.1, executa tasks F.1.task_1..5, fecha 6 gates
/start-phase F.2   # → Idem pra F.2 (pré-req: F.1 fechado)
# ... etc
```

Ou trigger natural: `"iniciar fase F.X"`, `"start phase F.X"`, `"rodar chapter F.X"`.

**Pré-condição global**: `git status` clean (sem changes pending) ANTES de qualquer `/start-phase`.

---

## 7. Links Cruzados — Documentos Vivos da Fase F

| Doc | Path | Pra que serve |
|-----|------|---------------|
| **PLAN principal** | `.claude/PLAN.md` | Todas as fases A-F com checkboxes + bullets. Source of truth. |
| **Study syntheses** | `.claude/PHASE-F-STUDY-SYNTHESIS.md` | Análise pré-planejamento: 11 endpoints fantasma, MCP landscape, gaps UX |
| **Chapter plans (detail)** | `.claude/PHASE-F-CHAPTER-PLANS.md` (gerado por orchestrator) | Plano por chapter F.1-F.9 com tasks, done_criteria, verdicts. Agente consome isso. |
| **Frontend gap (output F.1)** | `.claude/FRONTEND-GAP.md` (gerado em F.1) | Inventário 144 rotas + top 10 órfãos + chapter destino. Alimenta F.2-F.9. |
| **Audit deep** | `.claude/DEEP-AUDIT-2026-06-08.md` | Auditoria pré-Fase F (40K). Contexto histórico. |
| **Audit Fase F específico** | `.claude/AUDIT-2026-06-08-FASE-F.md` | Análise especifica Fase F (13K). |
| **Guardrails** | `.claude/GUARDRAILS.md` | 🚫 NUNCA + ✅ SEMPRE. INVIOLÁVEL. F.1 adiciona regra "backend novo sem frontend = débito". |
| **How-to start phase** | `.claude/HOW-TO-START-PHASE.md` | Procedimento `/start-phase` automatizado (skill `start-phase`). |
| **Validation checklist** | `.claude/VALIDATION-CHECKLIST.md` | Gates G1-G6 verificáveis. |
| **Stealth patches** | `.claude/STEALTH-PATCHES.md` (99K) | Catalog patches anti-detecção LinkedIn — referência F.3/F.7. |
| **Skills Hermes** | `.claude/skills/hermes-*/SKILL.md` | hermes-bug-hunt, hermes-deploy, hermes-li-lab, hermes-status, hermes-stealth-audit, hermes-frontend-gap (F.1 cria). |
| **Workflows Hermes** | `.claude/workflows/` | linkedin-anti-detection-sweep + futuros F.4 auto-skill, F.6 brain-loop |

---

## 8. Cheat Sheet — "Qual chapter resolve essa dor?"

| Dor do owner | Chapter |
|--------------|---------|
| "Tô fazendo curl pra ver estado daemon" | F.2 |
| "Não sei se patch stealth quebra LinkedIn" | F.3 |
| "Hermes podia sugerir skill nova ele mesmo" | F.4 |
| "15 MCPs viraram zoo, sem auth padrão" | F.5 |
| "Quero Hermes decidindo sozinho próxima ação" | F.6 |
| "Preciso provar tese cobaia antes escalar" | F.7 |
| "Quero compartilhar skills com outros owners" | F.8 |
| "E se VM cair? Tenho backup?" | F.9 |
| "Não sei o que tá faltando no frontend" | F.1 (responde ESSA pergunta) |

---

## 9. Regras de Ouro Fase F (não negociáveis)

1. **NUNCA** rodar `/start-phase F.X` sem F.X-1 ter fechado os 6 gates (exceção: F.9 standalone).
2. **NUNCA** instalar `patchright`/`playwright`/browser binary no **PC** — vive APENAS na VM.
3. **NUNCA** modificar `core/state.py` em F.2 (apenas LER) — quebra MERGED-001..016.
4. **NUNCA** expor MCP direto ao Brain em F.6 — sempre via gateway F.5 (audit + rate limit).
5. **SEMPRE** rodar `validate_implementation.py --phase A B C D E` antes E depois de cada task que toca código maduro.
6. **SEMPRE** commit prefix correto (`docs(audit):` F.1 / `feat(ui):` UI / `feat(backend):` backend / `infra:` infra).
7. **SEMPRE** owner valida visualmente (G6) antes de fechar chapter — automated tests não substituem olho humano.
8. **SE** sanity assert F.1 falhar (11 fantasmas não aparecem no top 10) → parser bugado, REFAZER antes seguir.
9. **SE** F.6 Brain.decide() não rodar 48h dry_run sem crash → adiar F.7, não dar autonomia real cobaia.
10. **SE** owner sentir Mission Control lento (F.2 pós-entrega) → F.5 ContextForge TOON compression resolve.

---

**Fim QUICKSTART**. Próximo passo: `/start-phase F.1` 🚀
