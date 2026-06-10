# Hermes ContextForge Gateway (F.5.1 scaffold)

> **Status**: F.5.1 scaffold — placeholder gateway. F.5.2 entrega real upstream MCPs dispatch.
> **Bind**: `127.0.0.1:55401` (loopback only, VM-side)
> **Framework**: FastMCP 3.0 (picked over IBM ContextForge — rationale below)

## Por que FastMCP 3.0 (e não IBM ContextForge)

Survey 2026-06-10 (WebSearch):

| Framework | Status Junho 2026 | Decisão F.5.1 |
|-----------|-------------------|---------------|
| **FastMCP 3.0** | GA Feb 2026 · 3.4.2 estável · 4M dl/dia · OAuth+OTel built-in · `pip install fastmcp` | ✅ **PICKED** |
| IBM ContextForge | 1.0.0 GA Feb 2026 · Docker proxy separado · 1.2.0 open Jun 4 · setup pesado | ⏳ defer F.5.6+ |

**Rationale**: FastMCP é framework Python in-process — instala via pip, integra com FastAPI existente, OAuth 2.1 + OpenTelemetry tracing já built-in. Mais simples pra owner solo no-code manter. ContextForge é gateway Docker container completo — bom pra enterprise multi-tenant, overkill pra single-VM Hermes. Se F.5.6 precisar multiplex >10 MCPs públicos com rate-limit por tenant, revisitar ContextForge sem refactor (FastMCP exporta tools via SSE/HTTP padrão MCP).

Sources:
- [FastMCP 3.0 GA blog post](https://jlowin.dev/blog/fastmcp-3-launch)
- [IBM ContextForge releases](https://github.com/IBM/mcp-context-forge/releases)

## Endpoints (F.5.1 minimal surface)

| Endpoint | Auth | Função |
|----------|------|--------|
| `GET /health` | none | startup gate probe (hermes_api_v2 lifespan) |
| `GET /tools` | OAuth (bypass loopback dev) | lista tools registrados (F.8 + F.9 consumer) |
| `GET /upstream` | OAuth | config.yaml upstream + public planned |
| `GET /audit-log?limit=100` | OAuth | tail JSONL audit log (F.5.2 popula) |
| `POST /dispatch/{server}/{tool}` | OAuth | F.5.1 returns 503 — F.5.2 wires real |

## Auth model

```
┌─────────────────────────────────────────────────────────────────┐
│ Default (dev local, HERMES_STRICT_MCP unset):                  │
│   localhost loopback request → bypass OAuth                    │
│   non-loopback → 401 Bearer required                           │
│                                                                 │
│ Strict (VM prod, HERMES_STRICT_MCP=1):                         │
│   ALL requests → 401 unless Authorization: Bearer $SECRET      │
│   F.5.2 substitui Bearer estático por JWT per-MCP audience     │
└─────────────────────────────────────────────────────────────────┘
```

## Run local (dev)

```bash
# PC dev (smoke test only — production roda VM):
cd D:/dev-projects/main/hermes-cloud-studio
pip install -r requirements.txt
python -m mcps.gateway.server
# → starts http://127.0.0.1:55401
curl http://127.0.0.1:55401/health
```

## Deploy VM

F.5.1 deploy via SCP + nohup. F.5.6+ promove a systemd unit.

```bash
# PC:
scp -r mcps/gateway hermes-gcp@136.115.74.69:~/.hermes/mcps/

# VM:
ssh hermes-gcp@136.115.74.69
pip3 install --user fastmcp PyYAML
cd ~/.hermes/mcps
nohup python3 -m gateway.server > ~/.hermes/logs/gateway.log 2>&1 &
curl http://127.0.0.1:55401/health
```

## NÃO implementado em F.5.1 (by design)

- ❌ Real upstream MCP dispatch — `POST /dispatch/...` returns 503. **F.5.2 entrega.**
- ❌ `mcp_calls` audit DB writes — **F.6 entrega via `ToolRegistry.invoke()` middleware**
- ❌ OAuth 2.1 JWT token issuance — **F.5.2 entrega quando primeiro custom MCP precisar**
- ❌ `mcp_registry` table seed — **F.5.3 entrega**
- ❌ `validate_implementation.py phase F` — **F.5.4 entrega**
- ❌ Public MCPs integration (GitHub/Sentry/Postgres/Playwright/Omnisearch/Hunter) — **F.5.6 entrega**

## Files

| File | Função |
|------|--------|
| `__init__.py` | re-export `build_app`, `GATEWAY_VERSION` |
| `server.py` | FastAPI app + endpoints (`/health`, `/tools`, `/upstream`, `/audit-log`, `/dispatch/*`) |
| `config.yaml` | Upstream MCPs declarativo (3 custom placeholders + 6 public planned) |
| `README.md` | Este arquivo |

## Cross-refs

- `.claude/MCP-ENFORCEMENT-STRATEGY.md` § 1, 4 (S2+S1+S3 combo)
- `.claude/PLAN.md` Chapter F.5 done_criteria
- `.claude/GUARDRAILS.md` § "🧰 MCP usage coverage"
- AgentMemory `mem_mq7jalw7` — decisão canônica MCP enforcement
