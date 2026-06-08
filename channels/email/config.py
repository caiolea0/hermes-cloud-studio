"""Email channel — config + paths.

MERGED-010 (E.1). SMTP outreach channel.
Paralelo ao linkedin/config.py em estrutura (dataclass + paths + helpers).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "channels_data" / "email"
RATE_DB_PATH = DATA_DIR / "email_rate.db"
TEMPLATE_DIR = DATA_DIR / "templates"

for d in (DATA_DIR, TEMPLATE_DIR):
    d.mkdir(parents=True, exist_ok=True)


@dataclass
class EmailConfig:
    """Configuração do channel Email pra outreach.

    Carrega de `config.settings` via `EmailConfig.from_settings()`.
    """

    # --- Account ---
    from_address: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    app_password: str = ""  # NUNCA logar/printar

    # --- Rate caps ---
    daily_cap: int = 500       # Gmail free = 500/dia (paid Workspace = 2000)
    hourly_cap: int = 50       # 50/h = distribui mais natural ao longo do dia

    # --- Warm-up ---
    warmup_days: int = 14
    warmup_start_pct: float = 0.10
    warmup_end_pct: float = 0.80

    # --- Send behavior ---
    reply_to: Optional[str] = None
    default_headers: dict = field(default_factory=dict)
    timeout: float = 30.0
    retry_max: int = 3
    retry_backoff: float = 2.0  # seconds * 2^attempt

    # --- Working hours (anti-spam signal) ---
    working_hours_enabled: bool = True
    working_hours_start: int = 8
    working_hours_end: int = 19
    working_days: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])  # Mon-Fri

    @classmethod
    def from_settings(cls) -> "EmailConfig":
        """Constrói EmailConfig a partir de `config.settings` (HermesSettings)."""
        from config import settings

        return cls(
            from_address=settings.email_from,
            smtp_host=settings.email_smtp_host,
            smtp_port=settings.email_smtp_port,
            app_password=settings.email_app_password,
            daily_cap=settings.email_daily_cap,
            hourly_cap=settings.email_hourly_cap,
            warmup_days=settings.email_warmup_days,
            warmup_start_pct=settings.email_warmup_start_pct,
            warmup_end_pct=settings.email_warmup_end_pct,
        )

    def assert_ready(self) -> None:
        """Fail-closed: aborta se credentials não configurados."""
        if not self.from_address:
            raise RuntimeError(
                "EMAIL_FROM ausente. Setar em .env antes de usar channels.email."
            )
        if not self.app_password:
            raise RuntimeError(
                "EMAIL_APP_PASSWORD ausente. Gerar em myaccount.google.com/apppasswords "
                "e setar em .env como EMAIL_APP_PASSWORD."
            )
