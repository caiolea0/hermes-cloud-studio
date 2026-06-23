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
    # H2-F1 OSM/Overpass fields
    source_type: Optional[str] = None   # 'osm', 'google_maps', 'cnpj', etc.
    osm_id: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    opening_hours: Optional[str] = None
    # H2-F2 CNPJ authority fields
    cnpj: Optional[str] = None
    razao_social: Optional[str] = None
    cnae: Optional[str] = None
    situacao_cadastral: Optional[str] = None
    cnpj_match_confidence: Optional[str] = None  # 'high', 'low', None
    # H2-F3 website contact-enrich fields
    whatsapp: Optional[str] = None
    contact_source: Optional[str] = None   # 'website', 'cnpj', 'osm', etc.
    scraped_at: Optional[str] = None       # ISO timestamp
    social_instagram: Optional[str] = None
    social_facebook: Optional[str] = None
    # H2-F4 categorize + ICP + qualify fields
    industry: Optional[str] = None
    sub_category: Optional[str] = None
    icp_fit: Optional[str] = None              # 'high' | 'medium' | 'low'
    psi_performance: Optional[int] = None
    psi_seo: Optional[int] = None
    psi_accessibility: Optional[int] = None
    mobile_friendly: Optional[int] = None      # 0/1 (sqlite bool)
    aggregate_rating: Optional[float] = None
    score_breakdown: Optional[str] = None      # JSON-string {sinal_id: pontos}
    score_confidence: Optional[str] = None     # 'high' | 'partial' | 'low'


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
    # H2-F2 CNPJ authority fields
    cnpj: Optional[str] = None
    razao_social: Optional[str] = None
    cnae: Optional[str] = None
    situacao_cadastral: Optional[str] = None
    cnpj_match_confidence: Optional[str] = None
    # H2-F3 website contact-enrich fields
    whatsapp: Optional[str] = None
    contact_source: Optional[str] = None
    scraped_at: Optional[str] = None
    social_instagram: Optional[str] = None
    social_facebook: Optional[str] = None
    # H2-F4 categorize + ICP + qualify fields
    industry: Optional[str] = None
    sub_category: Optional[str] = None
    icp_fit: Optional[str] = None
    psi_performance: Optional[int] = None
    psi_seo: Optional[int] = None
    psi_accessibility: Optional[int] = None
    mobile_friendly: Optional[int] = None
    aggregate_rating: Optional[float] = None
    score_breakdown: Optional[str] = None
    score_confidence: Optional[str] = None


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
