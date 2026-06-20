"""PA-F1.5 closeout tests — telegram determinism + hermes-hunter config."""
import math
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml


# ---------------------------------------------------------------------------
# Item 1 — Telegram threshold determinism
# ---------------------------------------------------------------------------

def test_telegram_threshold_fires_deterministic():
    """float('-inf') _last_threshold_alert guarantees fire regardless of uptime."""
    try:
        from daemon.telegram_alert import CobaiaAlertListener
    except ImportError:
        pytest.skip("daemon.telegram_alert not available in this env")

    mock_client = MagicMock()
    mock_client.send_alert.return_value = True
    listener = CobaiaAlertListener(client=mock_client)

    # float('-inf') makes since_last = monotonic() - (-inf) = +inf >> cooldown
    listener._last_threshold_alert = float('-inf')

    for i in range(4):
        listener.handle_event("cobaia.error", {"message": f"error {i}"})
    assert mock_client.send_alert.call_count == 0, "no alert before threshold"

    listener.handle_event("cobaia.error", {"message": "error 5"})
    assert mock_client.send_alert.call_count == 1, "alert fires at threshold"


# ---------------------------------------------------------------------------
# Item 2 — hermes-hunter in PC config.yaml
# ---------------------------------------------------------------------------

def test_hermes_hunter_in_config_yaml():
    """PC mcps/gateway/config.yaml has active hermes-hunter entry with required fields."""
    config_path = Path(__file__).parent.parent / "mcps" / "gateway" / "config.yaml"
    assert config_path.exists(), f"config.yaml not found at {config_path}"

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    upstream = cfg.get("upstream_mcps", [])
    hunter = next((m for m in upstream if m.get("name") == "hermes-hunter"), None)
    assert hunter is not None, "hermes-hunter not found in upstream_mcps"
    assert hunter.get("status") == "active", "hermes-hunter status must be active"
    assert hunter.get("auth_env") == "HUNTER_API_KEY", "auth_env must be HUNTER_API_KEY"
    assert "check_account_usage" in hunter.get("tools_preview", []), \
        "check_account_usage must be in tools_preview"
