"""Wait status describes request-local silence, never active generation."""

from types import SimpleNamespace
import threading

import pytest

from agent import chat_completion_helpers as h
from agent.chat_completion_nonstream import _NonStreamRequest
from agent.chat_completion_wait_notice import WaitNoticeState


def _request():
    request = _NonStreamRequest.__new__(_NonStreamRequest)
    notices, touches = [], []
    request.agent = SimpleNamespace(
        _emit_wait_notice=notices.append,
        _touch_activity=touches.append,
        _interrupt_requested=False,
        _codex_stream_last_event_ts=9999.0,  # Another request cannot hide this one's stall.
    )
    request.api_kwargs = {"model": "test-model"}
    request.call_start = 1000.0
    request.wd = SimpleNamespace(
        codex=True, stale_timeout=600.0, ttfb_enabled=True, ttfb_timeout=120.0,
        idle_enabled=True, idle_timeout=180.0, idle_requires_progress=False,
    )
    request.codex_watchdog_state = SimpleNamespace(
        lock=threading.Lock(), last_event_ts=None, last_progress_ts=None,
        retry_started_ts=None,
    )
    request.wait_notice_started_ts = None
    request.wait_notice = WaitNoticeState()
    request.result = {"error": None, "response": None}
    return request, notices, touches


def test_provider_wait_identity_includes_request_class_session_and_attempt():
    assert h._provider_wait_identity(
        request_class="delegation",
        session_id="20260908_162215_70dd49",
        attempt=2,
    ) == "delegation request in session …70dd49 — attempt 2"


def test_provider_request_context_is_scoped_and_restored():
    agent = SimpleNamespace(session_id="fallback-session", platform="cli")
    assert h._current_provider_wait_identity(agent) == (
        "foreground request in session …ession — attempt 1"
    )

    with h.provider_request_context(
        request_class="compression",
        session_id="20260908_162215_70dd49",
        attempt=4,
    ):
        assert h._current_provider_wait_identity(agent) == (
            "compression request in session …70dd49 — attempt 4"
        )

    assert h._current_provider_wait_identity(agent) == (
        "foreground request in session …ession — attempt 1"
    )


def test_nonstream_request_captures_scoped_identity(monkeypatch):
    watchdogs = SimpleNamespace(
        codex=False,
        stale_timeout=600.0,
        ttfb_enabled=False,
        ttfb_timeout=120.0,
        idle_enabled=False,
        idle_timeout=180.0,
        idle_requires_progress=False,
    )
    monkeypatch.setattr(h, "_resolve_nonstream_watchdogs", lambda *_args: watchdogs)
    agent = SimpleNamespace(
        api_mode="chat_completions",
        session_id="fallback-session",
        platform="cli",
    )

    with h.provider_request_context(
        request_class="delegation",
        session_id="20260908_162215_70dd49",
        attempt=5,
    ):
        request = _NonStreamRequest(agent, {"model": "test-model"})

    assert getattr(request, "request_identity", None) == (
        "delegation request in session …70dd49 — attempt 5"
    )


def test_nonstream_wait_notice_includes_scoped_request_identity():
    request, notices, _ = _request()
    setattr(
        request,
        "request_identity",
        h._provider_wait_identity(
            request_class="compression",
            session_id="20260908_162215_70dd49",
            attempt=3,
        ),
    )

    request._emit_wait_notice(60.0)

    assert "compression request in session …70dd49 — attempt 3" in notices[0]
    assert "60s with no response yet" in notices[0]
    assert "auto-reconnect at 120s" in notices[0]


@pytest.mark.parametrize(
    "event,progress,retry,expected",
    [
        (59.0, 59.0, None, None),  # Reasoning/text/tool arguments still arriving.
        (59.0, None, None, None),  # Lifecycle traffic is not transport silence either.
        (0.0, 0.0, None, "provider stream active; 60s without stream events"),
        (0.0, None, None, "provider stream active; 60s without stream events"),
        (1.0, None, None, None),  # 59 seconds of silence is still quiet.
        (None, None, None, "60s waiting for the first provider event"),
        (10.0, 10.0, 59.0, None),  # Internal reconnect gets a fresh first-event wait.
        (0.0, 0.0, 0.0, "60s waiting for the first provider event after reconnect"),
        (0.0, 0.0, 1.0, None),
    ],
)
def test_wait_notice_tracks_current_attempt_silence(event, progress, retry, expected):
    request, notices, touches = _request()
    state = request.codex_watchdog_state
    state.last_event_ts = None if event is None else request.call_start + event
    state.last_progress_ts = None if progress is None else request.call_start + progress
    state.retry_started_ts = None if retry is None else request.call_start + retry
    request._emit_wait_notice(30.0)
    request._emit_wait_notice(59.0)
    assert notices == []
    assert touches
    if event is None and retry is None:
        assert "receiving" not in touches[-1]
    request._emit_wait_notice(60.0)
    if expected is None:
        assert notices == []
        assert touches, "Quiet heartbeat must survive suppressing a visible warning"
    else:
        assert len(notices) == 1
        assert expected in notices[0]
        assert "auto-reconnect:" in notices[0]


def test_resumed_events_clear_only_this_requests_wait_notice(monkeypatch):
    request, notices, _ = _request()
    sentinel = object()
    ticks = [0]

    class Worker:
        def __init__(self, **kwargs):
            pass

        def start(self):
            pass

        def is_alive(self):
            return ticks[0] < 204

        def join(self, timeout):
            ticks[0] += 1
            if ticks[0] >= 201:
                request.codex_watchdog_state.last_event_ts = 1000.0 + ticks[0] * 0.3
            if ticks[0] == 204:
                request.result["response"] = sentinel

    monkeypatch.setattr(h.threading, "Thread", Worker)
    monkeypatch.setattr(h.time, "time", lambda: 1000.0 + ticks[0] * 0.3)
    assert request.run() is sentinel
    assert len(notices) == 2
    assert "waiting for the first provider event" in notices[0]
    # Nonempty thinking.delta payloads enter TUI reasoning history.
    assert notices[1] == ""
