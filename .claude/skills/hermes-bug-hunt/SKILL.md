---
name: hermes-bug-hunt
description: Code-review focado em problemas conhecidos do Hermes — race conditions nos 5 loops, auth gaps (WS sem token), bug import `time`, SQL injection em endpoints `/api/prospects` query, vazamento de tokens em logs. Trigger: "varrer bugs hermes", "code-review hermes", "/hermes-bug-hunt".
---

# /hermes-bug-hunt — Varredura bugs Hermes

## Dimensoes obrigatorias

Sempre rodar TODAS as 5 dimensoes, na ordem:

### 1. Race conditions nos 5 loops async
Arquivo: `server.py`

5 loops em `lifespan`:
- `sync_loop` (60s)
- `linkedin_sync_loop` (10s)
- `linkedin_scheduler_loop` (30s)
- `linkedin_health_monitor_loop` (adaptive)
- `linkedin_session_monitor_loop` (1h)

Verificar:
- [ ] Loops compartilham estado mutavel? (`_running_linkedin_campaigns`, `_LI_SESSION_LAST_OK`)
- [ ] Sem `asyncio.Lock` em writes concorrentes?
- [ ] WS broadcast pode ser chamado de N loops simultaneo?
- [ ] Cancelacao gracefully?

### 2. Auth gaps
- [ ] `/ws` sem `X-Hermes-Token` — exposto local mas ainda gap
- [ ] Endpoints `/api/internal/*` validacao de origem (so VM deveria poder POSTar)
- [ ] Token em log file? `grep -ri "$env:HERMES_AUTH_TOKEN" logs/`
- [ ] CORS wildcard `*` em prod?

### 3. SQL injection
Endpoints que aceitam filtros usuario:
- `/api/prospects?city=X&category=Y` — sao parametros bind ou interpolados?
- `/api/activities?type=X` — idem
- Qualquer custom query exposta

Comando rapido:
```
grep -nE "execute\(.*f['\"]|execute\(.*%s|execute\(.*\.format" server.py hermes_api_v2.py
```

### 4. Bug conhecido `time.time()`
Local: `server.py:698, 722`
Checar: `import time` no topo. Se ausente, adicionar.
```
grep -n "^import time\|^from time" server.py
grep -n "time\.time\|time\.sleep" server.py
```

### 5. Leakage / cleanup
- [ ] Subprocess `Popen` sempre tem `terminate()` no shutdown?
- [ ] DB connections fechadas? `WAL` mode persiste `-shm`/`-wal`?
- [ ] Photo cache (`photo_cache/`) tem TTL ou cresce indefinidamente?
- [ ] `_running_linkedin_campaigns` limpo apos campanha terminar?
- [ ] Subprocess scraper (`gosom_scraper.py`) — orfao se VM reiniciar?

## Output esperado

```
HERMES BUG HUNT — {timestamp}

DIMENSION 1 — Race conditions
  [ID-001] server.py:XYZ — descricao + fix sugerido
  ...

DIMENSION 2 — Auth gaps
  ...

(repete por dimensao)

SUMARIO:
- Critical: N
- High: N
- Medium: N
- Low: N

Priorizado:
1. {bug-id} — {fix em N min}
2. ...
```

## Quando rodar
- Antes de qualquer release
- Apos refactor grande em `server.py` ou `hermes_api_v2.py`
- Manual: 1x por semana

## Integracao
- Se achar Critical: criar task `Fix {bug-id}` via TaskCreate
- Persistir relatorio em `.claude/BUG-HUNT-{YYYY-MM-DD}.md`
- Memory save tipo `bug` por finding critico
