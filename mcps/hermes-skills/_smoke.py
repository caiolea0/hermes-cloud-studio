"""hermes-skills smoke test — F.5.2.

Verifica:
1. fastmcp importável (stub fallback PC)
2. server.py imports + mcp instance
3. 6 tools registered
4. _validate_skill_name rejeita path traversal
5. list_skills lê pc-skills (6 YAMLs existing skills/)
6. propose_skill_yaml_stub gera YAML válido com schema esperado
7. VALID_PROVIDERS contém 5 canonical

Smoke isolado — NÃO modifica YAMLs reais (toggle_active não invocado).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _stub_fastmcp_if_missing() -> str:
    try:
        import fastmcp  # noqa: F401
        return "real"
    except ImportError:
        import types
        stub = types.ModuleType("fastmcp")

        class _StubMCP:
            def __init__(self, name: str):
                self.name = name
                self._registered: list[str] = []

            def tool(self, *a, **kw):
                def deco(fn):
                    self._registered.append(fn.__name__)
                    return fn
                return deco

            def run(self, **kw):
                return None

        stub.FastMCP = _StubMCP  # type: ignore
        sys.modules["fastmcp"] = stub
        return "stub"


def _check_fastmcp() -> bool:
    mode = _stub_fastmcp_if_missing()
    print(f"[smoke] fastmcp mode = {mode}")
    return True


def _check_server_imports() -> bool:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import server  # type: ignore
    except SystemExit as exc:
        print(f"[smoke] SKIP server import → SystemExit ({exc})")
        return False
    except Exception as exc:
        print(f"[smoke] FAIL server import: {exc}")
        return False
    assert server.MCP_NAME == "hermes-skills"
    assert server.MCP_VERSION.startswith("0.1.0-f5.2")
    print(f"[smoke] OK server import (name={server.MCP_NAME} v={server.MCP_VERSION})")
    return True


def _check_tools() -> bool:
    import server  # type: ignore
    expected = {
        "list_skills", "get_skill", "toggle_active",
        "propose_skill_yaml_stub", "test_skill_dryrun", "get_metrics",
    }
    found = {n for n in expected if callable(getattr(server, n, None))}
    missing = expected - found
    if missing:
        print(f"[smoke] FAIL tools missing: {sorted(missing)}")
        return False
    print(f"[smoke] OK 6 tools registered")
    return True


def _check_path_traversal_rejected() -> bool:
    import server  # type: ignore
    bad_names = [
        "../etc/passwd",
        "skills/../escape",
        "name\\with\\backslash",
        "null\x00byte",
        "a" * 100,
        "",
        None,
    ]
    for name in bad_names:
        err = server._validate_skill_name(name)  # type: ignore
        if err is None:
            print(f"[smoke] FAIL path traversal allowed for {name!r}")
            return False
    # Valid name passes
    ok = server._validate_skill_name("linkedin-engagement")
    if ok is not None:
        print(f"[smoke] FAIL legit name rejected: {ok}")
        return False
    print("[smoke] OK path traversal rejected (7 bad + 1 good case)")
    return True


def _check_list_skills_pc() -> bool:
    import server  # type: ignore
    res = asyncio.run(server.list_skills())
    if not res.get("ok"):
        print(f"[smoke] FAIL list_skills: {res}")
        return False
    if res["count"] < 1:
        print(f"[smoke] WARN list_skills count=0 (skills/ empty?)")
        # Empty is OK for cold checkout
    print(f"[smoke] OK list_skills source={res['source']} count={res['count']}")
    return True


def _check_propose_stub() -> bool:
    import server  # type: ignore
    import yaml as _yaml
    res = asyncio.run(server.propose_skill_yaml_stub(
        name="test-propose",
        description="Skill scaffold test for smoke — at least 10 chars",
        model="deepseek/deepseek-chat:free",
    ))
    if not res.get("ok"):
        print(f"[smoke] FAIL propose stub: {res}")
        return False
    yaml_text = res["yaml_stub"]
    parsed = _yaml.safe_load(yaml_text)
    required_keys = {
        "name", "description", "version", "active", "model", "provider",
        "temperature", "max_tokens", "system_prompt", "triggers", "input_schema",
    }
    missing = required_keys - set(parsed.keys())
    if missing:
        print(f"[smoke] FAIL stub missing keys: {sorted(missing)}")
        return False
    if parsed["active"] is not False:
        print(f"[smoke] FAIL stub active must be False default")
        return False
    print(f"[smoke] OK propose_skill_yaml_stub schema valid (11 keys)")
    return True


def _check_valid_providers() -> bool:
    import server  # type: ignore
    expected = {"openrouter", "ollama", "anthropic", "openai", "deepseek"}
    if server.VALID_PROVIDERS != expected:
        print(f"[smoke] FAIL VALID_PROVIDERS drift")
        return False
    print("[smoke] OK VALID_PROVIDERS 5 canonical")
    return True


def main() -> int:
    print("=== hermes-skills smoke (F.5.2) ===")
    _check_fastmcp()
    checks = [
        _check_server_imports,
        _check_tools,
        _check_path_traversal_rejected,
        _check_list_skills_pc,
        _check_propose_stub,
        _check_valid_providers,
    ]
    all_ok = True
    for c in checks:
        all_ok = c() and all_ok
    print("=== %s ===" % ("PASS" if all_ok else "FAIL"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
