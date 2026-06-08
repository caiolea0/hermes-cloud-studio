# Hermes Cloud Studio — Implementation Plan (DEEP-AUDIT remediation)

> **Fonte da verdade durável** da execução dos fixes. Sobrevive compressão de contexto.
> Cada fix tem: análise, solução alinhada à arquitetura, arquivos+linhas, plano de teste, **persistência obrigatória**.
> Validação automatizada: `python scripts/validate_implementation.py` ao fim de cada fase.

**Total findings**: 20 (2 critical, 9 high, 8 medium, 1 low)
**Origem**: `.claude/DEEP-AUDIT-2026-06-08.md` — workflow `hermes-deep-audit` (172 raw → 20 confirmados 3/3 lentes valid)
**Estratégia**: 5 fases sequenciais. Cada fase termina com persistência + validação. Flag system reabre items que falharem check.

---

## Arquitetura de referência (sempre re-verificar)

Antes de cada fix, validar que solução respeita:

```
PC LOCAL (Windows)
├── Hermes.exe Tauri 2.0 — launcher
├── server.py :8500 — dashboard backend (ORQUESTRA)
├── socks5_proxy.py :55081 + ssh -R tunnel reverso (VM → PC residencial)
├── tunnel_supervisor.py — always-on via Task Scheduler
├── mcps/hermes-control/ — TS MCP server
└── Dashboard SPA — visualiza/controla, NUNCA executa LinkedIn

VM GCP (Linux)
├── hermes_api_v2.py :8420 — backend real (EXECUTA)
├── daemon/orchestrator.py — loop 24/7 P1-P7
├── linkedin/ — Patchright + stealth_compliance + preflight + account_profile + 3 patches
├── gosom_scraper (Docker) + night_scraper
├── Ollama (PC GPU via SSH tunnel reverso :11434)
└── ~/.hermes/skills/ YAML
```

**Regra fundamental**: trabalho pesado VM. PC orquestra. Mexer em algo que VIOLA isso = re-pensar antes de implementar.

---

## Convenções desta sessão de implementação

- **Branch strategy**: trabalho direto em `master` (projeto solo). Commit por finding ou por feature pequena. Push ao fim de cada fase.
- **Commit message format**: `fix(escope): MERGED-XXX — descrição curta`
- **Test before commit**: rodar `validate_implementation.py` ao menos em modo "single finding".
- **Persistência obrigatória ao fim de cada fase**:
  1. `mark_chapter` início da fase
  2. `TaskCreate` por finding
  3. `memory_save` ao fim da fase (tipo workflow)
  4. Update `.claude/PLAN.md` com checkboxes
  5. Update `.claude/GUARDRAILS.md` se regra nova surgir
  6. `python scripts/validate_implementation.py --phase X` antes de fechar fase
- **Anti-padrões proibidos**:
  - Skip fase de validação porque "óbvio que tá funcionando"
  - Marcar finding como done sem assertion concreta no script
  - Mexer em arquivo fora do escopo do finding sem flag separada
  - Implementar 2+ findings no mesmo commit sem necessidade técnica

---

# 🔴 FASE A — Security Critical (1-2 dias, ~3 commits)

**Objetivo**: fechar exposições que sangram dados agora. Tudo prerequisito do resto.

**Pré-requisito**: tunnel_supervisor UP, agentmemory funcional.

---

## A.1 — MERGED-002: AUTH_TOKEN vazio = fail-open

**Severity**: 🔴 critical · **Effort**: S · **Files**: `server.py:48,823-825` + `hermes_api_v2.py:28,154-156`

### Análise

Middleware atual em ambos PC e VM:
```python
AUTH_TOKEN = os.environ.get("HERMES_AUTH_TOKEN", "")  # default vazio
async def auth_middleware(request, call_next):
    if not AUTH_TOKEN:
        return await call_next(request)  # ← BYPASS TOTAL
    ...
```

**Por que crítico**: deploy sem env var → API 100% pública. Trivial de ocorrer em (a) primeira execução pré-config, (b) container/CI sem secret injected, (c) `.env` mal carregado por path relativo errado.

### Solução (alinhada arquitetura)

**Princípio**: fail-closed. Token ausente = serviço NÃO sobe.

```python
# server.py top-level (linha ~48):
AUTH_TOKEN = os.environ.get("HERMES_AUTH_TOKEN", "").strip()
if not AUTH_TOKEN:
    raise RuntimeError(
        "HERMES_AUTH_TOKEN obrigatório. Setar em .env ou env var antes de subir o server. "
        "Gerar via: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )

# server.py middleware (linha ~823-825): REMOVER o early-return bypass.
async def auth_middleware(request, call_next):
    if request.url.path.startswith("/api/"):
        token = request.headers.get("X-Hermes-Token", "")
        if not secrets.compare_digest(token, AUTH_TOKEN):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)
```

Idem em `hermes_api_v2.py:28,154-156` para `HERMES_VM_AUTH_TOKEN`.

**Bônus**: trocar comparação atual (provavelmente `==`) por `secrets.compare_digest` (timing-attack safe).

### Arquivos afetados

- `server.py` linhas 48, 823-825 — 3-5 linhas mudadas
- `hermes_api_v2.py` linhas 28, 154-156 — 3-5 linhas mudadas
- `.env.example` — já documenta `HERMES_AUTH_TOKEN=` — manter

### Plano de teste

1. **Local PC**: `unset HERMES_AUTH_TOKEN; python server.py` → deve abortar com mensagem clara
2. **Local PC com token**: setar token, subir, `curl /api/hermes/status` sem header → 401
3. **Local PC com token + header correto** → 200
4. **VM via SSH**: idem `hermes_api_v2.py`
5. **Validation**: `validate_implementation.py --finding MERGED-002`

### Persistência pós-fix

- Commit: `fix(security): MERGED-002 — fail-closed quando AUTH_TOKEN vazio`
- Update PLAN.md checkbox
- memory_save tipo `bug`: "MERGED-002 fechado. server.py + hermes_api_v2.py agora abortam se token ausente. Reduces deploy surface."

### Risco de regressão

- **Dev local que não setou env**: server NÃO sobe. Mensagem orienta como gerar token.
- **Tauri spawn server.py sem env**: precisa garantir Tauri injeta `HERMES_AUTH_TOKEN` no env do subprocesso (verificar `app/src-tauri/src/lib.rs`).

### Update GUARDRAILS

Adicionar em `.claude/GUARDRAILS.md` seção 🚫:
> Subir server.py ou hermes_api_v2.py sem `HERMES_AUTH_TOKEN`/`HERMES_VM_AUTH_TOKEN` → serviço aborta. Setar SEMPRE via `.env` ou env var antes de iniciar.

---

## A.2 — MERGED-001: WebSocket /ws sem autenticação

**Severity**: 🔴 critical · **Effort**: S · **Files**: `server.py:810-831`

### Análise

```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)  # NENHUMA validação
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
```

Broadcasts incluem: `sync` (prospects), `linkedin_progress` (campanhas), `daemon_state`, `partial_results`. Via Cloudflare tunnel `hermes.caioleo.com` — exposto na internet pública.

**Por que crítico**: combinação WS aberto + CORS `*` + tunnel HTTPS público = qualquer um do mundo pode conectar e exfiltrar pipeline comercial em tempo real. Possível breach LGPD.

### Solução (alinhada arquitetura)

WebSocket no FastAPI/Starlette NÃO passa por HTTP middleware. Auth no handshake DEVE ser dentro do endpoint.

```python
import secrets
from starlette.websockets import WebSocketDisconnect

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Auth no handshake — token via query OU header (browser não permite custom headers em WS)
    token = websocket.query_params.get("token", "") or websocket.headers.get("x-hermes-token", "")
    if not token or not secrets.compare_digest(token, AUTH_TOKEN):
        await websocket.close(code=1008, reason="Unauthorized")
        return
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
```

Cliente dashboard (já em `dashboard/app.js`) atualizar URL WS:
```js
const token = localStorage.getItem("hermes_token");
const ws = new WebSocket(`ws://localhost:8500/ws?token=${encodeURIComponent(token)}`);
```

### Arquivos afetados

- `server.py:810-831` — adicionar auth (~15 linhas)
- `dashboard/app.js` — anexar token ao WS URL (~5 linhas)

### Plano de teste

1. Browser console: `new WebSocket("ws://localhost:8500/ws")` → close 1008
2. Browser com token: `new WebSocket("ws://localhost:8500/ws?token=" + TOKEN)` → conecta + recebe broadcasts
3. Dashboard reload → conecta automaticamente
4. `validate_implementation.py --finding MERGED-001`

### Persistência pós-fix

- Commit: `fix(security): MERGED-001 — autenticar WebSocket /ws no handshake`
- memory_save: "WS handshake agora valida X-Hermes-Token via query param. Dashboard atualizado."

### Risco de regressão

- Clientes externos que conectavam sem token: quebram. Aceitável — eram exposição.
- Logs WS atualmente podem expor token na URL — silenciar via `uvicorn --access-log False` em prod OU log custom que mascara `?token=`.

### Update GUARDRAILS

Adicionar regra:
> WebSocket /ws exige X-Hermes-Token. FastAPI middleware NÃO cobre WS — validar dentro do handler. Token via query param OU header (browser não envia custom headers em WS native).

---

## A.3 — MERGED-003: Endpoints /api/internal/* confiam só em client.host

**Severity**: 🟡 high · **Effort**: S · **Files**: `server.py:2394,2433,2470`

### Análise

3 endpoints sensíveis:
```python
@app.post("/api/internal/account_type_set")   # set tipo conta LinkedIn
@app.post("/api/internal/li_at_rotate")        # rotaciona cookie LinkedIn ★ MUITO sensível
@app.post("/api/internal/linkedin/event")      # eventos da extension
```

Validação atual:
```python
if request.client.host not in ("127.0.0.1", "::1", "localhost"):
    raise HTTPException(403)
```

**Risco real**: server bind em `0.0.0.0:8500` (linha 3308) → qualquer LAN client pode conectar (IP local LAN, não loopback). Análise da lente Impact: client.host retorna IP TCP real (FastAPI default não respeita X-Forwarded-For sem ProxyHeadersMiddleware), então spoof via header não funciona com config atual. **MAS** bind 0.0.0.0 + futuro upgrade pra ProxyHeadersMiddleware (esperado quando subir atrás de nginx/cloudflare) = vulnerável.

### Solução (alinhada arquitetura)

Defesa em profundidade:

1. **Bind explícito 127.0.0.1** (não 0.0.0.0) — server.py:3308
2. **Token interno separado** (`HERMES_INTERNAL_TOKEN`) no header `X-Internal-Token`
3. **Manter check client.host** como segunda camada

```python
INTERNAL_TOKEN = os.environ.get("HERMES_INTERNAL_TOKEN", "").strip()
if not INTERNAL_TOKEN:
    raise RuntimeError("HERMES_INTERNAL_TOKEN obrigatório")

def _check_internal(request: Request):
    if request.client.host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(403, "loopback only")
    token = request.headers.get("X-Internal-Token", "")
    if not secrets.compare_digest(token, INTERNAL_TOKEN):
        raise HTTPException(401, "internal token invalid")

@app.post("/api/internal/account_type_set")
async def account_type_set(request: Request, ...):
    _check_internal(request)
    ...
```

Extension Chrome MV3 + `scripts/li_at_sync.py` precisam ler `HERMES_INTERNAL_TOKEN` e enviar header.

### Arquivos afetados

- `server.py` — adicionar `_check_internal` + 3 endpoints (~20 linhas), bind 127.0.0.1
- `extension/background.js` (e similares) — incluir header
- `scripts/li_at_sync.py` — header
- `.env.example` — documentar `HERMES_INTERNAL_TOKEN=`

### Plano de teste

1. Bind 127.0.0.1: `ss -ltn | grep 8500` → só loopback
2. `curl http://127.0.0.1:8500/api/internal/li_at_rotate -X POST -H "X-Internal-Token: $TOKEN"` → 200
3. `curl http://127.0.0.1:8500/api/internal/li_at_rotate -X POST` → 401
4. `curl http://<LAN_IP>:8500/api/internal/...` → conexão recusada
5. Extension sync ainda funciona em browser real (Brave/Chrome)

### Persistência

- Commit: `fix(security): MERGED-003 — token interno + bind loopback para /api/internal/*`
- memory_save: "INTERNAL_TOKEN adicionado. Bind 127.0.0.1. Extension + li_at_sync.py atualizados."

### Risco regressão

- Extension Chrome desatualizada → perde sync li_at silenciosamente. Mitigar: log claro "401 internal token" e instrução pra recarregar extension.

---

## Persistência Fase A 🔒

Ao fechar A:
1. ✅ Mark chapter "Phase A — Security Critical complete"
2. ✅ memory_save tipo `workflow`: "Hermes Phase A done. MERGED-001/002/003 fixed. Auth fail-closed + WS auth + internal token. 3 commits."
3. ✅ Update PLAN.md checkboxes A.1, A.2, A.3
4. ✅ Update GUARDRAILS.md com 3 regras novas
5. ✅ Run `python scripts/validate_implementation.py --phase A` → MUST pass all 3
6. ✅ `git push`

---

# 🟡 FASE B — State & Robustness (semana 1, ~5 commits)

**Objetivo**: bugs invisíveis + recovery em restart. Sistema deixa de mentir sobre estado.

---

## B.1 — MERGED-005: Race conditions SQLite sem busy_timeout

**Severity**: 🟡 high · **Effort**: S-M · **Files**: `linkedin/limiter.py`, `linkedin/account_profile.py`, hermes_local.db connections em `server.py`, command_center.db em `hermes_api_v2.py`

### Análise

5 loops PC + endpoints REST concorrentes + sync 60s acessam SQLite. WAL mode ajuda mas `SQLITE_BUSY` ainda ocorre se writer 1 demora >timeout default (5s).

### Solução

Helper de conexão padronizado:
```python
def _connect(path: str, timeout: float = 30.0) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=timeout, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")  # 30s
    conn.execute("PRAGMA synchronous=NORMAL")  # WAL + NORMAL = safe + fast
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
```

Aplicar em: `linkedin/limiter.py:_get_db`, `linkedin/account_profile.py` (já usa via outro path), todos os `sqlite3.connect()` em `server.py` e `hermes_api_v2.py`.

### Arquivos

- `linkedin/limiter.py` — refactor `_get_db()` (~10 linhas)
- `server.py` — grep `sqlite3.connect` → wrapper (~5-10 ocorrências)
- `hermes_api_v2.py` — idem
- Novo: `linkedin/db_utils.py` com helper canônico

### Test

- Smoke: rodar 3 processos paralelos escrevendo `rate_actions` — sem `database is locked`
- `validate_implementation.py --finding MERGED-005`: assertion grep `PRAGMA busy_timeout` em todos arquivos relevantes

---

## B.2 — MERGED-004: Globals in-memory perdem em restart

**Severity**: 🟡 high · **Effort**: M · **Files**: `hermes_api_v2.py:1046`, `server.py:51,520,541`

### Análise

- `_running_linkedin_campaigns: dict = {}` (VM) — tracker asyncio.Task vivos
- `_LI_SESSION_LAST_OK`, `_LI_HEALTH_NOTIFIED_AT` (PC) — estado de saúde
- `_audit_state`, `_agent_zero_context_id` (PC) — contexto AI

Restart = perda. Patchright + cookies VIVOS na VM (user_data_dir persiste), mas Hermes esquece. Reconciliação manual.

### Solução

Tabela nova `campaign_runs` em command_center.db:
```sql
CREATE TABLE IF NOT EXISTS campaign_runs (
    run_id TEXT PRIMARY KEY,
    campaign_id INTEGER NOT NULL,
    status TEXT NOT NULL,  -- running|completed|failed|orphaned
    started_at REAL NOT NULL,
    last_heartbeat REAL,
    pid INTEGER,
    metadata_json TEXT
);
```

`hermes_api_v2.py` lifespan:
```python
async def lifespan(app):
    # Startup: reconciliação
    rows = db.execute("SELECT * FROM campaign_runs WHERE status = 'running'").fetchall()
    for r in rows:
        # Heartbeat > 5min sem update → marcar orphaned
        if time.time() - r["last_heartbeat"] > 300:
            db.execute("UPDATE campaign_runs SET status='orphaned' WHERE run_id=?", (r["run_id"],))
    yield
    # Shutdown: marcar todas running como interrupted
    db.execute("UPDATE campaign_runs SET status='interrupted' WHERE status='running'")
```

Estado PC (`_LI_SESSION_LAST_OK`, etc) → persistir em hermes_local.db tabela `runtime_state` (key,value,updated_at).

### Arquivos

- `hermes_api_v2.py` — table + lifespan + heartbeat task (~50 linhas)
- `server.py` — runtime_state table + helpers (~30 linhas)
- `migrations/` — SQL migration script

### Test

- Iniciar campaign → matar processo VM → restart → endpoint `/api/linkedin/campaigns` mostra orphaned
- Restart PC server → endpoint `/api/linkedin/health` retorna último estado persistido

---

## B.3 — MERGED-015: asyncio.create_task sem hold de ref

**Severity**: 🟠 medium (mas habilitador de B.2) · **Effort**: S · **Files**: vários

### Análise

Python GC pode coletar tasks "soltos" → loops silenciosamente sumindo.

### Solução

Set módulo-level:
```python
_background_tasks: set[asyncio.Task] = set()

def spawn(coro):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
```

Substituir todos `asyncio.create_task(...)` por `spawn(...)`.

### Arquivos

- `server.py`, `hermes_api_v2.py`, `daemon/orchestrator.py`, `linkedin/*` — grep `create_task` → `spawn`

### Test

- `validate_implementation.py`: assertion zero `asyncio.create_task(` fora do helper

---

## B.4 — MERGED-007: 30+ `except Exception: pass`

**Severity**: 🟡 high · **Effort**: M · **Files**: `server.py`, `hermes_api_v2.py`, `daemon/orchestrator.py`, `linkedin/*`

### Análise

Falhas silenciosas mascaram bugs. Production debug pesadelo.

### Solução

Substituir patterns:
```python
# Antes
try: ...
except Exception: pass

# Depois
try: ...
except Exception:
    logger.exception("falha em <contexto específico>")
```

Onde silenciar é OK (cleanup em shutdown, broadcast WS opcional), manter mas com comentário `# noqa: silenciado intencional <razão>`.

### Approach

Não fazer em 1 commit gigante. Fazer arquivo por arquivo:
1. `server.py` (mais alta densidade) — split em sub-commits por região
2. `hermes_api_v2.py`
3. `daemon/orchestrator.py`
4. `linkedin/viewer.py`, `linkedin/engager.py`, `linkedin/connector.py`

### Test

- `validate_implementation.py --finding MERGED-007`: count `except Exception: pass` sem comentário noqa < 5 (target)

---

## B.5 — MERGED-016: _dispatch error sobrescrito por sync_loop

**Severity**: 🟠 medium · **Effort**: S · **Files**: `server.py` (área de pipeline dispatch + sync)

### Análise

Bug específico: erro em dispatch é gravado em state local, próximo sync 60s sobrescreve com dados do VM (que não sabe do erro). UI fica em loop "running" eterno.

### Solução

Sync respeitar campo `_local_error_until_ack`. Erro local fica visível até user dismiss explícito no dashboard.

### Arquivos

- `server.py` sync_loop + dispatch handler
- `dashboard/app.js` — botão "dismiss error"

### Test

- Forçar erro em pipeline → UI mostra erro → sync 60s passa → UI ainda mostra erro

---

## Persistência Fase B 🔒

1. Mark chapter Phase B
2. memory_save: B done. Race condições + state persistence + asyncio hold + logging + sync overwrite fix.
3. Update PLAN + GUARDRAILS (novas regras: sempre spawn() não create_task; pragma busy_timeout obrigatório; nunca silenciar exception sem noqa+razão)
4. `validate_implementation.py --phase B`
5. push

---

# 🟢 FASE C — Architecture Consistency (semana 2, ~6 commits)

**Objetivo**: contratos arquiteturais explícitos. Migração GPU sem dor. Monolitos quebrados em módulos.

---

## C.1 — MERGED-013: Settings central (pydantic-settings)

**Severity**: 🟠 medium (mas habilitador de C.2 e C.3) · **Effort**: M · **Files**: novo `config.py` raiz + refactor de todos `os.getenv`

### Análise

`os.getenv` espalhado, sem tipos, sem defaults explícitos, sem validação. Mudança de env var = grep no projeto inteiro.

### Solução

```python
# config.py (novo, raiz)
from pydantic_settings import BaseSettings, SettingsConfigDict

class HermesSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    
    # Auth
    auth_token: str  # required, sem default = fail se ausente
    internal_token: str
    vm_auth_token: str
    
    # VM
    vm_host: str = "136.115.74.69"
    vm_user: str = "hermes-gcp"
    vm_api_url: str = "http://136.115.74.69:8420"
    
    # Proxy
    proxy_port: int = 55081
    proxy_user: str = "hermes"
    proxy_pass: str
    
    # Ollama
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    
    # ... etc
    
settings = HermesSettings()
```

Substituir todos os `os.environ.get(...)` por `settings.attr`.

### Arquivos

- Novo `config.py` raiz (PC) + `config.py` em VM (espelhado)
- `server.py`, `hermes_api_v2.py`, `daemon/orchestrator.py`, `linkedin/*` — refactor
- `requirements.txt` — `pydantic-settings>=2.0`

### Test

- Startup sem `HERMES_AUTH_TOKEN` → ValidationError clara
- Validation: grep `os.environ.get` ou `os.getenv` em código de produção (não scripts/tests) < 5

---

## C.2 — MERGED-009: IP da VM hardcoded em 13+ lugares

**Severity**: 🟡 high · **Effort**: S (depois de C.1) · **Files**: grep `136.115.74.69` no projeto

### Análise

`grep -r "136.115.74.69"` retorna 13+ ocorrências. Migração pra VM GPU planejada este mês = refactor pesado.

### Solução

Todos os `136.115.74.69` literais → `settings.vm_host` (depende de C.1).

### Arquivos

- Vários (grep-and-replace coordenado)

### Test

- `grep -rn "136.115.74.69" --include="*.py" .` → 0 ocorrências em código (OK ter em .env, docs, comentários)

---

## C.3 — MERGED-008: Topologia "PC orquestra, VM executa" violada

**Severity**: 🟡 high · **Effort**: M · **Files**: `server.py` endpoints `/api/linkedin/*` + `/api/pipelines*` execution

### Análise

CLAUDE.md afirma "linkedin_viewer roda no PC, scraper/audit/outreach proxy VM". Análise confirma: server.py tem rotas que executam linkedin_viewer LOCALMENTE (não proxy). Inconsistência: PC não tem Patchright instalado, então NA REALIDADE essas rotas falham silenciosamente OU usam path quebrado.

### Solução

**Decisão**: TODA execução LinkedIn vai pra VM. PC é proxy.

Endpoints `/api/linkedin/campaigns*` no PC:
```python
@app.post("/api/linkedin/campaigns/start")
async def start_li_campaign(...):
    # Proxy direto pra VM
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{settings.vm_api_url}/api/linkedin/campaigns/start", json=..., headers={...})
    return r.json()
```

Atualizar CLAUDE.md + GUARDRAILS pra remover ambiguidade. Mover qualquer linkedin/* tentativa de executar no PC pra VM.

### Arquivos

- `server.py` — remover execução LinkedIn local, deixar só proxy
- CLAUDE.md, GUARDRAILS.md — atualizar topologia explícita

### Test

- `validate_implementation.py`: grep `import linkedin.viewer` em server.py → 0
- Integração: campaign start via PC → request chega na VM (logs `/var/log/hermes_api.log`)

---

## C.4 — MERGED-014: Dep circular VM 24/7 ↔ Ollama no PC

**Severity**: 🟠 medium · **Effort**: M (decisão estratégica) · **Files**: vários

### Análise

VM rodando 24/7 daemon chama Ollama via SSH tunnel reverso (:11434 PC → VM). Se PC dorme ou desliga: daemon LinkedIn quebra silenciosamente. **Acoplamento ruim.**

### Solução (decisão estratégica owner)

Opções:
- **Opção A**: Mover Ollama pra VM (mais simples mas perde GPU PC). Quando VM GPU vier, eliminar acoplamento naturalmente.
- **Opção B**: Cache LLM responses VM-side (reduzir frequência de calls pro PC). Fallback model leve VM-only se PC down.
- **Opção C**: Migração VM GPU prioritizada (este mês conforme PLAN.md). Resolve por extinção.

**Recomendação**: C (já planejado). Até lá, B como mitigação:
- VM tem `qwen3:4b` fallback local
- `ollama_router.py` tenta PC primeiro, cai pro local após 3s timeout

### Arquivos

- Novo `linkedin/ollama_router.py` na VM
- `daemon/orchestrator.py` — usar router em vez de direct URL

### Test

- Simular tunnel down: kill ssh process → daemon deve continuar (fallback local) com warning log

---

## C.5 — MERGED-011: Split monolitos server.py + hermes_api_v2.py

**Severity**: 🟡 high · **Effort**: L · **Files**: refactor pesado

### Análise

- `server.py` 3308 linhas, 48 endpoints + 5 loops
- `hermes_api_v2.py` 1861 linhas

Difícil de manter. Cada deploy é blast radius enorme.

### Solução

Split por domínio. FastAPI APIRouter:

```
server.py (raiz, ~200 linhas — app, lifespan, middleware)
├── api/
│   ├── prospects.py        # /api/prospects*
│   ├── tasks.py            # /api/tasks*
│   ├── audit.py            # /api/audit*
│   ├── outreach.py         # /api/outreach*
│   ├── scraper.py          # /api/scraper*
│   ├── pipelines.py        # /api/pipelines*
│   ├── photos.py           # /api/photos*
│   ├── linkedin.py         # /api/linkedin*
│   ├── server_ctrl.py      # /api/server*
│   ├── hermes.py           # /api/hermes*
│   ├── daemon.py           # /api/daemon*
│   ├── claude.py           # /api/claude*
│   ├── agent_zero.py       # /api/agent-zero*
│   └── internal.py         # /api/internal*
├── loops/
│   ├── sync.py             # sync_loop
│   ├── linkedin_sync.py
│   ├── linkedin_scheduler.py
│   ├── linkedin_health.py
│   └── linkedin_session.py
└── ws_manager.py
```

Idem `hermes_api_v2.py` na VM.

### Approach

NÃO em um commit. Iterativo:
1. Extrair APIRouter por domínio, um por commit
2. Cada commit não muda lógica, só move
3. Smoke test entre cada (server sobe + endpoints respondem)

### Arquivos

- Reorganização ampla — split em ~15 sub-commits

### Test

- Smoke após cada extração: `pytest` se houver, senão `curl` em cada endpoint
- Validation: `wc -l server.py` < 500 ao fim

---

## C.6 — MERGED-012: Lógica duplicada daemon/orchestrator.py vs scripts/pipeline.py

**Severity**: 🟠 medium · **Effort**: M · **Files**: `daemon/orchestrator.py`, `scripts/pipeline.py`

### Análise

Pipeline (discovery → audit → outreach) implementado em 2 lugares com lógica divergente. Bugs corrigidos em um não vão pro outro.

### Solução

Extrair core em módulo `core/pipeline.py`:
```python
# core/pipeline.py
class PipelineRunner:
    async def discovery(self): ...
    async def audit_pending(self): ...
    async def outreach_ready(self): ...
    async def run_full(self): ...
```

`daemon/orchestrator.py` chama `PipelineRunner` quando P3/P5 disparam.
`scripts/pipeline.py` vira CLI thin wrapper: `python -m scripts.pipeline --mode full`.

### Test

- Rodar `scripts/pipeline.py --mode full` → output idêntico ao daemon rodando P3+P5

---

## Persistência Fase C 🔒

1. Mark chapter Phase C
2. memory_save: arquitetura consolidada (Settings central, IP via env, topology enforced, Ollama router, monolitos split, pipeline dedupe)
3. GUARDRAILS update: "TODA execução LinkedIn vai pra VM, PC é proxy" agora oficial
4. PLAN checkboxes
5. validate_implementation.py --phase C
6. push

---

# 🟠 FASE D — Infra & Supervision (semana 3, ~4 commits)

---

## D.1 — MERGED-017: Subprocess scraper sem supervisão

**Severity**: 🟠 medium · **Effort**: S · **Files**: `hermes_api_v2.py:/api/scraper/*`, `scripts/li_at_sync.py`

### Análise

- `subprocess.Popen` sem `terminate()` em shutdown → zombies em VM
- `kill -0 $PID` no `check_running` é Linux-only (não portável, mas VM é Linux então OK)
- PID file `night_scraper.pid` pode ficar stale (processo crashou, PID no arquivo)

### Solução

```python
import psutil

def _is_alive(pid: int) -> bool:
    try:
        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False

# Em /api/scraper/start:
proc = subprocess.Popen([...], start_new_session=True)
# Persistir pid + create_time pra distinguir reciclagem de PID

# Lifespan shutdown:
for pid in tracked_subprocs:
    try: psutil.Process(pid).terminate()
    except: pass
```

### Test

- Start scraper → kill -9 manual → `/api/scraper/status` reporta dead (não "running")
- Restart hermes_api_v2 → scraper processo continua mas trackeado

---

## D.2 — MERGED-018: linkedin_session_monitor confunde flake com expirada

**Severity**: 🟠 medium · **Effort**: S · **Files**: `server.py:linkedin_session_monitor_loop`

### Análise

Loop probe a cada 1h. Se UMA falha por timeout (rede) → marca sessão expirada → alerta Telegram → spam.

### Solução

Confirmação por consecutive failures:
```python
async def linkedin_session_monitor_loop():
    consecutive_fail = 0
    REQUIRED = 3  # 3 falhas seguidas pra confirmar
    while True:
        ok = await probe_li_session()
        if ok:
            consecutive_fail = 0
        else:
            consecutive_fail += 1
            if consecutive_fail >= REQUIRED:
                await alert_session_expired()
        await asyncio.sleep(3600)
```

### Test

- Mock probe pra falhar 2x → sem alert. Falhar 3x → alert dispara.

---

## D.3 — MERGED-020: /api/server/restart-* sem rate-limit

**Severity**: 🟠 medium · **Effort**: S · **Files**: `server.py:/api/server/restart*`

### Análise

DoS trivial: curl em loop → service constantemente restartando, daemon nunca completa ciclo.

### Solução

slowapi (rate limiter FastAPI):
```python
from slowapi import Limiter
limiter = Limiter(key_func=lambda: "global")

@app.post("/api/server/restart-local")
@limiter.limit("2/hour")
async def restart_local(...): ...
```

### Test

- `for i in {1..5}; do curl -X POST /api/server/restart-local; done` → 3+ requests retornam 429

---

## D.4 — MERGED-006: Sync PC↔VM sem versionamento

**Severity**: 🟡 high · **Effort**: M · **Files**: `server.py:sync_loop`, `hermes_api_v2.py:/api/prospects` updates

### Análise

Sync PC pull a cada 60s. Edit local PC entre syncs → próximo sync sobrescreve com VM data → trabalho perdido silenciosamente.

### Solução

Cada prospect com `updated_at` + `version` int:
```sql
ALTER TABLE prospects ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE prospects ADD COLUMN updated_at REAL NOT NULL DEFAULT (julianday('now'));
```

Sync loop:
- Pull VM, comparar (vm.version, vm.updated_at) vs local
- Se local.version > vm.version → push local pra VM primeiro
- Se conflito (ambos modificados desde último sync) → marcar "conflict" + log + UI mostra

### Test

- Editar prospect no PC → editar mesmo no VM (via API direta) → sync detecta conflict
- Editar só PC → próximo sync push pra VM, mantém PC version

---

## Persistência Fase D 🔒

1. Mark chapter
2. memory_save
3. PLAN + GUARDRAILS
4. validate_implementation.py --phase D
5. push

---

# 🟢 FASE E — Features & Hardening (sprint, ~3+ commits)

---

## E.1 — MERGED-010: Channels Email/WhatsApp/Instagram stubs

**Severity**: 🟡 high · **Effort**: L (1 sprint) · **Files**: `channels/email/*`, `channels/whatsapp/*`, `channels/instagram/*`

### Análise

Daemon expõe P1-P7 multi-canal mas channels/ é `__init__.py` vazio.

### Solução

Implementar seguindo padrão LinkedIn. Per canal:
- `config.py` — rate limits, credentials path
- `limiter.py` — daily/weekly caps + warmup (canal-específico)
- `human.py` (se aplicável) — delays naturais
- `sender.py` — SMTP / WhatsApp Business API / Instagram Graph API

Prioridade do owner:
1. **Email** (SMTP via Gmail App Password) — mais simples, alto ROI
2. **WhatsApp** (WhatsApp Business API ou wppconnect/Baileys) — médio
3. **Instagram** (Graph API ou DM via Selenium — risco ban) — depois

Skills YAML novas: `email-outreach-generator`, `whatsapp-followup`, `instagram-engagement`.

### Approach

NÃO fazer 3 em paralelo. Sequencial: Email → testar 30 dias → WhatsApp → testar → Instagram.

### Persistência por canal

Cada canal completa = chapter próprio, memory save, GUARDRAILS atualizado com rate limits do canal.

---

## E.2 — MERGED-019: XSS Claude markdown sem allowlist

**Severity**: 🟢 low · **Effort**: S · **Files**: `dashboard/app.js` (markdown render do Claude page)

### Análise

Custom renderer faz `escapeHtml` mas allowlist de tags inline não definido. Theoreticamente Claude pode produzir markdown que escape → script tag injected → XSS contra próprio user.

Risco real: baixo (Claude output controlled by API, dashboard local). Mas vale fixar.

### Solução

Trocar custom renderer por DOMPurify após markdown parse:
```js
import DOMPurify from "dompurify";
const html = renderMarkdown(claudeOutput);
const safe = DOMPurify.sanitize(html, { ALLOWED_TAGS: [...], ALLOWED_ATTR: [...] });
container.innerHTML = safe;
```

### Test

- Injetar `<script>alert(1)</script>` em mock Claude response → não executa

---

## Persistência Fase E 🔒

Por canal (E.1): chapter, memory, PLAN, GUARDRAILS atualizado, validate.
Final (E.2): mark Phase E complete.

---

# 🎯 CHECK FINAL — Validation Harness

**Mecanismo automatizado pra detectar items pulados, mal implementados, ou regredidos.**

## Como funciona

Script `scripts/validate_implementation.py`:
```bash
# Validar tudo:
python scripts/validate_implementation.py

# Validar uma fase:
python scripts/validate_implementation.py --phase A

# Validar finding único:
python scripts/validate_implementation.py --finding MERGED-001

# Output JSON estruturado:
python scripts/validate_implementation.py --json > validation-report.json
```

Por finding, script executa **asserts concretos** (definidos em `.claude/VALIDATION-CHECKLIST.md`):
- grep no código pra confirmar mudança
- AST parse pra verificar estrutura
- curl em endpoints pra verificar comportamento
- sqlite query pra verificar schema
- subprocess pra rodar tests pequenos

Cada assert retorna `PASS` / `FAIL` / `SKIP` (skip se finding não aplica em ambiente atual).

## Output esperado

```
=== Hermes Implementation Validation ===
PHASE A (Security Critical)
  [PASS] MERGED-001 — WS handshake auth — server.py has 'await websocket.close(code=1008'
  [PASS] MERGED-002 — fail-closed AUTH — server.py raises if not AUTH_TOKEN
  [PASS] MERGED-003 — internal token + bind loopback — bind 127.0.0.1 + X-Internal-Token check

PHASE B (State & Robustness)
  [PASS] MERGED-005 — busy_timeout PRAGMA
  [FAIL] MERGED-004 — globals persistence — table campaign_runs NOT FOUND in command_center.db
        🚩 FLAG: re-implement MERGED-004 (lifespan reconciliation incompleto)
  [PASS] MERGED-015 — spawn() helper — 0 occurrences of bare asyncio.create_task
  ...

=== SUMMARY ===
PASS: 17 | FAIL: 2 | SKIP: 1
FLAGS RAISED:
  🚩 MERGED-004 — globals persistence — VM-side
  🚩 MERGED-010 — channels email — sender.py missing

Re-implementation needed. See VALIDATION-CHECKLIST.md for fix targets.
Exit code: 2
```

## Flag system

Se `validate` retorna FAIL em algum finding:
1. `validate_implementation.py --json` grava `validation-report.json`
2. Script `apply_flags.py` lê o report e:
   - Reabre task TaskCreate como `pending`
   - Edita PLAN.md desmarcando checkbox e adicionando 🚩 emoji
   - memory_save tipo `bug`: "MERGED-XXX regrediu: <reason>"
3. Owner (ou Claude) ataca o finding flag-ado e re-roda validate
4. Loop até `validate` ser 100% PASS

## Re-roda deep-audit no final

Após `validate_implementation.py` retornar 0:
```bash
node /path/to/hermes/.claude/workflows/deep-audit.js
```

Custo: 2-3M tokens. Resultado esperado: TOP findings mostra 0 dos MERGED-001..020 (todos fechados). Se algum aparecer, regressão detectada.

---

# 📋 Sequência de execução recomendada

```
Sessão dedicada (1 dia)
└── Fase A — security critical (3-4h)
    ├── Implementar A.1, A.2, A.3
    ├── validate --phase A
    ├── push
    └── memory + PLAN update

Sessão dedicada (3-5 dias)
└── Fase B — state & robustness
    ├── B.1..B.5 sequencial
    ├── validate --phase B
    └── push

Sessão arquitetural (1-2 semanas)
└── Fase C — architecture
    ├── C.1 (Settings) primeiro — habilitador
    ├── C.2 (IP via env)
    ├── C.3 (topology enforce)
    ├── C.5 (split monolitos) — iterativo, vários sub-commits
    ├── C.4, C.6
    ├── validate --phase C
    └── push

Sessão hardening (3-5 dias)
└── Fase D — infra
    ├── D.1..D.4
    ├── validate --phase D
    └── push

Sprint feature
└── Fase E — channels + xss
    ├── E.1 Email (sub-sprint)
    ├── E.1 WhatsApp (sub-sprint)
    ├── E.1 Instagram (sub-sprint)
    ├── E.2 XSS
    └── validate --all

Fim
└── Re-run deep-audit workflow
    └── Comparar findings vs original — esperado: MERGED-001..020 todos ausentes
```

---

# 📊 Estimativa total

| Fase | Effort | Sessões | Tokens estimados (sem workflows) |
|---|---|---|---|
| A | 4-6h | 1 | ~50k |
| B | 3-5 dias | 2-3 | ~150k |
| C | 1-2 semanas | 3-5 | ~400k |
| D | 3-5 dias | 1-2 | ~80k |
| E | 1 sprint | 4-6 | ~200k |
| Validation (recorrente) | - | - | ~10k/run |
| Re-run deep-audit | - | 1 | ~2.5M |

**Total**: ~3.5M tokens distribuídos ao longo de ~3-4 semanas. Não tudo em 1 sessão.

---

# 🔄 Como retomar este plano se contexto perdido

Procedimento canônico (cobre qualquer ponto da execução):

1. Read `.claude/IMPLEMENTATION-PLAN.md` (este arquivo)
2. Read `.claude/VALIDATION-CHECKLIST.md`
3. `python scripts/validate_implementation.py --json > /tmp/state.json`
4. Ler `/tmp/state.json` — primeiro FAIL é o próximo a atacar
5. `memory_smart_search "hermes phase implementation"` pra contexto histórico
6. Ler última seção do `.claude/PLAN.md` (estado da última sessão)

Persistência garantida em 5 camadas em todos os passos.
