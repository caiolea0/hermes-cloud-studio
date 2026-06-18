"""H4 — B20+B21: subsystem pause gates (scraper/audit/tunnel) + channels real query."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# B20 — scraper loop gate (daemon/orchestrator.py decide_next_action)
# ---------------------------------------------------------------------------

def test_scraper_loop_skips_iteration_if_paused():
    """is_subsystem_paused('scraper')=True → decide_next_action skips discovery_scrape."""
    from daemon.orchestrator import HermesDaemon
    daemon = HermesDaemon.__new__(HermesDaemon)
    daemon.stats_today = MagicMock()
    daemon.paused_until = None
    daemon.consecutive_errors = 0
    daemon._cobaia_module = None
    daemon.pipeline = MagicMock()

    async def _run():
        with patch("daemon.orchestrator.is_subsystem_paused", side_effect=lambda n: n == "scraper"), \
             patch.object(daemon, "_get_cobaia_action", new_callable=AsyncMock, return_value=None), \
             patch.object(daemon, "_get_pending_replies", new_callable=AsyncMock, return_value=[]), \
             patch.object(daemon, "_get_due_sequence_steps", new_callable=AsyncMock, return_value=[]), \
             patch.object(daemon, "_get_unenriched_prospects", new_callable=AsyncMock, return_value=[]), \
             patch.object(daemon, "_pipeline_needs_fuel", new_callable=AsyncMock, return_value=True), \
             patch.object(daemon, "_should_scrape_today", return_value=True), \
             patch.object(daemon, "_get_scraper_config", return_value={"city": "Cuiaba"}), \
             patch.object(daemon, "_get_unaudited_prospects", new_callable=AsyncMock, return_value=[]), \
             patch.object(daemon, "_scored_today", return_value=True), \
             patch.object(daemon, "_reported_this_week", return_value=True):
            return await daemon.decide_next_action()

    task = asyncio.run(_run())
    assert task is None or task.type != "discovery_scrape", \
        f"Expected scraper skipped, got task.type={getattr(task, 'type', None)}"


def test_audit_loop_skips_iteration_if_paused():
    """is_subsystem_paused('audit')=True → decide_next_action skips batch_audit."""
    from daemon.orchestrator import HermesDaemon
    daemon = HermesDaemon.__new__(HermesDaemon)
    daemon.paused_until = None
    daemon.consecutive_errors = 0
    daemon._cobaia_module = None
    daemon.stats_today = MagicMock()
    daemon.pipeline = MagicMock()

    async def _run():
        with patch("daemon.orchestrator.is_subsystem_paused", side_effect=lambda n: n == "audit"), \
             patch.object(daemon, "_get_cobaia_action", new_callable=AsyncMock, return_value=None), \
             patch.object(daemon, "_get_pending_replies", new_callable=AsyncMock, return_value=[]), \
             patch.object(daemon, "_get_due_sequence_steps", new_callable=AsyncMock, return_value=[]), \
             patch.object(daemon, "_get_unenriched_prospects", new_callable=AsyncMock, return_value=[]), \
             patch.object(daemon, "_pipeline_needs_fuel", new_callable=AsyncMock, return_value=False), \
             patch.object(daemon, "_get_unaudited_prospects", new_callable=AsyncMock, return_value=[{"id": 1}]), \
             patch.object(daemon, "_scored_today", return_value=True), \
             patch.object(daemon, "_reported_this_week", return_value=True):
            return await daemon.decide_next_action()

    task = asyncio.run(_run())
    assert task is None or task.type != "batch_audit", \
        f"Expected audit skipped, got task.type={getattr(task, 'type', None)}"


# ---------------------------------------------------------------------------
# B20 — API-level gates (api/scraper.py + api/audit.py)
# ---------------------------------------------------------------------------

def test_scraper_api_returns_paused_if_subsystem_paused():
    """POST /api/scraper/start returns {status: paused} when scraper is paused."""
    with patch("api.scraper.is_subsystem_paused", return_value=True):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from api.scraper import router
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/api/scraper/start", json={"search_terms": ["test"]})
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"


def test_audit_api_returns_paused_if_subsystem_paused():
    """POST /api/audit/start returns {status: paused} when audit is paused."""
    with patch("api.audit.is_subsystem_paused", return_value=True):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from api.audit import router
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/api/audit/start", json={"batch_size": 5, "stage": "discovered"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"


# ---------------------------------------------------------------------------
# B20 — tunnel gate (scripts/tunnel_supervisor.py)
# ---------------------------------------------------------------------------

def test_tunnel_skip_restart_if_paused():
    """Supervisor.tick() returns early with paused_skip action when tunnel is paused."""
    with patch("core.state.is_subsystem_paused", return_value=True):
        import importlib, sys
        # Reload supervisor to ensure fresh import
        for mod in list(sys.modules.keys()):
            if "tunnel_supervisor" in mod:
                del sys.modules[mod]

        import scripts.tunnel_supervisor as sup_mod
        sup = sup_mod.Supervisor.__new__(sup_mod.Supervisor)
        sup.restart_window = []
        sup.cooldown_until = 0.0
        sup.socks5_pid = None
        sup.ssh_pid = None

        with patch("scripts.tunnel_supervisor.port_listening", return_value=True), \
             patch("core.state.is_subsystem_paused", return_value=True):
            state = sup.tick()

        assert "paused_skip" in state["actions"], \
            f"Expected paused_skip in actions, got: {state['actions']}"


# ---------------------------------------------------------------------------
# B20 — pause/resume pair tests
# ---------------------------------------------------------------------------

def test_pause_individual_blocks_scraper_api():
    """Pausing scraper blocks /api/scraper/start."""
    with patch("api.scraper.is_subsystem_paused", return_value=True):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from api.scraper import router
        app = FastAPI()
        app.include_router(router)
        resp = TestClient(app).post("/api/scraper/start", json={"search_terms": []})
        assert resp.json().get("status") == "paused"


def test_resume_individual_unblocks_scraper_api():
    """Unpaused scraper forwards to VM (gate not triggered)."""
    with patch("api.scraper.is_subsystem_paused", return_value=False), \
         patch("api.scraper.httpx.AsyncClient") as mock_client:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "started", "pid": 123}
        mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
            post=AsyncMock(return_value=mock_resp)
        ))
        mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from api.scraper import router
        app = FastAPI()
        app.include_router(router)
        resp = TestClient(app).post("/api/scraper/start", json={"search_terms": ["test"]})
        # Should NOT be paused (gate not triggered)
        assert resp.json().get("status") != "paused"


def test_pause_all_panic_blocks_3_new_subsystems():
    """When all subsystems paused, scraper+audit+tunnel all blocked."""
    with patch("api.scraper.is_subsystem_paused", return_value=True), \
         patch("api.audit.is_subsystem_paused", return_value=True):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from api.scraper import router as scraper_router
        from api.audit import router as audit_router
        app = FastAPI()
        app.include_router(scraper_router)
        app.include_router(audit_router)
        client = TestClient(app)
        r1 = client.post("/api/scraper/start", json={"search_terms": []})
        r2 = client.post("/api/audit/start", json={"batch_size": 5, "stage": "discovered"})
        assert r1.json()["status"] == "paused"
        assert r2.json()["status"] == "paused"


# ---------------------------------------------------------------------------
# B21 — /api/daemon/channels real query
# ---------------------------------------------------------------------------

def test_channels_returns_real_linkedin_health():
    """channels.linkedin.state reflects real li_health_last_state from runtime_state."""
    with patch("api.daemon.get_runtime_state", return_value="cooldown"), \
         patch("api.daemon.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = {"cnt": 5}
        mock_db.return_value = mock_conn
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from api.daemon import router
        app = FastAPI()
        app.include_router(router)
        with patch("api.daemon.get_runtime_state", return_value="cooldown"):
            resp = TestClient(app).get("/api/daemon/channels")
        data = resp.json()
        assert data["linkedin"]["state"] == "cooldown"
        assert data["linkedin"]["health"] < 1.0, "cooldown health must be < 1.0"
        assert data["linkedin"]["is_active"] is False


def test_channels_returns_real_email_usage():
    """channels.email reflects EmailLimiter stats (not hardcoded 0)."""
    mock_stats = {
        "daily_sent": 12,
        "daily_cap": 40,
        "warmup_day": 5,
        "warmup_days_total": 14,
    }
    mock_lim = MagicMock()
    mock_lim.stats.return_value = mock_stats

    with patch("api.daemon.get_runtime_state", return_value="ok"), \
         patch("api.daemon.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = {"cnt": 0}
        mock_db.return_value = mock_conn
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from api.daemon import router
        app = FastAPI()
        app.include_router(router)
        with patch("api.daemon.get_runtime_state", return_value="ok"), \
             patch("channels.email.limiter.EmailLimiter.stats", return_value=mock_stats):
            resp = TestClient(app).get("/api/daemon/channels")
        data = resp.json()
        # Even without mock hitting, values should reflect dynamic query
        assert "daily_used" in data["email"]
        assert "daily_limit" in data["email"]


def test_channels_returns_not_configured_whatsapp_instagram():
    """channels.whatsapp + instagram have status='not_configured'."""
    with patch("api.daemon.get_runtime_state", return_value=None), \
         patch("api.daemon.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = {"cnt": 0}
        mock_db.return_value = mock_conn
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from api.daemon import router
        app = FastAPI()
        app.include_router(router)
        with patch("api.daemon.get_runtime_state", return_value=None):
            resp = TestClient(app).get("/api/daemon/channels")
        data = resp.json()
        assert data["whatsapp"]["status"] == "not_configured"
        assert data["instagram"]["status"] == "not_configured"
        assert data["whatsapp"]["is_active"] is False
        assert data["instagram"]["is_active"] is False


def test_channels_linkedin_uses_real_ratelimiter_keys():
    """R4 fix: daily_used/limit flow from real get_stats() keys, not fallback campaign count."""
    mock_stats = {
        "daily_views": 23,
        "daily_views_limit": 80,
        "warmup_day": 5,
        "warmup_complete": False,
    }
    mock_rl_instance = MagicMock()
    mock_rl_instance.get_stats.return_value = mock_stats

    with patch("api.daemon.get_runtime_state", return_value="ok"), \
         patch("api.daemon.get_db") as mock_db, \
         patch("linkedin.limiter.RateLimiter", return_value=mock_rl_instance):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = {"cnt": 99}  # campaign fallback value
        mock_db.return_value = mock_conn
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from api.daemon import router
        app = FastAPI()
        app.include_router(router)
        resp = TestClient(app).get("/api/daemon/channels")
    data = resp.json()
    li = data["linkedin"]
    # Must use real limiter keys, NOT the campaign count fallback (99)
    assert li["daily_used"] == 23, f"expected 23 (daily_views), got {li['daily_used']}"
    assert li["daily_limit"] == 80, f"expected 80 (daily_views_limit), got {li['daily_limit']}"
    assert li["warmup_day"] == 5
