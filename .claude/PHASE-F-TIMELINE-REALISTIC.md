# Phase F — Timeline Realístico Pós-Verdicts (2026-06-08)

> Re-baseline após processamento dos 4-lens verdicts (regression_risk + estimation_realism + guardrails_compliance + ui_empowerment) sobre os 8 chapters declarados (F.1 → F.9, F.3 fora de escopo).
> Substitui qualquer estimativa otimista anterior. Este é o cronograma DE TRABALHO REAL.

---

## 1. Premissas de Calibração

### 1.1 Definições
- **Sessão**: 1 invocação Claude Code com janela ~50–150k tokens executando 1 chapter (ou fatia coesa). Inclui leitura de contexto, edição, validate_implementation, commit, persistência 6-camadas.
- **Wall-clock**: tempo de relógio de owner solo (cleao) — inclui sessão Claude + intervenção humana (revisar PR, aprovar deploy VM, observar cobaia 24-72h, dormir).
- **Sessão líquida** ≠ **wall-clock**: 1 sessão técnica de 3h pode esticar 1-2 dias se exige observação (linkedin lab, cobaia warmup, smoke prod).

### 1.2 Regras de Calibração
1. **Penalty fixo por toque MADURO**: chapter que edita `core/*`, `loops/*`, `api/*`, `vm_api/*`, `linkedin/*`, `daemon/*`, `channels/*` paga +50% sessões sobre o declarado pra absorver: regressão A-E + SSH deploy VM + smoke pós-deploy.
2. **Penalty UI nova com WS**: cada canal WS novo adiciona +0.5 sessão (broadcast backend + handler frontend + reconnect logic + teste e2e).
3. **Penalty observação humana**: chapters que exigem janela 24-72h pra validar (F.5 lab, F.7 cobaia warmup) somam +N horas wall-clock fora da sessão Claude.
4. **Bonus pure-research**: chapters .claude/-only (F.1) ficam no declarado, sem penalty.
5. **Compounding integration**: chapters tardios (F.8, F.9) que dependem de 3+ chapters anteriores pagam +30% por debug de integração cruzada não previsto isoladamente.

### 1.3 Baseline de Referência
- 20/22 PASS em validate_implementation A-E (estado atual antes de F.1).
- Stack dual PC+VM: SSH deploy obrigatório pra qualquer mudança em VM (vm_api/, linkedin/, daemon/ rodando em VM).
- Owner solo, sem QA terceirizado, sem CI deploy automatizado.

---

## 2. Tabela Re-baseline por Chapter

| Chapter | Título | Sessões (chapter plan) | Sessões (declarado prompt) | Sessões (realista) | Δ realista vs declarado | Wall-clock extra | Justificativa principal |
|---|---|---|---|---|---|---|---|
| F.1 | Backend↔Frontend Gap Audit | 1 | 1 | **1** | 0 | 0h | Pure-research, zero código MADURO. Bonus pure-research aplicado. |
| F.2 | Mission Control Real-Time + Design System Polish | 5 | 4 | **7** | +3 | +4h smoke prod | Toca loops/sync.py + api/daemon.py + dashboard/app.js 3000+ linhas. Penalty MADURO (+50% sobre 5 = +2.5) + 3 canais WS novos (+1.5) = ~9; aliviado pra 7 por overlap de boilerplate. |
| F.4 | Auto-Skill Loop + Sentry observability | 6 | 6 | **10** | +4 | +6h Sentry calibração | Toca skill manager + ollama_router + integra Sentry MCP novo (descoberta + validação). Compounding: depende F.1 inventário + F.5 MCP gateway + F.6 brain hooks. Penalty MADURO + penalty MCP novo + observação pós-trigger primeiros 5 erros. |
| F.5 | MCP Gateway Foundation (ContextForge + FastMCP + 3 MCPs custom) | 8 | 6 | **12** | +6 | +24h hardening | Maior chapter do plano. Novo deploy VM (ContextForge Gateway), 3 servers FastMCP custom (linkedin/prospects/skills), OAuth 2.1 wiring, GitHub MCP integration, Postgres MCP read-only. Penalty MCP novo (cada server = ~1 sessão) + observabilidade. Wall-clock alto pra observar gateway em prod. |
| F.6 | Hermes Brain Orchestrator (decide loop + chat) | 6 | 5 | **9** | +4 | +8h dogfood | Núcleo cognitivo. Depende F.5 (MCPs prontos) + F.1 (inventário endpoints) + F.4 (skill manager retrofitado). Brain.decide() + agent-zero/chat WS + memory bridge. Compounding integration +30%. |
| F.7 | Cobaia Live Ops (warmup 14d + enrichment + outreach) | 4 sessões Claude + 14d observação | 4 | **6** | +2 | **+14d** warmup obrigatório | Sessões técnicas em si caem dentro (setup AgentMail + Hunter MCP + Firecrawl + Apollo gating). MAS wall-clock 14 dias de warmup email + monitoring bounce + Sentry alerts. Penalty observação humana dominante. |
| F.8 | Phase Orchestrator UI + Skill PR-based Deploy | 5 | 4 | **8** | +4 | +4h GitHub Actions | Integra GitHub MCP (F.4) + skill manager (F.4) + Mission Control UI (F.2). PR-based deploy substitui scp manual. Compounding integration +30% por depender 4 chapters anteriores estarem estáveis. |
| F.9 | Hardening + Documentação Owner + Handoff | 4 | 3 | **7** | +4 | +8h E2E walkthrough | Final hardening: rate-limit revisão, GUARDRAILS.md consolidado, owner runbook, E2E walkthrough completo (gateway → brain → skill PR → deploy → cobaia → mission control). Compounding integration máximo (depende TODOS chapters). |
| **TOTAL** | | **39** | **33** | **60** | **+27** | **+72h + 14d warmup** | |

> Nota: F.3 (Lab Testing Pipeline) declarado fora de escopo no prompt original — mantido fora. Workflow hermes-li-lab existente cobre necessidade tática.

### 2.1 Range de Incerteza
- **Total realista**: 60 sessões (mid-point).
- **Range**: **70–90 sessões** considerando bandas de erro ±25% em chapters de alta complexidade (F.5, F.6, F.8, F.9).
  - Cenário otimista (sem bugs cruzados, MCPs públicos sem regressão): **52 sessões**.
  - Cenário pessimista (ContextForge instabilidade, Sentry calibração extensa, cobaia warmup com bounce alto): **90+ sessões**.
- **Wall-clock total**: ~72h de espera fora-de-sessão (smoke prod + observação) + **14 dias contínuos** de cobaia warmup (F.7) que ocorrem em paralelo a F.8/F.9.

---

## 3. Ordem Serial Recomendada

Decisão: **F.1 → F.2 → F.5 → F.6 → F.4 → F.7+F.8 (paralelo) → F.9**

### 3.1 Por que esta ordem (sequenciamento de dependências)

```
F.1  (gap audit — alimenta priorização de TODOS chapters seguintes)
  ↓
F.2  (Mission Control real-time + design system — owner ganha visibilidade ANTES de mexer em brain)
  ↓
F.5  (MCP Gateway + 3 MCPs custom + ContextForge + FastMCP — fundação técnica pra F.4 e F.6)
  ↓
F.6  (Brain orchestrator — consome MCPs via gateway, exige F.5 pronto + F.2 UI Mission Control pra observação)
  ↓
F.4  (Auto-skill loop + Sentry — Brain (F.6) precisa estar vivo pra gerar skills; Sentry MCP via gateway F.5)
  ↓
F.7 ∥ F.8  (cobaia warmup 14d roda em paralelo a Phase Orchestrator UI; warmup é wall-clock, F.8 é sessões Claude)
  ↓
F.9  (hardening + handoff — só faz sentido com tudo acima estável)
```

### 3.2 Racional vs ordem ingênua F.1→F.2→F.4→F.5→F.6→F.7→F.8→F.9
- **F.4 ANTES de F.5/F.6 falha**: Auto-skill loop sem MCP gateway = scp+restart manual, exatamente o débito que F.4 quer eliminar. Sentry MCP precisa do gateway F.5.
- **F.6 ANTES de F.5 falha**: Brain.decide() consultar 15 MCPs direto = anti-pattern explicitado no estudo. Exige gateway primeiro.
- **F.2 ANTES de F.5/F.6 ganha**: owner ganha Mission Control real-time CEDO, observa todos chapters seguintes com cockpit decente. Sem F.2, debug de F.5/F.6 vira CLI-bound (regressão UX).
- **F.7 paralelo a F.8 ganha**: cobaia warmup é wall-clock puro (envio 5 emails/dia, monitorar bounce), libera sessões Claude pra atacar F.8 (Phase Orchestrator UI) em paralelo.

### 3.3 Marcos de Validação Inter-chapter
| Após chapter | Smoke check obrigatório antes de iniciar próximo |
|---|---|
| F.1 | FRONTEND-GAP.md gerado + 11 fantasmas presentes + 20/22 PASS preservado |
| F.2 | Mission Control timeline+decisions chegam via WS em <2s + dark mode togglável + 20/22 PASS + SSH deploy VM OK |
| F.5 | ContextForge gateway responde via curl + 3 MCPs custom registrados + OAuth handshake OK + 20/22 PASS |
| F.6 | Brain.decide() loga decisão a cada N min + chat WS responsivo + memory bridge persiste insights + 20/22 PASS |
| F.4 | Skill auto-gerada abre PR GitHub + Sentry recebe erro e Brain auto-disable funciona em sandbox + 20/22 PASS |
| F.7 (sessões) | AgentMail inbox criada + Hunter verifier <5% bounce + 1 cobaia rodando warmup dia 1 OK |
| F.8 | Phase Orchestrator UI roda 1 chapter end-to-end + skill PR-based deploy substitui scp + 20/22 PASS |
| F.9 | E2E walkthrough completo grava video + owner runbook validado em sessão fresh + 22/22 PASS (E.E aceito) |

---

## 4. Calendário Realístico (2-3 Meses)

### 4.1 Premissas de Ritmo
- Owner solo: assume **~3-5 sessões Claude / semana** (ritmo sustentável, não fim-de-semana queimado).
- Wall-clock incluindo dormir, almoço, vida real: **~10 sessões / mês** efetivas.
- Total 60 sessões mid-point → **~6 meses no ritmo conservador**, **~3 meses no ritmo agressivo (5+ sessões/semana)**.

### 4.2 Calendário Mês a Mês (alvo agressivo 3 meses)

#### **Mês 1 — Fundação UX + Gateway (Sessões 1–22)**
- **Semana 1**: F.1 completo (1 sessão) + F.2 sessões 1-3 (Mission Control real-time core)
- **Semana 2**: F.2 sessões 4-7 (design system polish + WS hardening + smoke prod)
- **Semana 3**: F.5 sessões 1-5 (ContextForge gateway VM + FastMCP framework + MCP custom #1 hermes-linkedin)
- **Semana 4**: F.5 sessões 6-12 (MCPs custom #2 hermes-prospects + #3 hermes-skills + GitHub MCP + Postgres MCP read-only + OAuth + hardening)
- **Marco mês 1**: Owner enxerga TUDO via Mission Control + Gateway responde, MCPs operacionais.

#### **Mês 2 — Brain + Auto-evolução (Sessões 23–41)**
- **Semana 5-6**: F.6 sessões 1-9 (Brain.decide loop + agent-zero/chat WS + memory bridge + dogfood inicial)
- **Semana 7**: F.4 sessões 1-5 (auto-skill loop + ollama_router retrofit + Sentry MCP integration)
- **Semana 8**: F.4 sessões 6-10 (auto-disable on Sentry signal + A/B skill testing via FastMCP versioning + smoke)
- **Marco mês 2**: Brain orquestrando + skill auto-gerada virando PR + Sentry fechando loop.

#### **Mês 3 — Cobaia Real + Phase Orchestrator + Handoff (Sessões 42–60)**
- **Semana 9**: F.7 sessões 1-3 (AgentMail inbox + Hunter verifier + Firecrawl enrichment) + **INÍCIO 14d warmup cobaia**
- **Semana 9-10**: F.8 sessões 1-4 (Phase Orchestrator UI + GitHub MCP wire pra skill PR deploy) [paralelo a warmup]
- **Semana 10-11**: F.7 sessões 4-6 (outreach inicial + monitoring bounce) + F.8 sessões 5-8 (phase orchestrator UI polish + e2e)
- **Semana 11-12**: F.9 sessões 1-7 (hardening final + GUARDRAILS consolidado + owner runbook + E2E walkthrough + handoff)
- **Marco mês 3**: 1 cobaia operacional 14d completos + Phase Orchestrator UI gerencia chapters + 22/22 PASS + owner roda sem Claude em loop.

### 4.3 Buffer e Riscos de Slippage
- **Buffer embutido**: range 70-90 sessões absorve ~30 sessões de bugs cruzados não previstos.
- **Slippage prováveis**:
  - F.5 ContextForge: +1 semana se OAuth wiring com FastMCP der bug.
  - F.6 Brain: +1 semana se memory bridge agentmemory gerar inconsistência cross-sessão.
  - F.7 cobaia: +7 dias se bounce >5% e precisar refazer warmup do zero.
- **Mitigação**: ao detectar slippage em F.5/F.6, congelar F.7/F.8 até estabilizar — NUNCA paralelizar instabilidade.

---

## 5. Tabela Resumo: Chapter / Declarado / Realista

| Chapter | Declarado | Realista | Wall-clock extra | Aceito? |
|---|---|---|---|---|
| F.1 | 1 | 1 | 0h | ✅ sem mudança |
| F.2 | 4 | 7 | +4h | ⚠️ +75% |
| F.4 | 6 | 10 | +6h | ⚠️ +67% |
| F.5 | 6 | 12 | +24h | 🔴 +100% (gateway + 3 MCPs custom subdimensionado) |
| F.6 | 5 | 9 | +8h | ⚠️ +80% |
| F.7 | 4 | 6 | +14d | 🔴 wall-clock dominante |
| F.8 | 4 | 8 | +4h | ⚠️ +100% (compounding) |
| F.9 | 3 | 7 | +8h | 🔴 +133% (final hardening sempre subestimado) |
| **TOTAL** | **33** | **60** (range 70-90) | **+72h + 14d** | **+82%** sobre declarado |

---

## 6. Recomendações Operacionais

### 6.1 Para o Owner
1. **Não anuncie data de entrega externa antes de F.5 fechar.** Gateway é o pivô — slippage aqui cascateia em todos chapters seguintes.
2. **Bloqueie 1 semana de calendário pra F.5 contínuo.** Context-switch dentro de F.5 (MCPs custom + OAuth + ContextForge) é caro — entra e sai do estado mental múltiplas vezes destrói produtividade.
3. **F.7 cobaia: começa antes de F.8 sessão 1.** Warmup é wall-clock paralelo, perda de 14 dias se sequenciar serial.
4. **F.9 walkthrough: grave em video.** Owner runbook + video = handoff defensivo se precisar pausar projeto por outro fogo.

### 6.2 Para o Phase Orchestrator (F.8 quando ativo)
1. Use este TIMELINE-REALISTIC.md como input baseline pra estimar fases futuras (não estimar do zero).
2. Detecte slippage early: se chapter > 1.5x sessões realísticas estimadas aqui, pause e re-baseline antes de continuar.
3. Bloqueie F.4 até F.6 ter Brain.decide() loop estável (>= 24h sem crash) — auto-skill loop alimentado por Brain instável gera skills lixo.

### 6.3 Para o Critic (Completeness Critic + Verdict lenses)
1. Rejeite chapters futuros com `estimated_sessions` ≤ declarado se tocarem código MADURO sem aplicar penalty +50%.
2. Rejeite chapters futuros sem `wall_clock_extra_hours` quando exigirem smoke prod ou observação cobaia.
3. Force `compounding_integration_penalty` em chapters com `dependencies_on_chapters` >= 3.

---

## 7. Persistência (Lock-in)

Ao mergear este artefato:
- `memory_save` type=workflow: `hermes phase F timeline re-baseline 60 sessões (range 70-90) + 72h wall-clock + 14d cobaia warmup, ordem serial F.1→F.2→F.5→F.6→F.4→F.7∥F.8→F.9`, concepts=[hermes, phase-f, timeline, calibração].
- `mark_chapter` "Phase F timeline re-baseline locked".
- `PLAN.md` Fase F: substituir qualquer linha "estimativa N sessões" por link pra este TIMELINE-REALISTIC.md.
- Git commit: `docs(plan): re-baseline Fase F timeline pós-verdicts (60 sessões, 3 meses)`.

---

**Status**: documento vivo. Re-baseline obrigatório após fechar cada chapter, comparando sessões reais gastas vs realista declarado aqui. Drift > 20% em chapter individual = update obrigatório deste arquivo + memory_save tipo lesson.
