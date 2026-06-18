"""UX-RM-F5-B — Citation resolver.

Maps (source_type, source_id) → {url, title, snippet, source_type, source_id}.
Fail-graceful: unknown source_id yields default render with source_type:source_id label.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("brain.citation_resolver")

_SKILLS_DIR = Path(__file__).parent.parent / "skills"


def resolve_citation(source_type: str, source_id: str) -> dict[str, Any]:
    """Resolve a citation to its clickable URL + snippet.

    Returns: {url, title, snippet, source_type, source_id}
    """
    handlers: dict[str, Any] = {
        "skill": _resolve_skill,
        "memory": _resolve_memory,
        "log": _resolve_log,
        "tool_result": _resolve_tool,
        "doc": _resolve_doc,
    }
    handler = handlers.get(source_type, _default)
    try:
        return handler(source_id)
    except Exception as exc:  # noqa: BLE001
        log.debug("citation fallback source_type=%s source_id=%s err=%s", source_type, source_id, exc)
        return _default(source_id, source_type=source_type)


def _resolve_skill(skill_id: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
        for ext in ("yaml", "yml"):
            path = _SKILLS_DIR / f"{skill_id}.{ext}"
            if path.exists():
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                return {
                    "url": "#skills",
                    "title": data.get("name", skill_id),
                    "snippet": str(data.get("description", ""))[:200],
                    "source_type": "skill",
                    "source_id": skill_id,
                }
    except Exception:  # noqa: BLE001
        pass
    return {
        "url": "#skills",
        "title": skill_id,
        "snippet": "",
        "source_type": "skill",
        "source_id": skill_id,
    }


def _resolve_memory(memory_id: str) -> dict[str, Any]:
    return {
        "url": "#memory",
        "title": f"Memória: {memory_id}",
        "snippet": "",
        "source_type": "memory",
        "source_id": memory_id,
    }


def _resolve_log(log_id: str) -> dict[str, Any]:
    return {
        "url": "#dashboard",
        "title": f"Log: {log_id}",
        "snippet": "",
        "source_type": "log",
        "source_id": log_id,
    }


def _resolve_tool(tool_id: str) -> dict[str, Any]:
    return {
        "url": "#observability",
        "title": f"Tool: {tool_id}",
        "snippet": "",
        "source_type": "tool_result",
        "source_id": tool_id,
    }


def _resolve_doc(doc_id: str) -> dict[str, Any]:
    return {
        "url": "#dashboard",
        "title": f"Doc: {doc_id}",
        "snippet": "",
        "source_type": "doc",
        "source_id": doc_id,
    }


def _default(source_id: str, *, source_type: str = "unknown") -> dict[str, Any]:
    return {
        "url": "#dashboard",
        "title": f"{source_type}:{source_id}",
        "snippet": "",
        "source_type": source_type,
        "source_id": source_id,
    }
