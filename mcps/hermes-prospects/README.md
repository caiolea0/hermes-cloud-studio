# hermes-prospects MCP

**Status**: F.5.2 scaffold · **Version**: 0.1.0-f5.2 · **Owner chapter**: F.7

CRUD + scoring sobre tabela `prospects` (~50k rows VM `~/.hermes/data/command_center.db`).

## Tools (7)

| Tool | Estratégia | Plano |
|---|---|---|
| `search_prospects(city, category, min_score, limit)` | Postgres MCP → SQLite fallback | Filtro multi-col |
| `score_lead(profile_data)` | **Python LOCAL (D3 strict)** | NUNCA delega — determinístico |
| `mark_converted(prospect_id, note)` | SQLite local UPDATE | + version bump (MERGED-006) |
| `get_campaign_stats(period_days)` | Postgres MCP → SQLite fallback | Agg count by stage N dias |
| `enrich_pipeline(prospect_id, provider)` | Placeholder F.5.6 | Apollo/Hunter/Firecrawl MCP plug |
| `list_top_scored(limit, min_score)` | Postgres MCP → SQLite fallback | ORDER BY score DESC |
| `get_by_status(status, limit)` | Postgres MCP → SQLite fallback | WHERE stage = ? |

## D3 — Delegate strategy

- **6 tools reads complexos** PREFEREM `mcp.postgres.query` via gateway dispatch
  (D3 cristalizada — single source truth). Fallback SQLite até F.5.6 plug
  Postgres MCP Pro.
- **`score_lead` é Python LOCAL determinístico** — NUNCA delega Postgres.
  Cálculo: base 50 + sinais (sem site +25, categoria valiosa +10, rating ≥4 +5,
  reviews ≥20 +5, phone +2, email +3, instagram +3). Clamp 0-100.

Toggle Postgres MCP path via env `HERMES_PROSPECTS_USE_POSTGRES_MCP=1`. Default
0 = SQLite direto (smoke + scaffold mode).

## Schema referência

```sql
prospects (id, vm_id, name, business_name, category, phone, email, address,
           city, state, website, has_website, google_maps_url, google_rating,
           google_reviews, social_instagram, social_facebook, linkedin_url,
           source, score, stage, notes, audit_summary, outreach_message,
           outreach_status, created_at, updated_at, photo_ref, version,
           last_synced_version, conflict_at)
```

Stages válidos: `discovered, qualified, audited, contacted, converted, dead`.

## Run

```bash
python mcps/hermes-prospects/server.py                           # stdio
HERMES_MCP_TRANSPORT=http python mcps/hermes-prospects/server.py # :55412
```

## Smoke

```bash
python mcps/hermes-prospects/_smoke.py
```

## Cross-refs

- `.claude/PLAN.md` § F.5.2 D3 (delegate strategy)
- `mcps/gateway/config.yaml` upstream `hermes-prospects`
- `core/state.get_db` (PC) / `vm_core/state` (VM) — paths DB canonical
