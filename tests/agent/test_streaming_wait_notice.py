from types import SimpleNamespace

from agent import chat_completion_helpers as h


def _streaming_call(*, api_mode: str = "chat_completions"):
    notices: list[str] = []
    touches: list[str] = []
    call = h._StreamingCall.__new__(h._StreamingCall)
    call.agent = SimpleNamespace(
        api_mode=api_mode,
        _emit_wait_notice=notices.append,
        _touch_activity=touches.append,
    )
    call.api_kwargs = {"model": "test-model"}
    call._stream_stale_timeout = 180.0
    call._mon = SimpleNamespace(last_heartbeat=1000.0, wait_notice_started_ts=None)
    setattr(
        call,
        "request_identity",
        h._provider_wait_identity(
            request_class="background_review",
            session_id="20260908_162215_70dd49",
            attempt=2,
        ),
    )
    return call, notices, touches


def test_streaming_wait_notice_includes_request_identity_and_recovery():
    call, notices, _ = _streaming_call()

    call._heartbeat(60)

    assert "background review request in session …70dd49 — attempt 2" in notices[0]
    assert "no stream output for 60s" in notices[0]
    assert "auto-reconnect at 180s" in notices[0]


def test_streaming_call_captures_scoped_request_identity():
    agent = SimpleNamespace(session_id="fallback-session", platform="cli")

    with h.provider_request_context(
        request_class="delegation",
        session_id="20260908_162215_70dd49",
        attempt=4,
    ):
        call = h._StreamingCall(agent, {"model": "test-model"}, None)

    assert getattr(call, "request_identity", None) == (
        "delegation request in session …70dd49 — attempt 4"
    )


def test_outer_codex_stream_heartbeat_does_not_overwrite_inner_watchdog_notice():
    call, notices, touches = _streaming_call(api_mode="codex_responses")

    call._heartbeat(60)

    assert notices == []
    assert touches == ["waiting for Codex provider response (60s)"]
