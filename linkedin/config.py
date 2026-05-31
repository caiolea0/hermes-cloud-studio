"""Configuration constants for LinkedIn anti-detection system."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "linkedin_data"
SESSION_DIR = DATA_DIR / "sessions"
PROFILE_DIR = DATA_DIR / "profiles"
RATE_DB_PATH = DATA_DIR / "rate_limits.db"

for d in (DATA_DIR, SESSION_DIR, PROFILE_DIR):
    d.mkdir(parents=True, exist_ok=True)


@dataclass
class LinkedInConfig:
    # --- Account ---
    account_email: str = ""
    account_type: str = "free"  # free | premium | sales_navigator

    # --- Proxy ---
    proxy_server: Optional[str] = None      # "http://host:port"
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None
    proxy_type: str = "residential"         # residential | datacenter

    # --- Rate Limits (per account type) ---
    # Defaults are SAFE limits (80% of real caps)
    daily_profile_views: int = 70           # free=70, premium=150, sales_nav=250
    daily_connection_requests: int = 30     # free=30, premium=80, sales_nav=150
    daily_messages: int = 25
    weekly_connection_requests: int = 40    # hard LinkedIn cap ~50/week free
    min_action_delay: float = 3.0           # seconds between actions
    max_action_delay: float = 15.0
    page_dwell_min: float = 8.0             # seconds on each profile page
    page_dwell_max: float = 45.0
    session_max_hours: float = 4.0          # max active session per day
    break_after_actions: int = 25           # take break after N actions
    break_duration_min: float = 120.0       # break 2-10 min
    break_duration_max: float = 600.0

    # --- Warm-up ---
    warmup_days: int = 14                   # days of gradual ramp-up
    warmup_start_pct: float = 0.15          # start at 15% of daily limit
    warmup_end_pct: float = 0.80            # ramp to 80%

    # --- Browser ---
    headless: bool = True
    use_system_chrome: bool = True          # channel="chrome" for real TLS fingerprint
    user_data_dir: Optional[str] = None     # persistent browser profile
    viewport_width: int = 1366
    viewport_height: int = 768
    timezone: str = "America/Sao_Paulo"
    locale: str = "pt-BR"
    geolocation: Optional[dict] = None      # {"latitude": -23.55, "longitude": -46.63}

    # --- Human Behavior ---
    mouse_speed: float = 1.0                # multiplier for mouse movement speed
    typing_speed: float = 1.0               # multiplier (1.0 = ~120ms avg between keys)
    scroll_naturally: bool = True
    simulate_reading: bool = True

    # --- Session ---
    session_file: Optional[str] = None      # path to saved auth state
    reuse_session: bool = True

    def apply_account_type(self):
        """Adjust limits based on account type."""
        if self.account_type == "premium":
            self.daily_profile_views = 150
            self.daily_connection_requests = 80
            self.daily_messages = 75
            self.weekly_connection_requests = 100
        elif self.account_type == "sales_navigator":
            self.daily_profile_views = 250
            self.daily_connection_requests = 150
            self.daily_messages = 120
            self.weekly_connection_requests = 180

    def __post_init__(self):
        self.apply_account_type()
        if not self.user_data_dir:
            safe_name = self.account_email.replace("@", "_at_").replace(".", "_") or "default"
            self.user_data_dir = str(PROFILE_DIR / safe_name)
        if not self.session_file:
            safe_name = self.account_email.replace("@", "_at_").replace(".", "_") or "default"
            self.session_file = str(SESSION_DIR / f"{safe_name}.json")
        if not self.geolocation:
            self.geolocation = {"latitude": -23.5505, "longitude": -46.6333}
