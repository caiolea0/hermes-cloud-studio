-- F.4.4 C1 — skill_sync_runs table (webhook + manual sync audit trail).
-- Cross-ref: .claude/PLAN.md § F.4.4 C1 D6 (WS + DB fanout).
--
-- Backing store for api/skills_webhook.py POST /api/skills/webhook/pr-merged.
-- Each GitHub PR-merged webhook that triggers a skills/ git sync inserts one row.
-- Trigger type 'manual' reserved for future /api/skills/webhook/sync-now endpoint.

CREATE TABLE IF NOT EXISTS skill_sync_runs (
    id              TEXT PRIMARY KEY,           -- UUID string
    trigger_type    TEXT NOT NULL,              -- 'webhook' | 'manual'
    pr_number       INTEGER NULL,               -- GitHub PR number (null for manual)
    pr_url          TEXT NULL,                  -- PR HTML URL (null for manual)
    sync_status     TEXT NOT NULL,              -- 'started' | 'completed' | 'conflict_manual' | 'failed'
    started_at      TEXT NOT NULL,              -- ISO-8601 UTC
    completed_at    TEXT NULL,                  -- NULL while in-progress
    error_message   TEXT NULL,                  -- populated on conflict_manual or failed
    affected_skills TEXT NULL                   -- JSON array of skill names from git diff
);

CREATE INDEX IF NOT EXISTS idx_skill_sync_runs_status
    ON skill_sync_runs(sync_status);

CREATE INDEX IF NOT EXISTS idx_skill_sync_runs_started_at
    ON skill_sync_runs(started_at);
