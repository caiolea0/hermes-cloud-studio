"""F.5.4 single-source MCP tier classification.

Resolve duplicação WARN D7-bis F.5.3 reviewer (mcps/gateway/server.py +
vm_api/mcp_coverage.py tinham 2 cópias idênticas ~50 linhas).

Tier semantics:
- active:      last_call < 7d (uso vigente)
- warning:     7d <= last_call < 30d (uso caindo)
- orphan:      tool registered (registry_tier=active) sem call last 30d
- deprecated:  registry override OU registered active sem call >30d (drift)
- quarantine:  registry override (skill auto-disable F.4)
- reserved:    registry override (planejado mas não ativado, F.5.6+)

Single import: `from vm_core.mcp_tiering import classify_tier, aggregate_by_tier`
usado por mcps/gateway/server.py + vm_api/mcp_coverage.py + scripts/_validate_phase_f.py.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any


_OVERRIDE_TIERS = frozenset({"deprecated", "quarantine", "reserved"})


def classify_tier(
    server: str,
    tool: str,
    last_call_at: str | None,
    registry_tier: str | None = None,
) -> str:
    """Classifica tier individual server+tool.

    Args:
        server: nome do MCP (ex: "hermes-linkedin").
        tool: nome do tool (ex: "send_invite").
        last_call_at: timestamp ISO da última chamada (None = sem call).
        registry_tier: tier persistido em mcp_registry (override real-time).

    Returns:
        Um de: active | warning | orphan | deprecated | quarantine | reserved.
    """
    # Registry override hard (deprecated/quarantine/reserved sempre preserva)
    if registry_tier in _OVERRIDE_TIERS:
        return registry_tier

    if not last_call_at:
        # Sem call: orphan se registered active, senão preserva registry_tier
        if registry_tier == "active" or registry_tier is None:
            return "orphan"
        return registry_tier

    try:
        last = datetime.fromisoformat(str(last_call_at).replace(" ", "T"))
    except (ValueError, TypeError, AttributeError):
        return "orphan"

    now = datetime.utcnow()
    delta = now - last
    if delta < timedelta(days=7):
        return "active"
    if delta < timedelta(days=30):
        return "warning"
    # >30d sem call em tool registered active = drift
    return "deprecated"


def classify_drift(registry_tier: str | None, runtime_tier: str | None) -> bool:
    """F.5.5 D4 drift detection helper (single-source).

    Drift = registered as active mas runtime estado degraded (orphan/warning/deprecated).
    Sinal pra owner: deprecar OR investigar uso real.

    Args:
        registry_tier: tier persistido em mcp_registry (source-of-truth manual).
        runtime_tier: tier classificado por classify_tier() runtime.

    Returns:
        True se drift detectado.
    """
    if registry_tier != "active":
        return False
    if runtime_tier in ("orphan", "warning", "deprecated"):
        return True
    return False


def aggregate_by_tier(items: list[dict]) -> dict[str, int]:
    """Summary count por tier (use após classify_tier por item).

    Args:
        items: lista de {server, tool, tier, registry_tier, ...}.

    Returns:
        {total_tools, active, warning, orphan, deprecated, quarantine, reserved}.
    """
    summary = {
        "total_tools": len(items),
        "active": 0,
        "warning": 0,
        "orphan": 0,
        "deprecated": 0,
        "quarantine": 0,
        "reserved": 0,
    }
    for item in items:
        tier = item.get("tier", "orphan")
        if tier in summary:
            summary[tier] += 1
        # registry_tier override contributions (deprecated/quarantine/reserved)
        reg_tier = item.get("registry_tier")
        if reg_tier in _OVERRIDE_TIERS and reg_tier != tier:
            # Já contado em tier — não double-count
            pass
    # Reconta deprecated/quarantine/reserved via registry_tier (compat F.5.3 endpoint shape)
    for key in ("deprecated", "quarantine", "reserved"):
        summary[key] = sum(1 for i in items if i.get("registry_tier") == key)
    return summary


def build_coverage_items(
    call_rows: list[dict],
    registry_rows: list[dict],
) -> list[dict]:
    """Join calls × registry com tier classify per tool.

    Args:
        call_rows: rows de mcp_calls agregados por (server, tool):
                   {server, tool, calls, avg_ms, last_call, errors}
        registry_rows: rows de mcp_registry:
                       {server, tools (JSON), tier, chapter_owner}

    Returns:
        Lista de items {server, tool, calls, avg_ms, last_call, errors,
                        tier, registry_tier, chapter_owner}.
    """
    call_map = {(r["server"], r["tool"]): r for r in call_rows}
    items: list[dict] = []
    for reg in registry_rows:
        try:
            tools = json.loads(reg.get("tools") or "[]")
        except (ValueError, TypeError):
            tools = []
        registry_tier = reg.get("tier", "active")
        for tool in tools:
            key = (reg["server"], tool)
            if key in call_map:
                r = call_map[key]
                tier = classify_tier(reg["server"], tool, r.get("last_call"), registry_tier)
                items.append({
                    "server": reg["server"],
                    "tool": tool,
                    "calls": r.get("calls", 0),
                    "avg_ms": r.get("avg_ms"),
                    "last_call": r.get("last_call"),
                    "errors": r.get("errors", 0),
                    "tier": tier,
                    "registry_tier": registry_tier,
                    "chapter_owner": reg.get("chapter_owner"),
                })
            else:
                tier = classify_tier(reg["server"], tool, None, registry_tier)
                items.append({
                    "server": reg["server"],
                    "tool": tool,
                    "calls": 0,
                    "avg_ms": None,
                    "last_call": None,
                    "errors": 0,
                    "tier": tier,
                    "registry_tier": registry_tier,
                    "chapter_owner": reg.get("chapter_owner"),
                })
    return items


def classify_coverage(
    call_rows: list[dict],
    registry_rows: list[dict],
) -> dict[str, Any]:
    """Wrapper compat F.5.3 endpoint shape: {summary, items}.

    Substitui `_classify_tiers_realtime` inline em
    mcps/gateway/server.py + vm_api/mcp_coverage.py.
    """
    items = build_coverage_items(call_rows, registry_rows)
    return {"summary": aggregate_by_tier(items), "items": items}
