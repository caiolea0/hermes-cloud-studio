---
description: Restart servico Hermes (local server.py, VM api, ou ambos)
argument-hint: "[local|vm|all]"
---

Restart via MCP `hermes-control server_restart(target=...)`. Sem MCP, fallback pra POST /api/server/restart-{target}.
Pausa daemon antes se for restart-all.
