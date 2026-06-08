# hermes-control MCP

MCP server que expõe o backend Hermes Cloud Studio como **tools de linguagem natural** pro Claude.

Em vez de você dizer "faz um POST em `/api/daemon/pause`", você diz "pausa o daemon" e o Claude chama a tool certa.

## Tools disponíveis (16)

| Tool | Pra quê |
|---|---|
| `hermes_status` | Snapshot saúde PC+VM+LI+daemon |
| `list_prospects` | Filtros city/category/stage/score |
| `daemon_state` | Estado P1-P7, fila, circuit breakers |
| `daemon_control` | Pause/resume daemon |
| `li_health` | Session, rate-limits, warm-up day |
| `li_rate_limits` | Limites diários LinkedIn |
| `li_campaigns` | Campanhas running/scheduled/done |
| `activities` | Activity log paginado |
| `pipeline_list` | Templates + executions recentes |
| `pipeline_execute` | Roda pipeline por ID |
| `scraper_status` | Estado do scraper Google Maps |
| `scraper_start` | Inicia scraper |
| `audit_start` | Batch audit (web scoring) |
| `skills_list` | Skills YAML do Hermes Agent |
| `skill_toggle` | Ativa/desativa skill |
| `server_restart` | Restart local/vm/all |

## Setup

```powershell
cd mcps/hermes-control
npm install
npm run build
```

## Configuração no `.mcp.json` raiz

```json
{
  "mcpServers": {
    "hermes-control": {
      "type": "stdio",
      "command": "node",
      "args": ["./mcps/hermes-control/dist/index.js"],
      "env": {
        "HERMES_API_URL": "http://localhost:8500",
        "HERMES_AUTH_TOKEN": "${HERMES_AUTH_TOKEN}"
      }
    }
  }
}
```

`HERMES_AUTH_TOKEN` precisa bater com o do `.env` da raiz do projeto.

## Smoke test

Com server.py rodando (`python server.py`):

```powershell
# build + run direto
npm run dev
# stderr: [hermes-control] MCP server listening (API=http://localhost:8500)
```

Pra testar fluxo MCP completo, restart Claude Code no projeto — server aparece em `/mcp`.

## Adicionar tool nova

1. Add objeto em `TOOLS[]` em `src/index.ts` com `name`, `description`, `inputSchema` (Zod), `handler`
2. `npm run build`
3. Restart MCP no Claude Code

## Roadmap

- v0.2: tools de DB query read-only (`query_prospects_db`)
- v0.2: `deploy_vm` com SSH dry-run + rsync
- v0.3: streaming/SSE pra acompanhar campanhas em real-time
- v0.3: tools de memory CRUD (proxy pra AgentMemory)
