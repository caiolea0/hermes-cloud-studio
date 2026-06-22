-- Hermes Postgres init — extensoes para CNPJ fuzzy-match PT-BR
-- Roda automaticamente no primeiro start do container (docker-entrypoint-initdb.d).
-- Conecta ao POSTGRES_DB (hermes) como POSTGRES_USER (hermes).
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- unaccent() do contrib e STABLE (nao IMMUTABLE) -> nao pode entrar em index expression.
-- Wrapper IMMUTABLE permite GIN trigram em immutable_unaccent(lower(col)). A forma de
-- dois argumentos (regdictionary explicito) e o que torna o wrapper seguro como IMMUTABLE.
CREATE OR REPLACE FUNCTION public.immutable_unaccent(text)
  RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS
$func$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $func$;
