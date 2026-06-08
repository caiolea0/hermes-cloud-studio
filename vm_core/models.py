"""Hermes Cloud Studio — VM Pydantic models (MERGED-011)."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class ProspectCreate(BaseModel):
    name: str
    business_name: Optional[str] = None
    category: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: str = "Cuiaba"
    state: str = "MT"
    website: Optional[str] = None
    google_maps_url: Optional[str] = None
    google_rating: Optional[float] = None
    google_reviews: int = 0
    photo_ref: Optional[str] = None
    source: str = "google_maps"


class ProspectUpdate(BaseModel):
    name: Optional[str] = None
    business_name: Optional[str] = None
    category: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    stage: Optional[str] = None
    score: Optional[int] = None
    notes: Optional[str] = None
    audit_summary: Optional[str] = None
    outreach_message: Optional[str] = None
    outreach_status: Optional[str] = None


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    assigned_to: str = "hermes"
    created_by: str = "claude"


class ActivityCreate(BaseModel):
    type: str
    title: str
    description: Optional[str] = None
    prospect_id: Optional[int] = None
    metadata: Optional[dict] = None


class ScraperConfig(BaseModel):
    cities: Optional[List[str]] = None
    categories: Optional[List[str]] = None
    only_no_site: bool = False
    rate_limit: float = 1.0


class AuditBatchRequest(BaseModel):
    prospect_ids: Optional[List[int]] = None
    batch_size: int = 50
    stage: str = "discovered"


class OutreachBatchRequest(BaseModel):
    prospect_ids: Optional[List[int]] = None
    batch_size: int = 25


class PipelineExecuteRequest(BaseModel):
    type: str
    config: dict = {}
