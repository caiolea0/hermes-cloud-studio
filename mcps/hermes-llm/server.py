"""hermes-llm MCP — F.5.7 routing dispatcher.

3-tier fallback chain (T1 NIM Free → T2 NIM credit → T3 Ollama PC local).
T4 OpenRouter explicit force_provider override only.

Ground truth: .claude/NVIDIA-MODELS-ROUTING-MATRIX.md §4 (12 tasks).
Pattern reference: mcps/hermes-skills/server.py (F.5.2 scaffold).

Tools (6):
  1. route(prompt, task_type, ...)
  2. list_available_models(provider, capability_filter)
  3. get_provider_status()
  4. track_cost(call_id, provider, model, tokens_in, tokens_out)
  5. set_routing_policy(policy_name)
  6. get_call_history(skill_name, window_days, limit)

Run: python mcps/hermes-llm/server.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SELF_DIR = Path(__file__).resolve().parent
if str(_SELF_DIR) not in sys.path:
    sys.path.insert(0, str(_SELF_DIR))


# F.6.2 fix — fastmcp StdioTransport spawns subprocess with empty env (apenas PATH).
# Sem load explicit, HERMES_NIM_API_KEY + outros tokens NÃO chegam neste process,
# fazendo NIM/OpenRouter clients reportarem "key missing". Load .env canônico VM/PC
# stdlib-only (sem depender python-dotenv que pode não estar no venv).
def _load_env_canonical() -> None:
    """Load .env from canonical locations into os.environ (stdlib only)."""
    candidates = [
        Path.home() / ".hermes" / ".env",            # VM canonical (F.5.5 systemd EnvironmentFile)
        _REPO_ROOT / ".env",                          # PC repo local
    ]
    for p in candidates:
        if not p.exists():
            continue
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
            break  # primeiro encontrado vence
        except Exception:
            pass


_load_env_canonical()

try:
    from fastmcp import FastMCP
except ImportError as exc:
    raise SystemExit("fastmcp não instalado. F.5.7 exige fastmcp>=3.0. Erro: " + str(exc))

from _adapters import NIMClient, OllamaPCClient, OpenRouterClient, get_client  # type: ignore  # noqa: E402
from _policy import (  # type: ignore  # noqa: E402
    ABORT_TRIGGERS_NO_FALLBACK,
    FALLBACK_TRIGGERS,
    RpmLimiter,
    VALID_POLICIES,
    VALID_PROVIDERS,
    VALID_TASK_TYPES,
    load_routing_config,
    route_decide,
    should_fallback,
)

MCP_NAME = "hermes-llm"
MCP_VERSION = "0.1.0-f5.7"

_VM_DB = Path(os.path.expanduser("~/.hermes/data/command_center.db"))
_PC_DB = _REPO_ROOT / "hermes_local.db"

_SENSITIVE_KEYS = frozenset({
    "li_at", "token", "cookie", "cookies", "password", "auth", "authorization",
    "api_key", "apikey", "secret", "bearer", "csrf", "csrf_token",
    "nvidia_api_key", "nvapi", "nim_token", "hermes_nim_api_key",
    "openrouter_api_key", "anthropic_api_key", "openai_api_key",
})

_runtime_state: dict[str, Any] = {
    "policy": "balanced",
    "rpm_nim_free": RpmLimiter(max_rpm=38),
    "rpm_nim_credit": RpmLimiter(max_rpm=60),
}


def _db_path() -> Path:
    return _VM_DB if _VM_DB.exists() else _PC_DB


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key_lower = str(k).strip().lower()
            redacted = False
            for sk in _SENSITIVE_KEYS:
                if sk in key_lower:
                    redacted = True
                    break
            out[k] = "[REDACTED]" if redacted else _sanitize(v)
        return out
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str) and value.startswith("nvapi-"):
        return "[REDACTED]"
    return value


def _validate_task_type(task_type: str) -> str | None:
    if not task_type or not isinstance(task_type, str):
        return "task_type must be non-empty string"
    if task_type not in VALID_TASK_TYPES:
        return f"task_type must be one of {sorted(VALID_TASK_TYPES)}"
    return None


def _validate_call_id(call_id: str) -> str | None:
    if not call_id or not isinstance(call_id, str):
        return "call_id must be non-empty string"
    if len(call_id) > 128:
        return "call_id too long (max 128 chars)"
    if any(ch in call_id for ch in ("\x00", "\n", "\r")):
        return "call_id contains unsafe chars"
    return None


mcp = FastMCP(MCP_NAME)


async def _execute_with_fallback(
    chain: list[tuple[str, str, str]],
    prompt: str,
    max_latency_ms: int,
    max_cost_credits: int,
) -> dict[str, Any]:
    messages = [{"role": "user", "content": prompt}]
    timeout_s = max(1.0, max_latency_ms / 1000.0)
    attempted: list[dict[str, Any]] = []

    for tier, provider, model in chain:
        if provider in ("nim_free", "nim"):
            if not _runtime_state["rpm_nim_free"].can_proceed():
                attempted.append({"tier": tier, "provider": provider, "model": model, "skipped": "rpm_cap"})
                continue
        if provider == "nim_credit":
            if not _runtime_state["rpm_nim_credit"].can_proceed():
                attempted.append({"tier": tier, "provider": provider, "model": model, "skipped": "rpm_cap"})
                continue
        if max_cost_credits == 0 and provider in ("nim_credit", "openrouter"):
            attempted.append({"tier": tier, "provider": provider, "model": model, "skipped": "cost_budget_zero"})
            continue

        client = get_client(provider)
        if client is None:
            attempted.append({"tier": tier, "provider": provider, "model": model, "skipped": "no_client"})
            continue

        result = await client.chat(model=model, messages=messages, timeout=timeout_s)
        attempted.append({
            "tier": tier,
            "provider": provider,
            "model": model,
            "ok": bool(result.get("ok")),
            "elapsed_ms": result.get("elapsed_ms"),
            "error": result.get("error"),
            "status_code": result.get("status_code"),
        })

        fallback, trigger = should_fallback(result)
        if result.get("ok") and not fallback:
            return {
                "ok": True,
                "provider": provider,
                "model": model,
                "tier": tier,
                "response": result.get("response"),
                "tool_calls": result.get("tool_calls"),
                "latency_ms": result.get("elapsed_ms"),
                "tokens_in": result.get("tokens_in", 0),
                "tokens_out": result.get("tokens_out", 0),
                "cost_credits": result.get("cost_credits", 0.0),
                "fallback_chain_attempted": attempted,
            }
        for name, fn in ABORT_TRIGGERS_NO_FALLBACK.items():
            if fn(result):
                return {
                    "ok": False,
                    "error": f"abort:{name}",
                    "provider": provider,
                    "model": model,
                    "tier": tier,
                    "details": result,
                    "fallback_chain_attempted": attempted,
                }

    return {
        "ok": False,
        "error": "all_tiers_failed",
        "fallback_chain_attempted": attempted,
    }


@mcp.tool()
async def route(
    prompt: str,
    task_type: str,
    model_hint: str = "",
    max_latency_ms: int = 30000,
    max_cost_credits: int = 0,
    force_provider: str = "",
    policy: str = "",
) -> dict:
    """Core dispatcher 3-tier fallback chain.

    Args:
        prompt: text prompt enviado provider.
        task_type: one of {default, reasoning, classify, code_gen, code_gen_light,
                   creative_ptbr, summarize, embedding, generic_light}.
        model_hint: opcional model_id override (not yet wired tier override F.5.7).
        max_latency_ms: timeout per-call (default 30s).
        max_cost_credits: budget total credits (0 = T1+T3 only, skip nim_credit/openrouter).
        force_provider: nim_free|nim_credit|ollama_pc|openrouter — single tier no fallback.
        policy: balanced (default) | cost-optimize | latency-optimize.

    Returns:
        dict {ok, provider, model, tier, response, tool_calls, latency_ms,
              tokens_in, tokens_out, cost_credits, fallback_chain_attempted}
    """
    err = _validate_task_type(task_type)
    if err:
        return {"ok": False, "error": err}
    if not prompt or not isinstance(prompt, str):
        return {"ok": False, "error": "prompt must be non-empty string"}
    if force_provider and force_provider not in VALID_PROVIDERS:
        return {"ok": False, "error": f"force_provider must be one of {sorted(VALID_PROVIDERS)}"}

    active_policy = policy or _runtime_state["policy"]
    if active_policy not in VALID_POLICIES:
        return {"ok": False, "error": f"policy must be one of {sorted(VALID_POLICIES)}"}

    chain = route_decide(task_type, policy=active_policy, force_provider=force_provider)
    if not chain:
        return {"ok": False, "error": f"no tier available for task_type={task_type} policy={active_policy}"}

    result = await _execute_with_fallback(chain, prompt, max_latency_ms, max_cost_credits)
    return result


@mcp.tool()
async def list_available_models(provider: str = "", capability_filter: str = "") -> dict:
    """Lista models do catalog routing_matrix config.yaml (não DB ainda — F.6 hidrata mcp_llm_models).

    Args:
        provider: filtro provider (nim_free|nim_credit|ollama_pc|openrouter).
        capability_filter: free_endpoint|function_calling|ptbr_official (best-effort tagging).

    Returns:
        dict {ok, count, models[{provider, model, tier, task_type}]}
    """
    config = load_routing_config()
    matrix = config.get("routing_matrix", {})
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for task_type, chain in matrix.items():
        for entry in chain:
            p = entry.get("provider", "")
            m = entry.get("model", "")
            key = (p, m)
            if key in seen:
                continue
            seen.add(key)
            if provider and p != provider:
                continue
            rows.append({
                "provider": p,
                "model": m,
                "tier": entry.get("tier", ""),
                "task_type_example": task_type,
            })
    return {
        "ok": True,
        "count": len(rows),
        "models": rows,
        "note": "F.6 hidrata mcp_llm_models DB c/ capabilities + free_endpoint + context flags",
    }


@mcp.tool()
async def get_provider_status() -> dict:
    """Health check 3 providers paralelo timeout 2s.

    Returns:
        dict per provider {up, latency_ms, rate_limit_remaining}
    """
    nim = NIMClient()
    ollama = OllamaPCClient()
    openrouter = OpenRouterClient()

    results = await asyncio.gather(
        nim.health(timeout=2.0),
        ollama.health(timeout=2.0),
        openrouter.health(timeout=2.0),
        return_exceptions=True,
    )

    def _coerce(r: Any) -> dict[str, Any]:
        if isinstance(r, Exception):
            return {"up": False, "error": str(r)[:200], "latency_ms": 0}
        return r if isinstance(r, dict) else {"up": False, "error": "unknown_result_type"}

    return {
        "ok": True,
        "nim_free": {
            **_coerce(results[0]),
            "rpm_remaining": _runtime_state["rpm_nim_free"].remaining(),
        },
        "nim_credit": {
            **_coerce(results[0]),
            "rpm_remaining": _runtime_state["rpm_nim_credit"].remaining(),
            "note": "shares NIM API key — credit balance check F.5.9 cron",
        },
        "ollama_pc": _coerce(results[1]),
        "openrouter": _coerce(results[2]),
    }


@mcp.tool()
async def track_cost(
    call_id: str,
    provider: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
) -> dict:
    """INSERT mcp_calls row extended cost columns. Idempotente call_id PK.

    Args:
        call_id: UUID string per dispatch.
        provider: nim_free|nim_credit|ollama_pc|openrouter.
        model: exact model_id.
        tokens_in: prompt tokens.
        tokens_out: completion tokens.

    Returns:
        dict {ok, call_id, inserted, table_extended}
    """
    err = _validate_call_id(call_id)
    if err:
        return {"ok": False, "error": err}
    if provider not in VALID_PROVIDERS:
        return {"ok": False, "error": f"provider must be one of {sorted(VALID_PROVIDERS)}"}
    if not isinstance(tokens_in, int) or tokens_in < 0:
        return {"ok": False, "error": "tokens_in must be int >= 0"}
    if not isinstance(tokens_out, int) or tokens_out < 0:
        return {"ok": False, "error": "tokens_out must be int >= 0"}

    db = _db_path()
    if not db.exists():
        return {
            "ok": True,
            "call_id": call_id,
            "inserted": False,
            "table_extended": False,
            "note": f"DB not found at {db} — F.5.7b migration apply pendente",
        }

    try:
        conn = sqlite3.connect(str(db))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(mcp_calls)")}
            extended = {"provider", "model", "tokens_in", "tokens_out", "cost_credits"}.issubset(cols)
            if not extended:
                conn.close()
                return {
                    "ok": True,
                    "call_id": call_id,
                    "inserted": False,
                    "table_extended": False,
                    "note": "mcp_calls missing F.5.7 columns — apply migration",
                }
            existing = conn.execute("SELECT 1 FROM mcp_calls WHERE id = ?", (call_id,)).fetchone()
            if existing:
                conn.close()
                return {"ok": True, "call_id": call_id, "inserted": False, "duplicate": True}
            conn.execute(
                "INSERT INTO mcp_calls (id, server, tool, provider, model, tokens_in, tokens_out, cost_credits) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (call_id, "hermes-llm", "route", provider, model, tokens_in, tokens_out, 0.0),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        return {"ok": False, "error": f"DB write failed: {str(exc)[:200]}"}

    return {"ok": True, "call_id": call_id, "inserted": True, "table_extended": True}


@mcp.tool()
async def set_routing_policy(policy_name: str) -> dict:
    """Muda policy ativa runtime.

    Args:
        policy_name: balanced | cost-optimize | latency-optimize.

    Returns:
        dict {ok, prev_policy, new_policy}
    """
    if policy_name not in VALID_POLICIES:
        return {"ok": False, "error": f"policy must be one of {sorted(VALID_POLICIES)}"}
    prev = _runtime_state["policy"]
    _runtime_state["policy"] = policy_name
    return {"ok": True, "prev_policy": prev, "new_policy": policy_name}


@mcp.tool()
async def get_call_history(skill_name: str = "", window_days: int = 7, limit: int = 50) -> dict:
    """SELECT mcp_calls WHERE server='hermes-llm' filtros opcionais.

    Args:
        skill_name: filter caller (requester column).
        window_days: janela (max 90).
        limit: max rows (max 500).

    Returns:
        dict {ok, table_exists, count, rows[], window_days, limit}
    """
    window_days = max(1, min(int(window_days), 90))
    limit = max(1, min(int(limit), 500))
    db = _db_path()
    if not db.exists():
        return {
            "ok": True,
            "table_exists": False,
            "count": 0,
            "rows": [],
            "window_days": window_days,
            "limit": limit,
            "note": f"DB not found at {db}",
        }
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "mcp_calls" not in tables:
            conn.close()
            return {
                "ok": True, "table_exists": False, "count": 0, "rows": [],
                "window_days": window_days, "limit": limit,
            }
        cutoff_ts = time.time() - window_days * 86400
        query = (
            "SELECT id, server, tool, provider, model, tokens_in, tokens_out, "
            "cost_credits, duration_ms, requester, created_at "
            "FROM mcp_calls WHERE server = 'hermes-llm' "
            "AND strftime('%s', created_at) >= ? "
        )
        params: list[Any] = [str(int(cutoff_ts))]
        if skill_name:
            query += "AND requester = ? "
            params.append(skill_name)
        query += "ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cols = {r[1] for r in conn.execute("PRAGMA table_info(mcp_calls)")}
        extended = {"provider", "model", "tokens_in", "tokens_out", "cost_credits"}.issubset(cols)
        if not extended:
            query = (
                "SELECT id, server, tool, duration_ms, requester, created_at "
                "FROM mcp_calls WHERE server = 'hermes-llm' "
                "AND strftime('%s', created_at) >= ? "
            )
            params = [str(int(cutoff_ts))]
            if skill_name:
                query += "AND requester = ? "
                params.append(skill_name)
            query += "ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

        rows = [dict(r) for r in conn.execute(query, params)]
        conn.close()
    except Exception as exc:
        return {"ok": False, "error": f"DB query failed: {str(exc)[:200]}"}
    return {
        "ok": True,
        "table_exists": True,
        "count": len(rows),
        "rows": rows,
        "window_days": window_days,
        "limit": limit,
        "extended_columns": extended,
    }


def main() -> None:
    transport = os.getenv("HERMES_MCP_TRANSPORT", "stdio").lower()
    if transport == "http":
        port = int(os.getenv("HERMES_HERMES_LLM_PORT", "55414"))
        mcp.run(transport="http", host="127.0.0.1", port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
