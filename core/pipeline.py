"""Hermes pipeline runner — modulo compartilhado.

Encapsula as 3 etapas do funil B2B (discovery -> audit -> outreach) num unico ponto.
Substitui logica que vivia em paralelo em scripts/pipeline.py (CLI) e
daemon/orchestrator.py (loop 24/7), garantindo que bug fix em um lado propague.

Uso (CLI sincrono):
    runner = PipelineRunner.from_settings()
    asyncio.run(runner.run_full(city="Cuiaba"))

Uso (daemon async):
    runner = PipelineRunner.from_settings(auth_token=settings.auth_token)
    res = await runner.discovery(city=cfg["city"], categories=cfg.get("categories"))

Cada metodo retorna dict com contagens + ids afetados, pra metricas/log_activity.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import httpx

logger = logging.getLogger("hermes.core.pipeline")


@dataclass
class PipelineResult:
    discovery: dict = field(default_factory=dict)
    audit: dict = field(default_factory=dict)
    outreach: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    timestamp: str = ""

    def as_dict(self) -> dict:
        return {
            "discovery": self.discovery,
            "audit": self.audit,
            "outreach": self.outreach,
            "elapsed_seconds": self.elapsed_seconds,
            "timestamp": self.timestamp,
        }


class PipelineRunner:
    """Pipeline canonico Hermes. Toda execucao Discovery/Audit/Outreach passa aqui."""

    def __init__(
        self,
        api_url: str,
        auth_token: str = "",
        timeout: float = 30.0,
        max_discover_per_category: int = 20,
        audit_batch_limit: int = 20,
        outreach_batch_limit: int = 10,
        outreach_min_score: int = 65,
    ):
        self.api_url = api_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout
        self.max_discover_per_category = max_discover_per_category
        self.audit_batch_limit = audit_batch_limit
        self.outreach_batch_limit = outreach_batch_limit
        self.outreach_min_score = outreach_min_score

    @classmethod
    def from_settings(cls, settings: Any = None, **overrides) -> "PipelineRunner":
        """Constroi runner a partir do config.settings (ou objeto compat)."""
        if settings is None:
            from config import settings as _s
            settings = _s
        api_url = overrides.pop("api_url", None) or f"http://localhost:{settings.dashboard_port}"
        auth_token = overrides.pop("auth_token", None) or settings.auth_token
        return cls(api_url=api_url, auth_token=auth_token, **overrides)

    # --- HTTP plumbing ---

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.auth_token:
            h["Authorization"] = f"Bearer {self.auth_token}"
        return h

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.api_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.request(method, url, headers=self._headers(), **kwargs)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            logger.warning("pipeline %s %s failed: %s", method, path, exc)
            return {"error": str(exc)}

    async def _log_activity(
        self,
        activity_type: str,
        title: str,
        description: Optional[str] = None,
        prospect_id: Optional[int] = None,
    ) -> None:
        await self._request(
            "POST",
            "/api/activities",
            json={
                "type": activity_type,
                "title": title,
                "description": description,
                "prospect_id": prospect_id,
            },
        )

    async def _existing_prospects_keys(self) -> set[tuple[str, str]]:
        res = await self._request("GET", "/api/prospects?limit=500")
        if "error" in res:
            return set()
        return {
            ((p.get("business_name") or "").lower(), (p.get("city") or "").lower())
            for p in res.get("prospects", [])
        }

    # --- Stages ---

    async def discovery(
        self,
        city: str,
        categories: Optional[Iterable[str]] = None,
        only_no_website: bool = False,
    ) -> dict:
        """Discovery via google_maps_scraper. Filtra duplicatas e cria prospects via API."""
        # Import tardio: scraper so importa quando rodar (evita dep no daemon se nao usar)
        from scripts.google_maps_scraper import CATEGORIES, discover_businesses

        cats = list(categories) if categories else list(CATEGORIES)
        logger.info("DISCOVERY %s — %d categorias", city, len(cats))
        await self._log_activity("discovery", f"Iniciando busca em {city}", f"{len(cats)} categorias")

        result = discover_businesses(city, cats, only_no_website=only_no_website)
        for err in result.get("errors") or []:
            logger.warning("discovery error: %s", err)

        existing = await self._existing_prospects_keys()
        new_prospects = [
            p
            for p in result.get("prospects", [])
            if ((p.get("business_name") or "").lower(), (p.get("city") or "").lower()) not in existing
        ]

        created_ids: list[int] = []
        for p in new_prospects:
            resp = await self._request(
                "POST",
                "/api/prospects",
                json={
                    "name": p["name"],
                    "business_name": p["business_name"],
                    "category": p["category"],
                    "phone": p.get("phone"),
                    "address": p.get("address"),
                    "city": p["city"],
                    "state": p.get("state", "MT"),
                    "website": p.get("website"),
                    "google_maps_url": p.get("google_maps_url"),
                    "google_rating": p.get("google_rating"),
                    "google_reviews": p.get("google_reviews", 0),
                    "source": "google_maps",
                },
            )
            if "id" in resp:
                created_ids.append(resp["id"])

        await self._log_activity(
            "discovery",
            f"{len(new_prospects)} novos negocios em {city}",
            f"sem_site={sum(1 for p in new_prospects if not p.get('has_website'))} "
            f"com_site={sum(1 for p in new_prospects if p.get('has_website'))}",
        )

        return {
            "new": len(new_prospects),
            "total_found": result.get("total_found", 0),
            "ids": created_ids,
        }

    async def audit_pending(self, limit: Optional[int] = None) -> dict:
        """Audita prospects no stage 'discovered'. Promove pra qualified/audited conforme score."""
        from scripts.web_audit import audit_prospect

        n = limit or self.audit_batch_limit
        res = await self._request("GET", f"/api/prospects?stage=discovered&limit={n}")
        prospects = res.get("prospects", [])
        if not prospects:
            return {"audited": 0}

        audited = 0
        for p in prospects:
            audit = audit_prospect(p)
            score = audit["score"]
            stage = "audited" if score >= 70 else ("qualified" if score >= 50 else "discovered")
            await self._request(
                "PATCH",
                f"/api/prospects/{p['id']}",
                json={
                    "score": score,
                    "stage": stage,
                    "audit_summary": audit["audit_summary"],
                },
            )
            await self._log_activity(
                "audit",
                f"Auditoria: {p.get('business_name') or p.get('name')}",
                f"score={score} stage={stage}",
                prospect_id=p["id"],
            )
            audited += 1
            await asyncio.sleep(0.5)
        return {"audited": audited}

    async def outreach_ready(self, limit: Optional[int] = None) -> dict:
        """Gera mensagem outreach pra prospects audited com score >= outreach_min_score."""
        from scripts.outreach_generator import generate_outreach

        n = limit or self.outreach_batch_limit
        res = await self._request(
            "GET",
            f"/api/prospects?stage=audited&min_score={self.outreach_min_score}&limit={n}",
        )
        prospects = res.get("prospects", [])
        if not prospects:
            return {"generated": 0}

        generated = 0
        for p in prospects:
            outreach = generate_outreach(p)
            await self._request(
                "PATCH",
                f"/api/prospects/{p['id']}",
                json={
                    "stage": "outreach",
                    "outreach_message": outreach["whatsapp_message"],
                    "outreach_status": "ready",
                },
            )
            await self._log_activity(
                "outreach",
                f"Mensagem: {p.get('business_name') or p.get('name')}",
                f"servicos={', '.join((outreach.get('recommended_services') or [])[:3])}",
                prospect_id=p["id"],
            )
            generated += 1
        return {"generated": generated}

    async def run_full(
        self,
        city: str,
        categories: Optional[Iterable[str]] = None,
    ) -> PipelineResult:
        start = time.monotonic()
        await self._log_activity("task", "Pipeline iniciado", f"city={city} mode=full")

        discovery = await self.discovery(city, categories)
        audit = await self.audit_pending()
        outreach = await self.outreach_ready()

        elapsed = round(time.monotonic() - start, 1)
        ts = datetime.now(timezone.utc).isoformat()
        result = PipelineResult(
            discovery=discovery,
            audit=audit,
            outreach=outreach,
            elapsed_seconds=elapsed,
            timestamp=ts,
        )
        await self._log_activity(
            "task",
            f"Pipeline concluido — novos={discovery.get('new', 0)} "
            f"auditados={audit.get('audited', 0)} outreach={outreach.get('generated', 0)}",
            f"elapsed={elapsed}s",
        )
        return result
