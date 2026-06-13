-- F.6.4 — brain_runs ADD COLUMN owner_comment (optional 500-char owner approve/deny note).
-- Cross-ref: .claude/PLAN.md § F.6.4 Decisões D2 (approve/deny + optional comment).
--
-- Idempotent guard: PRAGMA pre-check via Python (server.py lifespan) — SQLite ALTER TABLE
-- não suporta IF NOT EXISTS direto em ADD COLUMN. Lifespan wrap em try/except OperationalError.
--
-- Apply VM: sqlite3 ~/.hermes/data/command_center.db < migrations/2026_06_brain_runs_owner_comment.sql
-- Apply PC: server.py lifespan idempotent (catches "duplicate column name" silently).

ALTER TABLE brain_runs ADD COLUMN owner_comment TEXT;
