-- F.4.x WARNs C2 — W3: X-GitHub-Delivery dedup column for skill_sync_runs.
-- Cross-ref: .claude/PLAN.md § F.4 WARNs W3.
--
-- GitHub retries a webhook delivery on timeout / 5xx → two rows with same payload.
-- delivery_id = X-GitHub-Delivery header (UUID per delivery, same on retry).
-- Partial UNIQUE index: allows multiple NULL rows (legacy/manual triggers) but
-- enforces uniqueness on non-NULL delivery_ids.
--
-- Idempotent: CREATE IF NOT EXISTS + ALTER handled via _ensure_delivery_id_column().
-- Apply via: python -c "
--   from core.skill_proposals import ensure_skill_sync_runs_table
--   ensure_skill_sync_runs_table()
-- "
-- (ensure_skill_sync_runs_table() now calls _ensure_delivery_id_column() internally)

-- Raw SQL (run once — fails on second run if column exists):
ALTER TABLE skill_sync_runs ADD COLUMN delivery_id TEXT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_sync_runs_delivery_id
    ON skill_sync_runs(delivery_id)
    WHERE delivery_id IS NOT NULL;
