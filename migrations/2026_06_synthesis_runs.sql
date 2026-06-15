-- F.4.2 C3 — synthesis_runs table (PIVOT D6 honest scaffold backing store).
-- Cross-ref: .claude/PLAN.md § F.4.2 C3 (PIVOT D6 cristalizado 2026-06-15).
--
-- Backing store for AutoSkillRunner.trigger_workflow_synthesis() scaffold.
-- F.4.2 C3 persists 'queued' rows only; F.4.6 NOVA wires PATH 2 subprocess
-- consumer that transitions rows queued → running → completed | failed.

CREATE TABLE IF NOT EXISTS synthesis_runs (
    id              TEXT PRIMARY KEY,           -- UUID string
    trigger_type    TEXT NOT NULL,              -- 'manual' | 'cron'
    status          TEXT NOT NULL,              -- 'queued' | 'running' | 'completed' | 'failed'
    queued_at       TEXT NOT NULL,              -- ISO-8601 UTC
    requester       TEXT NOT NULL,              -- F4_REQUESTER='brain-f4' (D7 PIVOT)
    trigger_source  TEXT NOT NULL               -- 'api_manual' | 'ui_button' | 'cron_auto' | 'subprocess_path2'
);

CREATE INDEX IF NOT EXISTS idx_synthesis_runs_status ON synthesis_runs(status);
CREATE INDEX IF NOT EXISTS idx_synthesis_runs_queued_at ON synthesis_runs(queued_at);
