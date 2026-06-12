"""hermes-llm smoke test — F.5.7 fixture-safe.

Verifica:
1. fastmcp importável (stub fallback PC)
2. server.py imports + mcp instance
3. 6 tools registered
4. _validate_task_type rejeita invalid
5. _validate_call_id rejeita unsafe chars
6. _sanitize redacts NIM key prefix + sensitive dict keys
7. RpmLimiter 38/40 cap funciona (40 rapid calls → 38 True + 2 False)
8. route_decide retorna chain per task_type policy
9. list_available_models lista catalog routing_matrix
10. FALLBACK_TRIGGERS cobre 429/5xx/timeout/auth/empty

NÃO chama NIM real (sem HERMES_NIM_API_KEY → adapter retorna 503 graceful).
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

_SELF_DIR = Path(__file__).resolve().parent
if str(_SELF_DIR) not in sys.path:
    sys.path.insert(0, str(_SELF_DIR))


def _load_server_module():
    """Load mcps/hermes-llm/server.py explicit path — avoids name collision
    with repo root server.py (Hermes Command Center)."""
    if "hermes_llm_server" in sys.modules:
        return sys.modules["hermes_llm_server"]
    spec = importlib.util.spec_from_file_location(
        "hermes_llm_server", _SELF_DIR / "server.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_llm_server"] = mod
    spec.loader.exec_module(mod)
    return mod


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
    try:
        server = _load_server_module()
        _ = server
    except SystemExit as exc:
        print(f"[smoke] SKIP server import → SystemExit ({exc})")
        return False
    except Exception as exc:
        print(f"[smoke] FAIL server import: {exc}")
        return False
    assert server.MCP_NAME == "hermes-llm"
    assert server.MCP_VERSION.startswith("0.1.0-f5.7")
    print(f"[smoke] OK server import (name={server.MCP_NAME} v={server.MCP_VERSION})")
    return True


def _check_tools() -> bool:
    server = _load_server_module()
    expected = {
        "route", "list_available_models", "get_provider_status",
        "track_cost", "set_routing_policy", "get_call_history",
    }
    found = {n for n in expected if callable(getattr(server, n, None))}
    missing = expected - found
    if missing:
        print(f"[smoke] FAIL tools missing: {sorted(missing)}")
        return False
    print(f"[smoke] OK 6 tools registered")
    return True


def _check_validation() -> bool:
    server = _load_server_module()
    bad_tasks = ["", "invalid_task", None]
    for t in bad_tasks:
        if server._validate_task_type(t) is None:  # type: ignore
            print(f"[smoke] FAIL invalid task_type accepted: {t!r}")
            return False
    if server._validate_task_type("reasoning") is not None:
        print("[smoke] FAIL valid task_type rejected")
        return False

    bad_ids = ["", "x" * 200, "null\x00byte", "newline\nhere", None]
    for cid in bad_ids:
        if server._validate_call_id(cid) is None:  # type: ignore
            print(f"[smoke] FAIL bad call_id accepted: {cid!r}")
            return False
    if server._validate_call_id("call-uuid-abc123") is not None:
        print("[smoke] FAIL valid call_id rejected")
        return False
    print("[smoke] OK validators reject bad inputs + accept good")
    return True


def _check_sanitize() -> bool:
    server = _load_server_module()
    payload = {
        "prompt": "hello world",
        "api_key": "nvapi-secret-leak-123",
        "nested": {"NVIDIA_API_KEY": "nvapi-other", "safe": "value"},
        "openrouter_api_key": "sk-xxxxx",
        "raw_token_string": "nvapi-raw-string-12345",
    }
    out = server._sanitize(payload)
    if out["api_key"] != "[REDACTED]":
        print(f"[smoke] FAIL api_key not redacted: {out}")
        return False
    if out["nested"]["NVIDIA_API_KEY"] != "[REDACTED]":
        print(f"[smoke] FAIL nested NVIDIA_API_KEY not redacted: {out}")
        return False
    if out["openrouter_api_key"] != "[REDACTED]":
        print(f"[smoke] FAIL openrouter_api_key not redacted: {out}")
        return False
    if out["raw_token_string"] != "[REDACTED]":
        print(f"[smoke] FAIL nvapi- prefix string not redacted: {out}")
        return False
    if out["prompt"] != "hello world":
        print(f"[smoke] FAIL benign field altered: {out}")
        return False
    print("[smoke] OK _sanitize redacts NIM key + nested + nvapi- prefix")
    return True


def _check_rpm_limiter() -> bool:
    from _policy import RpmLimiter  # type: ignore
    lim = RpmLimiter(max_rpm=38, window_seconds=60)
    passes = 0
    blocks = 0
    for _ in range(40):
        if lim.can_proceed():
            passes += 1
        else:
            blocks += 1
    if passes != 38 or blocks != 2:
        print(f"[smoke] FAIL RpmLimiter 38/40 expected 38pass+2block got pass={passes} block={blocks}")
        return False
    if lim.remaining() != 0:
        print(f"[smoke] FAIL remaining expected 0 got {lim.remaining()}")
        return False
    print(f"[smoke] OK RpmLimiter 38 pass + 2 block (margin sobre 40 cap)")
    return True


def _check_route_decide() -> bool:
    from _policy import route_decide  # type: ignore
    chain = route_decide("reasoning", policy="balanced")
    if not chain:
        print("[smoke] FAIL route_decide reasoning balanced empty")
        return False
    providers = [p for _, p, _ in chain]
    if "openrouter" in providers:
        print(f"[smoke] FAIL balanced should deny openrouter but chain has it: {providers}")
        return False

    cost_chain = route_decide("reasoning", policy="cost-optimize")
    cost_providers = [p for _, p, _ in cost_chain]
    if "nim_credit" in cost_providers or "openrouter" in cost_providers:
        print(f"[smoke] FAIL cost-optimize should deny nim_credit+openrouter: {cost_providers}")
        return False

    forced = route_decide("reasoning", force_provider="nim_free")
    if len(forced) != 1 or forced[0][1] != "nim_free":
        print(f"[smoke] FAIL force_provider should yield single tier got {forced}")
        return False

    print(f"[smoke] OK route_decide balanced={len(chain)} tiers, cost-optimize filtered, force_provider=single")
    return True


def _check_list_available_models() -> bool:
    server = _load_server_module()
    res = asyncio.run(server.list_available_models())
    if not res.get("ok"):
        print(f"[smoke] FAIL list_available_models: {res}")
        return False
    if res["count"] < 5:
        print(f"[smoke] FAIL count too low {res['count']}")
        return False
    res_filt = asyncio.run(server.list_available_models(provider="ollama_pc"))
    if any(m["provider"] != "ollama_pc" for m in res_filt["models"]):
        print(f"[smoke] FAIL provider filter leaked")
        return False
    print(f"[smoke] OK list_available_models count={res['count']} filter ollama_pc count={res_filt['count']}")
    return True


def _check_fallback_triggers() -> bool:
    from _policy import FALLBACK_TRIGGERS, should_fallback  # type: ignore
    cases = [
        ({"ok": False, "status_code": 429}, "rate_limit"),
        ({"ok": False, "status_code": 503}, "server_error"),
        ({"ok": False, "error": "timeout"}, "timeout"),
        ({"ok": False, "status_code": 401}, "auth_fail"),
        ({"ok": True, "response": "hi"}, "empty_response"),
        ({"ok": False, "error": "model_not_found"}, "model_unavailable"),
    ]
    for resp, expected_trigger in cases:
        fn = FALLBACK_TRIGGERS[expected_trigger]
        if not fn(resp):
            print(f"[smoke] FAIL trigger {expected_trigger} did NOT fire on {resp}")
            return False

    abort_resp = {"ok": False, "status_code": 400}
    fb, trig = should_fallback(abort_resp)
    if fb or trig != "client_error":
        print(f"[smoke] FAIL 400 should abort no fallback got fb={fb} trig={trig}")
        return False
    print("[smoke] OK FALLBACK_TRIGGERS 6 + ABORT 400")
    return True


def main() -> int:
    print("=== hermes-llm smoke (F.5.7) ===")
    _check_fastmcp()
    checks = [
        _check_server_imports,
        _check_tools,
        _check_validation,
        _check_sanitize,
        _check_rpm_limiter,
        _check_route_decide,
        _check_list_available_models,
        _check_fallback_triggers,
    ]
    all_ok = True
    for c in checks:
        all_ok = c() and all_ok
    print("=== %s ===" % ("PASS" if all_ok else "FAIL"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
