"""H2-F5 Vuecra Handoff — unit tests.

Tests: ProspectBrief schema, idempotency logic, transition validation,
       migration fields, config field.
"""
import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# ProspectBrief schema
# ---------------------------------------------------------------------------

def test_prospect_brief_required_fields():
    from vm_core.models import ProspectBrief
    brief = ProspectBrief(prospect_id=42)
    assert brief.prospect_id == 42
    assert brief.score == 0
    assert brief.has_website is False


def test_prospect_brief_full():
    from vm_core.models import ProspectBrief
    brief = ProspectBrief(
        prospect_id=1,
        business_name="Padaria Central",
        category="restaurant",
        audit_summary="Site desatualizado",
        score=75,
        phone="65999999999",
        email="contato@padaria.com",
        website=None,
        has_website=False,
        photo_ref=None,
        social_instagram="@padaria",
        social_facebook=None,
        address="Rua X, 123",
        city="Cuiaba",
        state="MT",
        marked_at="2026-06-23T10:00:00+00:00",
        hermes_source="hermes-2.0",
    )
    assert brief.business_name == "Padaria Central"
    assert brief.score == 75
    assert brief.hermes_source == "hermes-2.0"


# ---------------------------------------------------------------------------
# ProspectUpdate H2-F5 fields
# ---------------------------------------------------------------------------

def test_prospect_update_h2f5_fields():
    from vm_core.models import ProspectUpdate
    u = ProspectUpdate(
        stage="site_ready",
        hermes_source="hermes-2.0",
        site_url="https://padaria.vuecra.app",
        site_project_id="proj-abc123",
        site_delivered_at="2026-06-23T12:00:00+00:00",
        vuecra_idempotency_key="hermes:1:1234567890",
    )
    assert u.stage == "site_ready"
    assert u.hermes_source == "hermes-2.0"
    assert u.site_url == "https://padaria.vuecra.app"
    assert u.vuecra_idempotency_key == "hermes:1:1234567890"


def test_prospect_update_exclude_none():
    from vm_core.models import ProspectUpdate
    u = ProspectUpdate(stage="site_ready")
    dumped = u.model_dump(exclude_none=True)
    assert "stage" in dumped
    assert "site_url" not in dumped


# ---------------------------------------------------------------------------
# Idempotency logic (extracted from vuecra.py)
# ---------------------------------------------------------------------------

def _idempotency_check(prospect, incoming_key, target_state, valid_sources):
    stage = prospect.get("stage", "")
    stored_key = prospect.get("vuecra_idempotency_key") or ""
    if stage == target_state:
        if not stored_key or stored_key == incoming_key:
            return "replay"
        return "conflict"
    if stage not in valid_sources:
        return "invalid_transition"
    if stored_key and stored_key != incoming_key:
        return "conflict"
    return "proceed"


def test_claim_new_prospect_site_ready():
    p = {"stage": "site_ready", "vuecra_idempotency_key": None}
    assert _idempotency_check(p, "key-A", "site_in_progress", ("site_ready",)) == "proceed"


def test_claim_replay_same_key():
    p = {"stage": "site_in_progress", "vuecra_idempotency_key": "key-A"}
    assert _idempotency_check(p, "key-A", "site_in_progress", ("site_ready",)) == "replay"


def test_claim_conflict_different_key():
    p = {"stage": "site_in_progress", "vuecra_idempotency_key": "key-B"}
    assert _idempotency_check(p, "key-A", "site_in_progress", ("site_ready",)) == "conflict"


def test_claim_invalid_transition_not_site_ready():
    p = {"stage": "qualified", "vuecra_idempotency_key": None}
    assert _idempotency_check(p, "key-A", "site_in_progress", ("site_ready",)) == "invalid_transition"


def test_delivered_proceed_from_in_progress():
    p = {"stage": "site_in_progress", "vuecra_idempotency_key": "key-A"}
    assert _idempotency_check(p, "key-A", "site_delivered", ("site_in_progress",)) == "proceed"


def test_delivered_replay():
    p = {"stage": "site_delivered", "vuecra_idempotency_key": "key-A"}
    assert _idempotency_check(p, "key-A", "site_delivered", ("site_in_progress",)) == "replay"


def test_delivered_invalid_from_site_ready():
    p = {"stage": "site_ready", "vuecra_idempotency_key": None}
    assert _idempotency_check(p, "key-A", "site_delivered", ("site_in_progress",)) == "invalid_transition"


def test_failed_revert():
    p = {"stage": "site_in_progress", "vuecra_idempotency_key": "key-A"}
    assert _idempotency_check(p, "key-A", "site_ready", ("site_in_progress",)) == "proceed"


def test_failed_replay_already_site_ready():
    p = {"stage": "site_ready", "vuecra_idempotency_key": "key-A"}
    assert _idempotency_check(p, "key-A", "site_ready", ("site_in_progress",)) == "replay"


def test_failed_invalid_from_delivered():
    p = {"stage": "site_delivered", "vuecra_idempotency_key": "key-A"}
    assert _idempotency_check(p, "key-A", "site_ready", ("site_in_progress",)) == "invalid_transition"


def test_no_key_stored_proceed():
    p = {"stage": "site_in_progress", "vuecra_idempotency_key": None}
    assert _idempotency_check(p, "key-A", "site_delivered", ("site_in_progress",)) == "proceed"


# ---------------------------------------------------------------------------
# Config field
# ---------------------------------------------------------------------------

def test_config_vuecra_site_ready_min_score_default():
    from config import settings
    assert settings.vuecra_site_ready_min_score == 70


# ---------------------------------------------------------------------------
# ProspectCreate H2-F5 fields
# ---------------------------------------------------------------------------

def test_prospect_create_h2f5_fields():
    from vm_core.models import ProspectCreate
    p = ProspectCreate(
        name="Test",
        hermes_source="hermes-2.0",
        site_url="https://example.com",
    )
    assert p.hermes_source == "hermes-2.0"
    assert p.site_url == "https://example.com"
    assert p.site_project_id is None
