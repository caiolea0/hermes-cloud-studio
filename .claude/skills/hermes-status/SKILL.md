---
name: hermes-status
description: Snapshot completo de saude do Hermes — PC backend, VM backend, LinkedIn health/rate-limits, daemon state, ultimos erros. Use no inicio de sessao Hermes ou quando algo parecer travado. Trigger: "status hermes", "como ta hermes", "/hermes-status".
---

# /hermes-status — Snapshot saude

## Quando disparar
- Inicio de sessao Hermes
- Apos restart de servico
- Quando user reporta "nao ta funcionando"
- Antes de iniciar campanha LinkedIn

## Procedimento

Preferir MCP `hermes-control` se disponivel:
```
hermes_status()         # agrega PC+VM+LI+daemon
li_rate_limits()        # snapshot limites do dia
activities(limit=10)    # ultimos 10 eventos
```

Fallback (sem MCP) — chamadas diretas via curl:
```powershell
curl -H "X-Hermes-Token: $env:HERMES_AUTH_TOKEN" http://localhost:8500/api/hermes/status
curl -H "X-Hermes-Token: $env:HERMES_AUTH_TOKEN" http://localhost:8500/api/daemon/state
curl -H "X-Hermes-Token: $env:HERMES_AUTH_TOKEN" http://localhost:8500/api/linkedin/health
```

## Output esperado (formato canonico)

```
HERMES STATUS — {YYYY-MM-DD HH:MM}

PC backend (:8500)   : {ok|degraded|down} — {detalhes}
VM backend (:8420)   : {ok|degraded|down} — last sync {Xs} ago
Daemon orchestrator  : {running|paused|circuit-broken} P{1-7} ativa
LinkedIn session     : {ok|challenge|cooldown|blocked} — warm-up day {X}/14
Rate limits hoje     : views {X}/70 · connects {Y}/30 · comments {Z}/{lim}
Working hours        : {dentro|fora} (Cuiaba {HH-HH})

Ultimos eventos:
- {timestamp} {tipo} {summary}
- ...

Alertas:
- {se houver: cooldown, challenge, erros recentes}
```

## Anti-padroes
- Nao rodar audit/scraper se status mostrar circuit-broken
- Nao iniciar campanha LI se session != ok
- Nao mexer em rate-limits manualmente — sao lei
