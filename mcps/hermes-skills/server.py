"""hermes-skills MCP — 6 tools YAML mgmt + DB hybrid stub.

D4 HYBRID storage strategy:
- list_skills + get_skill + toggle_active → glob skills/*.yaml filesystem
- propose_skill_yaml_stub → gera YAML in-memory (F.4 persiste skill_proposals)
- test_skill_dryrun → invoca skill em sandbox isolado mock LLM
- get_metrics → ler skill_runs table SE existe (silent empty fallback)

Tools (6):
  1. list_skills
  2. get_skill(name)
  3. toggle_active(name, active)
  4. propose_skill_yaml_stub(name, description, model)
  5. test_skill_dryrun(skill_yaml, input_data)
  6. get_metrics(skill_name, window_days)

Run: python mcps/hermes-skills/server.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "fastmcp não instalado. F.5.2 exige fastmcp>=3.0. Erro: " + str(exc)
    )

MCP_NAME = "hermes-skills"
MCP_VERSION = "0.1.0-f5.2"

# VM canonical (~/.hermes/skills/) primary; PC repo skills/ fallback
_VM_SKILLS = Path(os.path.expanduser("~/.hermes/skills"))
_PC_SKILLS = _REPO_ROOT / "skills"

_VM_DB = Path(os.path.expanduser("~/.hermes/data/command_center.db"))
_PC_DB = _REPO_ROOT / "hermes_local.db"

VALID_PROVIDERS = frozenset({
    "openrouter", "ollama", "anthropic", "openai", "deepseek",
})


def _skills_dir() -> Path:
    """VM canonical se existe E tem YAMLs; senão repo PC fallback."""
    if _VM_SKILLS.exists() and any(_VM_SKILLS.glob("*.yaml")):
        return _VM_SKILLS
    return _PC_SKILLS


def _db_path() -> Path:
    return _VM_DB if _VM_DB.exists() else _PC_DB


def _validate_skill_name(name: str) -> str | None:
    """Reject path traversal / unsafe filename chars. Returns error or None."""
    if not name or not isinstance(name, str):
        return "name must be non-empty string"
    if any(ch in name for ch in ("/", "\\", "..", "\x00")):
        return "name contains unsafe chars (path traversal blocked)"
    if len(name) > 64:
        return "name too long (max 64 chars)"
    return None


mcp = FastMCP(MCP_NAME)


@mcp.tool()
async def list_skills() -> dict:
    """Lista skills YAML em skills/ (filesystem read-only).

    Returns:
        dict {ok, source: "vm-skills"|"pc-skills", count, skills[]}
    """
    skills_dir = _skills_dir()
    if not skills_dir.exists():
        return {
            "ok": True, "source": str(skills_dir),
            "count": 0, "skills": [],
            "note": "skills dir not found (empty repo or VM mount missing)",
        }
    skills: list[dict] = []
    for yaml_path in sorted(skills_dir.glob("*.yaml")):
        try:
            with yaml_path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception as exc:
            skills.append({
                "file": yaml_path.name, "ok": False,
                "error": f"yaml parse: {str(exc)[:200]}",
            })
            continue
        skills.append({
            "file": yaml_path.name,
            "name": data.get("name"),
            "description": data.get("description", "")[:200],
            "version": data.get("version"),
            "active": bool(data.get("active", False)),
            "model": data.get("model"),
            "provider": data.get("provider"),
        })
    source = "vm-skills" if skills_dir == _VM_SKILLS else "pc-skills"
    return {
        "ok": True, "source": source,
        "count": len(skills), "skills": skills,
    }


@mcp.tool()
async def get_skill(name: str) -> dict:
    """Lê YAML completo de uma skill por name.

    Args:
        name: identifier sem extensão (ex "linkedin-engagement").

    Returns:
        dict {ok, name, file, yaml_data, raw} OR {ok: false, error}
    """
    err = _validate_skill_name(name)
    if err:
        return {"ok": False, "error": err}
    skills_dir = _skills_dir()
    yaml_path = skills_dir / f"{name}.yaml"
    if not yaml_path.exists():
        return {"ok": False, "error": f"skill {name!r} not found in {skills_dir}"}
    try:
        raw = yaml_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
    except Exception as exc:
        return {"ok": False, "error": f"yaml parse: {str(exc)[:200]}"}
    return {
        "ok": True, "name": name, "file": yaml_path.name,
        "yaml_data": data, "raw_chars": len(raw),
    }


@mcp.tool()
async def toggle_active(name: str, active: bool) -> dict:
    """Liga/desliga flag active no YAML. Atomic write via rename.

    Args:
        name: skill identifier.
        active: novo estado boolean.

    Returns:
        dict {ok, name, prev_active, new_active}
    """
    err = _validate_skill_name(name)
    if err:
        return {"ok": False, "error": err}
    skills_dir = _skills_dir()
    yaml_path = skills_dir / f"{name}.yaml"
    if not yaml_path.exists():
        return {"ok": False, "error": f"skill {name!r} not found"}
    try:
        with yaml_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception as exc:
        return {"ok": False, "error": f"yaml parse: {str(exc)[:200]}"}
    prev = bool(data.get("active", False))
    new = bool(active)
    if prev == new:
        return {"ok": True, "name": name, "prev_active": prev, "new_active": new, "no_change": True}
    data["active"] = new
    # Atomic write via temp + rename
    tmp_path = yaml_path.with_suffix(".yaml.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
        tmp_path.replace(yaml_path)
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return {"ok": False, "error": f"write failed: {str(exc)[:200]}"}
    return {
        "ok": True, "name": name,
        "prev_active": prev, "new_active": new,
    }


@mcp.tool()
async def propose_skill_yaml_stub(
    name: str,
    description: str,
    model: str = "deepseek/deepseek-chat:free",
    provider: str = "openrouter",
) -> dict:
    """Gera stub YAML em memória — F.4 entrega persistência em skill_proposals.

    Args:
        name: identifier kebab-case (ex "linkedin-followup-generator").
        description: 1-line PT-BR objetivo.
        model: model id (default deepseek free).
        provider: openrouter|ollama|anthropic|openai|deepseek.

    Returns:
        dict {ok, yaml_stub, next_step}
    """
    err = _validate_skill_name(name)
    if err:
        return {"ok": False, "error": err}
    if provider not in VALID_PROVIDERS:
        return {
            "ok": False,
            "error": f"provider must be one of {sorted(VALID_PROVIDERS)}",
        }
    if not description or len(description) < 10:
        return {"ok": False, "error": "description must be >= 10 chars"}
    stub = {
        "name": name,
        "description": description[:200],
        "version": "0.1.0",
        "active": False,
        "model": model,
        "provider": provider,
        "temperature": 0.6,
        "max_tokens": 500,
        "system_prompt": (
            "TODO owner review: descreva persona + objetivo + restricoes + tom. "
            f"Skill auto-proposta F.4 — review obrigatorio antes active=true."
        ),
        "triggers": [],
        "input_schema": {},
    }
    yaml_text = yaml.safe_dump(stub, sort_keys=False, allow_unicode=True)
    return {
        "ok": True,
        "yaml_stub": yaml_text,
        "proposal_name": name,
        "next_step": (
            "F.4 entrega skill_proposals DB persistence + dashboard review UI. "
            "F.5.2 retorna apenas stub in-memory."
        ),
    }


@mcp.tool()
async def test_skill_dryrun(
    skill_name: str,
    input_data: dict,
    mock_llm: bool = True,
) -> dict:
    """Dry-run skill em sandbox — F.5.2 scaffold retorna plan, F.future executa.

    Args:
        skill_name: nome skill já registrada (file exists).
        input_data: dict params validados contra input_schema.
        mock_llm: True = retorna stub response (default). False ainda reservado
                  F.future quando lab sandbox plug.

    Returns:
        dict {ok, skill_name, input_validated, llm_response, mode}
    """
    err = _validate_skill_name(skill_name)
    if err:
        return {"ok": False, "error": err}
    skill = await get_skill(skill_name)  # reusa validação + read
    if not skill.get("ok"):
        return skill
    schema = skill["yaml_data"].get("input_schema") or {}
    input_keys = set((input_data or {}).keys())
    required_keys = set(schema.keys()) if isinstance(schema, dict) else set()
    missing = required_keys - input_keys
    if missing:
        return {
            "ok": False,
            "error": f"input missing required keys per input_schema: {sorted(missing)}",
        }
    if not mock_llm:
        return {
            "ok": False,
            "error": "mock_llm=False ainda não implementado (F.future lab sandbox plug)",
        }
    return {
        "ok": True,
        "skill_name": skill_name,
        "mode": "mock_llm",
        "input_validated": list(input_keys),
        "llm_response": {
            "stub": True,
            "would_invoke": skill["yaml_data"].get("model"),
            "provider": skill["yaml_data"].get("provider"),
            "system_prompt_chars": len(skill["yaml_data"].get("system_prompt") or ""),
        },
        "next_step": "F.future: lab sandbox real exec via OpenRouter + capture trace",
    }


@mcp.tool()
async def get_metrics(skill_name: str, window_days: int = 7) -> dict:
    """Lê skill_runs table SE existe — silent empty se ausente (F.4 cria).

    Args:
        skill_name: identifier.
        window_days: janela (default 7, max 90).

    Returns:
        dict {ok, skill_name, window_days, table_exists, count, breakdown{}}
    """
    err = _validate_skill_name(skill_name)
    if err:
        return {"ok": False, "error": err}
    window_days = max(1, min(int(window_days), 90))
    db = _db_path()
    if not db.exists():
        return {
            "ok": True, "skill_name": skill_name, "window_days": window_days,
            "table_exists": False, "count": 0,
            "note": f"DB not found at {db} (PC pre-sync OR VM mount missing)",
        }
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        # Probe schema first
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "skill_runs" not in tables:
            conn.close()
            return {
                "ok": True, "skill_name": skill_name, "window_days": window_days,
                "table_exists": False, "count": 0,
                "note": "skill_runs table not created (F.4 entrega)",
            }
        cutoff = time.time() - window_days * 86400
        rows = list(conn.execute(
            "SELECT outcome, COUNT(*) as n FROM skill_runs "
            "WHERE skill_name = ? AND ts >= ? GROUP BY outcome",
            (skill_name, cutoff),
        ))
        conn.close()
    except Exception as exc:
        return {"ok": False, "error": f"DB query failed: {str(exc)[:200]}"}
    breakdown = {r["outcome"]: r["n"] for r in rows}
    return {
        "ok": True, "skill_name": skill_name,
        "window_days": window_days,
        "table_exists": True,
        "count": sum(breakdown.values()),
        "breakdown": breakdown,
    }


def main() -> None:
    transport = os.getenv("HERMES_MCP_TRANSPORT", "stdio").lower()
    if transport == "http":
        port = int(os.getenv("HERMES_HERMES_SKILLS_PORT", "55413"))
        mcp.run(transport="http", host="127.0.0.1", port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
