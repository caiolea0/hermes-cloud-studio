-- F.5.3 Commit 1 — mcp_calls table (S2 coluna vertebral coverage tracker)
-- Cross-ref: .claude/MCP-ENFORCEMENT-STRATEGY.md section 4.1 + PLAN.md F.5.3 D4.
-- Append-only audit trail. args/response truncados 10KB no INSERT (sanitize sensíveis pré-store).

CREATE TABLE IF NOT EXISTS mcp_calls (
    id           TEXT PRIMARY KEY,         -- UUID string
    server       TEXT NOT NULL,
    tool         TEXT NOT NULL,
    args         TEXT,                     -- JSON string (truncated 10KB, sanitized)
    response     TEXT,                     -- JSON string (truncated 10KB)
    error        TEXT,                     -- NULL se success
    duration_ms  INTEGER,
    requester    TEXT,                     -- 'brain' / 'cli' / 'api' / 'gateway' / etc
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mcp_calls_server_tool_time ON mcp_calls(server, tool, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mcp_calls_created_at ON mcp_calls(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mcp_calls_requester ON mcp_calls(requester);
