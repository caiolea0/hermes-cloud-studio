-- F.9.4 — Pipeline clone audit + A/B compare metrics
-- Cross-ref: .claude/PLAN.md § "F.9.4 Decisões Cristalizadas" D1/D3/D4
--
-- D1: cloned_from_id audit trail on pipeline_drafts (server-side atomic clone)
-- D3: ab_group on pipeline_runs_granular (stored per-row for direct GROUP BY aggregate)
--
-- Apply PC (once):
--   python scripts/run_migration.py migrations/2026_06_pipeline_clone_ab_compare.sql
-- OR manual:
--   python -c "
--   import sqlite3; db=sqlite3.connect('hermes_local.db')
--   try: db.execute('ALTER TABLE pipeline_drafts ADD COLUMN cloned_from_id TEXT NULL REFERENCES pipeline_drafts(id)')
--   except: pass
--   try: db.execute('ALTER TABLE pipeline_runs_granular ADD COLUMN ab_group TEXT NULL CHECK(ab_group IS NULL OR ab_group IN (\"A\",\"B\"))')
--   except: pass
--   db.commit(); db.close()
--   sqlite3 hermes_local.db 'CREATE INDEX IF NOT EXISTS idx_pipeline_runs_granular_ab_group ON pipeline_runs_granular(ab_group) WHERE ab_group IS NOT NULL'
--   "
--
-- Apply VM: same pattern via ssh
-- Idempotente: CREATE INDEX IF NOT EXISTS (ALTER TABLE fails silently if column exists)

-- 1) Clone audit trail
ALTER TABLE pipeline_drafts ADD COLUMN cloned_from_id TEXT NULL REFERENCES pipeline_drafts(id);

-- 2) A/B group per run-row (stored on step rows for direct GROUP BY without join)
ALTER TABLE pipeline_runs_granular ADD COLUMN ab_group TEXT NULL
    CHECK(ab_group IS NULL OR ab_group IN ('A', 'B'));

-- 3) Indexes for aggregate performance (idempotent)
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_granular_ab_group
    ON pipeline_runs_granular(ab_group) WHERE ab_group IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_pipeline_drafts_cloned_from
    ON pipeline_drafts(cloned_from_id) WHERE cloned_from_id IS NOT NULL;
