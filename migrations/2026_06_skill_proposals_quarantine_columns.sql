-- F.4.4 C2 — Quarantine columns for skill_proposals (W8 proper migration file).
-- Cross-ref: .claude/PLAN.md § F.4.4 C2 D5 + core/skill_proposals.py _ensure_quarantine_columns().
--
-- SQLite does NOT support IF NOT EXISTS for ALTER TABLE ADD COLUMN.
-- Apply idempotently via Python helper (recommended):
--   python -c "
--     import sqlite3
--     from core.skill_proposals import _ensure_quarantine_columns
--     conn = sqlite3.connect('hermes_local.db')
--     _ensure_quarantine_columns(conn)
--     conn.close()
--   "
-- VM apply (run Python helper on VM — raw SQL will error on second run):
--   ssh hermes-gcp@136.115.74.69 'python3 -c "
--     import sqlite3, sys; conn = sqlite3.connect(\"~/.hermes/data/command_center.db\")
--     for col in [(\"quarantine_reason\",\"TEXT\"),(\"quarantine_at\",\"TEXT\")]:
--         try: conn.execute(\"ALTER TABLE skill_proposals ADD COLUMN {} {} NULL\".format(*col)); conn.commit()
--         except: pass
--   "'

ALTER TABLE skill_proposals ADD COLUMN quarantine_reason TEXT NULL;
ALTER TABLE skill_proposals ADD COLUMN quarantine_at TEXT NULL;

-- Partial index for fast quarantine queries
CREATE INDEX IF NOT EXISTS idx_skill_proposals_quarantine
    ON skill_proposals(quarantine_at)
    WHERE quarantine_at IS NOT NULL;

-- PC sync_loop limitation note (W8):
-- hermes_local.db (PC mirror) does NOT receive quarantine_reason/quarantine_at via
-- the standard 60s sync_loop because server.py only syncs prospects + activities tables.
-- Quarantine state is authoritative on VM (command_center.db).
-- PC reads quarantine state only via /api/hermes/skills proxy to VM.
-- This is a known architectural limitation; fix would require extending sync_loop
-- to include skill_proposals table — deferred to F.7+ scope.
