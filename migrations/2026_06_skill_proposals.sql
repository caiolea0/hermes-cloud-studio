-- F.4.1 — Auto-Skill Loop W3 + GitHub PR deploy backend foundation
-- Cross-ref: .claude/PLAN.md § "F.4 Decisões Cristalizadas" D7 + D8
-- D7: hermes-skill-forge-runner skill EXTEND existing (NÃO redesign).
-- D8: dual source-of-truth — skill_proposals (workflow staging) + skills/ git (production).
--
-- Apply PC: python -c "import sqlite3; sqlite3.connect('hermes_local.db').executescript(open('migrations/2026_06_skill_proposals.sql','r',encoding='utf-8').read())"
-- Apply VM: sqlite3 ~/.hermes/data/command_center.db < migrations/2026_06_skill_proposals.sql
-- Idempotente: CREATE IF NOT EXISTS.

-- 1) skill_proposals — workflow staging (proposal → lab → PR → owner approve → merge → deployed)
-- Lifecycle: draft → lab_running → lab_passed|lab_failed → pr_open → pr_merged|pr_rejected → deployed|archived
CREATE TABLE IF NOT EXISTS skill_proposals (
    id                       TEXT PRIMARY KEY,                 -- UUID
    name                     TEXT NOT NULL,
    description              TEXT,
    source_pattern           TEXT,                              -- 'activity_30d_pattern' | 'owner_manual' | 'brain_observation'
    yaml_blob                TEXT NOT NULL,                     -- proposed skill YAML serialized
    lab_test_result          TEXT,                              -- JSON {status, stdout, stderr, latency_ms, exit_code}
    lab_test_status          TEXT NOT NULL DEFAULT 'pending'
                             CHECK(lab_test_status IN ('pending', 'passed', 'failed', 'skipped')),
    pr_url                   TEXT,                              -- F.4.2: GitHub PR URL after mcp.github.create_pull_request
    pr_branch                TEXT,                              -- F.4.2: 'skill/proposal-{id}'
    pr_status                TEXT NOT NULL DEFAULT 'not_created'
                             CHECK(pr_status IN ('not_created', 'open', 'merged', 'closed_rejected')),
    status                   TEXT NOT NULL DEFAULT 'draft'
                             CHECK(status IN ('draft', 'lab_running', 'lab_passed', 'lab_failed',
                                              'pr_open', 'pr_merged', 'pr_rejected', 'deployed', 'archived')),
    owner_decision_at        TIMESTAMP,
    owner_decision_reason    TEXT,
    cost_credits             REAL DEFAULT 0,                    -- D2: Brain synth cost via mcp_calls aggregate
    created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_skill_proposals_status_updated
    ON skill_proposals(status, updated_at DESC);

-- 2) skill_runs — runtime invocation history (F.4 cron daily 09h BRT analyzer + D6 quarantine threshold)
-- D6: success_rate < 0.5 last 10 runs → quarantine signal.
CREATE TABLE IF NOT EXISTS skill_runs (
    id                  TEXT PRIMARY KEY,                       -- UUID
    skill_name          TEXT NOT NULL,                          -- references skills/*.yaml filename basename
    invocation_context  TEXT,                                   -- JSON Brain.decide() args
    status              TEXT NOT NULL
                        CHECK(status IN ('pending', 'running', 'completed', 'error', 'timeout')),
    output_json         TEXT,                                   -- truncated 2000 chars (F.6.3 D6 pattern)
    error               TEXT,
    latency_ms          INTEGER,
    cost_credits        REAL DEFAULT 0,
    requester           TEXT,                                   -- 'brain' | 'owner' | 'cron' | 'pipeline'
    started_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at            TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_skill_runs_skill_started
    ON skill_runs(skill_name, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_skill_runs_status
    ON skill_runs(status, started_at DESC);
