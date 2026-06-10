# hermes-linkedin MCP

**Status**: F.5.2 scaffold · **Version**: 0.1.0-f5.2 · **Owner chapter**: F.7

Wrapper FastMCP 3.0 sobre `linkedin/*` modules. **NÃO modifica** nenhum file
BLACKLIST R2 (stealth/human/limiter/cooldown/preflight/account_profile/config/
stealth_compliance/ollama_router/db_utils). APENAS importa e wrap.

## Tools (8)

| Tool | Wraps | Plano |
|---|---|---|
| `get_health(force_refresh)` | `linkedin.cooldown.check_health` | Cache 5min OK, probe se forçado |
| `get_rate_limits(account_id)` | `RateLimiter.get_stats` | Capacidade + uso 24h/7d |
| `get_warmup_status(account_id)` | `RateLimiter.warmup_*` | Dia warmup + multiplicador por action |
| `get_account_profile(account_id)` | `AccountProfile.load` | Sticky session + burned flag |
| `assert_account_safe(account_id)` | `assert_not_burned` | Boolean safety check |
| `preflight_check(proxy_url)` | `preflight.assert_tunnel_healthy` | Datacenter IP gate |
| `probe_cooldown()` | `cooldown.probe_linkedin` | Probe ativo /feed/ via SOCKS5 |
| `start_campaign(type, config)` | Control plane handle | Echo config (campaign exec via VM API) |

## Sanitize

TODA response passa por `_sanitize()` que mascara keys sensíveis:
`li_at, token, cookie, password, auth, jsessionid, csrf, api_key, secret,
bearer, li_rm, lidc, bcookie, bscookie, x-li-track, liap, usermatchhistory,
analyticssynchistory` (mesmo pattern F.3.2 `linkedin/lab/_event_emit.py`
defense-in-depth — F.3.2 reviewer note 2a).

## Auth

OAuth 2.1 JWT validation via gateway (F.5.1 scaffold). Bypass loopback dev
(`HERMES_STRICT_MCP` não setado). Strict mode VM prod requires Bearer token
ENV `HERMES_GATEWAY_OAUTH_SECRET`. Rotação manual mensal (D5).

## Run

```bash
# Stdio (default, gateway dispatches)
python mcps/hermes-linkedin/server.py

# HTTP local (dev/debug)
HERMES_MCP_TRANSPORT=http python mcps/hermes-linkedin/server.py
# → http://127.0.0.1:55411

# Via gateway dispatch (F.5.3 wires real call)
curl -X POST http://localhost:55401/dispatch/hermes-linkedin/get_health \
  -H "Authorization: Bearer $HERMES_GATEWAY_OAUTH_SECRET"
```

## Smoke

```bash
python mcps/hermes-linkedin/_smoke.py
```

Verifica importabilidade de cada tool + schema sanity SEM invocar LinkedIn
real (fixture mode `HERMES_MCP_FIXTURE=1`). Smoke E2E real roda VM (F.5.4+).

## BLACKLIST R2 verify

Pós-commit:

```bash
git diff HEAD~1 --name-only linkedin/ | grep -v __pycache__
# Esperado: ZERO output (BLACKLIST R2 INTACTO)
```

## Cross-refs

- `mcps/gateway/config.yaml` upstream `hermes-linkedin` status active
- `.mcp.json` mcpServers entry
- `.claude/PLAN.md` § F.5.2 D1-D8 decisões cristalizadas
- `.claude/GUARDRAILS.md` § BLACKLIST R2 + § F.5 MCP Ecosystem
