"""Hermes Cloud Studio — Vuecra Handoff API (H2-F5).

HI2 endpoints consumed by Vuecra V4 Inbox.
Auth: X-Internal-Token (HERMES_INTERNAL_TOKEN, hmac.compare_digest fail-closed).
Idempotency: X-Idempotency-Key stored in prospects.vuecra_idempotency_key.

Stages: site_ready → site_in_progress → site_delivered (revert via /failed).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from config import settings
from vm_core.models import ProspectBrief
from vm_core.state import get_db, logger

router = APIRouter()

_INTERNAL_TOKEN = settings.internal_token.strip()
if not _INTERNAL_TOKEN:
    logger.warning(
        "HERMES_INTERNAL_TOKEN not set — /api/vuecra/* will reject all requests (fail-closed)"
    )


def _require_internal(request: Request) -> None:
    token = request.headers.get("X-Internal-Token", "")
    if not _INTERNAL_TOKEN or not secrets.compare_digest(token, _INTERNAL_TOKEN):
        raise HTTPException(status_code=401, detail="X-Internal-Token inválido ou ausente")


def _get_idem_key(request: Request, body: Optional[dict] = None) -> str:
    """Body wins over header per cross-project contract."""
    if body and body.get("idempotency_key"):
        return str(body["idempotency_key"])
    key = request.headers.get("X-Idempotency-Key", "")
    if not key:
        raise HTTPException(status_code=400, detail="X-Idempotency-Key obrigatório")
    return key


def _correlation_id(request: Request) -> str:
    return request.headers.get("X-Correlation-Id", "-")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _idempotency_check(
    prospect: dict,
    incoming_key: str,
    target_state: str,
    valid_sources: tuple,
) -> str:
    """Returns 'replay' | 'proceed' | 'invalid_transition' | 'conflict'."""
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


# ---------------------------------------------------------------------------
# GET /api/vuecra/queue
# ---------------------------------------------------------------------------

@router.get("/api/vuecra/queue", response_model=List[ProspectBrief])
async def vuecra_queue(request: Request, limit: int = Query(default=20, ge=1, le=200)):
    """Return prospects staged as site_ready ordered by score DESC."""
    _require_internal(request)
    logger.info(
        "vuecra queue request limit=%d correlation_id=%s",
        limit,
        _correlation_id(request),
    )
    db = get_db()
    try:
        rows = db.execute(
            """
            SELECT id, business_name, category, audit_summary, score,
                   phone, email, website, has_website, photo_ref,
                   social_instagram, social_facebook, address, city, state,
                   updated_at, hermes_source
            FROM prospects
            WHERE stage = 'site_ready'
            ORDER BY score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        db.close()

    return [
        ProspectBrief(
            prospect_id=row["id"],
            business_name=row["business_name"],
            category=row["category"],
            audit_summary=row["audit_summary"],
            score=row["score"] or 0,
            phone=row["phone"],
            email=row["email"],
            website=row["website"],
            has_website=bool(row["has_website"]),
            photo_ref=row["photo_ref"],
            social_instagram=row["social_instagram"],
            social_facebook=row["social_facebook"],
            address=row["address"],
            city=row["city"],
            state=row["state"],
            marked_at=row["updated_at"],
            hermes_source=row["hermes_source"],
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# POST /api/vuecra/{id}/claim
# ---------------------------------------------------------------------------

@router.post("/api/vuecra/{prospect_id}/claim")
async def vuecra_claim(prospect_id: int, request: Request):
    """Transition site_ready → site_in_progress (Vuecra claiming the lead)."""
    _require_internal(request)
    idem_key = _get_idem_key(request)
    corr = _correlation_id(request)

    db = get_db()
    try:
        row = db.execute(
            "SELECT id, stage, vuecra_idempotency_key FROM prospects WHERE id = ?",
            (prospect_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Prospect {prospect_id} não encontrado")

        prospect = dict(row)
        result = _idempotency_check(
            prospect,
            idem_key,
            target_state="site_in_progress",
            valid_sources=("site_ready",),
        )

        if result == "replay":
            logger.info(
                "vuecra claim REPLAY prospect_id=%d key=%s correlation_id=%s",
                prospect_id, idem_key, corr,
            )
            return {"status": "ok", "replay": True, "stage": "site_in_progress"}

        if result == "conflict":
            raise HTTPException(
                status_code=409,
                detail=f"Idempotency conflict: key={idem_key} stage={prospect['stage']}",
            )

        if result == "invalid_transition":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Transição inválida: claim requer stage=site_ready, "
                    f"atual={prospect['stage']}"
                ),
            )

        # proceed
        now = _now_iso()
        db.execute(
            """
            UPDATE prospects
               SET stage = 'site_in_progress',
                   vuecra_idempotency_key = ?,
                   updated_at = ?,
                   version = version + 1
             WHERE id = ?
            """,
            (idem_key, now, prospect_id),
        )
        db.commit()

    finally:
        db.close()

    logger.info(
        "vuecra claim OK prospect_id=%d key=%s correlation_id=%s",
        prospect_id, idem_key, corr,
    )
    return {"status": "ok", "replay": False, "stage": "site_in_progress"}


# ---------------------------------------------------------------------------
# POST /api/vuecra/{id}/delivered
# ---------------------------------------------------------------------------

class DeliveredBody(BaseModel):
    site_url: str
    site_project_id: Optional[str] = None
    idempotency_key: Optional[str] = None  # body wins over header


@router.post("/api/vuecra/{prospect_id}/delivered")
async def vuecra_delivered(prospect_id: int, body: DeliveredBody, request: Request):
    """Transition site_in_progress → site_delivered (Vuecra finished building the site)."""
    _require_internal(request)
    idem_key = _get_idem_key(request, body.model_dump())
    corr = _correlation_id(request)

    if not body.site_url:
        raise HTTPException(status_code=400, detail="site_url obrigatório")

    db = get_db()
    try:
        row = db.execute(
            "SELECT id, stage, vuecra_idempotency_key, site_url FROM prospects WHERE id = ?",
            (prospect_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Prospect {prospect_id} não encontrado")

        prospect = dict(row)
        result = _idempotency_check(
            prospect,
            idem_key,
            target_state="site_delivered",
            valid_sources=("site_in_progress",),
        )

        if result == "replay":
            logger.info(
                "vuecra delivered REPLAY prospect_id=%d key=%s correlation_id=%s",
                prospect_id, idem_key, corr,
            )
            return {
                "status": "ok",
                "replay": True,
                "stage": "site_delivered",
                "site_url": prospect.get("site_url"),
            }

        if result == "conflict":
            raise HTTPException(
                status_code=409,
                detail=f"Idempotency conflict: key={idem_key} stage={prospect['stage']}",
            )

        if result == "invalid_transition":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Transição inválida: delivered requer stage=site_in_progress, "
                    f"atual={prospect['stage']}"
                ),
            )

        # proceed
        now = _now_iso()
        db.execute(
            """
            UPDATE prospects
               SET stage = 'site_delivered',
                   site_url = ?,
                   site_project_id = ?,
                   site_delivered_at = ?,
                   vuecra_idempotency_key = ?,
                   updated_at = ?,
                   version = version + 1
             WHERE id = ?
            """,
            (body.site_url, body.site_project_id, now, idem_key, now, prospect_id),
        )
        db.commit()

    finally:
        db.close()

    logger.info(
        "vuecra delivered OK prospect_id=%d site_url=%s key=%s correlation_id=%s",
        prospect_id, body.site_url, idem_key, corr,
    )
    return {
        "status": "ok",
        "replay": False,
        "stage": "site_delivered",
        "site_url": body.site_url,
    }


# ---------------------------------------------------------------------------
# POST /api/vuecra/{id}/failed
# ---------------------------------------------------------------------------

class FailedBody(BaseModel):
    reason: Optional[str] = None
    idempotency_key: Optional[str] = None


@router.post("/api/vuecra/{prospect_id}/failed")
async def vuecra_failed(prospect_id: int, body: FailedBody, request: Request):
    """Revert site_in_progress → site_ready (Vuecra failed, returning lead to queue)."""
    _require_internal(request)
    idem_key = _get_idem_key(request, body.model_dump())
    corr = _correlation_id(request)

    db = get_db()
    try:
        row = db.execute(
            "SELECT id, stage, vuecra_idempotency_key FROM prospects WHERE id = ?",
            (prospect_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Prospect {prospect_id} não encontrado")

        prospect = dict(row)
        result = _idempotency_check(
            prospect,
            idem_key,
            target_state="site_ready",
            valid_sources=("site_in_progress",),
        )

        if result == "replay":
            logger.info(
                "vuecra failed REPLAY prospect_id=%d key=%s correlation_id=%s",
                prospect_id, idem_key, corr,
            )
            return {"status": "ok", "replay": True, "stage": "site_ready"}

        if result == "conflict":
            raise HTTPException(
                status_code=409,
                detail=f"Idempotency conflict: key={idem_key} stage={prospect['stage']}",
            )

        if result == "invalid_transition":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Transição inválida: failed requer stage=site_in_progress, "
                    f"atual={prospect['stage']}"
                ),
            )

        # revert
        now = _now_iso()
        db.execute(
            """
            UPDATE prospects
               SET stage = 'site_ready',
                   vuecra_idempotency_key = ?,
                   updated_at = ?,
                   version = version + 1
             WHERE id = ?
            """,
            (idem_key, now, prospect_id),
        )
        db.commit()

    finally:
        db.close()

    logger.info(
        "vuecra failed REVERT prospect_id=%d reason=%s key=%s correlation_id=%s",
        prospect_id, body.reason, idem_key, corr,
    )
    return {"status": "ok", "replay": False, "stage": "site_ready", "reason": body.reason}
