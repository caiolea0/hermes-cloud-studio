"""UX-RM-F6-B — Templates CRUD + renderer tests.

Coverage:
  1.  test_templates_migration_idempotent
  2.  test_create_template_validates_variables
  3.  test_create_template_rejects_invalid_variables
  4.  test_render_template_interpolates_variables
  5.  test_render_template_resolves_spintax
  6.  test_render_template_fallback_missing_var
  7.  test_template_presets_returns_cuiaba_b2b
  8.  test_template_editor_file_exists
  9.  test_template_renderer_extract_variables
  10. test_templates_list_filters_by_channel
  11. test_create_template_email_with_subject
  12. test_delete_template
"""
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Isolated SQLite DB for each test."""
    db_path = str(tmp_path / "test.db")
    import core.state as cs

    def _get():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(cs, "get_db", _get)
    return db_path


@pytest.fixture()
def client(tmp_db):
    from api.templates import router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_templates_migration_idempotent(tmp_db):
    """Running _apply_migration twice must not raise."""
    from api.templates import _apply_migration
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    _apply_migration(conn)
    _apply_migration(conn)  # second call — must be idempotent
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "templates" in tables
    conn.close()


def test_create_template_validates_variables(client):
    payload = {
        "name": "Test LI",
        "channel": "linkedin",
        "body": "Oi {{firstName}}, trabalha na {{company}}?",
    }
    r = client.post("/api/templates", json=payload)
    assert r.status_code == 201
    assert r.json()["id"] >= 1


def test_create_template_rejects_invalid_variables(client):
    payload = {
        "name": "Bad vars",
        "channel": "linkedin",
        "body": "Hello {{unknownVar}} and {{anotherBad}}",
    }
    r = client.post("/api/templates", json=payload)
    assert r.status_code == 400
    assert "Invalid variables" in r.json()["detail"]


def test_render_template_interpolates_variables(client):
    # Create template first
    r = client.post("/api/templates", json={
        "name": "Render test",
        "channel": "email",
        "body": "Oi {{firstName}}, da {{company}}!",
    })
    assert r.status_code == 201
    tid = r.json()["id"]

    r2 = client.post("/api/templates/render", json={
        "template_id": tid,
        "prospect_data": {"firstName": "Ana", "company": "Acme"},
        "deterministic": True,
    })
    assert r2.status_code == 200
    assert r2.json()["body"] == "Oi Ana, da Acme!"


def test_render_template_resolves_spintax(client):
    r = client.post("/api/templates", json={
        "name": "Spintax test",
        "channel": "linkedin",
        "body": "{spintax: crescendo|expandindo} rapido",
    })
    tid = r.json()["id"]

    r2 = client.post("/api/templates/render", json={
        "template_id": tid,
        "prospect_data": {},
        "deterministic": True,  # first option
    })
    assert r2.status_code == 200
    # Deterministic render picks first option
    assert r2.json()["body"] == "crescendo rapido"


def test_render_template_fallback_missing_var(client):
    r = client.post("/api/templates", json={
        "name": "Missing var",
        "channel": "linkedin",
        "body": "Oi {{firstName}}!",
    })
    tid = r.json()["id"]

    r2 = client.post("/api/templates/render", json={
        "template_id": tid,
        "prospect_data": {},  # firstName not provided
        "deterministic": True,
    })
    assert r2.status_code == 200
    assert "[firstName]" in r2.json()["body"]


def test_template_presets_returns_cuiaba_b2b(client):
    r = client.get("/api/templates/presets")
    assert r.status_code == 200
    presets = r.json()["presets"]
    assert len(presets) >= 4
    channels = {p["channel"] for p in presets}
    assert "linkedin" in channels
    assert "email" in channels
    # All presets should have valid variables
    from core.template_renderer import extract_variables, VALID_VARIABLES
    for p in presets:
        used = extract_variables(p["body"])
        assert used <= VALID_VARIABLES, f"Preset '{p['name']}' uses invalid vars: {used - VALID_VARIABLES}"


def test_template_editor_file_exists():
    """Template editor JS component must exist."""
    path = Path(__file__).parent.parent / "dashboard" / "components" / "template_editor.js"
    assert path.exists(), f"Missing: {path}"
    content = path.read_text(encoding="utf-8")
    assert "HermesTemplateEditor" in content
    assert "escapeHtml" not in content or "_esc" in content  # must not use global escapeHtml without guard
    assert "aria-modal" in content
    assert "aria-live" in content


def test_template_renderer_extract_variables():
    from core.template_renderer import extract_variables
    result = extract_variables("Oi {{firstName}}, da {{company}}. Seu titulo e {{jobTitle}}.")
    assert result == {"firstName", "company", "jobTitle"}


def test_templates_list_filters_by_channel(client):
    # Create templates for different channels
    client.post("/api/templates", json={"name": "LI tmpl", "channel": "linkedin", "body": "Oi {{firstName}}"})
    client.post("/api/templates", json={"name": "Email tmpl", "channel": "email", "body": "Oi {{firstName}}"})
    client.post("/api/templates", json={"name": "WA tmpl", "channel": "whatsapp", "body": "Oi {{firstName}}"})

    r_all = client.get("/api/templates")
    assert r_all.status_code == 200
    assert len(r_all.json()["templates"]) >= 3

    r_li = client.get("/api/templates?channel=linkedin")
    assert r_li.status_code == 200
    for t in r_li.json()["templates"]:
        assert t["channel"] == "linkedin"


def test_create_template_email_with_subject(client):
    payload = {
        "name": "Email com assunto",
        "channel": "email",
        "subject": "{{firstName}}, proposta para {{company}}",
        "body": "Ola {{firstName}},\n\nAttenciosamente,\n{{senderName}}",
    }
    r = client.post("/api/templates", json=payload)
    assert r.status_code == 201
    tid = r.json()["id"]

    r2 = client.get(f"/api/templates/{tid}")
    assert r2.status_code == 200
    t = r2.json()["template"]
    assert t["subject"] is not None
    assert "{{firstName}}" in t["subject"]


def test_delete_template(client):
    r = client.post("/api/templates", json={"name": "To delete", "channel": "linkedin", "body": "Oi {{firstName}}"})
    tid = r.json()["id"]

    r_del = client.delete(f"/api/templates/{tid}")
    assert r_del.status_code == 200
    assert r_del.json()["ok"] is True

    r_get = client.get(f"/api/templates/{tid}")
    assert r_get.status_code == 404
