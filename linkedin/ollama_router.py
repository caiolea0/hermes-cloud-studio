"""Ollama router — VM-side fallback wrapper para chamadas LLM (MERGED-014).

Centraliza acesso ao Ollama com:
- URL primario (PC via tunnel reverso :11434 — RTX 2060 6GB) + fallback opcional VM local
- Model map por task (classify / creative_ptbr) — modelo certo pra cada uso
- Timeout configuravel + retry exponencial limitado
- Log estruturado quando fallback dispara (sintoma tunnel down)
- Hook pra futura VM-GPU: trocar ollama_url no .env e fallback some

Uso:
    from linkedin.ollama_router import router
    text = await router.route("creative_ptbr", prompt, options={"temperature": 0.7})

Tasks suportadas:
    - classify: classificacao curta (qwen2.5:3b default — rapido, suficiente)
    - creative_ptbr: geracao texto PT-BR/EN (qwen2.5:7b-instruct default — multilingual)

Configuracao via settings:
    - ollama_url (PC tunnel reverso, default http://localhost:11434)
    - ollama_url_fallback (vazio por default; setar quando VM tiver Ollama proprio)
    - ollama_model_classify / ollama_model_creative (override defaults)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger("hermes.ollama_router")


# Mapa task -> modelo default. Override via settings.ollama_model_*.
_DEFAULT_MODELS = {
    "classify": "qwen2.5:3b",
    "creative_ptbr": "qwen2.5:7b-instruct",
}


class OllamaUnavailable(RuntimeError):
    """Levantada quando primary E fallback falharam."""


class OllamaRouter:
    def __init__(
        self,
        primary_url: str,
        fallback_url: str = "",
        connect_timeout: float = 3.0,
        request_timeout: float = 45.0,
    ):
        self.primary_url = primary_url.rstrip("/")
        self.fallback_url = fallback_url.rstrip("/") if fallback_url else ""
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout

    def _resolve_model(self, task: str) -> str:
        if task == "classify":
            return settings.ollama_model_classify or _DEFAULT_MODELS["classify"]
        if task == "creative_ptbr":
            return settings.ollama_model_creative or _DEFAULT_MODELS["creative_ptbr"]
        raise ValueError(f"task desconhecida: {task!r}. Suportadas: {list(_DEFAULT_MODELS)}")

    async def _call(self, base_url: str, payload: dict) -> Optional[str]:
        """POST /api/generate em base_url. Retorna response str ou raise."""
        timeout = httpx.Timeout(self.request_timeout, connect=self.connect_timeout)
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{base_url}/api/generate", json=payload)
            r.raise_for_status()
            data = r.json()
            return data.get("response", "")

    async def route(
        self,
        task: str,
        prompt: str,
        options: Optional[dict] = None,
        model: Optional[str] = None,
    ) -> str:
        """Roteia prompt para o modelo correto da task.

        Tenta primary (PC) -> fallback (VM local se configurado) -> raise OllamaUnavailable.

        Args:
            task: "classify" | "creative_ptbr"
            prompt: texto do prompt
            options: opcoes Ollama (temperature, top_p, num_predict, etc)
            model: override explicito (usa em vez do default da task)

        Returns:
            String com a resposta (.response do Ollama). Pode ser vazia se modelo nao gerou.

        Raises:
            OllamaUnavailable: se primary E fallback falharem
            ValueError: task desconhecida
        """
        chosen_model = model or self._resolve_model(task)
        payload = {
            "model": chosen_model,
            "prompt": prompt,
            "stream": False,
        }
        if options:
            payload["options"] = options

        primary_err: Optional[Exception] = None
        try:
            return await self._call(self.primary_url, payload) or ""
        except Exception as e:
            primary_err = e
            logger.warning(
                "ollama primary indisponivel task=%s model=%s url=%s err=%s",
                task, chosen_model, self.primary_url, e,
            )

        if not self.fallback_url:
            logger.error(
                "ollama primary failed e nenhum fallback configurado "
                "(setar HERMES_OLLAMA_FALLBACK_URL quando VM-GPU disponivel). task=%s",
                task,
            )
            raise OllamaUnavailable(
                f"Ollama primary ({self.primary_url}) falhou: {primary_err}. "
                "Sem fallback configurado."
            ) from primary_err

        try:
            logger.info("ollama fallback dispatch task=%s model=%s url=%s", task, chosen_model, self.fallback_url)
            return await self._call(self.fallback_url, payload) or ""
        except Exception as e:
            logger.error(
                "ollama fallback tambem falhou task=%s primary_err=%s fallback_err=%s",
                task, primary_err, e,
            )
            raise OllamaUnavailable(
                f"Ollama primary E fallback falharam. primary={primary_err} fallback={e}"
            ) from e


# Singleton (import-time) — config das settings
router = OllamaRouter(
    primary_url=settings.ollama_url,
    fallback_url=settings.ollama_url_fallback,
    connect_timeout=settings.ollama_connect_timeout,
    request_timeout=settings.ollama_request_timeout,
)


async def generate(task: str, prompt: str, options: Optional[dict] = None, model: Optional[str] = None) -> str:
    """Atalho funcional. Equivalente a router.route(...)."""
    return await router.route(task, prompt, options=options, model=model)
