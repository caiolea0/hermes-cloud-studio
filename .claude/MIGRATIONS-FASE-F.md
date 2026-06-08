# MIGRATIONS — FASE F (Hermes Cloud Studio)

> Spec canônica de schema evolution Fase F. Define ordem determinística, idempotência, topology PC vs VM, script único `apply_phase_f_migrations.py` e rollback granular por migration.
>
> **REGRA INVIOLÁVEL**: nenhuma migration F.x roda sem passar pelo entrypoint. Edits manuais em SQLite via `sqlite3 hermes.db` = banido (deixa schema drift entre PC/VM).
>
> **Baseline antes F**: `migrations/2026_06_linkedin_full.sql` aplicado em PC (`./data/hermes.db`) e VM (`/opt/hermes/data/hermes.db`) — schema A→E estável. Fase F NUNCA reescreve tabelas baseline; só `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN` aditivo.

---

## 0. Princípios (NÃO VIOLAR)

1. **Idempotência total** — toda migration roda 1x ou N vezes com mesmo resultado final. `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN` guardado por introspecção (`PRAGMA table_info`).
2. **Ordem canônica imutável** — uma vez merged numa branch, número da migration NÃO muda. Nova ordenação = nova migration no topo, não renomear histórico.
3. **Topology explícita** — cada migration declara `TARGET: PC | VM | BOTH`. Apply script ignora migrations fora da side onde roda.
4. **Rollback obrigatório** — toda `up` tem `down` correspondente. `down` é destrutivo (DROP/REMOVE COLUMN via copy-rename) e exige flag `--confirm-destructive`.
5. **Aplicação tracked** — tabela `schema_migrations` (criada pela migration 000) guarda `(id, applied_at, side, sha256_up)` — re-apply detecta hash mismatch e aborta.
6. **Zero auto-apply em startup** — `core/state.py` / `vm_core/state.py` NÃO chamam apply automático. Owner ou CI roda `python scripts/apply_phase_f_migrations.py` explicitamente.
7. **Atomicidade por migration** — cada arquivo `.sql` roda dentro de `BEGIN EXCLUSIVE; ... COMMIT;`. Falha = rollback automático SQLite + abort do script.
8. **PC vs VM divergência permitida** — algumas tabelas existem só num lado (ex: `daemon_decisions` só VM, `skill_proposals` só PC). NÃO forçar paridade.
9. **Sem dependência cross-DB** — nenhuma migration assume FK entre PC e VM (são SQLites separados). Replicação via sync API (loops/sync.py), não schema.
10. **Backup pré-apply obrigatório** — script copia `hermes.db` → `hermes.db.pre-F.<timestamp>.bak` antes de qualquer migration F.x. Rollback restore = cp do bak.

---

## 1. Topology de schemas

### PC (`D:/dev-projects/main/hermes-cloud-studio/data/hermes.db`)
Source of truth pra:
- `prospects`, `proposals`, `tasks`, `sequences`, `pipeline_runs`, `audit_runs`
- `campaigns`, `campaign_runs`, `runtime_state` (B fase persistência)
- `email_messages`, `email_warmup` (E.1)
- **Novos F**: `skill_proposals` (F.4), `mission_prefs` (F.2), `brain_decisions_local` (F.6 cache), `pipeline_studio_defs` (F.9)

### VM (`/opt/hermes/data/hermes.db`)
Source of truth pra:
- `linkedin_visits`, `linkedin_comments`, `linkedin_cooldowns` (baseline `2026_06_linkedin_full.sql`)
- `daemon_state`, `daemon_log`, `daemon_decisions`, `daemon_subsystems` (F.2)
- `lab_runs`, `lab_traces` (F.3)
- `live_ops_events` (F.7)
- `observability_metrics` (F.8)

### BOTH (replicado via sync)
- `schema_migrations` (controle)
- `feature_flags` (F.4 — owner toggles)

---

## 2. Ordem canônica das migrations Fase F

> Numeração: `F<chapter>_<seq>__<slug>.sql`. Seq garante ordem dentro do chapter quando >1 arquivo.

| # | Arquivo | Target | Chapter | Resumo |
|---|---|---|---|---|
| 000 | `F0_000__schema_migrations_table.sql` | BOTH | F.0 (bootstrap) | Cria tabela tracking `schema_migrations` + índice |
| 001 | `F1_001__noop_audit_marker.sql` | PC | F.1 | Marcador no-op (F.1 zero schema, só registra completion) |
| 002 | `F2_001__daemon_subsystems.sql` | VM | F.2 | Cria `daemon_subsystems` (name PK, status, last_action_at, next_run_at, paused) |
| 003 | `F2_002__daemon_decisions_idx.sql` | VM | F.2 | Adiciona índices em `daemon_decisions(created_at)`, `daemon_log(level, ts)` pra timeline 24h |
| 004 | `F2_003__mission_prefs.sql` | PC | F.2 | Cria `mission_prefs(owner_key PK, prefs_json, updated_at)` pra collapsed sections + refresh rate |
| 005 | `F3_001__lab_runs.sql` | VM | F.3 | Cria `lab_runs(id, flow, started_at, ended_at, status, profile_path, detection_class)` + `lab_traces(run_id FK, step, screenshot_path, dom_hash, ts)` |
| 006 | `F4_001__skill_proposals.sql` | PC | F.4 | Cria `skill_proposals(id, name, yaml_blob, source_session, status, owner_decision_at, sentry_error_count, ab_variant)` |
| 007 | `F4_002__feature_flags.sql` | BOTH | F.4 | Cria `feature_flags(flag_key PK, enabled, scope, updated_at, updated_by)` — replicado via sync |
| 008 | `F5_001__mcp_registry_cache.sql` | PC | F.5 | Cria `mcp_registry_cache(mcp_name PK, version, last_health_check, healthy, oauth_scope_hash)` pra ContextForge gateway routing |
| 009 | `F6_001__brain_decisions_local.sql` | PC | F.6 | Cria `brain_decisions_local(id, intent, route_picked, confidence, ollama_model, latency_ms, ts)` — cache local pra evaluate_result() loop |
| 010 | `F6_002__brain_intents_alter.sql` | VM | F.6 | ALTER `daemon_decisions` ADD COLUMN `intent_classified TEXT NULL` + ADD COLUMN `brain_confidence REAL NULL` (idempotente via PRAGMA check) |
| 011 | `F7_001__live_ops_events.sql` | VM | F.7 | Cria `live_ops_events(id, kind, payload_json, severity, cobaia_account, ts)` pra cobaia warmup observabilidade |
| 012 | `F7_002__prospects_enrichment_alter.sql` | PC | F.7 | ALTER `prospects` ADD COLUMN `enrichment_source TEXT NULL` + `enrichment_score INTEGER NULL` + `enriched_at TIMESTAMP NULL` (guard PRAGMA) |
| 013 | `F8_001__observability_metrics.sql` | VM | F.8 | Cria `observability_metrics(metric_key, value_num, value_text, ts, source)` + índice `(metric_key, ts DESC)` |
| 014 | `F9_001__pipeline_studio_defs.sql` | PC | F.9 | Cria `pipeline_studio_defs(id, name, dag_yaml, version, created_by, created_at, last_run_id NULL)` |

**Total**: 15 migrations (incluindo 000 bootstrap + 001 marker F.1).

---

## 3. Convenção de arquivo `.sql`

Cada migration vive em `migrations/phase_f/F<n>_<seq>__<slug>.sql` com cabeçalho YAML-em-comentário **obrigatório**:

```sql
-- @migration_id: F2_001__daemon_subsystems
-- @target: VM
-- @chapter: F.2
-- @depends_on: F0_000__schema_migrations_table
-- @rollback_safe: true
-- @sha256_up: <preenchido por apply script no momento do registro>
-- @description: Cria tabela daemon_subsystems pra Mission Control health cards

BEGIN EXCLUSIVE;

CREATE TABLE IF NOT EXISTS daemon_subsystems (
  name TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK(status IN ('healthy','warning','error','paused')) DEFAULT 'healthy',
  last_action_at TIMESTAMP NULL,
  next_run_at TIMESTAMP NULL,
  paused INTEGER NOT NULL DEFAULT 0,
  paused_until TIMESTAMP NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_daemon_subsystems_status
  ON daemon_subsystems(status);

-- Seed inicial dos 6 subsistemas conhecidos (idempotente via INSERT OR IGNORE)
INSERT OR IGNORE INTO daemon_subsystems(name) VALUES
  ('linkedin'), ('email'), ('scraper'), ('audit'), ('daemon'), ('tunnel');

COMMIT;
```

E o arquivo `.down.sql` correspondente em `migrations/phase_f/down/F2_001__daemon_subsystems.down.sql`:

```sql
-- @migration_id: F2_001__daemon_subsystems
-- @target: VM
-- @destructive: true

BEGIN EXCLUSIVE;
DROP INDEX IF EXISTS idx_daemon_subsystems_status;
DROP TABLE IF EXISTS daemon_subsystems;
COMMIT;
```

**ALTER TABLE idempotente** (ex: `F6_002`, `F7_002`) — usa pattern Python no apply script (não SQL puro, SQLite não tem `ADD COLUMN IF NOT EXISTS`):

```sql
-- @migration_id: F6_002__brain_intents_alter
-- @target: VM
-- @chapter: F.6
-- @depends_on: F2_001__daemon_subsystems
-- @rollback_safe: false  -- ALTER DROP COLUMN requer copy-rename, custoso
-- @alter_columns: daemon_decisions:intent_classified:TEXT NULL, daemon_decisions:brain_confidence:REAL NULL
-- (apply script lê @alter_columns e faz PRAGMA table_info check antes de cada ALTER)
```

---

## 4. Entrypoint único: `scripts/apply_phase_f_migrations.py`

**Caminho**: `D:/dev-projects/main/hermes-cloud-studio/scripts/apply_phase_f_migrations.py`

### Responsabilidades

1. **Detectar side** (PC vs VM) via hostname + path do DB:
   - `socket.gethostname()` matches `DESKTOP-*` ou path contém `D:\` → PC
   - Path `/opt/hermes/` ou hostname starts with `hermes-vm-` → VM
   - Override explícito via `--side pc|vm|both` (CI/test)
2. **Filtrar migrations** por `@target` matching side detectada (BOTH sempre roda).
3. **Backup pré-apply** — `shutil.copy2(db_path, f"{db_path}.pre-F.{ts}.bak")` antes do primeiro apply.
4. **Ler tracking** — `SELECT id, sha256_up FROM schema_migrations` (cria via 000 se ausente).
5. **Aplicar em ordem canônica** (lê `migrations/phase_f/*.sql` sorted by filename, valida cabeçalho YAML).
6. **Hash check** — pra migrations já aplicadas: re-hash arquivo `.sql` corrente, compara com `sha256_up` armazenado. Mismatch = abort + diff.
7. **Atomicidade** — cada migration roda em transação separada. Falha = rollback SQLite + sair com exit 1.
8. **Registro pós-apply** — `INSERT INTO schema_migrations(id, applied_at, side, sha256_up)` na MESMA transação do DDL.
9. **Modo dry-run** — `--dry-run` lista o que rodaria sem executar + valida sintaxe via `sqlite3 :memory:`.
10. **Modo rollback** — `python apply_phase_f_migrations.py --rollback F6_002__brain_intents_alter --confirm-destructive`:
    - Roda `down/F6_002__brain_intents_alter.down.sql` numa transação
    - DELETE da row em `schema_migrations`
    - Bloqueia rollback se outra migration aplicada depender desta (`@depends_on`)
11. **Cross-side dispatch** — `--side both` em PC roda PC local + opcionalmente dispatcha VM via SSH (`ssh hermes-vm 'cd /opt/hermes && python scripts/apply_phase_f_migrations.py --side vm'`). Flag `--vm-ssh-host` configurável (default lê `HERMES_VM_SSH` env).
12. **Lock** — cria `data/.migrations.lock` (file lock) na vida do processo. Concorrência = abort com erro claro.

### CLI

```
python scripts/apply_phase_f_migrations.py [opções]

  --side {pc,vm,both,auto}    Side onde rodar (default: auto)
  --dry-run                   Não executa, só lista + valida sintaxe
  --only F<id>                Aplica apenas 1 migration (pra debug)
  --up-to F<id>               Aplica até essa migration (inclusive)
  --rollback F<id>            Rollback de 1 migration específica
  --confirm-destructive       Obrigatório pra rollback
  --backup-dir PATH           Override destino dos backups (default: ao lado do .db)
  --no-backup                 Skip backup (CI test only — NUNCA em produção)
  --vm-ssh-host HOST          SSH alvo pra --side both dispatch (default: $HERMES_VM_SSH)
  --json                      Output JSON pra automação
  --strict-hash               Re-hash check em TODAS migrations aplicadas (default: só novas)
```

### Exit codes

- `0` — sucesso (migrations aplicadas ou nada a aplicar)
- `1` — erro de execução SQL (rollback automático)
- `2` — hash mismatch detectado (drift entre arquivo .sql e schema_migrations)
- `3` — lock file existente (outra instância rodando)
- `4` — rollback bloqueado por dependência
- `5` — backup falhou (disco cheio / permissão)
- `6` — SSH dispatch VM falhou em `--side both`

### Esqueleto Python (referência — não código MADURO ainda)

```python
"""apply_phase_f_migrations.py — entrypoint único Fase F.

Lê migrations/phase_f/*.sql, aplica em ordem canônica, tracked via
schema_migrations table. Suporta PC/VM/both dispatch + rollback.
"""
import argparse, hashlib, json, os, re, shutil, socket, sqlite3, sys, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "migrations" / "phase_f"
DOWN_DIR = MIGRATIONS_DIR / "down"

HEADER_RE = re.compile(r"--\s*@(\w+):\s*(.+)")

def parse_header(sql_text: str) -> dict:
    meta = {}
    for line in sql_text.splitlines():
        if not line.startswith("--"):
            if line.strip() and not line.strip().startswith("--"):
                break
        m = HEADER_RE.match(line.strip())
        if m:
            meta[m.group(1)] = m.group(2).strip()
    return meta

def detect_side(db_path: Path) -> str:
    host = socket.gethostname().lower()
    p = str(db_path).lower()
    if "/opt/hermes" in p or host.startswith("hermes-vm"):
        return "vm"
    if "d:\\" in p or host.startswith("desktop-") or os.name == "nt":
        return "pc"
    raise RuntimeError(f"side ambiguous: host={host} db={db_path}")

def ensure_tracking(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS schema_migrations(
      id TEXT PRIMARY KEY,
      applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      side TEXT NOT NULL,
      sha256_up TEXT NOT NULL
    );
    """)
    conn.commit()

def already_applied(conn) -> dict:
    return {row[0]: row[1] for row in conn.execute(
        "SELECT id, sha256_up FROM schema_migrations"
    )}

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def acquire_lock(db_path: Path):
    lock = db_path.parent / ".migrations.lock"
    if lock.exists():
        sys.exit(3)
    lock.write_text(f"{os.getpid()} {time.time()}")
    return lock

def apply_one(conn, sql_path: Path, side: str, dry: bool):
    text = sql_path.read_text(encoding="utf-8")
    meta = parse_header(text)
    if meta.get("target", "BOTH").lower() not in (side, "both"):
        return "skip-target"
    mid = meta["migration_id"]
    h = sha(text)
    applied = already_applied(conn)
    if mid in applied:
        if applied[mid] != h:
            sys.exit(2)
        return "already"
    if dry:
        # validate syntax against :memory:
        sqlite3.connect(":memory:").executescript(text)
        return "would-apply"
    try:
        conn.executescript(text)  # SQL itself wraps BEGIN...COMMIT
        conn.execute(
            "INSERT INTO schema_migrations(id, side, sha256_up) VALUES (?, ?, ?)",
            (mid, side, h),
        )
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        print(f"ERROR {mid}: {e}", file=sys.stderr)
        sys.exit(1)
    return "applied"

def rollback_one(conn, mid: str, side: str):
    # checar dependências reversas
    applied = already_applied(conn)
    if mid not in applied:
        print(f"not applied: {mid}", file=sys.stderr); sys.exit(4)
    for sql_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        meta = parse_header(sql_path.read_text(encoding="utf-8"))
        if meta.get("depends_on") == mid and meta["migration_id"] in applied:
            print(f"blocked: {meta['migration_id']} depends on {mid}", file=sys.stderr)
            sys.exit(4)
    down_path = DOWN_DIR / f"{mid}.down.sql"
    if not down_path.exists():
        print(f"no down script: {down_path}", file=sys.stderr); sys.exit(1)
    text = down_path.read_text(encoding="utf-8")
    try:
        conn.executescript(text)
        conn.execute("DELETE FROM schema_migrations WHERE id = ?", (mid,))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback(); print(f"ERROR rollback {mid}: {e}", file=sys.stderr); sys.exit(1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--side", default="auto", choices=["pc","vm","both","auto"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--up-to")
    ap.add_argument("--rollback")
    ap.add_argument("--confirm-destructive", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--backup-dir")
    ap.add_argument("--vm-ssh-host", default=os.environ.get("HERMES_VM_SSH"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict-hash", action="store_true")
    args = ap.parse_args()

    db_path = Path(os.environ.get(
        "HERMES_DB",
        PROJECT_ROOT / "data" / "hermes.db",
    ))
    side = args.side if args.side != "auto" else detect_side(db_path)

    lock = acquire_lock(db_path)
    try:
        if not args.no_backup and not args.dry_run:
            ts = time.strftime("%Y%m%d-%H%M%S")
            dest_dir = Path(args.backup_dir) if args.backup_dir else db_path.parent
            shutil.copy2(db_path, dest_dir / f"{db_path.name}.pre-F.{ts}.bak")

        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA busy_timeout = 30000")
        ensure_tracking(conn)

        if args.rollback:
            if not args.confirm_destructive:
                print("rollback requires --confirm-destructive", file=sys.stderr); sys.exit(1)
            rollback_one(conn, args.rollback, side)
            return

        results = []
        for sql_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            meta = parse_header(sql_path.read_text(encoding="utf-8"))
            mid = meta["migration_id"]
            if args.only and mid != args.only: continue
            res = apply_one(conn, sql_path, side, args.dry_run)
            results.append((mid, res))
            if args.up_to and mid == args.up_to: break

        if side == "both" and args.vm_ssh_host and not args.dry_run:
            ssh_cmd = f"ssh {args.vm_ssh_host} 'cd /opt/hermes && python scripts/apply_phase_f_migrations.py --side vm'"
            rc = os.system(ssh_cmd)
            if rc != 0: sys.exit(6)

        if args.json:
            print(json.dumps({"side": side, "results": results}))
        else:
            for mid, res in results: print(f"{mid}: {res}")
    finally:
        try: lock.unlink()
        except FileNotFoundError: pass

if __name__ == "__main__":
    main()
```

---

## 5. Rollback policy

### Por chapter

| Chapter | Rollback safety | Estratégia |
|---|---|---|
| F.0 | unsafe (schema_migrations apaga histórico) | NÃO rolar back. Drop manual + reapply tudo se necessário. |
| F.1 | safe (no-op) | `--rollback F1_001__noop_audit_marker` apaga só a row. |
| F.2 | safe | DROP daemon_subsystems + índices. Mission Control volta a stub. |
| F.3 | safe | DROP lab_runs/lab_traces. Skill hermes-li-lab para de logar. |
| F.4 | unsafe (skill_proposals tem dados owner-aprovados) | NÃO rolar back depois de aprovar primeira skill. Backup antes. |
| F.5 | safe | DROP mcp_registry_cache (cache, regenera). |
| F.6 | parcialmente safe | brain_decisions_local: safe drop. daemon_decisions ALTER: copy-rename custoso, requer manutenção scheduled. |
| F.7 | unsafe se warmup ativo | live_ops_events tem histórico cobaia. prospects ALTER preserva dados enrichment. |
| F.8 | safe | observability_metrics é série temporal regenerável. |
| F.9 | unsafe se DAGs em produção | pipeline_studio_defs tem código owner. Export YAML antes de drop. |

### Procedimento padrão rollback

```bash
# 1. Snapshot pre-rollback
cp data/hermes.db data/hermes.db.pre-rollback.$(date +%s).bak

# 2. Verificar dependências (script faz auto)
python scripts/apply_phase_f_migrations.py --rollback F6_002__brain_intents_alter --dry-run

# 3. Executar (exige flag)
python scripts/apply_phase_f_migrations.py --rollback F6_002__brain_intents_alter --confirm-destructive

# 4. Re-validar
python scripts/validate_implementation.py --phase A B C D E
```

### Restore from backup (rollback total)

```bash
# Para um chapter inteiro: restore do backup pré-apply F.x
ls data/hermes.db.pre-F.*.bak
cp data/hermes.db.pre-F.20260608-143022.bak data/hermes.db

# Sync VM idem
ssh hermes-vm 'cp /opt/hermes/data/hermes.db.pre-F.20260608-143025.bak /opt/hermes/data/hermes.db'
```

---

## 6. Estrutura de diretórios

```
migrations/
  2026_06_linkedin_full.sql        # baseline (NÃO TOCAR)
  phase_f/
    F0_000__schema_migrations_table.sql
    F1_001__noop_audit_marker.sql
    F2_001__daemon_subsystems.sql
    F2_002__daemon_decisions_idx.sql
    F2_003__mission_prefs.sql
    F3_001__lab_runs.sql
    F4_001__skill_proposals.sql
    F4_002__feature_flags.sql
    F5_001__mcp_registry_cache.sql
    F6_001__brain_decisions_local.sql
    F6_002__brain_intents_alter.sql
    F7_001__live_ops_events.sql
    F7_002__prospects_enrichment_alter.sql
    F8_001__observability_metrics.sql
    F9_001__pipeline_studio_defs.sql
    down/
      F1_001__noop_audit_marker.down.sql
      F2_001__daemon_subsystems.down.sql
      F2_002__daemon_decisions_idx.down.sql
      ... (1 .down.sql por migration aplicada)
    README.md   # link pra este spec
```

---

## 7. Critérios de done por chapter (gate de migration)

Toda task que cria/altera schema Fase F **OBRIGA** as 4 checks:

1. **Arquivo `.sql` criado** em `migrations/phase_f/F<n>_<seq>__<slug>.sql` com cabeçalho YAML completo.
2. **Arquivo `.down.sql` correspondente** em `migrations/phase_f/down/` (mesmo `migration_id`).
3. **Apply dry-run passa**: `python scripts/apply_phase_f_migrations.py --dry-run --only F<id>` retorna `would-apply` + 0 erros.
4. **Apply real + tracked**: `python scripts/apply_phase_f_migrations.py --only F<id>` retorna `applied` + row em `schema_migrations`.

Validação cruzada no `validate_implementation.py` (gate F.x): cada chapter F.x que declara `db_migrations` no plano DEVE ter as migrations correspondentes registradas em `schema_migrations` ao fim. PASS exige `SELECT COUNT(*) FROM schema_migrations WHERE id LIKE 'F<n>_%'` >= esperado.

---

## 8. Integração com CI / regression gate

`scripts/validate_implementation.py --phase F<n>` deve incluir check novo:

```python
def check_phase_f_migrations(side: str, expected_ids: list[str]) -> CheckResult:
    """Verifica que migrations esperadas estão aplicadas neste side."""
    conn = sqlite3.connect(db_path_for(side))
    applied = {row[0] for row in conn.execute(
        "SELECT id FROM schema_migrations WHERE side IN (?, 'both')", (side,)
    )}
    missing = [mid for mid in expected_ids if mid not in applied]
    if missing:
        return FAIL(f"migrations não aplicadas em {side}: {missing}")
    return PASS(f"{len(expected_ids)} migrations F.{chapter} ok em {side}")
```

Pré-test de cada task F.x que toca schema:

```python
# pre_test
python scripts/apply_phase_f_migrations.py --dry-run --json | \
  python -c "import sys,json; r=json.load(sys.stdin); \
    assert all(s in ('already','would-apply','skip-target') for _,s in r['results']); \
    print('migrations pre-state clean')"

# post_test
python scripts/apply_phase_f_migrations.py --json | \
  python -c "import sys,json; r=json.load(sys.stdin); \
    assert any(s=='applied' for _,s in r['results']) or all(s=='already' for _,s in r['results']); \
    print('migrations applied or idempotent re-run')"
```

---

## 9. Casos de borda + decisões

### 9.1 Migration F.x precisa rodar ANTES do código F.x ser deployado?
**Sim.** Ordem obrigatória: (1) PR migration mergeado + applied em PC+VM → (2) PR código que consome novas tabelas/colunas. Código novo SEM migration = erro `no such table/column`. Pré-test do task de código consumidor checa schema via `PRAGMA table_info`.

### 9.2 Two writers race no apply (CI + owner local)?
File lock `data/.migrations.lock` (exit 3). Lock NUNCA é stale-recovered automaticamente — owner deleta manual se processo morreu (mensagem do exit 3 instrui).

### 9.3 SQLite ALTER TABLE DROP COLUMN?
SQLite 3.35+ suporta `DROP COLUMN`, mas Hermes alvo é compatibilidade ampla. Down scripts pra ALTER COLUMN usam padrão **copy-rename**:
```sql
BEGIN EXCLUSIVE;
CREATE TABLE daemon_decisions_new AS SELECT id, ts, ... FROM daemon_decisions;
DROP TABLE daemon_decisions;
ALTER TABLE daemon_decisions_new RENAME TO daemon_decisions;
-- recriar índices originais
COMMIT;
```

### 9.4 Conflito hash (arquivo .sql editado pós-apply)?
Exit 2 + diff impresso. Owner DEVE: (a) reverter edição se cosmético, ou (b) criar nova migration `F<n>_<seq+1>__amend_<original>.sql` com correção, NUNCA editar arquivo aplicado.

### 9.5 Backup ocupando disco?
Política: manter últimos 5 backups por DB. Script de housekeeping `scripts/prune_migration_backups.py` (rodar manual ou cron):
```python
backups = sorted(Path("data").glob("hermes.db.pre-F.*.bak"))
for old in backups[:-5]:
    old.unlink()
```

### 9.6 PC offline quando F.x roda em VM (ou vice-versa)?
`--side both` em PC com SSH falhando → exit 6. Owner roda manualmente na VM depois (`--side vm`). schema_migrations divergente entre lados é DETECTADO no próximo sync (loops/sync.py adiciona check no início do tick: se PC tem migration F.x e VM não, log WARNING — não bloqueia sync, só alerta).

---

## 10. Checklist pré-merge de QUALQUER PR Fase F que toque schema

- [ ] Arquivo `.sql` em `migrations/phase_f/` com cabeçalho YAML completo
- [ ] Arquivo `.down.sql` em `migrations/phase_f/down/` correspondente
- [ ] `--dry-run` passa local (PC) e remoto (VM via SSH)
- [ ] Apply real passa em PC + VM (ou só no side declarado em `@target`)
- [ ] `validate_implementation.py --phase F<n>` PASS
- [ ] Hash registrado em `schema_migrations` confere em ambos lados (se BOTH)
- [ ] Backup pre-apply existe (`hermes.db.pre-F.*.bak`)
- [ ] PR descrição cita `migration_id` no formato `F<n>_<seq>__<slug>`
- [ ] Código consumidor da nova tabela/coluna está em PR SEPARADO mergeado DEPOIS
- [ ] GUARDRAILS.md regra "schema change via migration entrypoint" não violada

---

## 11. Anti-patterns banidos (NUNCA fazer)

1. `sqlite3 hermes.db < schema.sql` manual — bypassa tracking, gera drift.
2. `DROP TABLE` em migration `up` sem `.down.sql` espelho.
3. Editar arquivo `.sql` já aplicado em produção (hash mismatch → CI vermelho).
4. Renomear `migration_id` (quebra rollback + tracking).
5. Adicionar coluna `NOT NULL` sem default em tabela existente (falha em rows antigas — SQLite ALTER limitation).
6. Usar `PRAGMA foreign_keys = OFF` durante migration sem restaurar.
7. `INSERT` de seed data em migration sem `INSERT OR IGNORE` (re-apply duplica).
8. Migration que depende de timestamp/dado runtime (não-determinística).
9. `CREATE TRIGGER` complexo sem rollback testado (triggers escondem efeitos colaterais).
10. Cross-DB FK PC↔VM (não existe — são SQLites separados).

---

**Última atualização**: 2026-06-08 (alinhado com PLAN.md Fase F chapters F.0–F.9)
**Owner**: cleao
**Status**: SPEC ATIVA — vigora pra toda PR Fase F. Edições deste arquivo via PR + review explícito.
