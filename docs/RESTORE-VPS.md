# RESTORE-VPS — Hermes Cloud Studio 2.0

Runbook para restaurar a stack Hermes 2.0 a partir do backup mothball 2026-07-15 numa VPS Linux nova (Ubuntu 22+/24). Preserva os counts baseline do momento do freeze da VPS Contabo (`root@207.180.240.208`, host `geronimo-vps`, cancelada temporariamente após esta captura).

Este documento é auto-suficiente. Uma LLM (ou humano) sem acesso à conversa que gerou o backup deve conseguir executar de ponta a ponta seguindo apenas o que está aqui.

---

## 1. Onde está o backup

Diretório: `backups/vps-mothball-2026-07-15/` no repo `caiolea0/hermes-cloud-studio`.

**Não está versionado no git** (`.gitignore` cobre `backups/` — linha 102). Existe SÓ no disco local do PC do owner + cópia manual em cloud pessoal (regra 3-2-1). Se este runbook está sendo lido sem a pasta presente, ela precisa ser restaurada antes.

Estrutura:

| Path | Conteúdo | SHA256 |
|---|---|---|
| `dumps/hermes_pg_2026-07-15.dump` | pg_dump -Fc completo (25.3 MB) | `1349d1d47799e2e877693a18dda75fd3f2e4f2af905e246b5996acfaa62c34f3` |
| `dumps/command_center_2026-07-15.db` | SQLite backup WAL-safe (1.06 MB) | `3dc93d89411dced405f01c58e3aea0ea8dab785a79e8349b4d92fa6c0ce8ea3b` |
| `dumps/hermes_tiles_2026-07-15.tar.gz` | Tiles PMTiles Cuiabá (5.0 MB) | `81e8a1c1f114729a35af8fd0f175aee0a3216d373de8cb0ab647ae925bdc0831` |
| `dumps/SHA256SUMS.txt` | Manifest hashes | — |
| `secrets/.env.vps` | `/opt/hermes/.env` da VPS original (11 vars: `HERMES_AUTH_TOKEN`, `HERMES_PG_PASSWORD`, `HERMES_VM_AUTH_TOKEN`, `HERMES_INTERNAL_TOKEN`, `HERMES_PG_USER`, `HERMES_PG_DB`, `HERMES_BIND_IP`, `HERMES_PAGESPEED_KEY`, `HERMES_STRICT_MCP`, `FEATURE_LINKEDIN`, `OLLAMA_URL`) | `46be4e9be27d163f07e6cfab18ac30a95e3f7aacfc5137844cdb2615987b91ad` |
| `infra/baseline-counts.txt` | Counts SQLite + PG pós-freeze (verdade do backup) | — |
| `infra/infra-snapshot.txt` | .deployed_sha, docker ps -a, volumes, Tailscale IP, df -h, uname | `3537d87212d4f689a9d2d60cd0ca8cbb90784098b662025b1f49e8dee4abf380` |

Nota: `.pg_secret` mencionado no `docker-compose.yml` comment L121 **não existe** no host original — a senha PG vive apenas dentro de `.env.vps` como `HERMES_PG_PASSWORD=...`. Não é preciso recriar arquivo separado.

**Baseline counts** (bater exato após restore):

- SQLite: `prospects=2122`, `activities=2525` + 8 tabelas vazias (`campaign_runs`, `hunter_email_cache`, `linkedin_connections`, `linkedin_engagements`, `linkedin_posts`, `linkedin_profiles`, `pipeline_stats`, `tasks`)
- PG: `cnpj.estabelecimentos=333929`, `geo.business_points=2113`, `cnpj.market_signals=200`, `geo.bairros=194`, `geo.sweep_state=0`, `public.spatial_ref_sys=8500` (seed postgis)

---

## 2. Pré-requisitos da VPS nova

- Ubuntu 22.04+ ou 24.04 (a original era `Linux 6.8.0-106-generic x86_64`)
- Docker Engine + `docker compose` plugin (mesma versão da original: 29.5+)
- Chave SSH nova (gerar com `ssh-keygen -t ed25519`)
- Acesso ao repo GitHub `caiolea0/hermes-cloud-studio`
- `gh` CLI logado com permissão de admin no repo (para configurar secrets/vars do Actions)
- Tailscale account do owner (para IP interno; a original era `100.74.227.37`)

### GitHub Actions — 1 secret + 1 variable

Configurar **antes** de qualquer push:

```bash
# Secret com a chave PRIVADA SSH nova
gh secret set HERMES_VPS_SSH_KEY -R caiolea0/hermes-cloud-studio < ~/.ssh/nova_vps_ed25519

# Variable habilitando o deploy automático
gh variable set HERMES_AUTODEPLOY --body true -R caiolea0/hermes-cloud-studio
```

**Não existe** secret `HERMES_VPS_SSH_HOST` no workflow — o IP vive hardcoded no código (ver §3).

---

## 3. Provisionar a VPS + editar IP hardcoded

Instalar Docker:

```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker $USER  # se não for root
```

Copiar a chave PÚBLICA nova pra `~/.ssh/authorized_keys` da VPS (`root@<IP-NOVA>`).

Clonar o repo localmente (num PC ou na própria VPS) e **editar o IP antigo `207.180.240.208` → IP da VPS nova em 3 pontos**:

1. `.github/workflows/deploy-hermes.yml` — step "Setup SSH key":
   ```yaml
   ssh-keyscan -H <IP-NOVA> >> ~/.ssh/known_hosts
   ```
2. `.github/workflows/deploy-hermes.yml` — step "Deploy":
   ```yaml
   env:
     HERMES_VPS_HOST: root@<IP-NOVA>
   ```
3. `scripts/deploy-hermes-vps.sh:8`:
   ```bash
   VPS="${HERMES_VPS_HOST:-root@<IP-NOVA>}"
   ```

Commitar (**não** é `.md` nem `.claude/**`, então dispara deploy) — comportamento desejado, é o primeiro deploy da VPS nova:

```bash
git add .github/workflows/deploy-hermes.yml scripts/deploy-hermes-vps.sh
git commit -m "chore: migrate deploy target to new VPS IP"
git push origin master
gh run watch -R caiolea0/hermes-cloud-studio --exit-status
```

Se o deploy falhar (esperado — nada existe em `/opt/hermes` ainda), fazer o bootstrap manual:

```bash
ssh root@<IP-NOVA>
mkdir -p /opt/hermes
cd /opt/hermes
git clone https://github.com/caiolea0/hermes-cloud-studio.git .
```

---

## 4. Recriar `/opt/hermes/.env`

Copiar `secrets/.env.vps` do backup para `/opt/hermes/.env` na VPS nova (via `scp`), então:

```bash
chmod 600 /opt/hermes/.env
```

Revisar e ajustar se necessário:

- `HERMES_BIND_IP` — se a nova VPS usa outro IP Tailscale, atualizar (default `127.0.0.1`)
- `OLLAMA_URL` — se Ollama vai rodar em outro host
- Tokens (`HERMES_AUTH_TOKEN`, `HERMES_INTERNAL_TOKEN`, `HERMES_VM_AUTH_TOKEN`) podem ser mantidos ou rotacionados

---

## 5. Restore PostgreSQL

Subir SÓ o container do Postgres primeiro (não a stack toda):

```bash
cd /opt/hermes
docker compose up -d hermes-postgres
```

Aguardar healthy:

```bash
until docker inspect hermes-postgres --format '{{.State.Health.Status}}' | grep -q healthy; do sleep 3; done
```

Copiar dump e restaurar:

```bash
docker cp backups/vps-mothball-2026-07-15/dumps/hermes_pg_2026-07-15.dump hermes-postgres:/tmp/dump
docker exec hermes-postgres pg_restore --no-owner --no-acl -U hermes -d hermes /tmp/dump
```

### AVISO — erros esperados

`pg_restore` VAI reportar erros `already exists` em `public.spatial_ref_sys` (8500 rows seed padrão da imagem `postgis/postgis:16-3.4`) e nas extensões (`postgis`, `postgis_topology`), terminando com **exit code ≠ 0**.

**Isso é ESPERADO, não corrupção.** A imagem postgis já vem com esses objetos pré-criados; o dump inclui todos.

### Critério de sucesso: counts das 4 tabelas de negócio

**NÃO** olhar exit code. Rodar as 4 queries em `UNION ALL` (nunca cross join):

```sql
SELECT 'cnpj.estabelecimentos' AS tabela, COUNT(*) FROM cnpj.estabelecimentos
UNION ALL SELECT 'geo.business_points', COUNT(*) FROM geo.business_points
UNION ALL SELECT 'cnpj.market_signals', COUNT(*) FROM cnpj.market_signals
UNION ALL SELECT 'geo.bairros', COUNT(*) FROM geo.bairros;
```

Comparar com `infra/baseline-counts.txt`:

```
cnpj.estabelecimentos    333929
geo.business_points      2113
cnpj.market_signals      200
geo.bairros              194
```

**Se qualquer count divergir, abortar restore e investigar antes de continuar.**

---

## 6. Restore SQLite (antes de subir hermes-api/daemon)

O SQLite precisa estar no volume `hermes_hermes_data` **antes** de `hermes-api`/`hermes-daemon` subirem (senão eles inicializam DB vazio e não recuperam).

Container temporário Alpine para copiar o `.db` pro volume:

```bash
docker run --rm \
  -v hermes_hermes_data:/data \
  -v "$(pwd)/backups/vps-mothball-2026-07-15/dumps":/backup \
  alpine sh -c "mkdir -p /data/data && cp /backup/command_center_2026-07-15.db /data/data/command_center.db && chown -R 1000:1000 /data/data"
```

Nome do volume: `hermes_hermes_data` (o `docker-compose.yml` declara `hermes_data` e o compose project name `hermes` aplica prefixo → `hermes_hermes_data`).

Verificar:

```bash
docker run --rm -v hermes_hermes_data:/data alpine ls -la /data/data/
```

Deve mostrar `command_center.db` com ~1.1 MB.

---

## 7. Restore Tiles

Duas opções.

### Opção A — restaurar do backup (mesmos tiles, sem PLANET_URL)

```bash
docker run --rm \
  -v hermes_hermes_tiles:/data \
  -v "$(pwd)/backups/vps-mothball-2026-07-15/dumps":/backup \
  alpine tar -xzf /backup/hermes_tiles_2026-07-15.tar.gz -C /data
```

### Opção B — rebuild via `scripts/fetch_pmtiles.sh`

Exige env `PLANET_URL` apontando pra um PMTiles do planeta atualizado. O script (L35-36 tem comentários) sugere fallback via `tilemaker` + extract centro-oeste Geofabrik se URL padrão retornar 404 (Protomaps migrou infra em 2024).

```bash
PLANET_URL='https://<url-planet-pmtiles>' bash scripts/fetch_pmtiles.sh
```

Recomendação: opção A para restore inicial (rápido, determinístico). Opção B só se quiser tiles atualizados.

---

## 8. Overpass (SEM backup)

O volume `hermes_overpass_data` tinha 3.6 GB na VPS original e **não foi backupeado** (dados derivados do OSM público — reimportam sozinhos).

Na primeira subida do container `hermes-overpass`, ele detecta volume vazio e faz import inicial do OSM. **Demora horas** (típico 4-8h numa VPS de 4 vCPUs / 8 GB RAM). Isso é esperado, não erro. Monitorar:

```bash
docker logs -f hermes-overpass
```

Enquanto o import roda, endpoints Overpass (`http://localhost:12345/api/status`) vão retornar erro — normal. Após concluir, healthcheck vira `healthy`.

---

## 9. Subir stack completa

```bash
cd /opt/hermes
docker compose up -d --build
docker ps --format '{{.Names}}\t{{.Status}}' | grep hermes
```

Esperado (após tudo estabilizar):

```
hermes-api        Up X minutes (healthy)
hermes-daemon     Up X minutes             # sem healthcheck (worker)
hermes-web        Up X minutes (healthy)
hermes-postgres   Up X minutes (healthy)
hermes-overpass   Up X minutes             # (health: starting durante import inicial)
```

Portas host (bindadas a `HERMES_BIND_IP`, default `127.0.0.1`):

- `<HERMES_BIND_IP>:8800` — hermes-api (FastAPI)
- `<HERMES_BIND_IP>:8801` — hermes-web (nginx + dashboard)
- `127.0.0.1:5433` — hermes-postgres (só localhost)
- `127.0.0.1:12345` — hermes-overpass (só localhost)

---

## 10. Tailscale

Instalar e conectar:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up
tailscale ip -4  # anotar novo IP
```

Atualizar apontamentos que usavam o IP antigo (`100.74.227.37` — **MORTO** após cancelamento da VPS original):

- `dashboard-v2/config.js` — se houver constante com o IP
- Qualquer cliente PC que apontava via SSH pra `root@207.180.240.208` (`~/.ssh/config`, scripts locais)
- Endpoint do túnel Cloudflare (se ainda em uso) — reconfigurar `cloudflared` se aplicável

---

## 11. Smoke final (validação end-to-end)

```bash
# API health
curl -s http://<HERMES_BIND_IP>:8800/health

# Web health
curl -s http://<HERMES_BIND_IP>:8801/health

# PG counts (mesmo SQL da §5, UNION ALL — NÃO cross join)
docker exec hermes-postgres psql -U hermes -d hermes -c "
SELECT 'cnpj.estabelecimentos' AS tabela, COUNT(*) FROM cnpj.estabelecimentos
UNION ALL SELECT 'geo.business_points', COUNT(*) FROM geo.business_points
UNION ALL SELECT 'cnpj.market_signals', COUNT(*) FROM cnpj.market_signals
UNION ALL SELECT 'geo.bairros', COUNT(*) FROM geo.bairros;
"

# SQLite counts (2 queries separadas)
docker exec hermes-api python3 -c "
import sqlite3
c = sqlite3.connect('/var/lib/hermes/data/command_center.db')
print('prospects:', c.execute('SELECT COUNT(*) FROM prospects').fetchone()[0])
print('activities:', c.execute('SELECT COUNT(*) FROM activities').fetchone()[0])
"

# Dashboard
# Abrir http://<HERMES_BIND_IP>:8801/ no browser — deve carregar dashboard-v2
```

Todos os 6 counts devem bater exato com `infra/baseline-counts.txt`. Se qualquer um divergir, investigar antes de considerar o restore concluído.

---

## Fim

Restore concluído. `hermes-daemon` já estará rodando (compose up sobe todos). VPS nova operacional com dados idênticos ao momento do freeze 2026-07-15.
