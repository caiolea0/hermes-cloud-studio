"""hermes-prospects smoke test — F.5.2.

Verifica:
1. fastmcp importável (skip se ausente)
2. server.py importa + mcp instance
3. 7 tools registered
4. score_lead determinístico — input fixo → output fixo (NUNCA delega)
5. score_lead idempotente (mesma entrada = mesmo output cross-runs)
6. VALID_STAGES contém 6 stages canonical

Smoke isolado: NÃO faz query DB real (mocks via attribute checks).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _stub_fastmcp_if_missing() -> str:
    """Inject minimal FastMCP stub se ausente — permite smoke determinístico
    local sem ter fastmcp instalado. Tools real prod VM usa fastmcp real.

    Returns: "real" | "stub"
    """
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

            def run(self, **kw):  # noqa: ARG002
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
    assert server.MCP_NAME == "hermes-prospects"
    assert server.MCP_VERSION.startswith("0.1.0-f5.2")
    print(f"[smoke] OK server import (name={server.MCP_NAME} v={server.MCP_VERSION})")
    return True


def _check_tools() -> bool:
    import server  # type: ignore
    expected = {
        "search_prospects", "score_lead", "mark_converted",
        "get_campaign_stats", "enrich_pipeline", "list_top_scored",
        "get_by_status",
    }
    found = {n for n in expected if callable(getattr(server, n, None))}
    missing = expected - found
    if missing:
        print(f"[smoke] FAIL tools missing: {sorted(missing)}")
        return False
    print(f"[smoke] OK 7 tools registered")
    return True


def _check_score_lead_determinism() -> bool:
    import server  # type: ignore
    fixture = {
        "name": "Restaurante Cuiabá Burger",
        "category": "Restaurant",
        "has_website": False,
        "google_rating": 4.5,
        "google_reviews": 50,
        "phone": "+5565999999999",
        "email": "contato@cuiababurger.com",
        "social_instagram": "@cuiababurger",
    }
    r1 = asyncio.run(server.score_lead(fixture))
    r2 = asyncio.run(server.score_lead(fixture))
    if r1["score"] != r2["score"]:
        print(f"[smoke] FAIL score_lead not deterministic: {r1['score']} vs {r2['score']}")
        return False
    # Expected: 50 + 25 (no_website) + 10 (restaurant) + 5 (rating) + 5 (reviews)
    # + 2 (phone) + 3 (email) + 3 (instagram) = 103 → clamped 100
    expected_score = 100.0
    if r1["score"] != expected_score:
        print(f"[smoke] FAIL score_lead expected {expected_score} got {r1['score']}")
        return False
    # No website + minimal categoria fora valuable
    sparse = {"name": "Tech Co", "has_website": True, "category": "tech"}
    r3 = asyncio.run(server.score_lead(sparse))
    # 50 - 5 (has_website baseline) = 45
    if r3["score"] != 45.0:
        print(f"[smoke] FAIL sparse score expected 45 got {r3['score']}")
        return False
    print(f"[smoke] OK score_lead deterministic (full=100, sparse=45)")
    return True


def _check_valid_stages() -> bool:
    import server  # type: ignore
    expected = {"discovered", "qualified", "audited", "contacted", "converted", "dead"}
    if server.VALID_STAGES != expected:
        print(f"[smoke] FAIL VALID_STAGES drift: {server.VALID_STAGES ^ expected}")
        return False
    print("[smoke] OK VALID_STAGES contains 6 canonical")
    return True


def main() -> int:
    print("=== hermes-prospects smoke (F.5.2) ===")
    if not _check_fastmcp():
        return 0  # graceful PC skip
    checks = [
        _check_server_imports,
        _check_tools,
        _check_score_lead_determinism,
        _check_valid_stages,
    ]
    all_ok = True
    for c in checks:
        all_ok = c() and all_ok
    print("=== %s ===" % ("PASS" if all_ok else "FAIL"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
