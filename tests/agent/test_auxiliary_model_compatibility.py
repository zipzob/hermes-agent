import pytest


@pytest.fixture(autouse=True)
def enable_admission(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "provider_admission:\n  max_in_flight: 1\n", encoding="utf-8"
    )


def test_account_catalog_marks_missing_auxiliary_model_incompatible():
    from agent.auxiliary_model_compatibility import probe_codex_model_compatibility

    calls: list[str] = []

    def catalog(access_token: str):
        calls.append(access_token)
        return ["gpt-5.6-luna", "gpt-5.6-terra"]

    verdict = probe_codex_model_compatibility(
        "gpt-5.4-mini",
        access_token="synthetic-jwt",
        catalog_loader=catalog,
    )

    assert verdict == "incompatible"
    assert calls == ["synthetic-jwt"]


def test_recorded_provider_incompatibility_short_circuits_catalog():
    from agent.auxiliary_model_compatibility import (
        probe_codex_model_compatibility,
        record_codex_model_incompatibility,
    )

    record_codex_model_incompatibility(
        "gpt-5.4-mini", access_token="account-token"
    )

    verdict = probe_codex_model_compatibility(
        "gpt-5.4-mini",
        access_token="account-token",
        catalog_loader=lambda _token: (_ for _ in ()).throw(
            AssertionError("catalog must not run after a provider rejection")
        ),
    )

    assert verdict == "incompatible"


def test_sync_auxiliary_dispatch_rejects_catalog_incompatible_model(monkeypatch):
    from types import SimpleNamespace

    from agent import auxiliary_client as auxiliary

    dispatched: list[str] = []
    monkeypatch.setattr(
        auxiliary,
        "_relay_auxiliary_metadata",
        lambda **_kwargs: (
            "openai-codex",
            "gpt-5.4-mini",
            {"auxiliary_task": "compression", "retry_count": 0},
        ),
    )
    monkeypatch.setattr(
        "agent.auxiliary_model_compatibility.probe_codex_model_compatibility",
        lambda *_args, **_kwargs: "incompatible",
    )

    client = SimpleNamespace(api_key="synthetic-jwt")
    try:
        auxiliary._relay_sync_completion(
            client,
            {"model": "gpt-5.4-mini", "messages": []},
            provider="openai-codex",
            api_mode="codex_responses",
            create=lambda _request: dispatched.append("called"),
        )
    except Exception as exc:
        error = exc
    else:
        error = None

    assert error is not None
    assert auxiliary._is_model_incompatible_error(error)
    assert dispatched == []


def test_auxiliary_stream_holds_admission_until_exhausted(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from agent import auxiliary_client as auxiliary
    from hermes_cli.provider_admission import provider_admission_snapshot

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(
        auxiliary,
        "_relay_auxiliary_metadata",
        lambda **_kwargs: (
            "openai-codex",
            "gpt-5.4-mini",
            {"auxiliary_task": "compression", "retry_count": 0},
        ),
    )
    monkeypatch.setattr(
        "agent.auxiliary_model_compatibility.probe_codex_model_compatibility",
        lambda *_args, **_kwargs: "compatible",
    )
    completions = SimpleNamespace(create=lambda **_kwargs: iter(["first", "second"]))
    client = SimpleNamespace(
        api_key="synthetic-jwt",
        chat=SimpleNamespace(completions=completions),
    )

    stream = auxiliary._relay_sync_stream(
        client,
        {"model": "gpt-5.4-mini", "messages": [], "stream": True},
        provider="openai-codex",
        api_mode="codex_responses",
    )

    active = provider_admission_snapshot(registry_home=tmp_path)
    assert [(entry["request_class"], entry["state"]) for entry in active] == [
        ("compression", "active")
    ]
    assert list(stream) == ["first", "second"]
    assert provider_admission_snapshot(registry_home=tmp_path) == []


def test_auxiliary_stream_silence_notice_lives_until_exhaustion(
    monkeypatch, tmp_path
):
    import time
    from types import SimpleNamespace

    from agent import auxiliary_client as auxiliary
    from gateway.session_context import scoped_current_session_id

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(auxiliary, "_AUX_PROVIDER_WAIT_NOTICE_SECONDS", 0.01)
    monkeypatch.setattr(
        auxiliary,
        "_relay_auxiliary_metadata",
        lambda **_kwargs: (
            "openai-codex",
            "gpt-5.4-mini",
            {"auxiliary_task": "background_review", "retry_count": 1},
        ),
    )
    monkeypatch.setattr(
        "agent.auxiliary_model_compatibility.probe_codex_model_compatibility",
        lambda *_args, **_kwargs: "compatible",
    )
    notices: list[str] = []
    completions = SimpleNamespace(create=lambda **_kwargs: iter(["chunk"]))
    client = SimpleNamespace(
        api_key="synthetic-jwt",
        chat=SimpleNamespace(completions=completions),
    )

    with (
        scoped_current_session_id("20260908_162215_70dd49"),
        auxiliary.aux_wait_status_hook(notices.append),
    ):
        stream = auxiliary._relay_sync_stream(
            client,
            {
                "model": "gpt-5.4-mini",
                "messages": [],
                "stream": True,
                "timeout": 5.0,
            },
            provider="openai-codex",
            api_mode="codex_responses",
        )
        deadline = time.monotonic() + 0.5
        while not notices and time.monotonic() < deadline:
            time.sleep(0.005)
        assert any(
            "background review request in session …70dd49 — attempt 2" in notice
            for notice in notices
        ), notices
        assert list(stream) == ["chunk"]

    assert notices[-1] == ""


def test_auxiliary_stream_close_releases_admission(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from agent import auxiliary_client as auxiliary
    from hermes_cli.provider_admission import provider_admission_snapshot

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(
        auxiliary,
        "_relay_auxiliary_metadata",
        lambda **_kwargs: (
            "openai-codex",
            "gpt-5.4-mini",
            {"auxiliary_task": "compression", "retry_count": 0},
        ),
    )
    monkeypatch.setattr(
        "agent.auxiliary_model_compatibility.probe_codex_model_compatibility",
        lambda *_args, **_kwargs: "compatible",
    )

    def chunks():
        yield "unused"

    completions = SimpleNamespace(create=lambda **_kwargs: chunks())
    client = SimpleNamespace(
        api_key="synthetic-jwt",
        chat=SimpleNamespace(completions=completions),
    )
    stream = auxiliary._relay_sync_stream(
        client,
        {"model": "gpt-5.4-mini", "messages": [], "stream": True},
        provider="openai-codex",
        api_mode="codex_responses",
    )
    assert provider_admission_snapshot(registry_home=tmp_path)

    stream.close()

    assert provider_admission_snapshot(registry_home=tmp_path) == []


def test_auxiliary_provider_silence_notice_is_owned_and_cleared(
    monkeypatch, tmp_path
):
    import time
    from types import SimpleNamespace

    from agent import auxiliary_client as auxiliary
    from gateway.session_context import scoped_current_session_id

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(auxiliary, "_AUX_PROVIDER_WAIT_NOTICE_SECONDS", 0.01)
    monkeypatch.setattr(
        "agent.auxiliary_model_compatibility.probe_codex_model_compatibility",
        lambda *_args, **_kwargs: "compatible",
    )
    notices: list[str] = []

    def dispatch(_request):
        time.sleep(0.04)
        return SimpleNamespace(choices=[])

    with (
        scoped_current_session_id("20260908_162215_70dd49"),
        auxiliary.aux_wait_status_hook(notices.append),
        auxiliary._relay_aux_call_scope(("compression",), {}),
    ):
        auxiliary._set_relay_auxiliary_route(
            "openai-codex", "gpt-5.4-mini", "codex_responses"
        )
        result = auxiliary._relay_sync_completion(
            SimpleNamespace(api_key="synthetic-jwt"),
            {"model": "gpt-5.4-mini", "messages": [], "timeout": 5.0},
            provider="openai-codex",
            api_mode="codex_responses",
            create=dispatch,
        )

    assert result.choices == []
    assert any(
        "compression request in session …70dd49 — attempt 1" in notice
        and "waiting on gpt-5.4-mini" in notice
        and "provider silence" in notice
        and "auto-recovery at 5s" in notice
        for notice in notices
    ), notices
    assert notices[-1] == ""
