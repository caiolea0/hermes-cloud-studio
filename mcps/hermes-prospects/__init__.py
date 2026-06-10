"""hermes-prospects custom MCP — F.5.2 scaffold.

CRUD + scoring sobre tabela prospects.
- 6 tools delegam reads complexos pra Postgres MCP Pro via gateway (D3 strict)
  com fallback SQLite local até F.5.6 plug Postgres MCP.
- 1 tool scoring (Python local determinístico — NUNCA delega).
"""
