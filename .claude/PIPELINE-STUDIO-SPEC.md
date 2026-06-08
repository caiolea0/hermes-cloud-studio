# PIPELINE STUDIO SPEC — Fase F.9 (Cobaia Live Ops + Pipeline Visual Builder)

> Versão: 1.0 (2026-06-08)
> Chapter destino: **F.9** (depende de F.1 inventário + F.5 MCP Gateway + F.6 Brain agent + F.7 cobaia data layer)
> Owner: Caio (solo) — dashboard PC :7777 substitui edição manual YAML/CLI
> Filosofia: **DSL JSON declarativo + UI visual** que compila pra workflow Hermes existente (loops/sync.py + channels/* + Brain orchestrator)

---

## 0. Contexto e Justificativa

### 0.1 Por que Pipeline Studio?

Hoje (pós F.1-F.8), pipeline de cobaia/produção é definido em **3 lugares fragmentados**:
1. **YAML hardcoded** em `cobaias/<nome>/pipeline.yaml` — owner edita à mão, sem validação
2. **Loops sync.py** decidem ordem de execução por código — owner não vê fluxo
3. **Brain agent (F.6)** decide próximo passo dinamicamente — owner perde visibilidade

Owner solo perde 30-45min/dia em:
- `vim cobaia.yaml` → reload daemon → torcer pra não quebrar
- `ssh vm cat /var/hermes/state.json | jq` pra ver onde pipeline parou
- Debugar SQL no SQLite quando cobaia trava em step intermediário
- Recriar pipeline da cobaia X copy-paste pra cobaia Y (zero reuso)

**F.9 entrega**: 1 tela `/studio/pipelines` onde owner desenha pipeline drag-drop, salva como template reusável, vê execução real-time com WS events do Brain, pausa/edita/clona step a step. Substitui edição manual + reduz tempo setup nova cobaia de **2h pra 5min**.

### 0.2 Decisão arquitetural: Composição vs Subclass

**Considerado**: Subclass `BasePipeline` em Python (cada cobaia = classe filha) — pattern OOP clássico.

**Escolhido**: **Composição via DSL JSON** declarativo.

Justificativa cabeçuda:
| Critério | Subclass Python | DSL JSON (escolhido) |
|---|---|---|
| Owner edita sem deploy | NÃO (precisa restart) | SIM (hot reload via WS) |
| Versionável git diff legível | Médio (Python diff verboso) | ALTO (JSON pretty diff limpo) |
| UI builder gera | Difícil (gerar Python AST) | Trivial (JSON serializa direto) |
| A/B testing skill F.4 | Fork de classe = boilerplate | Clonar JSON + tweak 1 step |
| Brain agent F.6 lê | Reflexão Python custosa | json.load() em 5ms |
| Validação schema | mypy lento + parcial | jsonschema mature + rápido |
| Plugin custom step | Importar módulo Python | Registrar handler no registry |
| Migração futura (workflow engine externo tipo n8n) | Reescrever tudo | Adapter JSON→engine |

DSL JSON também alinha com filosofia Claude Code (skills/agents YAML+frontmatter) e MCP (tools JSON Schema). Subclass fica reservado APENAS pra `StepHandler` base class — cada tipo de step (linkedin_invite, email_send, brain_decide, wait_for_reply) é subclass Python registrada no `STEP_REGISTRY` global. **Pipeline = composição de handlers via JSON**.

---

## 1. DSL JSON — Schema Completo

### 1.1 Top-level Pipeline Document

```jsonc
{
  "$schema": "https://hermes.local/schema/pipeline-v1.json",
  "id": "cob-cuiaba-construtoras-v3",          // slug único, lowercase-kebab
  "name": "Cuiabá Construtoras — Fluxo Multi-canal v3",
  "version": "3.0.0",                            // semver, bump em mudança breaking
  "status": "active",                            // draft | active | paused | archived
  "owner": "cleao@hermes.local",
  "created_at": "2026-06-08T14:32:11Z",
  "updated_at": "2026-06-08T19:45:02Z",

  // Vínculo cobaia (opcional — pipeline pode ser template puro)
  "cobaia_id": "cob-cuiaba-construtoras",       // FK pra cobaias.id ou null
  "template_id": null,                           // se clonado, FK pro template origem

  // Defaults herdados por todos steps (overridable por step)
  "defaults": {
    "retry_policy": {
      "max_attempts": 3,
      "backoff_seconds": [60, 300, 900],         // exponencial
      "retry_on": ["network_error", "rate_limit", "transient_5xx"]
    },
    "timeout_seconds": 120,
    "owner_alert_on_failure": true,
    "log_level": "info"
  },

  // Triggers — quando pipeline inicia
  "triggers": [
    {
      "type": "manual",                          // owner aperta botão "Start"
      "label": "Iniciar manualmente"
    },
    {
      "type": "cron",
      "schedule": "0 9 * * 1-5",                 // 9h segunda-sexta
      "timezone": "America/Cuiaba"
    },
    {
      "type": "event",
      "event_name": "prospect.added_to_segment",
      "filter": { "segment_id": "cuiaba-construtoras-A" }
    }
  ],

  // Variáveis globais — referenciadas via ${vars.<name>} nos steps
  "vars": {
    "max_prospects_per_run": 20,
    "linkedin_account": "caio_primary",
    "skill_proposal_template": "construtora-proposta-v2",
    "owner_review_required": true
  },

  // Steps — DAG declarativo (não array linear; suporta paralelo via "after")
  "steps": [ /* ver seção 1.2 */ ],

  // Métricas e SLOs do pipeline inteiro
  "slo": {
    "max_duration_seconds": 86400,               // 24h fim-a-fim
    "min_success_rate_7d": 0.65,                 // se cair abaixo, alerta owner
    "max_cost_per_run_brl": 12.00                // limite gasto (Apollo/Firecrawl/etc)
  },

  // Hooks de observabilidade
  "observability": {
    "emit_ws_events": true,                      // broadcast cada step start/end
    "sentry_release_tag": "pipeline-v3.0.0",
    "audit_log": true                            // grava em audit_log tabela
  }
}
```

### 1.2 Step Definition

```jsonc
{
  "id": "step-linkedin-invite",                  // único dentro do pipeline
  "label": "Enviar convite LinkedIn",            // UI display
  "type": "linkedin.send_invite",                // FK pro STEP_REGISTRY
  "after": ["step-qualify-icp"],                 // dependências (DAG); [] = root
  "enabled": true,                                // false = skip mas mantém no fluxo

  // Inputs — referencia outputs de steps anteriores ou vars
  "inputs": {
    "prospect_id": "${steps.step-qualify-icp.output.prospect_id}",
    "message_template": "${vars.linkedin_invite_template}",
    "account": "${vars.linkedin_account}",
    "personalization": {
      "use_brain": true,                          // chama F.6 Brain pra gerar mensagem
      "brain_prompt_id": "linkedin-invite-cuiaba-v2"
    }
  },

  // Condições — step só executa se TODAS verdadeiras
  "conditions": [
    {
      "expr": "${steps.step-qualify-icp.output.score} >= 70"
    },
    {
      "expr": "${context.prospect.linkedin_url} != null"
    }
  ],

  // Output schema — declara o que step produz (validado em runtime)
  "output_schema": {
    "type": "object",
    "properties": {
      "invite_id": { "type": "string" },
      "sent_at": { "type": "string", "format": "date-time" },
      "status": { "type": "string", "enum": ["sent", "queued", "blocked"] }
    },
    "required": ["invite_id", "status"]
  },

  // Política de retry específica (sobrepõe defaults)
  "retry_policy": {
    "max_attempts": 2,
    "backoff_seconds": [300, 1800]
  },

  // Aprovação humana (gate manual antes de executar)
  "requires_approval": {
    "enabled": false,
    "approver_role": "owner",
    "auto_approve_if_score_gte": 85
  },

  // Branches — próximos steps condicionais (alternativa a "after" reverso)
  "on_success": ["step-wait-acceptance"],
  "on_failure": ["step-log-failure", "step-mark-prospect-blocked"],
  "on_timeout": ["step-pause-pipeline"],

  // Metadados UI
  "ui": {
    "position": { "x": 320, "y": 180 },          // coord canvas drag-drop
    "color": "#0a66c2",                          // override cor do tipo
    "icon": "linkedin",
    "notes": "Cuidado limite 15 convites/semana — verificar limiter antes"
  }
}
```

### 1.3 Step Types (STEP_REGISTRY — MVP)

| type | Categoria | Handler Python | Inputs principais | Outputs |
|---|---|---|---|---|
| `prospect.qualify_icp` | discovery | `handlers/qualify.py` | segment_id, criteria | prospect_id, score, fit_reasons |
| `prospect.enrich` | discovery | `handlers/enrich.py` | prospect_id, providers[] | enriched_data, sources |
| `linkedin.send_invite` | outreach | `handlers/li_invite.py` | prospect_id, template | invite_id, status |
| `linkedin.send_message` | outreach | `handlers/li_message.py` | thread_id, body | message_id, sent_at |
| `linkedin.wait_for_reply` | wait | `handlers/wait_reply.py` | thread_id, timeout_h | reply_text or null |
| `email.send` | outreach | `handlers/email_send.py` | to, template, vars | message_id, status |
| `email.wait_for_reply` | wait | `handlers/wait_email.py` | thread_id, timeout_h | reply_text or null |
| `brain.decide` | logic | `handlers/brain.py` | context, prompt_id | decision, next_step_id, confidence |
| `brain.compose_message` | logic | `handlers/brain_compose.py` | prospect_id, channel, intent | message_body, tokens_used |
| `human.approve` | gate | `handlers/approval.py` | summary, options[] | approved, approver, notes |
| `wait.timer` | wait | `handlers/wait_timer.py` | duration_seconds | resumed_at |
| `wait.cron` | wait | `handlers/wait_cron.py` | next_cron_expr | resumed_at |
| `cobaia.update_status` | state | `handlers/cobaia.py` | cobaia_id, status, field_patches | updated_at |
| `proposal.send` | outreach | `handlers/proposal.py` | prospect_id, template_id | proposal_id, sent_at |
| `mcp.invoke` | integration | `handlers/mcp.py` | server, tool, args | tool_result |
| `condition.branch` | logic | `handlers/branch.py` | expr, true_step, false_step | branch_taken |
| `loop.foreach` | logic | `handlers/foreach.py` | items_expr, sub_steps[] | results[] |
| `notify.owner` | side-effect | `handlers/notify.py` | channel, message, priority | delivered |

**Extensibilidade**: novo step type = nova subclass `StepHandler` + entry em `STEP_REGISTRY` + JSON Schema do input/output. Hot reload via F.4 skill loop.

### 1.4 Validation Rules (jsonschema + custom)

- `id` único globalmente (slug pattern `^[a-z0-9-]+$`, max 64 chars)
- `version` semver válido
- DAG sem ciclos (toposort antes de salvar; rejeita se ciclo detectado)
- Toda `${...}` reference resolve pra step existente OU var existente
- Toda dependência em `after[]` referencia step existente
- `cron` schedule válido (crontab parser)
- `timeout_seconds` <= `slo.max_duration_seconds`
- Steps `requires_approval.enabled=true` NÃO podem estar em `on_failure` (deadlock risk)
- Pipeline com `status=active` precisa ter pelo menos 1 trigger
- Custom: cada step type valida seus próprios inputs via JSON Schema registrado no handler

---

## 2. Curated Templates (MVP — 5 fluxos prontos)

Templates seedados em `cobaias/_templates/*.json` no primeiro boot do F.9. Owner clona + adapta. Cada um é DSL JSON completo, executável.

### 2.1 Template 1: `linkedin-cold-outreach-v1`

**Caso**: descoberta + qualificação + convite LinkedIn + follow-up 1 toque
**Duração típica**: 7 dias
**Custo médio**: R$ 0,80/prospect (só Brain tokens)

**Steps** (resumo executivo — JSON completo em `cobaias/_templates/linkedin-cold-outreach-v1.json`):

```
1. prospect.qualify_icp     (segment: vars.target_segment)
       │
       ▼
2. condition.branch          (score >= 70?)
       │ true                       │ false
       ▼                             ▼
3. brain.compose_message    9. cobaia.update_status (skipped, low_score)
   (channel=linkedin, intent=cold_invite)
       │
       ▼
4. human.approve            (auto_approve_if_score_gte: 85)
       │
       ▼
5. linkedin.send_invite     (retry max 2, backoff 5min/30min)
       │
       ▼
6. linkedin.wait_for_reply  (timeout_h: 168)  ← 7 dias
       │ reply received              │ timeout
       ▼                              ▼
7. brain.decide             8. notify.owner (no reply 7d, mark cold)
   (next: send_proposal | nurture | drop)
       │
       ▼
   [branches conforme decisão Brain]
```

### 2.2 Template 2: `email-warmup-14d-v1`

**Caso**: warmup novo domínio email antes de campanha real
**Duração**: 14 dias fixos
**Custo**: R$ 0,20/dia (Hunter verifier + AgentMail send)

```
TRIGGER: cron @daily 8h America/Cuiaba

1. cobaia.update_status     (mark: warmup_day_N)
       │
       ▼
2. condition.branch          (day < 14?)
       │ true                       │ false (day == 14)
       ▼                             ▼
3. email.send                15. notify.owner (warmup complete, ready prod)
   (volume escalada: 2/3/5/8/12/18/25/35/50/70/90/110/130/150)
       │                                    │
       ▼                                    ▼
4. wait.timer (4h)                  16. cobaia.update_status (status=ready)
       │
       ▼
5. email.wait_for_reply     (cobaia peers respondem random)
       │
       ▼
6. brain.decide             (avalia warmup health: bounce rate, reply rate)
       │
       ▼
7. notify.owner             (daily digest: enviados, bounces, score atual)
```

### 2.3 Template 3: `multi-channel-deal-cycle-v1`

**Caso**: pipeline B2B completo discovery→proposta→fechamento
**Duração**: 30-90 dias
**Custo médio**: R$ 8-15/deal

```
1. prospect.qualify_icp
       │
       ▼
2. prospect.enrich          (Firecrawl site + Hunter email + Apollo signals)
       │
       ▼
3. brain.decide             (escolhe canal primário: LinkedIn | Email | WhatsApp)
       │
       ├─ LinkedIn ───────────┬─ Email ─────────────┬─ WhatsApp ──────────┐
       ▼                       ▼                      ▼                     ▼
4a. linkedin.send_invite   4b. email.send         4c. whatsapp.send_template
       │                       │                      │
       ▼                       ▼                      ▼
5. linkedin.wait_for_reply  5. email.wait_for_reply  5. whatsapp.wait_reply
       │                       │                      │
       └──────────┬────────────┴──────────────────────┘
                  ▼
6. brain.decide             (qualified lead? continuar | nurture | drop)
                  │
                  ▼
7. proposal.send            (skill_proposals.create + WhatsApp/email envio)
                  │
                  ▼
8. human.approve            (owner revisa proposta antes envio final)
                  │
                  ▼
9. wait.timer (72h)         (janela resposta)
                  │
                  ▼
10. brain.decide            (won | lost | negotiate | reschedule)
                  │
                  ▼
11. cobaia.update_status    (pipeline_stage final + log decision)
```

### 2.4 Template 4: `skill-ab-test-v1` (orquestração F.4)

**Caso**: testar 2 variantes de skill em paralelo, Brain decide vencedora
**Duração**: 48h ou N=30 execuções
**Custo**: 0 (só compute interno)

```
TRIGGER: event = "skill.variant_proposed"

1. condition.branch     (variants_count == 2?)
       │
       ▼
2. loop.foreach          (items: ["variant_A", "variant_B"])
       │
       ├─ executa em paralelo ─┐
       ▼                       ▼
3a. brain.decide          3b. brain.decide
    (run variant A)           (run variant B)
       │                       │
       ▼                       ▼
4a. cobaia.update_status  4b. cobaia.update_status
    (log result A)            (log result B)
       │                       │
       └──────────┬────────────┘
                  ▼
5. wait.timer (48h)  OR  condition (N>=30)
                  │
                  ▼
6. brain.decide          (compara métricas, escolhe vencedora)
                  │
                  ▼
7. mcp.invoke            (server=github, tool=create_pr — auto-promover vencedora)
                  │
                  ▼
8. human.approve         (owner aprova PR)
                  │
                  ▼
9. notify.owner          (vencedora promovida, perdedora archived)
```

### 2.5 Template 5: `cobaia-onboarding-v1`

**Caso**: setup completo nova cobaia (DB + warmup + primeiro pipeline)
**Duração**: 14-21 dias
**Custo**: R$ 0,50 setup + R$ 0,20/dia warmup

```
TRIGGER: manual (owner cria nova cobaia via UI)

1. cobaia.update_status     (status=initializing)
       │
       ▼
2. mcp.invoke               (postgres: create cobaia schema + seed config)
       │
       ▼
3. mcp.invoke               (github: scaffold cobaias/<nome>/ folder + base files)
       │
       ▼
4. condition.branch         (email_required?)
       │ true                       │ false
       ▼                             ▼
5. [trigger template:         8. cobaia.update_status (status=ready)
    email-warmup-14d-v1]
       │
       ▼ (após 14d)
6. notify.owner             (warmup OK, pronto pra primeiro pipeline)
       │
       ▼
7. human.approve            (owner escolhe template inicial: cold-outreach | multi-channel)
       │
       ▼
8. cobaia.update_status     (status=ready, primary_pipeline_id=<chosen>)
```

---

## 3. Wireframes ASCII — UI Pipeline Studio

### 3.1 Tela `/studio/pipelines` — Lista de Pipelines

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ HERMES COMMAND CENTER › Pipeline Studio                    [+ Novo Pipeline] │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Filtros: [Status ▼] [Cobaia ▼] [Template ▼] [Owner: cleao ✓]   🔍 Buscar...│
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ ● cuiaba-construtoras-v3              ACTIVE   v3.0.0    Updated 2h    │  │
│ │   Cuiabá Construtoras — Multi-canal v3                                 │  │
│ │   12 steps · 4 running · 89 completed · 3 failed  ▓▓▓▓▓▓▓░░░ 72%      │  │
│ │   [▶ Run] [⏸ Pause] [📋 Clone] [✏ Edit] [📊 Stats] [🗂 Archive]      │  │
│ ├────────────────────────────────────────────────────────────────────────┤  │
│ │ ● cob-cuiaba-email-warmup            ACTIVE   v1.2.0    Day 11/14     │  │
│ │   Email Warmup — Domínio Hermes2                                       │  │
│ │   8 steps · 1 running · 0 failed  ▓▓▓▓▓▓▓▓░░ 78%                      │  │
│ │   [⏸ Pause] [📋 Clone] [✏ Edit] [📊 Stats]                            │  │
│ ├────────────────────────────────────────────────────────────────────────┤  │
│ │ ○ skill-ab-test-linkedin-inv         DRAFT    v0.1.0    Never ran      │  │
│ │   A/B test variantes invite LinkedIn Cuiabá                            │  │
│ │   9 steps · 0 running                                                  │  │
│ │   [▶ Activate] [✏ Edit] [📋 Clone] [🗑 Delete]                        │  │
│ ├────────────────────────────────────────────────────────────────────────┤  │
│ │ ⏸ legacy-email-blast-v0              PAUSED   v0.5.0    Last ran 7d   │  │
│ │   Email Blast Cuiabá (deprecated — use multi-channel-deal-cycle)       │  │
│ │   [▶ Resume] [🗂 Archive] [📊 Stats]                                  │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ TEMPLATES (clonar pra começar rápido):                                       │
│ [LinkedIn Cold Outreach] [Email Warmup 14d] [Multi-Channel Deal Cycle]      │
│ [Skill A/B Test] [Cobaia Onboarding]                                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Tela `/studio/pipelines/:id/edit` — Visual Builder

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Pipeline Studio › cuiaba-construtoras-v3 (Edit)        [Save] [Validate] [▶]│
├──────────┬───────────────────────────────────────────────────────┬──────────┤
│ STEPS    │                    CANVAS (DAG drag-drop)            │ INSPECTOR│
│          │                                                       │          │
│ Search.. │  ┌───────────────┐                                    │ Step:    │
│          │  │ qualify_icp   │◄─── start                          │ linkedin │
│ Outreach │  │ score>=70?    │                                    │ .send_   │
│  ├ LI inv│  └───┬───────┬───┘                                    │ invite   │
│  ├ LI msg│      │ true  │ false                                  │          │
│  ├ Email │      ▼       ▼                                        │ Inputs:  │
│  └ WApp  │  ┌───────┐ ┌──────┐                                   │ prospect │
│          │  │ brain │ │ skip │                                   │ _id:     │
│ Logic    │  │ comp  │ └──────┘                                   │ ${...}   │
│  ├ Brain │  └───┬───┘                                            │          │
│  ├ Branch│      ▼                                                │ Template:│
│  ├ Foreach  ┌───────┐                                            │ [dropdwn]│
│  └ Approve  │ human │  ← auto if score>=85                      │          │
│          │  │ approve                                             │ Retry:   │
│ Waits    │  └───┬───┘                                            │ max: 2   │
│  ├ Timer │      ▼                                                │ backoff: │
│  ├ Cron  │  ┌───────────┐                                        │ 5m,30m   │
│  └ Reply │  │ LI invite │ ◄── SELECIONADO (highlight ciano)     │          │
│          │  └───┬───┬───┘                                        │ Approval:│
│ State    │      │ ok│ fail                                       │ [ ] req  │
│  ├ Update│      ▼   ▼                                            │          │
│  ├ Notify│  ┌────┐ ┌────────┐                                    │ Notes:   │
│          │  │wait│ │ notify │                                    │ Limite   │
│ MCP      │  │repl│ │ owner  │                                    │ 15/sem   │
│  ├ GitHub│  └─┬──┘ └────────┘                                    │          │
│  ├ Sentry│    ▼                                                  │ [Delete] │
│  └ Custom│  ┌────────┐                                            │          │
│          │  │ brain  │                                            │          │
│          │  │ decide │                                            │          │
│          │  └────────┘                                            │          │
│          │                                                       │          │
│          │  [Auto-layout] [Fit] [Zoom: 100%]    Steps: 12        │          │
└──────────┴───────────────────────────────────────────────────────┴──────────┘

Footer: Validation: ✓ DAG OK ✓ Refs OK ⚠ 1 warning: step "wait_reply" timeout > SLO
        Hot reload: ON (mudanças aplicadas live na próxima execução)
        WS connected: ws://localhost:7777/ws/pipelines  ● online
```

### 3.3 Tela `/studio/pipelines/:id/run/:run_id` — Live Execution

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Pipeline Run › cuiaba-construtoras-v3 › run_2026-06-08_14:32         [⏸ ⏹]│
├──────────────────────────────────────────────────────────────────────────────┤
│ Status: RUNNING        Started: 14:32:11    Duration: 02h 13m   Step 6/12   │
│ Prospect: João Silva (Construtora Aurora MT)   Score: 87   Brain conf: 0.91│
│                                                                              │
│ ┌──── DAG (live) ─────────────┐  ┌──── TIMELINE (WS events) ──────────────┐│
│ │                              │  │ 14:32:11  ▶ run started               ││
│ │  ✓ qualify_icp   (1.2s)     │  │ 14:32:12  ✓ qualify_icp done score=87 ││
│ │       │                      │  │ 14:32:13  → brain.compose_message     ││
│ │  ✓ brain compose (3.1s)     │  │ 14:32:16  ✓ message ready 247 tokens  ││
│ │       │                      │  │ 14:32:16  ⏸ awaiting approval owner   ││
│ │  ✓ human approve (auto)     │  │ 14:32:17  ✓ auto-approved (score>=85) ││
│ │       │                      │  │ 14:32:18  → linkedin.send_invite       ││
│ │  ✓ LI invite sent           │  │ 14:32:24  ✓ invite_id=urn:li:invt:9k.. ││
│ │       │                      │  │ 14:32:25  → linkedin.wait_for_reply    ││
│ │  ● wait_reply (RUNNING)     │  │           timeout 168h                  ││
│ │       │ 2h 13m elapsed      │  │ 16:45:18  ⚡ reply received!           ││
│ │       ▼                      │  │ 16:45:19  → brain.decide               ││
│ │  ○ brain decide              │  │ 16:45:23  ⏳ (in progress)             ││
│ │       │                      │  │                                        ││
│ │  ○ proposal send             │  │                                        ││
│ │       │                      │  │                                        ││
│ │  ○ ... 5 mais                │  │                                        ││
│ └──────────────────────────────┘  └────────────────────────────────────────┘│
│                                                                              │
│ ┌──── CURRENT STEP DETAIL ─────────────────────────────────────────────────┐│
│ │ Step: brain.decide  (in progress, 4s elapsed)                            ││
│ │ Inputs:                                                                  ││
│ │   context.reply_text: "Oi Caio, interessante! Pode mandar proposta?"    ││
│ │   context.prospect.score: 87                                             ││
│ │   prompt_id: "post-reply-decision-v2"                                    ││
│ │                                                                          ││
│ │ Brain reasoning (streaming):                                             ││
│ │ > Reply expressa interesse explícito ("pode mandar proposta")           ││
│ │ > Score 87 (alto), histórico 0 objeções                                 ││
│ │ > Decisão preliminar: send_proposal com template construtora-v2         ││
│ │ > Confiança: 0.94 (alta)                                                ││
│ │                                                                          ││
│ │ [Force step] [Skip step] [Pause pipeline] [Edit & rerun]                ││
│ └──────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│ Run cost: R$ 0.32 (Brain: 1247 tok, MCP: 3 calls)   SLO: 24h ✓ (10% used) │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 3.4 Tela `/studio/pipelines/:id/stats` — Métricas Agregadas

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Pipeline Stats › cuiaba-construtoras-v3                  [7d ▼] [Export CSV]│
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌────── HEALTH ────────┐  ┌────── THROUGHPUT ──────┐  ┌──── COST ──────┐  │
│ │ Success rate: 72%    │  │ Runs: 89                │  │ Total: R$ 47   │  │
│ │ SLO target: 65%  ✓   │  │ Completed: 64           │  │ Avg/run: R$ 0.53│ │
│ │ Last fail: 4h ago    │  │ Failed: 18              │  │ Budget: R$ 12  │  │
│ │ MTTR: 23min          │  │ Running: 7              │  │ Within SLO ✓   │  │
│ └──────────────────────┘  └─────────────────────────┘  └────────────────┘  │
│                                                                              │
│ ┌──── STEP FUNNEL ─────────────────────────────────────────────────────────┐│
│ │ qualify_icp       ████████████████████████████  100% (89/89)            ││
│ │ brain_compose     ███████████████████████░░░░░   82% (73/89)            ││
│ │ human_approve     ██████████████████████░░░░░░   78% (70/89)            ││
│ │ LI_invite         ██████████████████████░░░░░░   78% (70/89)            ││
│ │ wait_reply        ███████████████░░░░░░░░░░░░░   54% (48/89)            ││
│ │ brain_decide      ██████████████░░░░░░░░░░░░░░   51% (45/89)            ││
│ │ proposal_send     ████████████░░░░░░░░░░░░░░░░   42% (37/89)            ││
│ │ deal_closed       ██████░░░░░░░░░░░░░░░░░░░░░░   18% (16/89)  ⭐ FINAL  ││
│ └──────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│ ┌──── BOTTLENECKS ─────────────────────────────────────────────────────────┐│
│ │ Step               Avg duration   P95        Failures    Action          ││
│ │ wait_reply         48h            120h       12 timeout  [Tune timeout]  ││
│ │ brain_compose      4.2s           12s        3           [Optimize]      ││
│ │ LI_invite          6.1s           18s        2 blocked   [Check limiter] ││
│ └──────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│ ┌──── RECENT FAILURES (last 7d) ───────────────────────────────────────────┐│
│ │ run_id                step           error                       Time    ││
│ │ run_2026-06-08_09:14  LI_invite      rate_limit_hit              5h ago  ││
│ │ run_2026-06-07_16:22  brain_compose  timeout 12s exceeded         18h    ││
│ │ run_2026-06-06_11:05  wait_reply     prospect blocked sender      2d ago ││
│ │                                                              [Show all 18]││
│ └──────────────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────────────┘
```

### 3.5 Tela `/studio/pipelines/new` — Wizard Criação

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Novo Pipeline                                              Step 1 of 3       │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ 1. ESCOLHA UM PONTO DE PARTIDA                                              │
│                                                                              │
│ ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐  │
│ │  🆕 Em branco        │  │  📋 Clonar pipeline │  │  📦 Usar template   │  │
│ │                     │  │      existente      │  │                     │  │
│ │  Canvas vazio,      │  │                     │  │  5 templates curados│  │
│ │  monte do zero      │  │  Cópia editável de  │  │  prontos pra uso   │  │
│ │                     │  │  pipeline atual     │  │                     │  │
│ │  [Selecionar]       │  │  [Escolher origem ▼]│  │  [Ver templates]    │  │
│ └─────────────────────┘  └─────────────────────┘  └─────────────────────┘  │
│                                                                              │
│ TEMPLATES DISPONÍVEIS:                                                       │
│ ┌──────────────────────────────────────────────────────────────────────────┐│
│ │ ○ linkedin-cold-outreach-v1                                              ││
│ │   Descoberta + qualificação + convite + follow-up 7d                     ││
│ │   12 steps · ~R$ 0.80/prospect · 7d duração típica                       ││
│ │                                                                          ││
│ │ ○ email-warmup-14d-v1                                                    ││
│ │   Warmup escalado novo domínio 14 dias                                   ││
│ │   8 steps · R$ 2.80/14d · automático                                     ││
│ │                                                                          ││
│ │ ● multi-channel-deal-cycle-v1   ← SELECIONADO                           ││
│ │   B2B completo: discovery→proposta→fechamento multi-canal                ││
│ │   18 steps · R$ 8-15/deal · 30-90d                                       ││
│ │                                                                          ││
│ │ ○ skill-ab-test-v1                                                       ││
│ │   A/B testing variantes skill F.4 (auto-promove vencedora)               ││
│ │   9 steps · R$ 0 · 48h ou N=30                                           ││
│ │                                                                          ││
│ │ ○ cobaia-onboarding-v1                                                   ││
│ │   Setup completo nova cobaia (DB + warmup + 1º pipeline)                 ││
│ │   8 steps · R$ 3.30 · 14-21d                                             ││
│ └──────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│                                              [Cancelar]  [Continuar →]      │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Defaults e Convenções

### 4.1 Defaults globais (aplicados se step omite)

```jsonc
{
  "retry_policy": {
    "max_attempts": 3,
    "backoff_seconds": [60, 300, 900],
    "retry_on": ["network_error", "rate_limit", "transient_5xx"]
  },
  "timeout_seconds": 120,
  "owner_alert_on_failure": true,
  "log_level": "info",
  "requires_approval": { "enabled": false },
  "observability": {
    "emit_ws_events": true,
    "audit_log": true
  }
}
```

### 4.2 Naming conventions

- Pipeline `id`: `<scope>-<segment>-<version>` (ex: `cob-cuiaba-construtoras-v3`)
- Step `id`: `step-<verb>-<noun>` (ex: `step-send-invite`, `step-qualify-icp`)
- Variable refs: `${vars.foo}` (top-level) ou `${steps.<id>.output.field}` (step output)
- Context refs: `${context.prospect.field}` (runtime context injetado pelo engine)
- Template files: `cobaias/_templates/<id>.json` (read-only seeds)
- User pipelines: `cobaias/<cobaia_id>/pipelines/<id>.json` (editáveis)

### 4.3 Versionamento

- Pipeline editado salva nova versão (semver):
  - **PATCH** (3.0.1): mudança UI/notes/labels, sem efeito execução
  - **MINOR** (3.1.0): step adicionado/removido, nova var, novo branch
  - **MAJOR** (4.0.0): mudança breaking (DAG reestruturada, step removido em uso)
- Versões antigas mantidas em `pipelines_history` table; runs em flight terminam na versão que iniciaram
- Diff visual disponível em `/studio/pipelines/:id/history`

### 4.4 Hot reload semântica

- Save de pipeline ACTIVE não aborta runs em execução
- Próxima run pega versão nova
- Owner pode forçar "Restart all runs com nova versão" (botão explícito, confirma 2x)
- Runs ativas em step `wait.*` recebem versão nova na hora de retomar (resume context)

---

## 5. MVP vs F.9.5 (Roadmap)

### 5.1 MVP F.9 (1ª entrega — 4-5 sessões)

**Inclui**:
- DSL JSON schema completo (seções 1.1-1.4 deste doc)
- Engine executor Python (`core/pipeline_engine.py`) com 18 step types do registry
- 5 templates seedados (seção 2)
- 4 telas UI:
  - `/studio/pipelines` (lista)
  - `/studio/pipelines/:id/edit` (visual builder — drag-drop básico, sem auto-layout)
  - `/studio/pipelines/:id/run/:run_id` (live execution + WS timeline)
  - `/studio/pipelines/new` (wizard 3 steps)
- APIs novas:
  - `GET /api/pipelines` — lista paginada com filtros
  - `GET /api/pipelines/:id` — detalhe completo
  - `POST /api/pipelines` — cria novo
  - `PUT /api/pipelines/:id` — atualiza (versionado)
  - `DELETE /api/pipelines/:id` — soft delete (move para archived)
  - `POST /api/pipelines/:id/validate` — valida sem salvar
  - `POST /api/pipelines/:id/run` — inicia execução manual
  - `POST /api/pipelines/:id/clone` — clona pipeline ou template
  - `GET /api/pipelines/:id/runs` — histórico runs
  - `GET /api/pipelines/:id/runs/:run_id` — detalhe run
  - `POST /api/pipelines/:id/runs/:run_id/pause` — pausa run
  - `POST /api/pipelines/:id/runs/:run_id/resume` — retoma
  - `POST /api/pipelines/:id/runs/:run_id/abort` — aborta
  - `POST /api/pipelines/:id/runs/:run_id/steps/:step_id/force` — força avanço step
  - `WS /ws/pipelines/:run_id` — eventos live (step_start, step_end, log, decision)
- DB migrations:
  - `pipelines` (id, name, version, status, dsl_json, cobaia_id, created_at, updated_at, owner)
  - `pipelines_history` (pipeline_id, version, dsl_json, created_at)
  - `pipeline_runs` (id, pipeline_id, pipeline_version, started_at, ended_at, status, cost_brl, trigger_type)
  - `pipeline_run_steps` (run_id, step_id, status, started_at, ended_at, inputs_json, outputs_json, error)
- Persistência:
  - Hot reload via filewatcher `cobaias/*/pipelines/*.json` (owner pode editar arquivo direto se preferir)
  - WS broadcast `pipeline.*` events (start, end, step_start, step_end, decision, error)
  - Audit log toda mudança DSL (quem, quando, diff)
- Guardrails:
  - DAG cycle detector ANTES de save
  - Schema validation jsonschema + custom rules
  - Cost guard: pipeline com `slo.max_cost_per_run_brl` excedido pausa auto e alerta owner
  - SLO guard: pipeline com `min_success_rate_7d` abaixo do target gera alerta dashboard

**NÃO inclui MVP** (fica pra F.9.5):
- Auto-layout do DAG (MVP usa coords manuais salvas; auto-layout = bonus)
- Branching condicional complexo (MVP suporta apenas branch true/false simples)
- Loops aninhados (MVP `loop.foreach` é single-level)
- Pipeline-as-trigger (pipeline A dispara pipeline B nativamente — MVP usa event bus genérico)
- Simulação dry-run sem efeitos colaterais (MVP só execução real)
- Diff visual entre versões (MVP mostra JSON diff bruto)
- Bulk operations (clonar 10 pipelines de uma vez)
- Marketplace de templates compartilhados entre owners
- Export/import pipeline como YAML (MVP só JSON)
- Mobile/responsive (MVP é desktop-first, owner usa monitor 27")

### 5.2 F.9.5 Roadmap (próximas 2-3 sessões pós-MVP)

**Auto-layout DAG**:
- Algoritmo dagre.js no frontend
- Botão "Auto-organize" reposiciona steps preservando ordem
- Save coords resultantes pro DSL

**Branching avançado**:
- `condition.switch` (N branches por expressão)
- `condition.race` (primeiro step a completar vence, outros abortam)
- `condition.parallel_join` (espera todos paralelos antes próximo)

**Dry-run mode**:
- Execução simula side effects (LinkedIn/Email/MCP), só logs decisões
- Útil pra debug pipeline antes ativar
- Reusa engine com flag `dry_run=True` propagada pra handlers

**Diff visual versões**:
- Side-by-side DSL com syntax highlight diff
- Lista mudanças semânticas humanizadas ("Step 'X' removido", "Timeout 'wait_reply' aumentou 24h→168h")

**Pipeline-as-trigger**:
- Step type novo `pipeline.trigger` invoca outro pipeline com inputs
- Permite composição (pipeline pai chama pipeline filho reusável)

**Template marketplace**:
- Compartilhar templates entre owners (multi-tenant futuro)
- Rating + fork stats
- Owner publica template com `is_public=true`

**Mobile responsive**:
- Lista + live execution funcionam no mobile (owner check status no celular)
- Edit fica desktop-only (canvas drag-drop não funciona bem touch)

---

## 6. Integração com Chapters Existentes

### 6.1 Dependências (input)

- **F.1 (FRONTEND-GAP.md)**: identifica que `/api/pipelines/*` é endpoint novo (não existe hoje). Top 10 fantasmas N/A pra F.9 (são endpoints completamente novos).
- **F.5 (MCP Gateway IBM ContextForge)**: handler `mcp.invoke` rota TODOS os MCP calls pelo gateway, nunca direto. Gateway aplica auth+rate-limit+audit.
- **F.6 (Brain agent)**: handler `brain.decide` e `brain.compose_message` invocam Brain via API interna `POST /api/brain/decide`. Brain devolve decision JSON estruturada conforme `output_schema` do step.
- **F.7 (Cobaia data layer)**: pipelines vinculam `cobaia_id` FK; handler `cobaia.update_status` escreve via API `PATCH /api/cobaias/:id`.
- **F.4 (Auto-skill loop)**: template `skill-ab-test-v1` orquestra ciclo de promoção skill via pipeline (em vez de hardcoded em `loops/skill_evaluator.py`).

### 6.2 Saídas (output)

- **Reduz dívida F.1**: pipelines passam a consumir `/api/daemon/state`, `/api/daemon/timeline`, `/api/daemon/decisions` via WS broadcasts do engine — fecha 3 dos 11 endpoints fantasmas.
- **Habilita F.7 Live Ops**: cobaia ganha aba "Pipelines" no `/cobaias/:id` mostrando todos pipelines ativos + histórico runs.
- **Habilita F.4 evolução**: skills A/B testing deixa de exigir restart daemon — pipeline `skill-ab-test-v1` roda em paralelo às operações normais.

### 6.3 Não-objetivos (fora F.9 — futuro F.10+)

- Editor visual de skills (continua YAML em F.4)
- Editor visual de prompts Brain (continua em arquivos `.md` em F.6)
- Multi-tenant / multi-owner (Hermes é solo-owner)
- Engine workflow externo (n8n/Temporal) — DSL JSON foi escolhido pra ser portável FUTURAMENTE, mas adapter fica fora F.9

---

## 7. Decisões em Aberto (pra owner ratificar antes F.9 start)

1. **Step `human.approve` deve bloquear pipeline ou paralelizar?**
   - Opção A: bloqueia (default; pipeline pausa até owner clicar)
   - Opção B: paraleliza (continua execução; owner aprova async, se rejeitar reverte)
   - **Recomendação**: A (mais previsível pra owner solo; B vira race condition se owner demora)

2. **`brain.decide` reasoning streaming na UI — quanto detalhe expor?**
   - Opção A: só decisão final + confiança
   - Opção B: chain-of-thought completo streaming (como Claude Code mostra)
   - **Recomendação**: B (owner aprende padrão Brain, ganha confiança pra automatizar mais)

3. **Pipeline pausado conta SLO duration ou pausa o cronômetro?**
   - Opção A: conta (SLO 24h = 24h wall-clock independente de pausa)
   - Opção B: pausa cronômetro (SLO 24h = 24h de execução ativa)
   - **Recomendação**: B (pausa intencional não deve estourar SLO; alinha com expectativa owner)

4. **Erro fatal em step sem `on_failure` definido — comportamento?**
   - Opção A: aborta pipeline inteira
   - Opção B: marca step failed, continua pipeline (steps subsequentes que dependem dele auto-skip)
   - **Recomendação**: A (default conservador; owner explicita `on_failure` quando quer continuar)

5. **Pipeline executor — single-process asyncio ou worker pool?**
   - Opção A: asyncio single-process (alinha com `loops/sync.py` atual; simples)
   - Opção B: worker pool (Celery/RQ; permite distribuir entre PC e VM)
   - **Recomendação**: A no MVP (Hermes solo, throughput baixo; pool fica F.10 se necessário)

---

## 8. Critérios de Aceite F.9 (DoD)

Pipeline Studio é considerado completo quando:

- [ ] DSL JSON schema versão 1 publicado em `mcps/pipeline-schema-v1.json` + `jsonschema` validator no engine
- [ ] 5 templates curados em `cobaias/_templates/*.json`, todos passam validação + dry-run sem erros
- [ ] Engine `core/pipeline_engine.py` executa todos 18 step types do registry MVP
- [ ] 4 telas UI navegáveis em `/studio/pipelines*` (lista, edit, run, new) com WS live updates
- [ ] APIs CRUD + run control + WS funcionam (15 endpoints novos sob `/api/pipelines/*`)
- [ ] DB migrations aplicadas em PC + VM com rollback testado
- [ ] Owner consegue: clonar template → editar 2 steps → ativar → ver execução live → pausar → editar mid-flight → retomar — fluxo end-to-end <5min
- [ ] Tempo médio setup nova cobaia cai de 2h pra <10min (medido em 2 cobaias reais)
- [ ] `validate_implementation.py --phase F.9` 100% PASS
- [ ] `validate_implementation.py --phase A B C D E F.1-F.8` continua sem regressão
- [ ] FRONTEND-GAP.md atualizado: 3 endpoints fantasmas daemon fechados
- [ ] PLAN.md F.9 checkbox completo + memory_save workflow + mark_chapter
- [ ] Skill `/hermes-pipeline-studio` operacional (gera pipeline novo a partir de descrição NL via Brain)
- [ ] Documentação owner em `.claude/PIPELINE-STUDIO-GUIDE.md` (não substitui este SPEC; é manual de uso)

---

## 9. Apêndice — JSON Schema Formal (jsonschema draft-07)

```jsonc
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://hermes.local/schema/pipeline-v1.json",
  "title": "Hermes Pipeline DSL v1",
  "type": "object",
  "required": ["id", "name", "version", "status", "owner", "steps"],
  "properties": {
    "id": { "type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,63}$" },
    "name": { "type": "string", "minLength": 3, "maxLength": 120 },
    "version": { "type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$" },
    "status": { "enum": ["draft", "active", "paused", "archived"] },
    "owner": { "type": "string", "format": "email" },
    "cobaia_id": { "type": ["string", "null"] },
    "template_id": { "type": ["string", "null"] },
    "created_at": { "type": "string", "format": "date-time" },
    "updated_at": { "type": "string", "format": "date-time" },
    "defaults": { "$ref": "#/definitions/defaults" },
    "triggers": {
      "type": "array",
      "items": { "$ref": "#/definitions/trigger" }
    },
    "vars": { "type": "object", "additionalProperties": true },
    "steps": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/definitions/step" }
    },
    "slo": { "$ref": "#/definitions/slo" },
    "observability": { "$ref": "#/definitions/observability" }
  },

  "definitions": {
    "defaults": {
      "type": "object",
      "properties": {
        "retry_policy": { "$ref": "#/definitions/retry_policy" },
        "timeout_seconds": { "type": "integer", "minimum": 1, "maximum": 604800 },
        "owner_alert_on_failure": { "type": "boolean" },
        "log_level": { "enum": ["debug", "info", "warn", "error"] }
      }
    },
    "retry_policy": {
      "type": "object",
      "properties": {
        "max_attempts": { "type": "integer", "minimum": 0, "maximum": 10 },
        "backoff_seconds": {
          "type": "array",
          "items": { "type": "integer", "minimum": 1 }
        },
        "retry_on": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    },
    "trigger": {
      "type": "object",
      "required": ["type"],
      "oneOf": [
        {
          "properties": {
            "type": { "const": "manual" },
            "label": { "type": "string" }
          }
        },
        {
          "properties": {
            "type": { "const": "cron" },
            "schedule": { "type": "string" },
            "timezone": { "type": "string" }
          },
          "required": ["schedule"]
        },
        {
          "properties": {
            "type": { "const": "event" },
            "event_name": { "type": "string" },
            "filter": { "type": "object" }
          },
          "required": ["event_name"]
        }
      ]
    },
    "step": {
      "type": "object",
      "required": ["id", "type", "label"],
      "properties": {
        "id": { "type": "string", "pattern": "^step-[a-z0-9-]{2,60}$" },
        "label": { "type": "string", "minLength": 3, "maxLength": 100 },
        "type": { "type": "string" },
        "after": {
          "type": "array",
          "items": { "type": "string" }
        },
        "enabled": { "type": "boolean", "default": true },
        "inputs": { "type": "object" },
        "conditions": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "expr": { "type": "string" }
            },
            "required": ["expr"]
          }
        },
        "output_schema": { "type": "object" },
        "retry_policy": { "$ref": "#/definitions/retry_policy" },
        "requires_approval": {
          "type": "object",
          "properties": {
            "enabled": { "type": "boolean" },
            "approver_role": { "type": "string" },
            "auto_approve_if_score_gte": { "type": "number" }
          }
        },
        "on_success": { "type": "array", "items": { "type": "string" } },
        "on_failure": { "type": "array", "items": { "type": "string" } },
        "on_timeout": { "type": "array", "items": { "type": "string" } },
        "ui": {
          "type": "object",
          "properties": {
            "position": {
              "type": "object",
              "properties": {
                "x": { "type": "number" },
                "y": { "type": "number" }
              }
            },
            "color": { "type": "string", "pattern": "^#[0-9a-fA-F]{6}$" },
            "icon": { "type": "string" },
            "notes": { "type": "string", "maxLength": 500 }
          }
        }
      }
    },
    "slo": {
      "type": "object",
      "properties": {
        "max_duration_seconds": { "type": "integer", "minimum": 1 },
        "min_success_rate_7d": { "type": "number", "minimum": 0, "maximum": 1 },
        "max_cost_per_run_brl": { "type": "number", "minimum": 0 }
      }
    },
    "observability": {
      "type": "object",
      "properties": {
        "emit_ws_events": { "type": "boolean" },
        "sentry_release_tag": { "type": "string" },
        "audit_log": { "type": "boolean" }
      }
    }
  }
}
```

---

## 10. Referências cruzadas

- `.claude/PHASE-F-STUDY-SYNTHESIS.md` — diagnóstico Fase F (este spec resolve gap "owner edita YAML manual")
- `.claude/IMPLEMENTATION-PLAN.md` — F.9 task breakdown detalhado (5 sessões estimadas)
- `.claude/PLAN.md` — progress tracker F.9 (atualizar ao completar tasks)
- `.claude/GUARDRAILS.md` — herda regras Fase F (zero código MADURO modificado sem regression gate)
- `mcps/pipeline-schema-v1.json` — schema formal (a criar em F.9.task_1)
- `cobaias/_templates/*.json` — 5 templates seedados (a criar em F.9.task_3)
- `core/pipeline_engine.py` — engine executor (a criar em F.9.task_2)
- `dashboard/components/pipeline-studio/*.js` — UI components (a criar em F.9.task_4-7)

---

**FIM PIPELINE-STUDIO-SPEC.md v1.0** — owner ratifica decisões abertas (seção 7) antes de F.9 começar implementação.
