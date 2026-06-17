-- H6 B15 — mcp_calls.caller_chapter traceability column
-- Cross-ref: HARDENING-F.FUTURE H6 / brain/dispatch.py / mcps/gateway/server.py
-- Idempotent: try/except OperationalError in core/state.py + gateway build_app().
--
-- WHY: requester='brain-f4' workaround (D7 PIVOT F.4.2) encodes chapter in
-- mcp_calls.requester string. This column separates concerns:
--   requester = WHO called (brain/cli/auto_skill_runner/cobaia)
--   caller_chapter = WHICH phase owns this invocation (F.4/F.7/F.9/etc)
-- Allows JOIN cost aggregate by phase without LIKE 'brain-f%' hacks.

ALTER TABLE mcp_calls ADD COLUMN caller_chapter TEXT NULL;
CREATE INDEX IF NOT EXISTS idx_mcp_calls_caller_chapter ON mcp_calls(caller_chapter);
