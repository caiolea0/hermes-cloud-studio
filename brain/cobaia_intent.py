"""F.7 C2 — Brain intent handler: cobaia_warmup_next_action.

Deterministic fast-path (task_type=None) — NO LLM call.
Returns action based on current phase + day from context.

Persists brain_decisions row with requester='brain-f7-cobaia' for observability.

Called via handle_intent() fast-path (same pattern as route_skill_run F.9.2).
"""
from __future__ import annotations

import random
from typing import Any

# Actions per phase
_LURKING_ACTIONS = ["engagement_like_post", "engagement_comment_post"]
_RAMP_ACTIONS = ["engagement_like_post", "engagement_comment_post", "connection_request"]
_NORMAL_ACTIONS = [
    "engagement_like_post",
    "engagement_comment_post",
    "connection_request",
    "profile_view",
]

_SKILL_MAP = {
    "engagement_like_post": "linkedin-engagement",
    "engagement_comment_post": "linkedin-engagement",
    "connection_request": "linkedin-connection-sender",
    "profile_view": "linkedin-profile-researcher",
}


def decide_cobaia_warmup_action(context: dict[str, Any]) -> dict[str, Any]:
    """Deterministic action selector for cobaia warmup phase.

    Args:
        context: {current_day, phase, caps_today, today_metrics, errors_24h}

    Returns:
        {action, skill_name, args, requires_confirm, low_conf}
    """
    phase = context.get("phase", "lurking")
    current_day = int(context.get("current_day", 0))
    caps = context.get("caps_today", {})
    metrics = context.get("today_metrics", {})

    # Check remaining caps
    connects_remaining = max(0, caps.get("connects", 0) - metrics.get("connects_sent", 0))
    engagements_remaining = max(0, caps.get("engagements", 0) - metrics.get("engagements_count", 0))
    views_remaining = max(0, caps.get("views", 0) - metrics.get("views_count", 0))

    if phase == "lurking":
        # Lurking: only engagement (comments/likes) — connects always 0
        if engagements_remaining > 0:
            action = random.choice(_LURKING_ACTIONS)
        else:
            return _no_action("lurking_cap_reached", current_day)

    elif phase == "ramp":
        candidates = []
        if engagements_remaining > 0:
            candidates.extend(["engagement_like_post", "engagement_comment_post"])
        if connects_remaining > 0:
            candidates.append("connection_request")
        if not candidates:
            return _no_action("ramp_caps_reached", current_day)
        action = random.choice(candidates)

    else:  # normal
        candidates = []
        if engagements_remaining > 0:
            candidates.extend(["engagement_like_post", "engagement_comment_post"])
        if connects_remaining > 0:
            candidates.append("connection_request")
        if views_remaining > 0:
            candidates.append("profile_view")
        if not candidates:
            return _no_action("normal_caps_reached", current_day)
        action = random.choice(candidates)

    skill_name = _SKILL_MAP.get(action, "linkedin-engagement")
    return {
        "action": action,
        "skill_name": skill_name,
        "args": {"phase": phase, "day": current_day, "stub": True},
        "requires_confirm": False,
        "low_conf": False,
        "status": "action_selected",
    }


def _no_action(reason: str, current_day: int) -> dict[str, Any]:
    return {
        "action": None,
        "skill_name": None,
        "args": {},
        "requires_confirm": False,
        "low_conf": False,
        "status": f"no_action:{reason}",
        "current_day": current_day,
    }
