-- F.5.3 Commit 1 — mcp_registry table (source-of-truth MCPs declarados Hermes)
-- Schema SQLite (NÃO Postgres). JSON arrays como TEXT serializado.
-- Idempotente via CREATE TABLE IF NOT EXISTS + ON CONFLICT seed script.
-- Cross-ref: .claude/MCP-ENFORCEMENT-STRATEGY.md section 5.2 + PLAN.md F.5.3 D3.

CREATE TABLE IF NOT EXISTS mcp_registry (
    server          TEXT PRIMARY KEY,
    tools           TEXT,                              -- JSON array string SQLite
    status          TEXT NOT NULL DEFAULT 'active',    -- active/pending/reserved/deprecated/quarantine
    chapter_owner   TEXT NOT NULL,                     -- F.5.2, F.5.6, etc
    required_by_dc  TEXT,                              -- JSON array string: ["F.6","F.7","F.4"]
    tier            TEXT NOT NULL DEFAULT 'active',    -- active/warning/deprecated/quarantine/orphan/drift/reserved
    oauth_required  INTEGER NOT NULL DEFAULT 1,        -- 0/1 boolean SQLite
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mcp_registry_status ON mcp_registry(status);
CREATE INDEX IF NOT EXISTS idx_mcp_registry_tier ON mcp_registry(tier);
CREATE INDEX IF NOT EXISTS idx_mcp_registry_chapter ON mcp_registry(chapter_owner);
