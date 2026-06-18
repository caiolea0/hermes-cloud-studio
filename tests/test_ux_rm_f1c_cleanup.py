"""UX-RM-F1-C cleanup tests.

G1  LI_USE_MOCK flag deleted from dashboard/app.js
G2  comment/edit + comment/delete return 501 NotImplemented
G3  intelligence package importable + scoring + enrichment raise NotImplementedError
G4  n/c channel renders 'Configurar' link in DOM template
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "dashboard" / "app.js"


# ---------------------------------------------------------------------------
# Item 1 — LI_USE_MOCK removed
# ---------------------------------------------------------------------------

def test_li_use_mock_flag_deleted():
    """No LI_USE_MOCK reference must remain in dashboard/app.js."""
    content = APP_JS.read_text(encoding="utf-8")
    matches = re.findall(r"LI_USE_MOCK", content)
    assert matches == [], f"LI_USE_MOCK still present ({len(matches)} occurrences)"


# ---------------------------------------------------------------------------
# Item 2 — comment endpoints return 501
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def linkedin_test_client():
    sys.path.insert(0, str(ROOT))
    from api.linkedin import router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_comment_edit_endpoint_returns_501(linkedin_test_client):
    r = linkedin_test_client.post("/api/linkedin/comment/edit", json={"comment_id": 1})
    assert r.status_code == 501, f"Expected 501, got {r.status_code}"
    body = r.json()
    assert body.get("ok") is False
    assert "not_implemented" in body.get("error", "")


def test_comment_delete_endpoint_returns_501(linkedin_test_client):
    r = linkedin_test_client.post("/api/linkedin/comment/delete", json={"comment_id": 1})
    assert r.status_code == 501, f"Expected 501, got {r.status_code}"
    body = r.json()
    assert body.get("ok") is False
    assert "not_implemented" in body.get("error", "")


# ---------------------------------------------------------------------------
# Item 3 — intelligence/ package skeleton
# ---------------------------------------------------------------------------

def test_intelligence_package_importable():
    sys.path.insert(0, str(ROOT))
    import intelligence  # noqa: F401
    assert hasattr(intelligence, "__doc__") or True  # just importable is enough


def test_intelligence_scoring_raises_notimplemented():
    sys.path.insert(0, str(ROOT))
    from intelligence.scoring import calculate_score
    with pytest.raises(NotImplementedError):
        calculate_score({"id": 1, "name": "test"})


def test_intelligence_enrichment_raises_notimplemented():
    sys.path.insert(0, str(ROOT))
    import asyncio
    from intelligence.enrichment import enrich_prospect
    with pytest.raises(NotImplementedError):
        asyncio.run(enrich_prospect(1))


# ---------------------------------------------------------------------------
# Item 4 — n/c channel renders 'Configurar' link
# ---------------------------------------------------------------------------

def test_nc_channel_renders_configure_link():
    """The app.js n/c branch must include a 'Configurar' link element."""
    content = APP_JS.read_text(encoding="utf-8")
    # Find the not_configured branch
    nc_match = re.search(
        r"not_configured.*?health === undefined\)(.*?)} else \{",
        content,
        re.DOTALL,
    )
    assert nc_match, "Could not locate not_configured branch in app.js"
    nc_block = nc_match.group(1)
    assert "Configurar" in nc_block, (
        "n/c branch does not contain 'Configurar' link"
    )
