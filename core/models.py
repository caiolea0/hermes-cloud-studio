"""Hermes Cloud Studio — Pydantic request/response models.

Extraido de server.py durante MERGED-011 (split monolitos).
"""
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
    website: Optional[str] = None
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


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[str] = None
    result: Optional[str] = None


class ActivityCreate(BaseModel):
    type: str
    title: str
    description: Optional[str] = None
    prospect_id: Optional[int] = None
    metadata: Optional[dict] = None


class ClaudeCommand(BaseModel):
    command: str
    context: Optional[str] = None


class AuditConfig(BaseModel):
    batch_size: int = 50
    stage: str = "discovered"


class ScraperConfig(BaseModel):
    cities: Optional[List[str]] = None
    categories: Optional[List[str]] = None
    only_no_site: bool = False
    rate_limit: float = 1.0


class ScraperPrompt(BaseModel):
    prompt: str


class BulkProspectAction(BaseModel):
    ids: List[int]
    action: str  # "stage_change", "score_update"
    value: str


class PipelineTemplateCreate(BaseModel):
    name: str
    type: str = "custom"
    description: Optional[str] = None
    prompt: Optional[str] = None
    targets_config: Optional[dict] = None
    schedule_config: Optional[dict] = None


class PipelineTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    targets_config: Optional[dict] = None
    schedule_config: Optional[dict] = None
    is_active: Optional[bool] = None


class PipelineExecuteRequest(BaseModel):
    template_id: int
    override_prompt: Optional[str] = None


class AgentZeroChatRequest(BaseModel):
    message: str
    context_id: Optional[str] = None
