-- H1 B7: Adiciona events_jsonl_path a lab_runs para rastrear onde events foram persistidos.
-- Idempotente: SQLite nao suporta ALTER TABLE IF NOT EXISTS; aplicar via try/except no Python.
-- Path padrao computado por ARTIFACTS_BASE/{run_id}/events.jsonl (nao precisa de coluna,
-- mas persiste pra auditoria e futuras queries SQL sobre runs com eventos.
ALTER TABLE lab_runs ADD COLUMN events_jsonl_path TEXT NULL;
