"""H7 B12 — Tests for mcps/hermes-linkedin/server.py start_campaign delegate.

Cover OPÇÃO D design: MCP tool POSTs hermes_api_v2 endpoint, preserves task
tracker, returns campaign_id. BLACKLIST R2 preserved — no direct linkedin/*
imports here.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Load hermes-linkedin server.py as module (hyphenated dirname blocks normal import)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_PATH = _REPO_ROOT / "mcps" / "hermes-linkedin" / "server.py"


class _FakeTool:
    """Stand-in for FastMCP @mcp.tool() decorator — preserves fn for direct call."""

    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *a, **kw):
        return self.fn(*a, **kw)


class _FakeFastMCP:
    def __init__(self, *a, **kw):
        pass

    def tool(self, *a, **kw):
        def _wrap(fn):
            return _FakeTool(fn)
        return _wrap

    def run(self, *a, **kw):  # pragma: no cover
        pass


@pytest.fixture(scope="module")
def li_server():
    # Inject fake fastmcp (VM-only dep) before loading server.py
    fake_pkg = type(sys)("fastmcp")
    fake_pkg.FastMCP = _FakeFastMCP  # type: ignore[attr-defined]
    with patch.dict(sys.modules, {"fastmcp": fake_pkg}):
        spec = importlib.util.spec_from_file_location("hermes_linkedin_server", _SERVER_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# T1: rejects invalid campaign_type
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_campaign_type_rejected(li_server):
    fn = li_server.start_campaign.fn  # underlying coroutine behind FastMCP tool decorator
    result = await fn(campaign_type="bogus", config={})
    assert result["ok"] is False
    assert "campaign_type must be" in result["error"]


# ---------------------------------------------------------------------------
# T2: type → endpoint mapping
# ---------------------------------------------------------------------------

def test_type_to_endpoint_mapping(li_server):
    assert li_server._TYPE_TO_ENDPOINT == {
        "viewer": "/api/linkedin/campaigns/view",
        "engager": "/api/linkedin/campaigns/engage",
        "connector": "/api/linkedin/campaigns/connect",
    }


# ---------------------------------------------------------------------------
# T3-T5: delegate HTTP POST hermes_api_v2 success path (viewer/engager/connector)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("campaign_type,expected_endpoint", [
    ("viewer", "/api/linkedin/campaigns/view"),
    ("engager", "/api/linkedin/campaigns/engage"),
    ("connector", "/api/linkedin/campaigns/connect"),
])
@pytest.mark.asyncio
async def test_start_campaign_delegates_to_vm_api(li_server, campaign_type, expected_endpoint):
    fn = li_server.start_campaign.fn

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"ok": True, "campaign_id": 42})
    mock_response.content = b'{"ok":true,"campaign_id":42}'

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__.return_value = mock_client_ctx
    mock_client_ctx.__aexit__.return_value = None
    mock_client_ctx.post = AsyncMock(return_value=mock_response)

    with patch.dict("os.environ", {
        "HERMES_VM_API_URL": "http://vm.test:8420",
        "HERMES_VM_AUTH_TOKEN": "tok-xyz",
    }), patch("httpx.AsyncClient", return_value=mock_client_ctx):
        result = await fn(campaign_type=campaign_type, config={"target_count": 10})

    assert result["ok"] is True
    assert result["campaign_id"] == 42
    assert result["campaign_type"] == campaign_type
    assert result["delegated_to"] == expected_endpoint

    mock_client_ctx.post.assert_called_once()
    call_args = mock_client_ctx.post.call_args
    assert call_args[0][0] == f"http://vm.test:8420{expected_endpoint}"
    assert call_args[1]["json"] == {"target_count": 10}
    headers = call_args[1]["headers"]
    assert headers["X-Hermes-Token"] == "tok-xyz"
    assert headers["X-Hermes-Requester"] == "brain-f5-mcp-linkedin"


# ---------------------------------------------------------------------------
# T6: HTTP error captured via sentry_via_gateway, returns ok=False
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_campaign_http_failure_returns_error_and_calls_sentry(li_server):
    fn = li_server.start_campaign.fn

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__.return_value = mock_client_ctx
    mock_client_ctx.__aexit__.return_value = None
    mock_client_ctx.post = AsyncMock(side_effect=RuntimeError("connection refused"))

    sentry_calls = []

    def _fake_capture(exc, requester="unknown", extra=None, level="error"):
        sentry_calls.append({"exc": str(exc), "requester": requester, "extra": extra})

    # Inject fake module into sys.modules so the inline import inside start_campaign uses it
    fake_mod = MagicMock()
    fake_mod.capture_exception = _fake_capture

    with patch("httpx.AsyncClient", return_value=mock_client_ctx), \
         patch.dict(sys.modules, {"core.sentry_via_gateway": fake_mod}):
        result = await fn(campaign_type="viewer", config={})

    assert result["ok"] is False
    assert "connection refused" in result["error"]
    assert result["delegated_to"] == "/api/linkedin/campaigns/view"
    assert len(sentry_calls) == 1
    assert sentry_calls[0]["requester"] == "brain-f5-mcp-linkedin"
    assert sentry_calls[0]["extra"]["campaign_type"] == "viewer"


# ---------------------------------------------------------------------------
# T7: vm response sanitized (defense-in-depth — VM body could echo li_at)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_campaign_sanitizes_vm_response(li_server):
    fn = li_server.start_campaign.fn

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={
        "ok": True,
        "campaign_id": 7,
        "li_at": "AQEDxxxx-secret-cookie",
        "nested": {"token": "leaked"},
    })
    mock_response.content = b'{"ok":true}'

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__.return_value = mock_client_ctx
    mock_client_ctx.__aexit__.return_value = None
    mock_client_ctx.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client_ctx):
        result = await fn(campaign_type="viewer", config={})

    assert result["ok"] is True
    assert result["vm_response"]["li_at"] == "[REDACTED]"
    assert result["vm_response"]["nested"]["token"] == "[REDACTED]"
