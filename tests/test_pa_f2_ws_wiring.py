"""PA-F2 — WS wiring: event_type standardize + orphan emit/listener fixes.

Tests (6):
1. brain.py WS broadcast uses event_type (not type)
2. brain.py SSE stream keeps type (no regression)
3. cobaia.queue_updated emitted on enroll path
4. cobaia.queue_updated emitted on advance path (orchestrator)
5. sequence.enrolled has frontend listener (app.js grep)
6. No orphan WS listener/emit pairs (cross-check emit↔listen)
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# 1. brain.py WS broadcast uses event_type
# ---------------------------------------------------------------------------

def test_brain_ws_broadcast_uses_event_type():
    """_emit_ws_event must pass event_type key, not type, to ws_manager.broadcast."""
    src = (ROOT / "api" / "brain.py").read_text(encoding="utf-8")
    # The WS broadcast inside _emit_ws_event must use event_type key
    assert '"event_type": event_type' in src, \
        "_emit_ws_event must broadcast with event_type key"
    # Post-SSE WS telemetry broadcast must also use event_type
    assert '"event_type": "brain.ai_query_used"' in src, \
        "post-SSE WS broadcast must use event_type key"
    # Must NOT have the old pattern: {"type": event_type in _emit_ws_event context
    # (still allowed in SSE yields as 'type': 'error'/'final' etc.)
    assert '{"type": event_type' not in src, \
        "_emit_ws_event must not broadcast with type key"


# ---------------------------------------------------------------------------
# 2. brain.py SSE stream keeps type (no regression)
# ---------------------------------------------------------------------------

def test_brain_sse_stream_keeps_type():
    """SSE yields in stream_decide must still use type key (not event_type)."""
    src = (ROOT / "api" / "brain.py").read_text(encoding="utf-8")
    # SSE error yield uses type
    assert "'type': 'error'" in src, "SSE error yield must keep type key"
    # SSE last_event check uses type=='final'
    assert "last_event.get(\"type\") == \"final\"" in src or \
           "last_event.get('type') == 'final'" in src, \
        "last_event type check must still use type key for SSE parsing"


# ---------------------------------------------------------------------------
# 3. cobaia.queue_updated emitted on enroll path
# ---------------------------------------------------------------------------

def test_cobaia_queue_updated_emitted_on_enroll():
    """sequences.py enroll endpoint must broadcast cobaia.queue_updated."""
    src = (ROOT / "api" / "sequences.py").read_text(encoding="utf-8")
    assert '"cobaia.queue_updated"' in src, \
        "sequences.py enroll must broadcast cobaia.queue_updated"
    # Confirm the reason field is included
    assert '"reason": "enroll"' in src, \
        "cobaia.queue_updated broadcast must include reason=enroll"


# ---------------------------------------------------------------------------
# 4. cobaia.queue_updated emitted on advance + skip paths
# ---------------------------------------------------------------------------

def test_cobaia_queue_updated_emitted_on_advance_and_skip():
    """orchestrator._advance_enrollment and cobaia skip endpoint must emit cobaia.queue_updated."""
    orch = (ROOT / "daemon" / "orchestrator.py").read_text(encoding="utf-8")
    assert '"cobaia.queue_updated"' in orch, \
        "orchestrator._advance_enrollment must broadcast cobaia.queue_updated"
    assert '"reason": "advance"' in orch, \
        "advance broadcast must include reason=advance"

    cobaia = (ROOT / "api" / "cobaia.py").read_text(encoding="utf-8")
    # skip endpoint must call _ws_emit with cobaia.queue_updated
    assert '"cobaia.queue_updated"' in cobaia, \
        "cobaia skip endpoint must emit cobaia.queue_updated"
    assert '"reason": "skip"' in cobaia, \
        "cobaia.queue_updated skip emit must include reason=skip"


# ---------------------------------------------------------------------------
# 5. sequence.enrolled has frontend listener
# ---------------------------------------------------------------------------

def test_sequence_enrolled_has_frontend_listener():
    """app.js must handle sequence.enrolled event_type (toast + canvas refresh)."""
    src = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    assert "sequence.enrolled" in src, \
        "app.js must contain sequence.enrolled handler"
    # Must call hermesToast on enrolled
    assert "hermesToast" in src, "app.js must call hermesToast for sequence.enrolled"
    # SequenceCanvas.refresh call
    assert "SequenceCanvas" in src and "refresh" in src, \
        "app.js must attempt SequenceCanvas.refresh on sequence.enrolled"


# ---------------------------------------------------------------------------
# 6. No orphan WS pairs (emit↔listen balanced)
# ---------------------------------------------------------------------------

def test_no_orphan_ws_pairs():
    """Every WS listener has a corresponding backend emit, and vice versa."""
    # Collect backend emits (event_type strings)
    backend_files = list((ROOT / "api").glob("*.py")) + \
                    list((ROOT / "daemon").glob("*.py")) + \
                    list((ROOT / "core").glob("*.py")) + \
                    [ROOT / "server.py"]

    emit_events: set[str] = set()
    for f in backend_files:
        try:
            src = f.read_text(encoding="utf-8")
        except Exception:
            continue
        # Match "event_type": "some.event" and "cobaia.queue_updated" etc.
        for m in re.findall(r'"event_type"\s*:\s*"([^"]+)"', src):
            emit_events.add(m)
        # Also match _ws_emit("some.event", ...) pattern
        for m in re.findall(r'_ws_emit\s*\(\s*"([^"]+)"', src):
            emit_events.add(m)

    # Collect frontend listeners from components
    frontend_files = list((ROOT / "dashboard" / "components").glob("*.js")) + \
                     [ROOT / "dashboard" / "app.js"]
    listen_events: set[str] = set()
    for f in frontend_files:
        try:
            src = f.read_text(encoding="utf-8")
        except Exception:
            continue
        # event.event_type === 'some.event' or === "some.event"
        for m in re.findall(r"event(?:_type|\.event_type)?\s*===?\s*['\"]([^'\"]+)['\"]", src):
            if "." in m:  # only dot-notation events (skip 'sync', 'error', etc.)
                listen_events.add(m)
        # Also: event_type === 'cobaia.queue_updated'
        for m in re.findall(r"['\"]([a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*)['\"]", src):
            if m in {  # known listener event names
                "cobaia.queue_updated", "sentry.issue_new", "sequence.enrolled",
                "cobaia.state_changed", "cobaia.daily_check_done", "cobaia.auto_paused",
                "cobaia.session_dispatched", "cobaia.session_error",
            }:
                listen_events.add(m)

    # Critical pairs that must be balanced
    critical_pairs = {
        "cobaia.queue_updated": ("emit", "listen"),
        "sentry.issue_new": ("emit", "listen"),
        "sequence.enrolled": ("emit", "listen"),
    }

    for event_name, (_e, _l) in critical_pairs.items():
        assert event_name in emit_events, \
            f"No backend emit found for {event_name}"
        assert event_name in listen_events, \
            f"No frontend listener found for {event_name}"


# ---------------------------------------------------------------------------
# 7. cobaia._ws_emit passes dict (not json string) to broadcast
# ---------------------------------------------------------------------------

def test_cobaia_ws_emit_passes_dict_not_string():
    """cobaia.py _ws_emit must pass dict to ws_manager.broadcast, not json.dumps string."""
    src = (ROOT / "api" / "cobaia.py").read_text(encoding="utf-8")
    # Should NOT have json.dumps in _ws_emit
    # Find the _ws_emit function body
    ws_emit_match = re.search(
        r"def _ws_emit.*?(?=\ndef |\Z)", src, re.DOTALL
    )
    assert ws_emit_match, "_ws_emit function not found in cobaia.py"
    ws_emit_body = ws_emit_match.group()
    assert "json.dumps" not in ws_emit_body, \
        "_ws_emit must not pass json.dumps (double-serialization bug) to broadcast"
    assert '"event_type"' in ws_emit_body or "'event_type'" in ws_emit_body, \
        "_ws_emit must use event_type key"
