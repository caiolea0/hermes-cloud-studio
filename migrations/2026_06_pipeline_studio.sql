-- F.9.1 — Pipeline Studio Visual backend foundation
-- Cross-ref: .claude/PLAN.md § "F.9 Decisões Cristalizadas" D2 (TABLE DEDICADA pipeline_drafts)
-- D2: NÃO YAML files (perde query SQL + version). CRUD REST + versionamento auto + ab_group nullable.
-- D3: pipeline_runs_granular FK pipeline_drafts(id) — engine F.9.2 executor grava per-step.
--
-- Apply PC:  python -c "import sqlite3; sqlite3.connect('hermes_local.db').executescript(open('migrations/2026_06_pipeline_studio.sql','r',encoding='utf-8').read())"
-- Apply VM:  sqlite3 ~/.hermes/data/command_center.db < migrations/2026_06_pipeline_studio.sql
-- Idempotente: CREATE IF NOT EXISTS.

-- 1) pipeline_drafts — owner-built pipelines source-of-truth
-- D2 columns extended: + updated_at + last_executed_at + status + description + tags + ab_group
CREATE TABLE IF NOT EXISTS pipeline_drafts (
    id                  TEXT PRIMARY KEY,                 -- UUID
    name                TEXT NOT NULL,
    description         TEXT,
    yaml_blob           TEXT NOT NULL,                    -- pipeline YAML serialized
    version             INTEGER NOT NULL DEFAULT 1,       -- auto-increment on UPDATE
    status              TEXT NOT NULL DEFAULT 'draft'
                        CHECK(status IN ('draft', 'active', 'archived')),
    tags                TEXT,                             -- JSON array TEXT
    ab_group            TEXT
                        CHECK(ab_group IS NULL OR ab_group IN ('A', 'B')),
    owner               TEXT NOT NULL DEFAULT 'caio',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_executed_at    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pipeline_drafts_status_updated
    ON pipeline_drafts(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_drafts_ab_group
    ON pipeline_drafts(ab_group) WHERE ab_group IS NOT NULL;

-- 2) pipeline_runs_granular — F.9.2 executor grava per-step
-- D3: cost_credits column (REUSE F.8.1 mcp_calls cost tracking pattern)
CREATE TABLE IF NOT EXISTS pipeline_runs_granular (
    run_id           TEXT NOT NULL,
    draft_id         TEXT NOT NULL REFERENCES pipeline_drafts(id),
    step_idx         INTEGER NOT NULL,
    step_name        TEXT NOT NULL,
    tool_invoked     TEXT,
    status           TEXT NOT NULL
                     CHECK(status IN ('pending', 'running', 'completed', 'error', 'skipped')),
    output_json      TEXT,                                -- truncated 2000 chars (F.6.3 D6 pattern)
    error            TEXT,
    started_at       TIMESTAMP,
    ended_at         TIMESTAMP,
    latency_ms       INTEGER,
    cost_credits     REAL DEFAULT 0,
    PRIMARY KEY (run_id, step_idx)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_granular_draft_time
    ON pipeline_runs_granular(draft_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_granular_run
    ON pipeline_runs_granular(run_id, step_idx);
