# Hermes Cloud Studio — Contexto para Claude

> Sistema autônomo de prospecção B2B e automação LinkedIn 24/7.
> Stack: Tauri 2.0 (Rust) + FastAPI + SQLite WAL + Patchright + OpenRouter/Ollama.
> Owner: Caio Leão (Cuiabá, MT, Brasil). Linguagem padrão: PT-BR.

---

## 1. Topologia (3 camadas)

```
┌── PC Windows (D:\dev-projects\main\hermes-cloud-studio) ─────────────┐
│  Hermes.exe (Tauri)  →  spawns invisíveis:                            │
│    • python server.py            (FastAPI :8500 — backend PC)         │
│    • python socks5_proxy.py     (proxy :55081 → VM)                   │
│    • ssh tunnel hermes-gcp@VM   (forward 55081 + 11434 Ollama)        │
│  Dashboard SPA (dashboard/) servido por server.py em /dashboard       │
└───────────────────────────────────────────────────────────────────────┘
                │ HTTP(S) + WS                  │ SSH/proxy
┌── GCP VM e2-standard-4  (IP 136.115.74.69, user hermes-gcp) ─────────┐
│  hermes_api_v2.py (FastAPI :8420 — backend VM)                        │
│  daemon/orchestrator.py (HermesDaemon — loop autônomo 24/7)           │
│  gosom_scraper.py (Docker, free) + night_scraper.py (Places API)      │
│  linkedin/ (Patchright stealth) — sessão via LI_AT em ~/.hermes/.env  │
│  Ollama (qwen3:8b/14b, phi4-mini, gemma3:4b)                          │
│  Skills YAML em ~/.hermes/skills/                                     │
└───────────────────────────────────────────────────────────────────────┘
                │
┌── External  ─────────────────────────────────────────────────────────┐
│  OpenRouter (tier free) · Cloudflare Tunnel (hermes.caioleo.com)      │
│  Telegram Bot · Google Places API · AgentMemory MCP (:3141)           │
└───────────────────────────────────────────────────────────────────────┘
```

**Regra fundamental:** trabalho pesado (scraper, LinkedIn campaigns, audit em lote) roda na VM. PC orquestra, cacheia e mostra UI. PC ↔ VM sync via polling HTTP a cada 60s + push do VM pra PC via `HERMES_PC_EVENT_URL`.

---

## 2. Arquivos críticos por tamanho/relevância

| Arquivo | Linhas | Papel |
|---|---|---|
| `server.py` | 3.307 | Backend PC :8500 — 48 endpoints + WS + 5 loops |
| `hermes_api_v2.py` | 1.861 | Backend VM :8420 — endpoints CRUD + scraper subprocess + LinkedIn async |
| `dashboard/app.js` | grande | SPA logic — navegação hash, API client, WS |
| `app/src-tauri/src/lib.rs` | médio | Tauri runtime — health loop, process mgmt, tray |
| `daemon/orchestrator.py` | médio | Loop autônomo, fila de prioridades P1–P7 |
| `scripts/pipeline.py` | médio | Discovery → audit → outreach end-to-end |
| `linkedin/` | múltiplos | Patchright + 11 patches stealth + rate limiter SQLite |

DB: `hermes_local.db` (PC, mirror ~41MB) e `~/.hermes/data/command_center.db` (VM, master).

---

## 3. Backend PC (`server.py`, porta 8500)

**Auth:** header `X-Hermes-Token` validado em todas as rotas `/api/*`. CORS wildcard. **WebSocket `/ws` não tem auth** — confia em same-origin.

**Endpoints agrupados (~48 total):**
- `/api/prospects*` — CRUD + bulk + cidades/categorias + stats
- `/api/activities` — log paginado
- `/api/tasks*` — fila + bulk + `send-to-claude` (Agent Zero)
- `/api/claude/execute` e `/api/agent-zero/*` — chat com contexto persistente (`_agent_zero_context_id`)
- `/api/audit/*` — batch + single + status
- `/api/outreach/generate/{id}` — geração de mensagem
- `/api/scraper/{status,start,stop,history,parse-prompt}` — proxy pra VM
- `/api/photos/{ref}` — cache local de fotos Google Maps (pasta `photo_cache/`)
- `/api/pipelines*` — templates + execução + executions history; tipos: `linkedin_viewer` (local), `scraper`/`audit`/`outreach` (proxy VM), `custom` (Agent Zero)
- `/api/linkedin/*` — campanhas (view/engage/connect/discover), rate-limits, health, comment edit/delete, account detect, auth
- `/api/server/*` — restart-local / restart-vm / restart-all / shutdown
- `/api/hermes/*` — status, sync, skills (proxy VM), memory (AgentMemory local)
- `/api/daemon/*` — state, pause/resume, log, decisions, channels, timeline, broadcast
- `/api/workqueue` — prospects pendentes
- `/api/stats` — pipeline 7 dias

**5 loops em background (lifespan):**
1. `sync_loop` (60s) — pull prospects+activities da VM, upsert SQLite, broadcast `sync`
2. `linkedin_sync_loop` (10s) — pull campanhas rodando, atualiza progress, preserva estados `scheduled`/`cancelled`
3. `linkedin_scheduler_loop` (30s) — despacha campanhas agendadas se gates abriram
4. `linkedin_health_monitor_loop` (adaptive 60s–5min) — probe health, alerta Telegram em transição
5. `linkedin_session_monitor_loop` (1h) — detecta sessão expirada, alerta no Telegram

**Eventos WS:** `sync`, `linkedin_progress`, `linkedin_campaign_created`, `linkedin_health`, `daemon_state`, `daemon_broadcast`.

**Gate system LinkedIn:** campanhas auto-agendam se health/rate-limit/working-hours bloqueado. `_compute_schedule_state()` retorna a janela mais distante + razões.

**⚠️ Bug conhecido:** `time.time()` usado sem `import time` (linhas 698, 722) — pode quebrar em runtime se ambiente não tiver `time` autoimportado.

**Pessimistic session:** `_LI_SESSION_LAST_OK` permanece false até próximo `/session-check` OK — bloqueia campanhas até sync manual do LI_AT.

---

## 4. Backend VM (`hermes_api_v2.py`, porta 8420)

**Auth:** mesmo header, var `HERMES_VM_AUTH_TOKEN`. Espera estrutura em `~/.hermes/`:
- `data/command_center.db` (SQLite WAL, 8 tabelas: prospects, activities, pipeline_stats, tasks, linkedin_campaigns, linkedin_profiles, linkedin_engagements + migração `2026_06_linkedin_full.sql`)
- `scripts/`, `skills/`, `logs/`, `cron/jobs.json`

**Endpoints destacados:**
- `/api/dashboard` — agregado pesado (counts, recentes, top)
- `/api/scraper/start` — `subprocess.Popen(["python3", "gosom_scraper.py", ...])` com flags `--cities --categories --only-no-site`. PID em `night_scraper.pid`, log em `~/.hermes/logs/night_scraper_YYYYMMDD.log`, checkpoint em `gosom_checkpoint.json`
- `/api/audit/start` — thread batch; scoring 0–100 mapeia stage: <50 discovered, 50–69 qualified, ≥70 audited
- `/api/outreach/batch` — gera msg pra audited+score≥60 sem mensagem
- `/api/pipeline/execute` — `audit | outreach | linkedin_viewer (NÃO IMPLEMENTADO — viewer roda no PC) | full`
- `/api/hermes/skills` — lê glob `*.yaml`/`*.yml`, retorna name/desc/model/active; PATCH escreve de volta no YAML
- `/api/linkedin/*` — 11 endpoints, controlam campanhas async via Patchright. Task tracker in-memory: `_running_linkedin_campaigns`
- `/api/internal/account_type_set` e `/api/internal/li_at_update` — webhook recebido da extensão Chrome

**Real-time push:** `_li_log` monkey-patched envia HTTP POST pra `HERMES_PC_EVENT_URL` (fire-and-forget). É como o PC recebe progresso das campanhas LinkedIn.

**Importante:** Agent Zero, OpenRouter e multi-turn LLM context vivem no PC. VM só tem Ollama local e Patchright.

---

## 5. Desktop Tauri (`app/src-tauri/`)

- **Janela:** 1400×900 (min 900×600), centrada, hidden até server responder. Título "Hermes Command Center".
- **Frontend:** carrega `http://localhost:55000` (proxy pro server.py:8500/dashboard). Não bundle nada — sempre live disk.
- **CSP:** desabilitado (null).
- **Process mgmt:** 3 processos filhos com `CREATE_NO_WINDOW` (0x08000000), stdout/stderr null:
  - `python server.py` → port probe :55000 (se já aberto, reusa)
  - `python socks5_proxy.py 55081` → port probe :55081
  - `ssh -R 127.0.0.1:55081:127.0.0.1:55081 -R 127.0.0.1:11434:127.0.0.1:11434 hermes-gcp@136.115.74.69`
- **Health loop (10s):** mark_healthy reseta contador após 30s saudável. `RestartTracker`: max 3 restarts em 60s, depois 60s de cooldown.
- **Tray menu PT:** Abrir Dashboard · Ligar/Desligar Tunnel · Reiniciar Serviços · Sair. Tooltip atualiza a cada 10s com `Server: ok|recovering|cooldown · Proxy: ... · Tunnel: ...`
- **Shutdown:** flag + kill nos 3 filhos + `exit(0)`.
- **Lançadores:**
  - `Hermes.bat` — tenta release, fallback debug
  - `Hermes.ps1` — kill exe anterior, detecta mudança em `.rs/Cargo.toml/tauri.conf.json` por mtime, rebuilda se necessário, spawna
- **IPC commands:** `get_status`, `start_server`, `start_proxy`, `start_tunnel`, `stop_tunnel`, `toggle_tunnel`.
- **`app/src/index.html`** é placeholder com spinner + polling de `/api/dashboard` (15 tentativas × 2s) → redirect pra dashboard real.

---

## 6. Dashboard SPA (`dashboard/`)

Vanilla HTML/CSS/JS. **11 páginas** (data-page nav, hash routing):

| Page | Função | APIs |
|---|---|---|
| `control` (Mission Control) | Activity Orbit + canais (Email/LinkedIn/WA/IG) + timeline 24h + avatar Hermes | WS events daemon_state, activity, channel_update |
| `dashboard` | KPIs + Hermes Live + scraper + audit + AI status + activities + top prospects + tasks | `/api/dashboard`, `/api/activities`, `/api/prospects`, `/api/audit/status`, `/api/hermes/status` |
| `prospects` | Tabela com filtros (city/category/website/stage), bulk, painel lateral | `/api/prospects`, `/api/prospects/{id}`, bulk PATCH |
| `proposals` | Grid de mensagens geradas | `/api/proposals`, `/api/prospects/{id}/proposal` |
| `audit` | Batch control + progress + results | `/api/audit/start`, `/api/audit/status`, WS `audit_done` |
| `pipeline` | Builder + live monitor + command center + history | `/api/pipelines*`, `/api/pipeline-executions/*` |
| `tasks` (Fila do Dia) | Cards por task com filtros e ações | `/api/tasks` |
| `skills` | Toggle skills do Hermes Agent | `/api/hermes/skills` |
| `memory` | Facts/Preferences/Patterns CRUD | `/api/hermes/memory/*` |
| `missions` | Calendário semanal | `/api/missions` |
| `claude` | Terminal AI com markdown inline + histórico em localStorage | `/api/claude/execute` |
| `linkedin` | Campanhas (View/Connect/Engage/Comment), session, warmup | `/api/linkedin/*` |

**WS handler** (`handleWSEvent`): sync, pipeline_progress, audit_done, scraper_update, daemon_state, activity, channel_update, reply_received, decision, alert. **Fallback polling:** dashboard 30s, scraper 10s. **Reconnect:** 3s.

**Auth:** token + API URL em `localStorage` (`hermes_token`, `hermes_api`). Header `X-Hermes-Token`. 401 → login modal.

**Design tokens (`styles.css`):** `--bg #0a0a0c`, `--accent #7c3aed` (violeta), `--lime #d1fe17`, `--green #10b981`, `--red #ef4444`. `--sidebar-w 240px`, `--topbar-h 56px`, `--r 14px`. Glassmorphism: `backdrop-filter: blur(20px) saturate(1.4)`. Easing `cubic-bezier(0.4,0,0.2,1)`.

**Markdown render do Claude page:** custom inline (sem lib). `escapeHtml` previne XSS, mas sem allowlist.

**localStorage usado:** `hermes_api`, `hermes_token`, `claude_history` (last 50), `hermes_sent_proposals`, `li_active_tab`, `li_campaign_collapsed_*`, `li_section_collapsed_*`.

**Quirks:**
- Modais não bloqueiam viewport (sem backdrop-blur), só opacity toggle
- Ripple effect via event delegation em document
- Bulk selection é `Set` global
- Sem framework (vanilla puro), tudo via `innerHTML`/`textContent`

---

## 7. Camada LinkedIn (`linkedin/`)

**Patchright** (fork do Playwright com fix do CDP `Runtime.enable` leak), `channel="chrome"` pra TLS/JA3 reais, perfil user-data-dir por conta, `headless=False`, `xvfb-run` na VM.

**`config.py` — `LinkedInConfig`** dataclass: limites diários/semanais por tipo (free/premium/sales_nav), warm-up 14 dias, lurking 7 dias (zero outreach), working hours (default 8h–20h, timezone America/Cuiaba), proxy, viewport, header/UA.

**`stealth.py` — 11 patches JS:**
1. `navigator.webdriver=false`
2. `window.chrome` completo (loadTimes/csi/app)
3. Plugins (PDF, Native Client)
4. Languages (pt-BR, pt, en-US, en)
5. Platform Win32
6. Hardware concurrency 8 / device memory 8GB
7. Permissions API smoothing (notifications)
8. WebGL vendor "Google Inc."/renderer "NVIDIA GTX 1660"
9. Canvas fingerprint noise
10. WebRTC IP leak (ICE servers null)
11. `Function.prototype.toString` masking

**`human.py`** — Mouse via curvas de Bezier cúbicas + tremor ±1–2px gaussiano. Typing com Fitts's Law e bigram timing. Click com offset gaussiano (não centro morto). Reading sim: 35% scroll, 30% pause, 20% mouse, 15% nada. Overshoot 12%.

**`limiter.py`** — SQLite WAL, 3 tabelas (`rate_actions`, `warmup_state`, `session_state`). Warm-up por ação: lurking d0–6 ≈ 4% views / 0% connects → ramp d7–13 linear → normal d14+. Working hours gate. **30min cooldown entre campaigns.** Break após N ações (default 25).

**`viewer.py` / `engager.py` / `connector.py`** — flows com human behavior + record action.

**`cooldown.py`** — probe `/feed/` via SOCKS5 + LI_AT. Estados: `ok`, `challenge`, `cooldown` (429), `blocked`. Cache disco: ok 5min, cooldown 30min, challenge 10min.

**`account_detector.py`** — detecta free/premium/sales_navigator por DOM markers. Cache 24h.

**`company_finder.py`** — descobre HR/recruiters em empresa-target, hydrate cache 7d.

---

## 8. Outros módulos

### `channels/`
Email / Instagram / WhatsApp. **Stubs** — só `__init__.py` por enquanto. Implementação pendente.

### `extension/` (Chrome MV3)
Sync de `li_at` em tempo real do Chrome do Caio → POST pra `localhost:55000/api/internal/li_at_rotate`. Listen `chrome.cookies.onChanged` + alarm 30min safety net. Detecta account type via DOM em todas as páginas do LinkedIn, com cooldown 1h, POST pra `/api/internal/account_type_set`. Popup mostra status sync + tipo de conta.

### `daemon/orchestrator.py`
**HermesDaemon** — loop adaptativo 5–30s. Prioridades:
- P1 (7–20h): replies pendentes
- P2 (8–18h): sequence steps due
- P3 (6–22h): batch enrichment
- P4 (0–6h ou pipeline vazia): discovery scrape noturna
- P5 (0–7h, 20–23h): audit em lote
- P6 (22–23h): recalcular scores
- P7 (Dom 19–21h): relatório semanal

Rate-limit por canal: LinkedIn 70/d + warmup, Email 75/d, WA 25/d, IG off. Circuit breaker: 5 erros = 10min pause. Estado persiste em `daemon_state` table. Broadcast `daemon_state` / `activity` / `decision` no WS.

Diferente do `scripts/pipeline.py` (síncrono on-demand).

### `scripts/`
- `pipeline.py` — discovery → dedup → audit → score → outreach → sync. Modos: full/discovery/audit-pending/outreach-ready
- `google_maps_scraper.py` — Places API, minimal, on-demand
- `gosom_scraper.py` (raiz) — Docker, free, 91 categorias × 16 cidades MT, checkpoint-resume. **Preferido pra noturno.**
- `night_scraper.py` (raiz) — Places API massiva (legacy)
- `web_audit.py` — checa website/SSL/mobile/WA/social → score 0–100 (+25 sem site = sinal positivo!, +bonus categoria valiosa)
- `outreach_generator.py` — 23 templates × mapping categoria→serviços. Branch `has_website` muda discurso. Outputs WA + email em PT, assinado "Caio Leão, Designer & Estrategista Digital, Cuiabá, MT"
- `li_at_sync.py` + `.bat` — lê cookies do Chrome/Edge/Brave/Opera/Vivaldi via DPAPI + AES-GCM, POST pra `/api/internal/li_at_rotate`. Task Scheduler.

### Raiz
- `_health_ep.py` — endpoint `/api/linkedin/health`
- `socks5_proxy.py` — proxy auth `hermes:cuiaba2026`
- `telegram_bridge.py` — bot → `claude -p` subprocess → response. `/start`, `/status`. Quebra em 4096 chars
- `create_icon.py` / `create_last_run.py` — utils
- `hermes_desktop.py` — DEPRECATED (substituído pelo Tauri)
- `intelligence/`, `task_queue/` — stubs vazios (futura predição + queue)

---

## 9. Skills LinkedIn (`skills/*.yaml`)

6 skills com schema `{name, description, version, active, model, provider, temperature, max_tokens, system_prompt, triggers, input_schema}`:

| Skill | Model | Foco |
|---|---|---|
| `linkedin-post-generator` | deepseek-chat:free | Posts 1300 chars com hook+valor+CTA |
| `linkedin-profile-researcher` | qwen3:8b (Ollama) | Análise + ice-breaker + classificação alta/média/baixa |
| `linkedin-connection-sender` | deepseek-chat:free | Notas de invite 300 chars personalizadas |
| `linkedin-engagement` | minimax-m1:free | Comentários 50–200 chars com insight/pergunta/dado |
| `linkedin-trend-monitor` | deepseek-chat:free | Tendências + gaps |
| `weekly-mission-planner` | nemotron-70b:free | Distribuição semanal de ações |

Sem acentos no YAML (decisão do autor pra evitar problemas de encoding em parsing).

---

## 10. Config / Env / Secrets

**`.env` na raiz** (template em `.env.example`):
```
VM_USER=hermes-gcp · VM_HOST=136.115.74.69 · PROXY_PORT=55081 · PROXY_USER=hermes · PROXY_PASS=...
DASHBOARD_PORT=55000 · HERMES_SYNC_INTERVAL=60
HERMES_VM_API=http://VM_IP:8420 · AGENT_ZERO_URL=http://VM_IP:50080 · AGENT_ZERO_API_KEY=...
GOOGLE_PLACES_API_KEY=... · OPENROUTER_API_KEY=... 
HERMES_AUTH_TOKEN=... · HERMES_VM_AUTH_TOKEN=...
LINKEDIN_EMAIL/PASSWORD · LINKEDIN_ACCOUNT_TYPE · LINKEDIN_PROXY*
TELEGRAM_BOT_TOKEN · TELEGRAM_CHAT_ID
EMAIL_FROM/TO/APP_PASSWORD
```

**`.mcp.json`** — `agentmemory` MCP em `http://localhost:3141`, scope isolated, agent_id `hermes-cloud-studio`, Ollama qwen3:8b.

**SSH:** `ssh -i $env:USERPROFILE\.ssh\id_ed25519 hermes-gcp@136.115.74.69`

**Túnel público:** `https://hermes.caioleo.com` (Cloudflare).

---

## 11. Convenções e gotchas

- **Pasta de trabalho:** `D:\dev-projects\main\hermes-cloud-studio` (a subpasta `Hermes Cloud Studio` está vazia, ignorar).
- **Idioma:** todo conteúdo gerado (posts, mensagens, UI text, logs visíveis) em PT-BR. Comentários em código podem ser PT-BR.
- **Tom no LinkedIn:** especialista contribuindo, NUNCA vendedor. Comentário genérico ("ótimo post", "concordo") é banido.
- **Identidade da assinatura:** "Caio Leão, Designer & Estrategista Digital, Cuiabá, MT".
- **Working hours:** Cuiabá timezone (America/Cuiaba), default 8h–20h.
- **Rate limits são lei** — não burlar warm-up nem limites diários sob nenhuma circunstância. Ban no LinkedIn = projeto morto.
- **Segurança LinkedIn:** sempre passar por `stealth.py` patches, residential SOCKS5, e human.py timing. Se for testar, use `headless=False` e modo lab antes de produção.
- **Servidores:** mudar `server.py` requer recarregar (uvicorn reload em dev, restart no Tauri em prod). Frontend é hot — basta refresh.
- **DB são WAL:** múltiplos readers + 1 writer OK; sempre usar `journal_mode=WAL`.
- **Não duplicar AgentMemory:** já configurado via MCP em `.mcp.json`. Memory CRUD do dashboard usa `localhost:3141`.

---

## 12. Workflow comum

**Adicionar endpoint novo no backend PC:**
1. Editar `server.py` (rota + handler)
2. Se proxy pra VM: adicionar contraparte em `hermes_api_v2.py`
3. Adicionar consumo em `dashboard/app.js` (função + UI)
4. Reiniciar via tray "Reiniciar Serviços" ou `npm run tauri dev`

**Criar nova skill LinkedIn:**
1. Novo YAML em `skills/{name}.yaml` seguindo schema
2. Sincronizar pra VM em `~/.hermes/skills/`
3. Aparece automaticamente em `/api/hermes/skills`

**Renovar LI_AT:**
1. Login manual no Chrome (Caio)
2. Extension detecta `cookies.onChanged` e POST automático pra `/api/internal/li_at_rotate`
3. Server escreve em `~/.hermes/.env` na VM via SSH
4. Próximo `linkedin_session_monitor_loop` valida e libera campanhas

**Debug campanha LinkedIn travada:**
1. `/api/linkedin/health?force_refresh=1` — vê estado real
2. `/api/linkedin/rate-limits` — limites e janela
3. `/api/linkedin/campaigns/{id}/log` — log da campanha
4. Se cooldown: aguardar (não forçar). Se challenge: revisar conta no LinkedIn manualmente.

---

## 13. Histórico recente (git)

```
e6e3eab feat: add Hermes Daemon 24/7 orchestrator and Mission Control dashboard
8d1164f docs: rewrite README with full architecture
b9e5448 feat(tauri): rebuild desktop app with health loop and auto-restart
69ea8ae feat: add Telegram bridge and Cloudflare tunnel config
b5c0a74 feat(skills): add 6 LinkedIn automation skill YAML definitions
e413b69 feat(dashboard): Skills, Memory, Missions + WebSocket + Claude markdown
4c5d48a refactor(dashboard): split monolithic HTML into modular CSS/JS files
4fc54f6 feat(auth): add token-based authentication
```

Roadmap implícito (do `docs/HERMES-PROJECT-CONTEXT.md`): expansão de disco VM, rotação fina de modelos OpenRouter, expandir Telegram bridge, polir mobile, refinamento contínuo.
