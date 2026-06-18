-- Phase 5: owner_verified gate for cobaia activation safety.
-- Prevents auto_skill_runner from creating GitHub PRs for unverified skills.
-- Idempotent via TRY/CATCH-equivalent (will fail silently if columns exist).

ALTER TABLE skill_proposals ADD COLUMN owner_verified INTEGER DEFAULT 0;
ALTER TABLE skill_proposals ADD COLUMN allowed_mcps TEXT;
ALTER TABLE skill_proposals ADD COLUMN verified_at TEXT;
ALTER TABLE skill_proposals ADD COLUMN verified_by TEXT;
ALTER TABLE skill_proposals ADD COLUMN verification_notes TEXT;
ALTER TABLE skill_proposals ADD COLUMN awaiting_verify_since TEXT;

CREATE INDEX IF NOT EXISTS idx_skill_proposals_verified ON skill_proposals(owner_verified);
