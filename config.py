"""Hermes Cloud Studio — Settings central (pydantic-settings).

Fonte da verdade pra TODAS env vars do projeto. Substitui os.environ.get espalhado.

Uso:
    from config import settings
    settings.auth_token
    settings.vm_host

Carregamento:
    1. .env na raiz (se existir)
    2. variáveis de ambiente (override .env)

Required fields (sem default) abortam startup se ausentes — fail-closed.
Optional fields têm default seguro.

Notas:
    - Pra PC: .env em D:\\dev-projects\\main\\hermes-cloud-studio\\.env
    - Pra VM: copiar config.py + ~/.hermes/.env. HERMES_HOME aponta pra base.
    - HERMES_AUTH_TOKEN / HERMES_INTERNAL_TOKEN / HERMES_VM_AUTH_TOKEN devem
      ser gerados via: python -c "import secrets; print(secrets.token_urlsafe(32))"
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_BASE_DIR = Path(__file__).parent


class HermesSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Auth (fail-closed: vazio dispara raise no consumidor) ---
    auth_token: str = Field(default="", validation_alias="HERMES_AUTH_TOKEN")
    internal_token: str = Field(default="", validation_alias="HERMES_INTERNAL_TOKEN")
    vm_auth_token: str = Field(default="", validation_alias="HERMES_VM_AUTH_TOKEN")

    # --- VM connection ---
    vm_host: str = Field(default="136.115.74.69", validation_alias="VM_HOST")
    vm_user: str = Field(default="hermes-gcp", validation_alias="VM_USER")
    vm_api_url: str = Field(default="", validation_alias="HERMES_VM_API")
    vm_api_port: int = Field(default=8420, validation_alias="VM_API_PORT")

    # --- Proxy / Tunnel ---
    socks5_port: int = Field(default=55081, validation_alias="PROXY_PORT")
    proxy_user: str = Field(default="hermes", validation_alias="PROXY_USER")
    proxy_pass: str = Field(default="", validation_alias="PROXY_PASS")

    # --- Dashboard ---
    dashboard_port: int = Field(default=55000, validation_alias="DASHBOARD_PORT")
    sync_interval: int = Field(default=60, validation_alias="HERMES_SYNC_INTERVAL")

    # --- Agent Zero ---
    agent_zero_url: str = Field(default="http://localhost:50080", validation_alias="AGENT_ZERO_URL")
    agent_zero_api_key: str = Field(default="", validation_alias="AGENT_ZERO_API_KEY")

    # --- External APIs ---
    google_places_api_key: str = Field(default="", validation_alias="GOOGLE_PLACES_API_KEY")
    openrouter_api_key: str = Field(default="", validation_alias="OPENROUTER_API_KEY")

    # H2-F4 — Google PageSpeed Insights (free, 25k/dia, 240/min)
    pagespeed_key: str = Field(default="", validation_alias="HERMES_PAGESPEED_KEY")

    # --- GitHub (F.4.2 PAT + F.4.4 webhook secret) ---
    github_personal_access_token: str = Field(default="", validation_alias="GITHUB_PERSONAL_ACCESS_TOKEN")
    github_webhook_secret: str = Field(default="", validation_alias="GITHUB_WEBHOOK_SECRET")

    # --- AgentMemory ---
    agentmemory_url: str = Field(default="http://localhost:3111", validation_alias="AGENTMEMORY_URL")

    # --- Ollama (MERGED-014 router) ---
    # PC tunnel reverso (RTX 2060 6GB) e' o primary. fallback vazio = sem VM local.
    # Migracao VM-GPU: trocar ollama_url pra http://localhost:11434 e setar fallback="".
    ollama_url: str = Field(default="http://localhost:11434", validation_alias="OLLAMA_URL")
    ollama_url_fallback: str = Field(default="", validation_alias="HERMES_OLLAMA_FALLBACK_URL")
    ollama_model_classify: str = Field(default="qwen2.5:3b", validation_alias="HERMES_OLLAMA_MODEL_CLASSIFY")
    ollama_model_creative: str = Field(default="qwen2.5:7b-instruct", validation_alias="HERMES_OLLAMA_MODEL_CREATIVE")
    ollama_connect_timeout: float = Field(default=3.0, validation_alias="HERMES_OLLAMA_CONNECT_TIMEOUT")
    ollama_request_timeout: float = Field(default=45.0, validation_alias="HERMES_OLLAMA_REQUEST_TIMEOUT")

    # --- Telegram ---
    telegram_bot_token: str = Field(default="", validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", validation_alias="TELEGRAM_CHAT_ID")

    # --- Email (MERGED-010 E.1 channel) ---
    email_from: str = Field(default="", validation_alias="EMAIL_FROM")
    email_to: str = Field(default="", validation_alias="EMAIL_TO")
    email_app_password: str = Field(default="", validation_alias="EMAIL_APP_PASSWORD")
    email_smtp_host: str = Field(default="smtp.gmail.com", validation_alias="EMAIL_SMTP_HOST")
    email_smtp_port: int = Field(default=587, validation_alias="EMAIL_SMTP_PORT")
    email_daily_cap: int = Field(default=500, validation_alias="EMAIL_DAILY_CAP")
    email_hourly_cap: int = Field(default=50, validation_alias="EMAIL_HOURLY_CAP")
    email_warmup_days: int = Field(default=14, validation_alias="EMAIL_WARMUP_DAYS")
    email_warmup_start_pct: float = Field(default=0.10, validation_alias="EMAIL_WARMUP_START_PCT")
    email_warmup_end_pct: float = Field(default=0.80, validation_alias="EMAIL_WARMUP_END_PCT")

    # --- LinkedIn ---
    linkedin_email: str = Field(default="", validation_alias="LINKEDIN_EMAIL")
    linkedin_password: str = Field(default="", validation_alias="LINKEDIN_PASSWORD")
    linkedin_account_type: str = Field(default="free", validation_alias="LINKEDIN_ACCOUNT_TYPE")
    linkedin_proxy: Optional[str] = Field(default=None, validation_alias="LINKEDIN_PROXY")
    linkedin_proxy_user: Optional[str] = Field(default=None, validation_alias="LINKEDIN_PROXY_USER")
    linkedin_proxy_pass: Optional[str] = Field(default=None, validation_alias="LINKEDIN_PROXY_PASS")

    # --- Feature flags (Hermes 2.0) ---
    # FEATURE_LINKEDIN=off congela cobaia/warmup/stealth + sequence-send (daemon P0/P2).
    # Default True preserva o comportamento 1.x (GCP) até o cutover; VPS/2.0 seta "off".
    feature_linkedin: bool = Field(default=True, validation_alias="FEATURE_LINKEDIN")

    # FEATURE_SCRAPE_T2=on habilita Patchright headless como fallback quando T1 retorna vazio.
    # VPS-only (daemon container). Default off — T1 curl_cffi cobre ~40-70% dos sites.
    feature_scrape_t2: bool = Field(default=False, validation_alias="FEATURE_SCRAPE_T2")

    # H2-F3 scrape settings
    scrape_min_interval: float = Field(default=4.0, validation_alias="HERMES_SCRAPE_MIN_INTERVAL")
    scrape_max_concurrent: int = Field(default=4, validation_alias="HERMES_SCRAPE_MAX_CONCURRENT")

    # --- Hermes paths (HERMES_HOME default ~/.hermes; honra env var) ---
    hermes_home: Path = Field(
        default_factory=lambda: Path.home() / ".hermes",
        validation_alias="HERMES_HOME",
    )

    # --- VM bridge ---
    hermes_vm_restart_cmd: str = Field(
        default=(
            "systemctl --user restart hermes-api 2>/dev/null || "
            "(pkill -f hermes_api_v2 2>/dev/null; sleep 2; "
            "cd ~ && nohup python3 hermes_api_v2.py > logs/api.log 2>&1 & echo restarted)"
        ),
        validation_alias="HERMES_VM_RESTART_CMD",
    )
    hermes_pc_event_url: str = Field(
        default="http://127.0.0.1:55000/api/internal/linkedin/event",
        validation_alias="HERMES_PC_EVENT_URL",
    )

    # --- Hermes Postgres dedicado (H2-F2 CNPJ authority) ---
    # Senha gerada na VPS via openssl rand -hex 24 — NUNCA no git.
    # Em container: hermes_pg_host=hermes-postgres (docker network), port 5432.
    # No host VPS: host=127.0.0.1, port=5433.
    hermes_pg_host: str = Field(default="hermes-postgres", validation_alias="HERMES_PG_HOST")
    hermes_pg_port: int = Field(default=5432, validation_alias="HERMES_PG_PORT")
    hermes_pg_user: str = Field(default="hermes", validation_alias="HERMES_PG_USER")
    hermes_pg_password: str = Field(default="", validation_alias="HERMES_PG_PASSWORD")
    hermes_pg_db: str = Field(default="hermes", validation_alias="HERMES_PG_DB")

    @property
    def hermes_pg_dsn(self) -> str:
        return (
            f"postgresql://{self.hermes_pg_user}:{self.hermes_pg_password}"
            f"@{self.hermes_pg_host}:{self.hermes_pg_port}/{self.hermes_pg_db}"
        )

    @property
    def vm_api_url_resolved(self) -> str:
        """Retorna vm_api_url explícito OU computa de vm_host/vm_api_port."""
        return self.vm_api_url or f"http://{self.vm_host}:{self.vm_api_port}"


settings = HermesSettings()
