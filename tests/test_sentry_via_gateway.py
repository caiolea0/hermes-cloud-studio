"""H5 — Tests for core/sentry_via_gateway.py wrapper.

8 tests covering: gateway dispatch, fallback buffer, signatures, edge cases.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import core.sentry_via_gateway as svgw


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_buffer():
    svgw._LOCAL_BUFFER.clear()


# ---------------------------------------------------------------------------
# T1: capture_exception dispatches via gateway (fire-and-forget)
# ---------------------------------------------------------------------------

def test_capture_exception_dispatches_via_gateway():
    """Gateway dispatch is attempted when capture_exception called."""
    calls = []

    async def _fake_dispatch():
        calls.append("dispatched")

    with patch.object(asyncio, "get_running_loop") as mock_loop:
        mock_lp = MagicMock()
        mock_lp.create_task = lambda coro: calls.append("task_created") or asyncio.ensure_future(coro)
        mock_loop.return_value = mock_lp

        # Patch _gateway_dispatch_async to track calls
        original = svgw._gateway_dispatch_async
        invoked = []

        def _patched(tool, args, requester):
            invoked.append((tool, args["requester"]))

        svgw._gateway_dispatch_async = _patched
        try:
            exc = ValueError("test error")
            svgw.capture_exception(exc, requester="brain-f4")
            assert len(invoked) == 1
            assert invoked[0][0] == "capture_exception"
            assert invoked[0][1] == "brain-f4"
        finally:
            svgw._gateway_dispatch_async = original


# ---------------------------------------------------------------------------
# T2: capture_exception fallback buffers when gateway down + no SDK
# ---------------------------------------------------------------------------

def test_capture_exception_fallback_buffer_when_gateway_down():
    """Events buffered when gateway dispatch fails and sentry_sdk unavailable."""
    _clear_buffer()

    def _failing_dispatch(tool, args, requester):
        raise RuntimeError("gateway down")

    with patch.object(svgw, "_gateway_dispatch_async", _failing_dispatch):
        with patch.object(svgw, "_SENTRY_AVAILABLE", False):
            with patch.object(svgw, "_sentry_sdk", None):
                exc = IOError("disk error")
                svgw.capture_exception(exc, requester="brain-core")

    assert len(svgw._LOCAL_BUFFER) == 1
    assert svgw._LOCAL_BUFFER[0]["exc_type"] in ("IOError", "OSError")  # Python 3 alias
    assert svgw._LOCAL_BUFFER[0]["requester"] == "brain-core"
    _clear_buffer()


# ---------------------------------------------------------------------------
# T3: capture_message compatible signature (level + requester + **kwargs)
# ---------------------------------------------------------------------------

def test_capture_message_compatible_signature():
    """capture_message accepts level, requester, and extra kwargs without error."""
    dispatched = []

    def _fake_dispatch(tool, args, requester):
        dispatched.append((tool, args))

    with patch.object(svgw, "_gateway_dispatch_async", _fake_dispatch):
        with patch.object(svgw, "_SENTRY_AVAILABLE", False):
            # Should not raise even with unknown kwarg `extras=`
            svgw.capture_message(
                "cobaia auto-paused: manual",
                level="warning",
                requester="brain-f7-cobaia",
                extras={"reason": "manual"},  # non-standard kwarg — absorbed by **_kwargs
            )

    assert dispatched[0][0] == "capture_message"
    assert dispatched[0][1]["level"] == "warning"


# ---------------------------------------------------------------------------
# T4: add_breadcrumb fire-and-forget (no raise when SDK absent)
# ---------------------------------------------------------------------------

def test_add_breadcrumb_fire_and_forget():
    """add_breadcrumb never raises, works with or without sentry_sdk."""
    with patch.object(svgw, "_SENTRY_AVAILABLE", False):
        with patch.object(svgw, "_sentry_sdk", None):
            # Should not raise
            svgw.add_breadcrumb(
                category="cobaia",
                message="warmup day 1",
                level="info",
                data={"day": 1},
            )


# ---------------------------------------------------------------------------
# T5: buffer cap at 100 — excess dropped
# ---------------------------------------------------------------------------

def test_buffer_cap_100_drops_excess():
    """Buffer capped at _MAX_BUFFER — 101st event dropped."""
    _clear_buffer()

    def _noop(*a, **kw):
        pass

    with patch.object(svgw, "_gateway_dispatch_async", _noop):
        with patch.object(svgw, "_SENTRY_AVAILABLE", False):
            with patch.object(svgw, "_sentry_sdk", None):
                for i in range(105):
                    svgw.capture_exception(ValueError(f"err {i}"), requester="test")

    assert len(svgw._LOCAL_BUFFER) == 100  # capped
    _clear_buffer()


# ---------------------------------------------------------------------------
# T6: flush_buffer retries against sentry_sdk after recovery
# ---------------------------------------------------------------------------

def test_flush_buffer_retries_after_recovery():
    """flush_buffer replays buffered events via capture_message/capture_exception."""
    _clear_buffer()
    svgw._LOCAL_BUFFER.append({
        "type": "message",
        "message": "retry me",
        "level": "warning",
        "requester": "brain-f4",
    })

    captured = []

    def _fake_capture_message(msg, level="info", requester="unknown", **kw):
        captured.append(msg)

    with patch.object(svgw, "capture_message", _fake_capture_message):
        count = svgw.flush_buffer()

    assert count == 1
    assert captured[0] == "retry me"
    assert len(svgw._LOCAL_BUFFER) == 0


# ---------------------------------------------------------------------------
# T7: requester encoding propagated to gateway args
# ---------------------------------------------------------------------------

def test_requester_encoding_propagated():
    """requester value appears in gateway dispatch args."""
    dispatched = []

    def _capture(tool, args, requester):
        dispatched.append({"tool": tool, "args": args, "requester": requester})

    with patch.object(svgw, "_gateway_dispatch_async", _capture):
        with patch.object(svgw, "_SENTRY_AVAILABLE", False):
            svgw.capture_exception(RuntimeError("oops"), requester="brain-f9")

    assert dispatched[0]["requester"] == "brain-f9"
    assert dispatched[0]["args"]["requester"] == "brain-f9"


# ---------------------------------------------------------------------------
# T8: capture_exception(None) — captures current exception context (no-arg)
# ---------------------------------------------------------------------------

def test_capture_exception_no_arg_no_raise():
    """capture_exception() without exc= arg handles no active exception gracefully."""
    _clear_buffer()
    dispatched = []

    def _capture(tool, args, requester):
        dispatched.append(args)  # args dict has exception_type, requester, etc.

    with patch.object(svgw, "_gateway_dispatch_async", _capture):
        with patch.object(svgw, "_SENTRY_AVAILABLE", False):
            with patch.object(svgw, "_sentry_sdk", None):
                # Outside except block — sys.exc_info()[1] is None
                svgw.capture_exception(requester="brain-core")

    assert len(dispatched) >= 1, f"_capture not called — dispatched={dispatched}"
    assert dispatched[0]["exception_type"] == "UnknownException"
    assert dispatched[0]["requester"] == "brain-core"
    _clear_buffer()
