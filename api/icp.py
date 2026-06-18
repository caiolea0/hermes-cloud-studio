"""UX-RM-F3-B — ICP Profile endpoints.

Routes:
  GET  /api/icp/profile   -> {data: {icp fields...}}
  POST /api/icp/profile   -> {status: "saved"}
  GET  /api/icp/presets   -> {presets: [...3 templates...]}
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()

_PRESETS = [
    {
        "id": "cuiaba_saas_founders",
        "name": "Cuiaba SaaS Founders",
        "icp": {
            "industries": ["Software", "SaaS", "Information Technology"],
            "company_size_min": 5,
            "company_size_max": 50,
            "job_titles": ["Founder", "CEO", "Co-founder"],
            "seniority_levels": ["c_level"],
            "countries": ["BR"],
            "states": ["MT"],
            "cities": ["Cuiaba"],
            "max_prospects_per_day": 5,
        },
    },
    {
        "id": "mt_marketing_agencies",
        "name": "Mato Grosso Marketing Agencies",
        "icp": {
            "industries": ["Marketing and Advertising", "Marketing Services"],
            "company_size_min": 2,
            "company_size_max": 30,
            "job_titles": ["Founder", "Director", "Head of Marketing"],
            "seniority_levels": ["c_level", "director"],
            "countries": ["BR"],
            "states": ["MT", "GO"],
            "max_prospects_per_day": 5,
        },
    },
    {
        "id": "br_growth_directors",
        "name": "Brazil Growth/Marketing Directors",
        "icp": {
            "industries": ["Software", "Marketing", "E-Learning", "Financial Services"],
            "company_size_min": 20,
            "company_size_max": 200,
            "job_titles": ["Growth Director", "Marketing Director", "VP Marketing"],
            "seniority_levels": ["director", "vp"],
            "countries": ["BR"],
            "max_prospects_per_day": 3,
        },
    },
]


class ICPProfilePayload(BaseModel):
    industries: List[str] = Field(default_factory=list)
    company_size_min: Optional[int] = None
    company_size_max: Optional[int] = None
    revenue_range: Optional[str] = None
    job_titles: List[str] = Field(default_factory=list)
    seniority_levels: List[str] = Field(default_factory=list)
    countries: List[str] = Field(default_factory=lambda: ["BR"])
    states: List[str] = Field(default_factory=list)
    cities: List[str] = Field(default_factory=list)
    keywords_include: List[str] = Field(default_factory=list)
    keywords_exclude: List[str] = Field(default_factory=list)
    max_prospects_per_day: int = 5


@router.get("/api/icp/profile")
async def get_icp_profile():
    from core import icp_store
    data = icp_store.get_current_user_profile()
    return {"data": data or {}}


@router.post("/api/icp/profile")
async def save_icp_profile(body: ICPProfilePayload):
    from core import icp_store
    icp_store.upsert_profile(body.dict())
    return {"status": "saved"}


@router.get("/api/icp/presets")
async def get_icp_presets():
    return {"presets": _PRESETS}
