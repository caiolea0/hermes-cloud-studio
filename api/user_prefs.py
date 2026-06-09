"""Hermes Cloud Studio — User Preferences API (F.2.5b Step 2).

Endpoints PC-only (UX local dashboard, VM não precisa replicar):
- GET  /api/user-prefs → {version, data}
- PUT  /api/user-prefs → Pydantic UserPrefs strict + safe_merge + version++

Storage: `runtime_state` key `user_prefs` embedded `{version: N, data: {...}}`.
Atomic 1 write — sem segundo key separado pra version.

Concurrency: last-wins (owner solo, sem conflict detect). Frontend NÃO envia
version no PUT. F.future adiciona check se sócio entrar.

Validation: extra keys silently dropped (Config.extra='ignore') — frontend
evolve sem backend update breaking.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from core.limiter import limiter
from core.state import get_runtime_state, set_runtime_state

router = APIRouter()


# F.2.5b — schema strict, extra keys ignored (forward-compat)
class UserPrefs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    theme: Optional[Literal["light", "dark", "auto"]] = None
    refresh_rate: Optional[Literal[10, 30, 60]] = None
    collapsed_sections: Optional[list[str]] = None
    tile_order: Optional[list[str]] = None
    tile_visibility: Optional[dict[str, bool]] = None
    sound_notifications: Optional[bool] = None
    badge_counter_unread_errors: Optional[bool] = None


def _safe_merge_dict(target: dict, update: dict) -> dict:
    """Python equivalent de hermesUtils.safeMerge JS — filtra None ANTES de merge.

    Preserva keys existentes em `target` quando `update` envia value=None
    (defensive contra PUT parcial apagar prefs). Falsy 0/False/'' PRESERVADOS.
    """
    if not isinstance(update, dict):
        return dict(target or {})
    cleaned = {k: v for k, v in update.items() if v is not None}
    merged = dict(target or {})
    merged.update(cleaned)
    return merged


def _load_user_prefs() -> dict:
    """Lê {version, data} normalizado. Migra legacy raw dict → {version:1, data:raw}."""
    raw = get_runtime_state("user_prefs", None)
    if raw is None:
        return {"version": 0, "data": {}}
    if isinstance(raw, dict) and "version" in raw and "data" in raw:
        return {
            "version": int(raw.get("version", 0)),
            "data": raw.get("data") if isinstance(raw.get("data"), dict) else {},
        }
    # Legacy/corrupted — wrap em embedded shape
    return {"version": 1, "data": raw if isinstance(raw, dict) else {}}


@router.get("/api/user-prefs")
async def get_user_prefs():
    """Retorna {version, data}. Default {version: 0, data: {}} se nunca setado."""
    return _load_user_prefs()


@router.put("/api/user-prefs")
@limiter.limit("30/minute")
async def put_user_prefs(request: Request, prefs: UserPrefs):
    """Merge incremental + version++ + last-wins.

    Body Pydantic-validated: theme inválido = 422; extra keys silently ignored.
    Frontend NÃO envia version — backend gerencia. Last-wins (owner solo).
    Retorna struct completo {version, data} pós-merge — frontend usa pra cachear.
    """
    current = _load_user_prefs()
    update = prefs.model_dump(exclude_none=True)
    merged_data = _safe_merge_dict(current["data"], update)
    new_state = {"version": current["version"] + 1, "data": merged_data}
    set_runtime_state("user_prefs", new_state)
    return new_state
