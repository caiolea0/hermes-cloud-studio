# hermes-enrich MCP

**H2-F2 — CNPJ authority lookup + validation para prospects Hermes (Cuiabá/MT).**

FastMCP 3.0. Atrás do gateway (`mcps/gateway`). Porta `8802` (Tailscale-interna).

## Tools

### `cnpj_lookup(name, city?, bairro?, phone?)`

Busca CNPJ na base Receita Federal (Cuiabá subset) via pg_trgm similarity.

```json
{
  "name": "Burger King Cuiabá",
  "bairro": "Centro"
}
```

Resposta:
```json
{
  "cnpj": "12345678000199",
  "razao_social": "BK BRASIL OPERACOES E ASSESSORIA A RESTAURANTES SA",
  "nome_fantasia": "BURGER KING",
  "cnae": "5611201",
  "situacao_cadastral": "02",
  "telefone1": "+55659999-1234",
  "confidence": "high",
  "similarity": 0.72,
  "candidates": [...],
  "error": null
}
```

`confidence = 'high'` → aceitar campos; `'low'` → só registrar CNPJ (não sobrescrever dados);
`null` → sem match (similarity < 0.45).

### `cnpj_validate(cnpj)`

Valida situação cadastral via BrasilAPI (gratuito, sem chave).

```json
{"cnpj": "12345678000199"}
```

Resposta:
```json
{
  "cnpj": "12345678000199",
  "razao_social": "BK BRASIL OPERACOES...",
  "situacao_cadastral": "ATIVA",
  "cnae_fiscal": "5611201",
  "data_abertura": "2010-03-15",
  "municipio": "CUIABA",
  "uf": "MT",
  "ok": true,
  "error": null
}
```

## Dependências

- `hermes-postgres` (container) rodando na rede `geronimo-net`
- `cnpj.estabelecimentos` populada por `scripts/load_cnpj_cuiaba.py`
- `psycopg2-binary` (requirements.txt)

## Run

```bash
# No repo root (VPS):
python mcps/hermes-enrich/server.py
# Ou via gateway config.yaml (padrão produção)
```

## Registro

- `mcps/gateway/config.yaml`: upstream `hermes-enrich` → `python3 mcps/hermes-enrich/server.py`
- `.mcp.json`: entry `hermes-enrich` (HTTP via gateway ou stdio direto)
