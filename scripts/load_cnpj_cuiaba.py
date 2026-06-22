"""H2-F2 — Ingestão RF CNPJ (Cuiabá/MT subset) → hermes-postgres.

Baixa dumps trimestrais da Receita Federal (dados abertos, zero custo),
filtra apenas Cuiabá por código RF (NÃO IBGE), carrega em cnpj.estabelecimentos.

Uso:
    python scripts/load_cnpj_cuiaba.py
    python scripts/load_cnpj_cuiaba.py --year-month 2025-05
    python scripts/load_cnpj_cuiaba.py --base-url https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/2025-05/
    python scripts/load_cnpj_cuiaba.py --dry-run   # conta linhas sem inserir

Conexão Postgres: vars HERMES_PG_* (lidas do .env ou ambiente).
No host VPS use: HERMES_PG_HOST=127.0.0.1 HERMES_PG_PORT=5433

Coluna `version` not bumped: load é full-replace idempotente (UPSERT on cnpj PK).
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
import os
import sys
import time
import zipfile
from pathlib import Path
from typing import Generator, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("hermes.load_cnpj")

# Caminho base RF — URL mais recente deve ser passada via --base-url
RF_BASE = "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj"
NUM_SHARDS = 10  # Estabelecimentos0..9 e Empresas0..9

# Mapeamento colunas no CSV RF (0-indexed, sem header)
# Estabelecimentos: CNPJ_BASICO|CNPJ_ORDEM|CNPJ_DV|IDENTIFICADOR|NOME_FANTASIA|
#   SITUACAO_CADASTRAL|DATA_SITUACAO|MOTIVO_SITUACAO|NOME_CIDADE_EXTERIOR|PAIS|
#   DATA_INICIO_ATIVIDADE|CNAE_FISCAL_PRINCIPAL|CNAE_FISCAL_SECUNDARIA|
#   TIPO_LOGRADOURO|LOGRADOURO|NUMERO|COMPLEMENTO|BAIRRO|CEP|UF|MUNICIPIO|
#   DDD1|TELEFONE1|DDD2|TELEFONE2|DDDfax|FAX|CORREIO_ELETRONICO|
#   SITUACAO_ESPECIAL|DATA_SITUACAO_ESPECIAL
E_BASICO = 0; E_ORDEM = 1; E_DV = 2; E_FANTASIA = 4
E_SITUACAO = 5; E_DATA_SITUACAO = 6; E_DATA_ABERTURA = 10
E_CNAE_PRINC = 11; E_CNAE_SEC = 12
E_TIPO_LOGR = 13; E_LOGR = 14; E_NUMERO = 15; E_COMPL = 16
E_BAIRRO = 17; E_CEP = 18; E_UF = 19; E_MUNICIPIO = 20
E_DDD1 = 21; E_TEL1 = 22; E_DDD2 = 23; E_TEL2 = 24
E_EMAIL = 27

# Empresas: CNPJ_BASICO|RAZAO_SOCIAL|...
EM_BASICO = 0; EM_RAZAO = 1

# Municipios: CODIGO|DESCRICAO
MUN_COD = 0; MUN_DESC = 1

BATCH_SIZE = 2000


def _load_env() -> None:
    candidates = [Path.home() / ".hermes" / ".env", _ROOT / ".env"]
    for p in candidates:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip(); v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        break


def _pg_connect():
    import psycopg2
    host = os.environ.get("HERMES_PG_HOST", "127.0.0.1")
    port = int(os.environ.get("HERMES_PG_PORT", "5433"))
    user = os.environ.get("HERMES_PG_USER", "hermes")
    password = os.environ.get("HERMES_PG_PASSWORD", "")
    db = os.environ.get("HERMES_PG_DB", "hermes")
    # G5 fail-closed: senha vazia = config incompleta. Erro claro antes de tentar conectar.
    if not password:
        raise RuntimeError("HERMES_PG_PASSWORD nao configurado — ingestao CNPJ abortada")
    return psycopg2.connect(
        host=host, port=port, user=user, password=password, dbname=db,
        connect_timeout=10,
    )


def _ensure_schema(conn) -> None:
    """Cria schema cnpj + tabela estabelecimentos + indexes GIN trigram."""
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS cnpj")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cnpj.estabelecimentos (
                cnpj        CHAR(14) PRIMARY KEY,
                cnpj_basico CHAR(8)  NOT NULL,
                nome_fantasia    TEXT,
                razao_social     TEXT,
                cnae_principal   CHAR(7),
                cnae_secundarios TEXT,
                situacao_cadastral CHAR(2),
                data_situacao    DATE,
                data_abertura    DATE,
                logradouro       TEXT,
                numero           TEXT,
                bairro           TEXT,
                cep              CHAR(8),
                municipio_rf     INTEGER,
                uf               CHAR(2),
                telefone1        TEXT,
                telefone2        TEXT,
                email            TEXT
            )
        """)
        # GIN indexes pra trigram fuzzy match PT-BR
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_estab_fantasia_trgm
            ON cnpj.estabelecimentos
            USING gin (unaccent(lower(nome_fantasia)) gin_trgm_ops)
            WHERE nome_fantasia IS NOT NULL
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_estab_razao_trgm
            ON cnpj.estabelecimentos
            USING gin (unaccent(lower(razao_social)) gin_trgm_ops)
            WHERE razao_social IS NOT NULL
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_estab_municipio
            ON cnpj.estabelecimentos(municipio_rf)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_estab_cnpj_basico
            ON cnpj.estabelecimentos(cnpj_basico)
        """)
    conn.commit()
    logger.info("Schema cnpj.estabelecimentos OK")


def _download_stream(url: str) -> bytes:
    """Baixa URL inteira, loggando progresso a cada 50MB."""
    logger.info("Baixando %s", url)
    req = Request(url, headers={"User-Agent": "HermesBot/2.0 (dados abertos RF)"})
    chunks = []
    total = 0
    try:
        with urlopen(req, timeout=300) as resp:
            while True:
                chunk = resp.read(1 << 20)  # 1 MB
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total % (50 << 20) < (1 << 20):
                    logger.info("  %dMB baixados…", total >> 20)
    except URLError as exc:
        raise RuntimeError(f"Download falhou {url}: {exc}") from exc
    logger.info("  Download completo: %dMB", total >> 20)
    return b"".join(chunks)


def _iter_csv_zip(data: bytes, filename_hint: str = "") -> Generator[list[str], None, None]:
    """Itera linhas CSV de dentro do zip, encoding Latin-1 (padrão RF)."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        target = names[0]  # RF sempre 1 arquivo por zip
        logger.info("  CSV interno: %s (%d nomes)", target, len(names))
        with zf.open(target) as f:
            reader = csv.reader(
                io.TextIOWrapper(f, encoding="latin-1", errors="replace"),
                delimiter=";",
                quotechar='"',
            )
            for row in reader:
                yield row


def _find_cuiaba_rf_code(base_url: str) -> int:
    """Baixa Municipios.zip e encontra o código RF de Cuiabá-MT."""
    url = base_url.rstrip("/") + "/Municipios.zip"
    data = _download_stream(url)
    for row in _iter_csv_zip(data, "Municipios"):
        if len(row) < 2:
            continue
        desc = row[MUN_DESC].strip().upper()
        cod_str = row[MUN_COD].strip()
        # Procura "CUIABA" (sem cedilha — RF usa ASCII uppercase)
        if "CUIABA" in desc and cod_str.isdigit():
            code = int(cod_str)
            logger.info("Cuiabá código RF = %d (%s)", code, row[MUN_DESC].strip())
            return code
    raise RuntimeError("Cuiabá não encontrado em Municipios.zip — verificar dump RF")


def _load_empresas(base_url: str, cuiaba_basicos: set[str]) -> dict[str, str]:
    """Carrega Empresas*.zip e retorna {cnpj_basico: razao_social} para set filtrado."""
    razoes: dict[str, str] = {}
    for i in range(NUM_SHARDS):
        url = base_url.rstrip("/") + f"/Empresas{i}.zip"
        try:
            data = _download_stream(url)
        except RuntimeError as exc:
            logger.warning("Empresas%d: %s — pulando", i, exc)
            continue
        count = 0
        for row in _iter_csv_zip(data, f"Empresas{i}"):
            if len(row) <= EM_RAZAO:
                continue
            basico = row[EM_BASICO].strip().zfill(8)
            if basico in cuiaba_basicos:
                razoes[basico] = row[EM_RAZAO].strip()
                count += 1
        logger.info("Empresas%d: %d razoes encontradas (acumulado %d)", i, count, len(razoes))
        if len(razoes) >= len(cuiaba_basicos):
            logger.info("Todos cnpj_basicos encontrados — interrompendo empresas scan")
            break
    return razoes


def _safe_date(s: str) -> Optional[str]:
    """'20230415' → '2023-04-15', mantém None pra valor inválido."""
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return None


def _safe_phone(ddd: str, num: str) -> Optional[str]:
    ddd = ddd.strip(); num = num.strip()
    if num and num != "0":
        return f"+55{ddd}{num}" if ddd else num
    return None


def run(base_url: str, dry_run: bool = False) -> int:
    """Executa ingestão completa. Retorna COUNT(*) final."""
    _load_env()

    conn = _pg_connect()
    logger.info("Conectado ao hermes-postgres")
    _ensure_schema(conn)

    # 1) Código RF de Cuiabá
    cuiaba_code = _find_cuiaba_rf_code(base_url)

    # 2) Stream Estabelecimentos — dois passes: (a) filtrar+coletar cnpj_basicos, (b) upsert
    rows_cuiaba: list[dict] = []
    cuiaba_basicos: set[str] = set()

    for i in range(NUM_SHARDS):
        url = base_url.rstrip("/") + f"/Estabelecimentos{i}.zip"
        try:
            data = _download_stream(url)
        except RuntimeError as exc:
            logger.warning("Estabelecimentos%d: %s — pulando", i, exc)
            continue

        count_shard = 0
        for row in _iter_csv_zip(data, f"Estabelecimentos{i}"):
            if len(row) <= E_MUNICIPIO:
                continue
            uf = row[E_UF].strip().upper()
            mun_str = row[E_MUNICIPIO].strip()
            if uf != "MT" or not mun_str.isdigit():
                continue
            if int(mun_str) != cuiaba_code:
                continue

            basico = row[E_BASICO].strip().zfill(8)
            ordem = row[E_ORDEM].strip().zfill(4)
            dv = row[E_DV].strip().zfill(2)
            cnpj_full = basico + ordem + dv

            logr = " ".join(filter(None, [
                row[E_TIPO_LOGR].strip(),
                row[E_LOGR].strip(),
                row[E_NUMERO].strip(),
                row[E_COMPL].strip(),
            ])) or None

            rows_cuiaba.append({
                "cnpj": cnpj_full,
                "cnpj_basico": basico,
                "nome_fantasia": row[E_FANTASIA].strip() or None,
                "cnae_principal": row[E_CNAE_PRINC].strip() or None,
                "cnae_secundarios": row[E_CNAE_SEC].strip() or None,
                "situacao_cadastral": row[E_SITUACAO].strip() or None,
                "data_situacao": _safe_date(row[E_DATA_SITUACAO]),
                "data_abertura": _safe_date(row[E_DATA_ABERTURA]),
                "logradouro": logr,
                "numero": row[E_NUMERO].strip() or None,
                "bairro": row[E_BAIRRO].strip() or None,
                "cep": row[E_CEP].strip().replace("-", "") or None,
                "municipio_rf": cuiaba_code,
                "uf": "MT",
                "telefone1": _safe_phone(row[E_DDD1], row[E_TEL1]),
                "telefone2": _safe_phone(row[E_DDD2], row[E_TEL2]),
                "email": row[E_EMAIL].strip().lower() or None,
                "razao_social": None,  # preenchido abaixo
            })
            cuiaba_basicos.add(basico)
            count_shard += 1

        logger.info("Estabelecimentos%d: %d Cuiabá (acumulado %d)", i, count_shard, len(rows_cuiaba))

    if not rows_cuiaba:
        logger.error("Nenhum estabelecimento Cuiabá encontrado. Verificar código RF e dump.")
        conn.close()
        return 0

    logger.info("Total encontrado: %d estabelecimentos Cuiabá", len(rows_cuiaba))

    # 3) Join razao_social de Empresas
    razoes = _load_empresas(base_url, cuiaba_basicos)
    for r in rows_cuiaba:
        r["razao_social"] = razoes.get(r["cnpj_basico"])

    if dry_run:
        logger.info("DRY-RUN: %d linhas (sem inserir). Primeiras 5:", len(rows_cuiaba))
        for r in rows_cuiaba[:5]:
            logger.info("  %s | %s | %s | %s", r["cnpj"], r["razao_social"] or r["nome_fantasia"], r["cnae_principal"], r["situacao_cadastral"])
        conn.close()
        return len(rows_cuiaba)

    # 4) UPSERT em batches
    upsert_sql = """
        INSERT INTO cnpj.estabelecimentos
            (cnpj, cnpj_basico, nome_fantasia, razao_social, cnae_principal,
             cnae_secundarios, situacao_cadastral, data_situacao, data_abertura,
             logradouro, numero, bairro, cep, municipio_rf, uf,
             telefone1, telefone2, email)
        VALUES
            (%(cnpj)s, %(cnpj_basico)s, %(nome_fantasia)s, %(razao_social)s,
             %(cnae_principal)s, %(cnae_secundarios)s, %(situacao_cadastral)s,
             %(data_situacao)s, %(data_abertura)s,
             %(logradouro)s, %(numero)s, %(bairro)s, %(cep)s,
             %(municipio_rf)s, %(uf)s, %(telefone1)s, %(telefone2)s, %(email)s)
        ON CONFLICT (cnpj) DO UPDATE SET
            nome_fantasia     = EXCLUDED.nome_fantasia,
            razao_social      = EXCLUDED.razao_social,
            cnae_principal    = EXCLUDED.cnae_principal,
            cnae_secundarios  = EXCLUDED.cnae_secundarios,
            situacao_cadastral= EXCLUDED.situacao_cadastral,
            data_situacao     = EXCLUDED.data_situacao,
            logradouro        = EXCLUDED.logradouro,
            bairro            = EXCLUDED.bairro,
            telefone1         = EXCLUDED.telefone1,
            telefone2         = EXCLUDED.telefone2,
            email             = EXCLUDED.email
    """
    total_inserted = 0
    t0 = time.time()
    for i in range(0, len(rows_cuiaba), BATCH_SIZE):
        batch = rows_cuiaba[i:i + BATCH_SIZE]
        with conn.cursor() as cur:
            cur.executemany(upsert_sql, batch)
        conn.commit()
        total_inserted += len(batch)
        if total_inserted % 10000 == 0 or total_inserted == len(rows_cuiaba):
            logger.info("  Upsert: %d/%d (%.1fs)", total_inserted, len(rows_cuiaba), time.time() - t0)

    # 5) Relatório final
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cnpj.estabelecimentos WHERE municipio_rf = %s", (cuiaba_code,))
        final_count = cur.fetchone()[0]

    logger.info(
        "Ingestão completa: %d total em cnpj.estabelecimentos (Cuiabá, municipio_rf=%d) — %.1fs",
        final_count, cuiaba_code, time.time() - t0,
    )
    conn.close()
    return final_count


def _latest_base_url() -> str:
    """Tenta detectar o dump mais recente (últimos 12 meses, mais recente primeiro)."""
    from datetime import datetime, timedelta
    today = datetime.utcnow()
    for delta_months in range(0, 12):
        year = today.year
        month = today.month - delta_months
        while month <= 0:
            month += 12
            year -= 1
        candidate = f"{RF_BASE}/{year:04d}-{month:02d}/"
        try:
            req = Request(
                candidate + "Municipios.zip",
                headers={"User-Agent": "HermesBot/2.0"},
                method="HEAD",
            )
            with urlopen(req, timeout=15) as resp:
                if resp.status < 400:
                    logger.info("Dump RF detectado: %s", candidate)
                    return candidate
        except Exception:
            pass
    raise RuntimeError("Nenhum dump RF acessível nos últimos 12 meses. Passe --base-url manualmente.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingestão RF CNPJ → hermes-postgres (Cuiabá)")
    parser.add_argument(
        "--base-url",
        help="URL base do dump RF (ex: https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/2025-05/)",
    )
    parser.add_argument(
        "--year-month",
        help="Ano-mês do dump (ex: 2025-05). Alternativa a --base-url.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Contar linhas sem inserir no Postgres")
    args = parser.parse_args()

    if args.base_url:
        base = args.base_url
    elif args.year_month:
        base = f"{RF_BASE}/{args.year_month}/"
    else:
        base = _latest_base_url()

    count = run(base_url=base, dry_run=args.dry_run)
    logger.info("Resultado final: %d registros", count)
    sys.exit(0 if count > 0 else 1)
