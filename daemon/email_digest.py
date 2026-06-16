"""F.7 C4 — Cobaia daily email digest (APScheduler job).

Job 'cobaia_email_digest_daily' fires at 09:00 BRT.
Renders bug export (24h) + warmup status → sends via Gmail SMTP.

On send failure: logs + Sentry breadcrumb, does NOT crash daemon.

Env vars (same as .env.example):
    EMAIL_FROM       sender address
    EMAIL_TO         recipient (default: cleao.mkt@gmail.com)
    EMAIL_APP_PASSWORD  Gmail app password
    EMAIL_SMTP_HOST  default smtp.gmail.com
    EMAIL_SMTP_PORT  default 587
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger("hermes.cobaia.email_digest")

RECIPIENT = os.environ.get("EMAIL_TO", "cleao.mkt@gmail.com")
SENDER = os.environ.get("EMAIL_FROM", "")
APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD", "")
SMTP_HOST = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("EMAIL_SMTP_PORT", "587"))


def _send_email(subject: str, body_text: str) -> bool:
    """Send plain-text email via SMTP. Returns True on success, False on skip/fail."""
    if not SENDER or not APP_PASSWORD:
        logger.info(
            "email_digest: SMTP not configured (EMAIL_FROM/EMAIL_APP_PASSWORD missing) — skipping"
        )
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SENDER
        msg["To"] = RECIPIENT
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER, APP_PASSWORD)
            server.sendmail(SENDER, [RECIPIENT], msg.as_string())
        logger.info("email_digest sent to %s subject=%r", RECIPIENT, subject)
        return True
    except Exception as exc:
        logger.warning("email_digest send failed: %s", exc)
        _sentry_breadcrumb("cobaia.email_digest_failed", {"error": str(exc)})
        return False


def _sentry_breadcrumb(msg: str, data: dict) -> None:
    try:
        import sentry_sdk  # type: ignore[import-not-found]
        sentry_sdk.add_breadcrumb(category="cobaia", message=msg, data=data, level="warning")
    except Exception:
        pass


def _render_digest() -> tuple[str, str]:
    """Returns (subject, body_text)."""
    from datetime import date

    from core.alert_aggregator import aggregate_bugs_24h, render_markdown_summary

    today = date.today().isoformat()
    subject = f"[Hermes Cobaia] Daily Digest {today}"

    data = aggregate_bugs_24h(hours=24)
    md = render_markdown_summary(data)

    warmup_line = "Warmup: status unavailable"
    try:
        from linkedin.cobaia_warmup import CobaiaWarmupManager
        from linkedin.config import CobaiaConfig

        mgr = CobaiaWarmupManager(cfg=CobaiaConfig())
        status = mgr.get_status()
        warmup_line = (
            f"Warmup: day {status.get('current_day', '?')}/{status.get('total_days', 14)} "
            f"phase={status.get('phase', '?')} "
            f"consecutive_errors={status.get('consecutive_errors', 0)}"
        )
    except Exception:
        pass

    body = f"{md}\n\n---\n{warmup_line}\n"
    return subject, body


def run_email_digest() -> None:
    """APScheduler job callback — render and send daily digest."""
    try:
        subject, body = _render_digest()
        _send_email(subject, body)
    except Exception as exc:
        logger.error("email_digest job exception: %s", exc, exc_info=True)
        _sentry_breadcrumb("cobaia.email_digest_exception", {"error": str(exc)})


def init_email_digest_scheduler(scheduler) -> bool:
    """Register cobaia_email_digest_daily job on an existing APScheduler instance.

    Returns True if registered, False if APScheduler unavailable.
    """
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("APScheduler not installed — email digest scheduler disabled")
        return False
    try:
        scheduler.add_job(
            run_email_digest,
            trigger=CronTrigger(hour=9, minute=0, timezone="America/Cuiaba"),
            id="cobaia_email_digest_daily",
            replace_existing=True,
            name="Cobaia email digest daily (F.7 C4)",
            misfire_grace_time=3600,
        )
        logger.info("cobaia_email_digest_daily registered — next fire: 09:00 BRT")
        return True
    except Exception as exc:
        logger.error("email digest scheduler registration failed: %s", exc)
        return False
