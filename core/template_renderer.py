"""Template renderer — variable interpolation + spintax.

Spintax {spintax: a|b|c} is legitimate anti-spam message variation,
not fake data. random.choice here selects among author-written alternatives.
Exception listed in .claude/MCP-BANNED-PATTERNS.json under _exceptions.
"""
import random
import re

VALID_VARIABLES = {
    "firstName", "lastName", "fullName", "company", "jobTitle",
    "city", "industry", "customField1", "customField2", "senderName",
}

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")
_SPIN_RE = re.compile(r"\{spintax:\s*([^}]+)\}")


def render(template: str, data: dict) -> str:
    """Interpolate {{var}} and resolve {spintax: a|b|c}."""
    def _spin(m):
        options = [o.strip() for o in m.group(1).split("|")]
        return random.choice(options)  # spintax: author-written variation, not fake data

    def _var(m):
        key = m.group(1).strip()
        return str(data.get(key, f"[{key}]"))

    result = _SPIN_RE.sub(_spin, template)
    result = _VAR_RE.sub(_var, result)
    return result


def render_preview(template: str, data: dict) -> str:
    """Deterministic render for preview — spintax picks first option."""
    def _spin_first(m):
        options = [o.strip() for o in m.group(1).split("|")]
        return options[0] if options else ""

    def _var(m):
        key = m.group(1).strip()
        return str(data.get(key, f"[{key}]"))

    result = _SPIN_RE.sub(_spin_first, template)
    result = _VAR_RE.sub(_var, result)
    return result


def extract_variables(template: str) -> set:
    """Return set of {{var}} names used in template."""
    return set(_VAR_RE.findall(template))
