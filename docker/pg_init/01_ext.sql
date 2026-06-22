-- Hermes Postgres init — extensoes para CNPJ fuzzy-match PT-BR
-- Roda automaticamente no primeiro start do container (docker-entrypoint-initdb.d).
-- Conecta ao POSTGRES_DB (hermes) como POSTGRES_USER (hermes).
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
