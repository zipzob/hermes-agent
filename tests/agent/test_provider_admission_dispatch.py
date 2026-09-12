import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from agent import auxiliary_client
from agent import chat_completion_helpers as helpers
from agent.chat_completion_nonstream import _NonStreamRequest
from agent.turn_api_call import perform_api_call
from gateway.session_context import scoped_current_session_id
from hermes_cli.provider_admission import (
    ProviderAdmissionRequest,
    provider_admission,
    provider_admission_snapshot,
)


@pytest.fixture(autouse=True)
def enable_admission(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "provider_admission:\n  max_in_flight: 1\n", encoding="utf-8"
    )


def test_foreground_codex_dispatch_holds_cross_process_admission(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    watchdogs = SimpleNamespace(
        codex=False,
        stale_timeout=60.0,
        ttfb_enabled=False,
        ttfb_timeout=60.0,
        idle_enabled=False,
        idle_timeout=60.0,
        idle_requires_progress=False,
        est_tokens=0,
    )
    monkeypatch.setattr(helpers, "_resolve_nonstream_watchdogs", lambda *_: watchdogs)

    agent = SimpleNamespace(
        api_mode="codex_responses",
        provider="openai-codex",
        model="gpt-5.6-sol",
        api_key="not-a-jwt",
        session_id="session-foreground",
        platform="cli",
        _interrupt_requested=False,
        _touch_activity=lambda *_: None,
        _emit_wait_notice=lambda *_: None,
        _client_log_context=lambda: "test",
    )

    def dispatch(_agent, _kwargs, *, make_client):
        del make_client
        entries = provider_admission_snapshot(registry_home=tmp_path)
        assert len(entries) == 1, "physical Codex dispatch started without admission"
        assert entries[0]["state"] == "active"
        assert entries[0]["request_class"] == "foreground"
        assert entries[0]["session_id"] == "session-foreground"
        return object()

    monkeypatch.setattr(helpers, "_dispatch_nonstreaming_api_request", dispatch)

    response = _NonStreamRequest(agent, {"model": "gpt-5.6-sol"}).run()

    assert response is not None
    assert provider_admission_snapshot(registry_home=tmp_path) == []


def test_nonstream_codex_dispatch_persists_exact_physical_attempt(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    watchdogs = SimpleNamespace(
        codex=False,
        stale_timeout=60.0,
        ttfb_enabled=False,
        ttfb_timeout=60.0,
        idle_enabled=False,
        idle_timeout=60.0,
        idle_requires_progress=False,
        est_tokens=0,
    )
    monkeypatch.setattr(helpers, "_resolve_nonstream_watchdogs", lambda *_: watchdogs)
    agent = SimpleNamespace(
        api_mode="codex_responses",
        provider="openai-codex",
        model="gpt-5.6-sol",
        api_key="not-a-jwt",
        session_id="session-attempt",
        platform="cli",
        _interrupt_requested=False,
        _touch_activity=lambda *_: None,
        _emit_wait_notice=lambda *_: None,
        _client_log_context=lambda: "test",
    )

    def dispatch(_agent, _kwargs, *, make_client):
        del make_client
        entries = provider_admission_snapshot(registry_home=tmp_path)
        assert entries[0]["metadata"] == {"attempt": 4}
        return object()

    monkeypatch.setattr(helpers, "_dispatch_nonstreaming_api_request", dispatch)

    with helpers.provider_request_context(
        request_class="foreground", session_id="session-attempt", attempt=4
    ):
        assert _NonStreamRequest(agent, {"model": "gpt-5.6-sol"}).run() is not None


def test_subagent_codex_dispatch_registers_as_delegation(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    watchdogs = SimpleNamespace(
        codex=False,
        stale_timeout=60.0,
        ttfb_enabled=False,
        ttfb_timeout=60.0,
        idle_enabled=False,
        idle_timeout=60.0,
        idle_requires_progress=False,
        est_tokens=0,
    )
    monkeypatch.setattr(helpers, "_resolve_nonstream_watchdogs", lambda *_: watchdogs)
    agent = SimpleNamespace(
        api_mode="codex_responses",
        provider="openai-codex",
        model="gpt-5.6-terra",
        api_key="not-a-jwt",
        session_id="session-delegation",
        platform="subagent",
        _interrupt_requested=False,
        _touch_activity=lambda *_: None,
        _emit_wait_notice=lambda *_: None,
        _client_log_context=lambda: "test",
    )

    def dispatch(_agent, _kwargs, *, make_client):
        del make_client
        entries = provider_admission_snapshot(registry_home=tmp_path)
        assert entries[0]["request_class"] == "delegation"
        return object()

    monkeypatch.setattr(helpers, "_dispatch_nonstreaming_api_request", dispatch)

    assert _NonStreamRequest(agent, {"model": "gpt-5.6-terra"}).run() is not None


def test_auxiliary_compression_dispatch_holds_shared_admission(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    def dispatch(_request):
        entries = provider_admission_snapshot(registry_home=tmp_path)
        assert len(entries) == 1, "auxiliary Codex dispatch started without admission"
        assert entries[0]["request_class"] == "compression"
        assert entries[0]["session_id"] == "session-compression"
        return SimpleNamespace(choices=[])

    with (
        scoped_current_session_id("session-compression"),
        auxiliary_client._relay_aux_call_scope(("compression",), {}),
    ):
        auxiliary_client._set_relay_auxiliary_route(
            "openai-codex", "gpt-5.4-mini", "codex_responses"
        )
        result = auxiliary_client._relay_sync_completion(
            SimpleNamespace(),
            {"model": "gpt-5.4-mini", "messages": []},
            provider="openai-codex",
            api_mode="codex_responses",
            create=dispatch,
        )

    assert result.choices == []
    assert provider_admission_snapshot(registry_home=tmp_path) == []


def test_async_auxiliary_compression_dispatch_holds_shared_admission(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    async def dispatch(_request):
        entries = provider_admission_snapshot(registry_home=tmp_path)
        assert len(entries) == 1, "async auxiliary dispatch started without admission"
        assert entries[0]["request_class"] == "compression"
        assert entries[0]["session_id"] == "session-async-compression"
        return SimpleNamespace(choices=[])

    async def invoke():
        with (
            scoped_current_session_id("session-async-compression"),
            auxiliary_client._relay_aux_call_scope(("compression",), {}),
        ):
            auxiliary_client._set_relay_auxiliary_route(
                "openai-codex", "gpt-5.4-mini", "codex_responses"
            )
            return await auxiliary_client._relay_async_completion(
                SimpleNamespace(),
                {"model": "gpt-5.4-mini", "messages": []},
                provider="openai-codex",
                api_mode="codex_responses",
                create=dispatch,
            )

    result = asyncio.run(invoke())
    assert result.choices == []
    assert provider_admission_snapshot(registry_home=tmp_path) == []


def test_streaming_foreground_codex_dispatch_holds_shared_admission(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    def stream_call(_agent, _kwargs, *, make_client):
        del make_client
        assert helpers._current_provider_wait_identity(agent) == (
            "foreground request in session …eaming — attempt 3"
        )
        entries = provider_admission_snapshot(registry_home=tmp_path)
        assert len(entries) == 1, "streaming Codex dispatch started without admission"
        assert entries[0]["request_class"] == "foreground"
        assert entries[0]["session_id"] == "session-streaming"
        return object()

    transport = SimpleNamespace(preflight_kwargs=lambda value, **_kwargs: value)
    agent = SimpleNamespace(
        api_mode="codex_responses",
        provider="openai-codex",
        model="gpt-5.6-sol",
        api_key="not-a-jwt",
        base_url="https://chatgpt.com/backend-api/codex",
        session_id="session-streaming",
        platform="cli",
        is_subagent=False,
        _disable_streaming=False,
        _fallback_index=0,
        _model_request_active=None,
        _pending_redirect_lock=None,
        _pending_redirect=None,
        _has_stream_consumers=lambda: True,
        _get_transport=lambda: transport,
        _is_copilot_url=lambda: False,
        _is_codex_backend=lambda: True,
        _has_pending_redirect=lambda: False,
        _interrupt_requested=False,
        _touch_activity=lambda *_: None,
        _emit_wait_notice=lambda *_: None,
        _client_log_context=lambda: "test",
    )
    _wire_real_codex_dispatch(agent, monkeypatch, stream_call)
    # Bound the regression: a broken composition must fail, not hang the runner.
    timer = threading.Timer(2, lambda: setattr(agent, "_interrupt_requested", True))
    timer.start()
    try:
        verdict = _perform(agent)
    finally:
        timer.cancel()
        timer.join()
    assert verdict.response is not None
    assert provider_admission_snapshot(registry_home=tmp_path) == []


def _wire_real_codex_dispatch(agent, monkeypatch, dispatch):
    monkeypatch.setattr(helpers, "_resolve_nonstream_watchdogs", lambda *_: SimpleNamespace(
        codex=False, stale_timeout=60, ttfb_enabled=False, ttfb_timeout=60,
        idle_enabled=False, idle_timeout=60, idle_requires_progress=False, est_tokens=0,
    ))
    monkeypatch.setattr(helpers, "_dispatch_nonstreaming_api_request", dispatch)
    agent._interruptible_api_call = lambda kwargs: helpers.interruptible_api_call(agent, kwargs)
    agent._interruptible_streaming_api_call = lambda kwargs, on_first_delta=None: (
        helpers.interruptible_streaming_api_call(agent, kwargs, on_first_delta=on_first_delta)
    )


@pytest.mark.parametrize("phase", ["construct", "release"])
def test_worker_lifecycle_cannot_silently_leak_admission(monkeypatch, phase):
    agent = SimpleNamespace(
        api_mode="codex_responses", provider="openai-codex", model="model",
        session_id="session", platform="cli", _interrupt_requested=False,
        _touch_activity=lambda *_: None, _emit_wait_notice=lambda *_: None,
        _client_log_context=lambda: "test",
    )
    _wire_real_codex_dispatch(agent, monkeypatch, lambda *_a, **_k: object())
    released = []

    def release():
        released.append(True)
        if phase == "release":
            raise RuntimeError("synthetic release failure")

    monkeypatch.setattr(_NonStreamRequest, "_acquire_provider_admission", lambda _: SimpleNamespace(release=release))
    if phase == "construct":
        def fail_construct(*_a, **_k):
            raise RuntimeError("synthetic construct failure")
        monkeypatch.setattr(helpers.threading, "Thread", fail_construct)
    with pytest.raises(RuntimeError, match=f"synthetic {phase} failure"):
        _NonStreamRequest(agent, {"model": "model"}).run()
    assert released == [True]


def _perform(agent):
    return perform_api_call(
        agent,
        api_kwargs={"model": "gpt-5.6-sol"},
        _original_api_kwargs={},
        _llm_middleware_trace=[],
        _moa_prepared_request=None,
        _retry=SimpleNamespace(),
        thinking_spinner=None,
        retry_count=2,
        api_call_count=1,
        api_request_id="request-streaming",
        effective_task_id="task-streaming",
        turn_id="turn-streaming",
        interrupted=False,
    )



def test_streaming_queue_notice_identifies_blocker_once_and_clears(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    notices: list[str] = []
    notice_ready = threading.Event()

    def emit_notice(message):
        notices.append(message)
        if message:
            notice_ready.set()

    transport = SimpleNamespace(preflight_kwargs=lambda value, **_kwargs: value)
    agent = SimpleNamespace(
        api_mode="codex_responses",
        provider="openai-codex",
        model="gpt-5.6-sol",
        api_key="not-a-jwt",
        base_url="https://chatgpt.com/backend-api/codex",
        session_id="session-foreground",
        platform="cli",
        is_subagent=False,
        _disable_streaming=False,
        _fallback_index=0,
        _interrupt_requested=False,
        _model_request_active=None,
        _pending_redirect_lock=None,
        _pending_redirect=None,
        _has_stream_consumers=lambda: True,
        _get_transport=lambda: transport,
        _is_copilot_url=lambda: False,
        _is_codex_backend=lambda: True,
        _interruptible_streaming_api_call=lambda *_args, **_kwargs: object(),
        _has_pending_redirect=lambda: False,
        _emit_wait_notice=emit_notice,
        _touch_activity=lambda *_: None,
        _client_log_context=lambda: "test",
    )
    _wire_real_codex_dispatch(agent, monkeypatch, lambda *_a, **_k: object())
    blocker = ProviderAdmissionRequest(
        lane="openai-codex:profile",
        request_class="compression",
        session_id="20260908_162215_70dd49",
        provider="openai-codex",
        model="gpt-5.4-mini",
    )
    outcome: dict[str, object] = {}

    def invoke():
        outcome["value"] = perform_api_call(
            agent,
            api_kwargs={"model": "gpt-5.6-sol"},
            _original_api_kwargs={},
            _llm_middleware_trace=[],
            _moa_prepared_request=None,
            _retry=SimpleNamespace(),
            thinking_spinner=None,
            retry_count=1,
            api_call_count=1,
            api_request_id="request-queued",
            effective_task_id="task-queued",
            turn_id="turn-queued",
            interrupted=False,
        )

    with provider_admission(blocker, registry_home=tmp_path):
        worker = threading.Thread(target=invoke)
        worker.start()
        notice_ready.wait(timeout=1.0)
        time.sleep(0.15)
    worker.join(timeout=5)

    assert not worker.is_alive()
    nonempty = [notice for notice in notices if notice]
    assert nonempty == [
        "Foreground queued behind compression gpt-5.4-mini request in session "
        "…70dd49 — attempt 2, 0s queued"
    ]
    assert notices[-1] == ""
    assert outcome.get("value") is not None


def test_compression_queue_notice_identifies_foreground_owner_and_clears(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    notices: list[str] = []
    notice_ready = threading.Event()
    outcome: dict[str, object] = {}

    def emit_notice(message):
        notices.append(message)
        if message:
            notice_ready.set()

    def invoke():
        with (
            scoped_current_session_id("session-compression"),
            auxiliary_client.aux_wait_status_hook(emit_notice),
            auxiliary_client._relay_aux_call_scope(("compression",), {}),
        ):
            auxiliary_client._set_relay_auxiliary_route(
                "openai-codex", "gpt-5.4-mini", "codex_responses"
            )
            outcome["value"] = auxiliary_client._relay_sync_completion(
                SimpleNamespace(),
                {"model": "gpt-5.4-mini", "messages": []},
                provider="openai-codex",
                api_mode="codex_responses",
                create=lambda _request: SimpleNamespace(choices=[]),
            )

    blocker = ProviderAdmissionRequest(
        lane="openai-codex:profile",
        request_class="foreground",
        session_id="20260908_162215_70dd49",
        provider="openai-codex",
        model="gpt-5.6-sol",
    )
    with provider_admission(blocker, registry_home=tmp_path):
        worker = threading.Thread(target=invoke)
        worker.start()
        notice_ready.wait(timeout=1.0)
        time.sleep(0.15)
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert [notice for notice in notices if notice] == [
        "Compression queued behind foreground gpt-5.6-sol request in session "
        "…70dd49 — attempt 1, 0s queued"
    ]
    assert notices[-1] == ""
    assert outcome.get("value") is not None
