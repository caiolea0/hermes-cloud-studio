"""F.8.1 — NIM credit balance polling cron (daily 09h BRT).

Cross-ref: .claude/PLAN.md § "F.8 Decisões Cristalizadas" D7 (NIM polling INCLUIR F.8.1,
F.5.9 deferred → F.8.1 absorve).

Reuses nim_credit_history table F.5.7 schema:
  (balance_credits, free_rpm_window_count, recorded_at, source)

NVIDIA NIM credit endpoint (BEST-EFFORT — URL not publicly documented for free tier):
  GET https://integrate.api.nvidia.com/v1/account/credits
  Authorization: Bearer $HERMES_NIM_API_KEY

⚠️ Initial deploy: endpoint may return 404 (owner discovers real URL via
build.nvidia.com dashboard or NVIDIA dev support). Script gracefully captures
non-200 to errors_inbox + Sentry — cron continues. Owner adjusts NIM_API_URL
constant when endpoint confirmed.

Defesa-em-profundidade:
- key missing -> exit 0 + warn (não crash cron)
- 401/403/network -> insert errors_inbox + Sentry capture, exit 1 (cron retry next day)
- 200 OK -> insert nim_credit_history (source='cron_daily')

Cron register via mcp__scheduled-tasks__create_scheduled_task ("0 9 * * *"
America/Cuiaba) — see commit message F.8.1b.

Run manual: python scripts/check_nim_credits.py
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Best-effort .env load — cron environments often lack env vars.
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from core.observability import record_error_inbox  # noqa: E402

DB_PATH = ROOT / "hermes_local.db"
NIM_API_URL = "https://integrate.api.nvidia.com/v1/account/credits"
WARNING_THRESHOLD = 1000.0
CRITICAL_THRESHOLD = 200.0

try:
    import sentry_sdk  # type: ignore
    _SENTRY_OK = True
except ImportError:
    sentry_sdk = None  # type: ignore
    _SENTRY_OK = False


def _extract_balance(payload: dict) -> float:
    """Best-effort balance extraction.

    NVIDIA NIM response shape is not publicly documented for credit balance —
    accept a few common keys. Owner adjusts after first successful poll.
    """
    for key in ("credits_remaining", "balance", "remaining", "credit_balance"):
        if key in payload and isinstance(payload[key], (int, float)):
            return float(payload[key])
    # Nested .data.* fallback
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        for key in ("credits_remaining", "balance", "remaining"):
            if key in data and isinstance(data[key], (int, float)):
                return float(data[key])
    return 0.0


def _insert_history(balance: float, source: str = "cron_daily") -> None:
    conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
    try:
        conn.execute(
            "INSERT INTO nim_credit_history (balance_credits, source) VALUES (?, ?)",
            (balance, source),
        )
        conn.commit()
    finally:
        conn.close()


async def poll_nim_credits() -> dict:
    api_key = os.getenv("HERMES_NIM_API_KEY", "")
    if not api_key.startswith("nvapi-"):
        return {"ok": False, "error": "key_missing_or_invalid_prefix",
                "balance_credits": None}

    if not DB_PATH.exists():
        return {"ok": False, "error": f"DB not found: {DB_PATH}",
                "balance_credits": None}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                NIM_API_URL,
                headers={"Authorization": f"Bearer {api_key}",
                         "Accept": "application/json"},
            )
        except Exception as exc:
            record_error_inbox(
                DB_PATH,
                category="nim_polling_error",
                severity="warning",
                title="NIM credit polling network error",
                message=str(exc)[:1000],
            )
            if _SENTRY_OK and sentry_sdk is not None:
                sentry_sdk.capture_exception(exc)
            return {"ok": False, "error": f"network: {exc}",
                    "balance_credits": None}

    if resp.status_code != 200:
        snippet = resp.text[:500] if resp.text else ""
        record_error_inbox(
            DB_PATH,
            category="nim_polling_error",
            severity="warning" if resp.status_code < 500 else "critical",
            title=f"NIM credit polling HTTP {resp.status_code}",
            message=snippet,
        )
        return {"ok": False, "error": f"http_{resp.status_code}",
                "balance_credits": None, "snippet": snippet}

    try:
        payload = resp.json()
    except Exception as exc:
        record_error_inbox(
            DB_PATH,
            category="nim_polling_error",
            severity="warning",
            title="NIM credit polling JSON parse fail",
            message=str(exc)[:500],
        )
        return {"ok": False, "error": f"json_parse: {exc}",
                "balance_credits": None}

    balance = _extract_balance(payload)
    try:
        _insert_history(balance, source="cron_daily")
    except Exception as exc:
        record_error_inbox(
            DB_PATH,
            category="nim_polling_error",
            severity="critical",
            title="NIM credit history insert failed",
            message=str(exc)[:500],
        )
        if _SENTRY_OK and sentry_sdk is not None:
            sentry_sdk.capture_exception(exc)
        return {"ok": False, "error": f"db_insert: {exc}",
                "balance_credits": balance}

    return {
        "ok": True,
        "balance_credits": balance,
        "warning":  balance < WARNING_THRESHOLD,
        "critical": balance < CRITICAL_THRESHOLD,
        "source": "cron_daily",
    }


def main() -> int:
    result = asyncio.run(poll_nim_credits())
    print(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
