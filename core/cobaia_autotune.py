"""F.7 C5 — Cobaia auto-tune: KPI breach → synthesis trigger (D10 reactive automatic).

detect_and_trigger() aggregates:
  1. detect_sustained_low_kpi() — KPIs below D3 thresholds for sustained hours
  2. get_last_autotune_trigger() — 72h cooldown gate (anti-cascade storm)
  3. Insert cobaia_autotune_triggers row (audit trail)
  4. REUSE F.4.2 synthesis_runs via core.skill_proposals (ensure_synthesis_runs_table)
  5. WS emit + Sentry breadcrumb + Telegram alert (C4 TelegramClient reuse)

Auto-triggered WITHOUT owner confirm (D10). PR review = the gate (F.4.2 C2 pattern).
"""
from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.cobaia_metrics import (
    KPI_THRESHOLDS,
    detect_sustained_low_kpi,
    get_last_autotune_trigger,
)

logger = logging.getLogger("hermes.cobaia.autotune")

COOLDOWN_HOURS = 72
COBAIA_REQUESTER = "brain-f7-cobaia-autotune"


def _db_path() -> Path:
    try:
        from core.state import DB_PATH
        return DB_PATH
    except Exception:
        return Path(__file__).parent.parent / "hermes_local.db"


def _get_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or _db_path()
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _ensure_autotune_table(conn: sqlite3.Connection) -> None:
    """Idempotent — create cobaia_autotune_triggers if not present."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cobaia_autotune_triggers (
            id TEXT PRIMARY KEY,
            account_handle TEXT NOT NULL,
            trigger_at TEXT NOT NULL,
            kpi_breached TEXT NOT NULL,
            kpi_value REAL NOT NULL,
            kpi_threshold REAL NOT NULL,
            sustained_hours INTEGER NOT NULL,
            synthesis_run_id TEXT NULL,
            result_status TEXT NULL,
            result_pr_url TEXT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cobaia_autotune_account
            ON cobaia_autotune_triggers(account_handle, trigger_at DESC);
        """
    )
    conn.commit()


def _insert_trigger_row(
    conn: sqlite3.Connection,
    trigger_id: str,
    account_handle: str,
    kpi: str,
    kpi_value: float,
    kpi_threshold: float,
    sustained_hours: int,
    synthesis_run_id: Optional[str],
    now: str,
) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO cobaia_autotune_triggers
           (id, account_handle, trigger_at, kpi_breached, kpi_value, kpi_threshold,
            sustained_hours, synthesis_run_id, result_status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            trigger_id,
            account_handle,
            now,
            kpi,
            kpi_value,
            kpi_threshold,
            sustained_hours,
            synthesis_run_id,
            "queued",
            now,
        ),
    )
    conn.commit()


def _queue_synthesis_run(kpi_name: str, account_handle: str, now: str) -> Optional[str]:
    """REUSE F.4.2 synthesis_runs table: insert 'queued' row, return run_id.

    Does NOT invoke AutoSkillRunner (avoids GatewayDispatcher dependency in sync
    context). Directly uses core.skill_proposals primitives — same table + schema.
    """
    try:
        from core.skill_proposals import (
            _connect as _sp_connect,
            ensure_synthesis_runs_table,
        )
        run_id = str(uuid.uuid4())
        trigger_source = f"cobaia_autotune_{kpi_name}"
        conn = _sp_connect()
        try:
            ensure_synthesis_runs_table(conn)
            conn.execute(
                """INSERT INTO synthesis_runs
                   (id, trigger_type, status, queued_at, requester, trigger_source)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (run_id, "cron", "queued", now, COBAIA_REQUESTER, trigger_source),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info(
            "synthesis_run queued: run_id=%s kpi=%s account=%s",
            run_id, kpi_name, account_handle,
        )
        return run_id
    except Exception as exc:
        logger.warning("synthesis_run queue failed: %s", exc)
        return None


def _ws_emit(event_type: str, data: dict) -> None:
    try:
        from core.state import ws_manager
        import asyncio
        import json
        payload = json.dumps({"type": event_type, **data})
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(ws_manager.broadcast(payload))
    except Exception:
        pass


def _sentry_breadcrumb(msg: str, data: dict) -> None:
    from core.sentry_via_gateway import add_breadcrumb
    add_breadcrumb(category="cobaia_autotune", message=msg, data=data, level="info")


def _telegram_alert(kpi_name: str, kpi_value: float, threshold: float) -> None:
    try:
        from core.telegram_client import TelegramClient
        client = TelegramClient()
        client.send_alert(
            severity="warning",
            title=f"Cobaia autotune: {kpi_name} abaixo do limite",
            body=(
                f"Valor atual: {kpi_value:.4f} | Limite D3: {threshold:.4f}\n"
                f"Breach 24h+ → synthesis queued (F.4.2 scaffold)"
            ),
        )
    except Exception as exc:
        logger.debug("telegram_alert for autotune failed: %s", exc)


def detect_and_trigger(
    account_handle: str = "cobaia",
    sustained_hours: int = 24,
    db_path: Optional[Path] = None,
) -> dict:
    """Detect sustained KPI breaches and trigger synthesis if cooldown allows.

    D10 — reactive automatic: no owner confirm required; queued in synthesis_runs.

    Returns:
        {
            triggered: int,   number of KPIs that fired synthesis
            skipped: int,     number of KPIs still in 72h cooldown
            breaches: list,   all detected KPI breaches (triggered + skipped)
            triggered_kpis: list[str],
        }
    """
    now = datetime.now(timezone.utc).isoformat()
    actual_db = db_path or _db_path()

    breaches = detect_sustained_low_kpi(
        account_handle, hours=sustained_hours, db_path=actual_db
    )

    if not breaches:
        logger.info("cobaia autotune: no KPI breaches detected for %s", account_handle)
        return {"triggered": 0, "skipped": 0, "breaches": [], "triggered_kpis": []}

    logger.info(
        "cobaia autotune: %d breach(es) for %s: %s",
        len(breaches),
        account_handle,
        [b["kpi"] for b in breaches],
    )

    triggered = 0
    skipped = 0
    triggered_kpis: list[str] = []

    conn = _get_db(actual_db)
    try:
        _ensure_autotune_table(conn)
    finally:
        conn.close()

    for breach in breaches:
        kpi_name = breach["kpi"]
        kpi_value = breach["value"]
        kpi_threshold = breach["threshold"]
        breach_hours = breach["sustained_hours"]

        # 72h cooldown gate
        last = get_last_autotune_trigger(
            account_handle, kpi_name,
            cooldown_hours=COOLDOWN_HOURS, db_path=actual_db,
        )
        if last:
            logger.info(
                "cobaia autotune cooldown active: kpi=%s last_trigger=%s",
                kpi_name, last.get("trigger_at"),
            )
            skipped += 1
            continue

        # Queue synthesis_run (REUSE F.4.2)
        run_id = _queue_synthesis_run(kpi_name, account_handle, now)

        # Persist trigger row
        trigger_id = str(uuid.uuid4())
        conn = _get_db(actual_db)
        try:
            _insert_trigger_row(
                conn, trigger_id, account_handle,
                kpi_name, kpi_value, kpi_threshold,
                breach_hours, run_id, now,
            )
        finally:
            conn.close()

        # Side effects (best-effort)
        _ws_emit("cobaia.autotune_triggered", {
            "account_handle": account_handle,
            "kpi": kpi_name,
            "value": kpi_value,
            "threshold": kpi_threshold,
            "run_id": run_id,
            "trigger_id": trigger_id,
        })
        _sentry_breadcrumb("cobaia.autotune_triggered", {
            "kpi": kpi_name, "value": kpi_value, "run_id": run_id,
        })
        _telegram_alert(kpi_name, kpi_value, kpi_threshold)

        triggered += 1
        triggered_kpis.append(kpi_name)
        logger.info(
            "cobaia autotune triggered: kpi=%s value=%.4f threshold=%.4f run_id=%s",
            kpi_name, kpi_value, kpi_threshold, run_id,
        )

    return {
        "triggered": triggered,
        "skipped": skipped,
        "breaches": breaches,
        "triggered_kpis": triggered_kpis,
    }
