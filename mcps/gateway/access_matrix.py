"""H7 B11 HARDENING — Access matrix per-requester allowlist (under shared bearer).

Mitigation: caller compromised só escalates pra MCPs explicitamente allowed.
Bearer auth (OAuth secret) continua sendo primeira camada. Access matrix é
defense-in-depth segunda camada.

Config: mcps/gateway/access_matrix.json (loaded once at startup, hot-reload
manual via gateway restart). JSON format:
    {
      "version": 1,
      "default_policy": "deny" | "allow",
      "rules": {
        "<requester>": {"allow": ["<mcp_name>", "*"]}
      }
    }

Decisão:
- requester desconhecido + default_policy="deny" → DENIED
- requester desconhecido + default_policy="allow" → ALLOWED
- requester conhecido + allow contém "*" → ALLOWED
- requester conhecido + allow contém server_name → ALLOWED
- requester conhecido + server_name NÃO em allow → DENIED
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes.gateway.access_matrix")

_DEFAULT_MATRIX_PATH = Path(__file__).parent / "access_matrix.json"


class AccessMatrix:
    """Per-requester allowlist enforcement."""

    def __init__(self, default_policy: str = "deny", rules: Optional[dict] = None) -> None:
        self.default_policy = default_policy if default_policy in ("allow", "deny") else "deny"
        self.rules: dict[str, dict] = rules or {}

    def check(self, requester: str, server_name: str) -> tuple[bool, str]:
        """Returns (allowed, reason)."""
        if not requester:
            requester = "unknown"
        rule = self.rules.get(requester)
        if rule is None:
            if self.default_policy == "allow":
                return True, f"default_allow (requester={requester} unknown)"
            return False, f"default_deny (requester={requester} unknown, target={server_name})"
        allow_list = rule.get("allow", [])
        if "*" in allow_list:
            return True, f"wildcard_allow (requester={requester})"
        if server_name in allow_list:
            return True, f"explicit_allow (requester={requester}, target={server_name})"
        return False, f"not_in_allowlist (requester={requester}, target={server_name})"


def load_matrix(path: Optional[Path] = None) -> AccessMatrix:
    """Load access matrix from JSON. Missing/invalid → AccessMatrix(default_policy=allow) (fail-open)."""
    path = path or _DEFAULT_MATRIX_PATH
    if not path.exists():
        logger.warning("access_matrix.json not found at %s — fail-open (default_policy=allow)", path)
        return AccessMatrix(default_policy="allow")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.error("access_matrix.json parse failed: %s — fail-open", exc)
        return AccessMatrix(default_policy="allow")
    default_policy = data.get("default_policy", "deny")
    rules = data.get("rules", {})
    if not isinstance(rules, dict):
        rules = {}
    return AccessMatrix(default_policy=default_policy, rules=rules)
