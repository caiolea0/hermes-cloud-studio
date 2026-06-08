"""AccountProfile — bundle persistente per-account com burned_flag.

Patch-008 escopo reduzido (versao validada pelas 3 lentes do workflow stealth-sweep):
- AccountProfile JSON sidecar com {account_id, proxy_sticky_id, timezone, geo,
  user_data_dir, session_file, burned_flag, last_login_ts, burn_reason}
- Burn setter quando detectar /checkpoint, /uas/login forced, /authwall
- Bloqueia retry no mesmo proxy_sticky_id quando burned
- NAO mexe em fingerprint_seed manual (Patchright cuida — overshoot proibido)
- NAO importa cookies Netscape (conflita com minimal-seed atual)

Uso:
    from linkedin.account_profile import AccountProfile

    profile = AccountProfile.load_or_create(
        account_id="milgrauz_lab",
        user_data_dir="/path/...",
        session_file="/path/...",
        timezone="America/Cuiaba",
        geolocation={"latitude": -15.6, "longitude": -56.1},
    )

    if profile.is_burned():
        raise RuntimeError(f"Account {profile.account_id} burned: {profile.burn_reason}")

    # ... after navigation, check URL
    if profile.detect_burn_signal(page.url):
        profile.burn(reason=f"redirect to {page.url}")
        # raises automatically on next is_burned check
"""
from __future__ import annotations
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# URLs que indicam burn signal (LinkedIn forçou re-login ou bloqueou)
BURN_URL_PATTERNS = (
    "/checkpoint/challenge",
    "/checkpoint/lg/login-submit",
    "/uas/login",
    "/authwall",
    "/login-submit",
    "session-expired",
    "/blocked",
)


def _profiles_dir() -> Path:
    """Lê do linkedin.config.PROFILE_DIR pra consistência."""
    try:
        from linkedin.config import DATA_DIR
        d = Path(DATA_DIR) / "account_profiles"
    except Exception:
        d = Path.home() / ".hermes" / "account_profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class AccountProfile:
    account_id: str
    user_data_dir: str = ""
    session_file: str = ""
    proxy_sticky_id: str = ""             # token usado no proxy_username (sticky session)
    timezone: str = "America/Cuiaba"
    geolocation: dict = field(default_factory=lambda: {"latitude": -15.601, "longitude": -56.0974})
    locale: str = "pt-BR"

    # Burn tracking
    burned_flag: bool = False
    burn_reason: str = ""
    burn_timestamp: float = 0.0

    # Histórico
    created_at: float = field(default_factory=time.time)
    last_login_ts: float = 0.0
    last_check_ts: float = 0.0
    login_count: int = 0
    challenge_count: int = 0

    @property
    def json_path(self) -> Path:
        return _profiles_dir() / f"{self.account_id}.json"

    # --- IO ---

    @classmethod
    def load(cls, account_id: str) -> Optional["AccountProfile"]:
        path = _profiles_dir() / f"{account_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**data)
        except Exception as e:
            logger.warning(f"AccountProfile load failed for {account_id}: {e}")
            return None

    @classmethod
    def load_or_create(
        cls,
        account_id: str,
        user_data_dir: str = "",
        session_file: str = "",
        timezone: str = "America/Cuiaba",
        geolocation: Optional[dict] = None,
        locale: str = "pt-BR",
    ) -> "AccountProfile":
        existing = cls.load(account_id)
        if existing:
            # atualiza paths se mudaram (idempotente)
            if user_data_dir:
                existing.user_data_dir = user_data_dir
            if session_file:
                existing.session_file = session_file
            existing.save()
            return existing
        # Novo: gerar sticky_session_id deterministic (hash account_id + ts)
        import hashlib
        sticky = hashlib.sha256(f"{account_id}_{time.time()}".encode()).hexdigest()[:16]
        profile = cls(
            account_id=account_id,
            user_data_dir=user_data_dir,
            session_file=session_file,
            proxy_sticky_id=sticky,
            timezone=timezone,
            geolocation=geolocation or {"latitude": -15.601, "longitude": -56.0974},
            locale=locale,
        )
        profile.save()
        logger.info(f"AccountProfile criado: {account_id} sticky={sticky}")
        return profile

    def save(self):
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        self.json_path.write_text(json.dumps(asdict(self), indent=2, default=str), encoding="utf-8")

    # --- Burn lifecycle ---

    def is_burned(self) -> bool:
        return self.burned_flag

    def burn(self, reason: str):
        if self.burned_flag:
            return  # idempotente
        self.burned_flag = True
        self.burn_reason = reason
        self.burn_timestamp = time.time()
        self.save()
        logger.error(f"AccountProfile {self.account_id} BURNED: {reason}")

    def detect_burn_signal(self, url: str) -> bool:
        """Returns True se URL indica burn (mas NAO marca — chamador decide)."""
        if not url:
            return False
        url_low = url.lower()
        return any(p in url_low for p in BURN_URL_PATTERNS)

    def check_and_burn(self, url: str) -> bool:
        """Combina detect + burn. Returns True se burned nesta call."""
        if self.detect_burn_signal(url):
            self.burn(reason=f"burn URL detectada: {url[:200]}")
            return True
        return False

    # --- Métricas ---

    def record_login(self):
        self.login_count += 1
        self.last_login_ts = time.time()
        self.save()

    def record_challenge(self):
        self.challenge_count += 1
        self.save()

    def record_check(self):
        self.last_check_ts = time.time()
        self.save()

    # --- Reset (manual recovery) ---

    def unburn(self, reason: str = "manual unburn"):
        """SOMENTE chamado manualmente apos owner verificar conta na UI LinkedIn."""
        if not self.burned_flag:
            return
        self.burned_flag = False
        self.burn_reason = f"unburned: {reason} (was: {self.burn_reason})"
        self.save()
        logger.warning(f"AccountProfile {self.account_id} UNBURNED: {reason}")


def assert_not_burned(account_id: str) -> AccountProfile:
    """Helper: load + raise se burned. Chamar antes de qualquer pipeline."""
    profile = AccountProfile.load(account_id)
    if profile and profile.is_burned():
        raise RuntimeError(
            f"AccountProfile {account_id} esta BURNED: {profile.burn_reason} "
            f"(em {time.ctime(profile.burn_timestamp)}). "
            f"Verifique conta na UI LinkedIn. Pra liberar: profile.unburn('motivo')"
        )
    return profile or AccountProfile.load_or_create(account_id)
