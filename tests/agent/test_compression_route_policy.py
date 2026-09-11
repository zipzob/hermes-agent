"""Deterministic tests for model-window-dependent compression routing."""

import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from agent.auxiliary_client import (
    _RERAISE_ORIGINAL,
    _aux_recovery_ladder,
    _drive_ladder,
    _prepare_aux_request,
    get_async_text_auxiliary_client,
    get_text_auxiliary_client,
)
from agent.context_compressor import ContextCompressor
from run_agent import AIAgent


def test_large_context_compression_route_inherits_explicit_main_runtime():
    main_runtime = {
        "provider": "openai-codex",
        "model": "gpt-5.6-sol-900k",
        "base_url": "https://chatgpt.com/backend-api/codex",
        "api_key": None,
        "api_mode": "codex_responses",
        "context_length": 900_000,
        "compression_threshold_tokens": 765_000,
    }
    static_route = (
        "openai-codex",
        "gpt-5.4-mini",
        "https://chatgpt.com/backend-api/codex",
        None,
        "codex_responses",
    )
    client = object()
    route_info = {}

    with (
        patch(
            "agent.auxiliary_client._get_auxiliary_task_config",
            return_value={
                "inherit_main_when_incompatible": True,
                "context_length": 272_000,
            },
        ),
        patch(
            "agent.auxiliary_client._resolve_task_provider_model",
            return_value=static_route,
        ),
        patch(
            "agent.auxiliary_client.resolve_provider_client",
            return_value=(client, main_runtime["model"]),
        ) as resolve,
    ):
        assert get_text_auxiliary_client(
            "compression", main_runtime=main_runtime, route_info=route_info
        ) == (client, main_runtime["model"])

    assert route_info == {"compression_inherited_main_for_context": True}
    resolve.assert_called_once_with(
        main_runtime["provider"],
        model=main_runtime["model"],
        explicit_base_url=main_runtime["base_url"],
        explicit_api_key=main_runtime["api_key"],
        api_mode=main_runtime["api_mode"],
        main_runtime=main_runtime,
    )


@pytest.mark.parametrize("resolved_client", [object(), None])
def test_async_getter_inherits_exact_compatible_main_route(resolved_client):
    credential = lambda: "fixture"
    runtime = {
        "provider": "azure",
        "model": "large-deployment",
        "base_url": "https://example.invalid/openai",
        "api_key": credential,
        "api_mode": "chat_completions",
        "context_length": 900_000,
        "compression_threshold_tokens": 765_000,
    }
    static_route = (
        "openai-codex",
        "gpt-5.4-mini",
        "https://chatgpt.com/backend-api/codex",
        None,
        "codex_responses",
    )

    with (
        patch(
            "agent.auxiliary_client._get_auxiliary_task_config",
            return_value={
                "inherit_main_when_incompatible": True,
                "context_length": 272_000,
            },
        ),
        patch(
            "agent.auxiliary_client._resolve_task_provider_model",
            return_value=static_route,
        ),
        patch(
            "agent.auxiliary_client.resolve_provider_client",
            return_value=(resolved_client, runtime["model"] if resolved_client else None),
        ) as resolve,
        patch(
            "agent.auxiliary_client._try_configured_fallback_for_unavailable_client"
        ) as configured_fallback,
    ):
        result = get_async_text_auxiliary_client(
            "compression", main_runtime=runtime
        )

    assert result == (
        resolved_client,
        runtime["model"] if resolved_client else None,
    )
    resolve.assert_called_once_with(
        runtime["provider"],
        model=runtime["model"],
        async_mode=True,
        explicit_base_url=runtime["base_url"],
        explicit_api_key=credential,
        api_mode=runtime["api_mode"],
        main_runtime=runtime,
    )
    configured_fallback.assert_not_called()


def test_agent_runtime_exposes_resolved_context_length_for_routing():
    agent: Any = AIAgent.__new__(AIAgent)
    agent.model = "custom-large"
    agent.provider = "custom"
    agent.base_url = "http://localhost:11434/v1"
    agent.api_key = None
    agent.api_mode = "chat_completions"
    agent.auth_mode = ""
    agent.context_compressor = type(
        "Compressor",
        (),
        {"context_length": 640_000, "threshold_tokens": 400_000},
    )()

    runtime = agent._current_main_runtime()
    assert runtime["context_length"] == 640_000
    assert runtime["compression_threshold_tokens"] == 400_000


def test_real_summary_dispatch_carries_window_and_trigger_metadata():
    compressor = ContextCompressor(
        model="gpt-5.6-sol-900k",
        provider="openai-codex",
        api_mode="codex_responses",
        base_url="https://chatgpt.com/backend-api/codex",
        api_key="",
        config_context_length=900_000,
        threshold_percent=0.85,
        quiet_mode=True,
    )
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Complete summary"),
                finish_reason="stop",
            )
        ]
    )

    with patch("agent.context_compressor.call_llm", return_value=response) as call:
        assert compressor._call_summary_llm("Summarize", time.monotonic()) == "Complete summary"

    runtime = call.call_args.kwargs["main_runtime"]
    assert runtime["context_length"] == 900_000
    assert runtime["compression_threshold_tokens"] == 765_000


@pytest.mark.parametrize("async_mode", [False, True])
def test_shared_call_planner_applies_compatibility_route(async_mode):
    runtime = {
        "provider": "openai-codex",
        "model": "gpt-5.6-sol-900k",
        "base_url": "https://chatgpt.com/backend-api/codex",
        "api_key": None,
        "api_mode": "codex_responses",
        "context_length": 900_000,
        "compression_threshold_tokens": 765_000,
    }
    static_route = (
        "openai-codex",
        "gpt-5.4-mini",
        "https://chatgpt.com/backend-api/codex",
        None,
        "codex_responses",
    )
    client = SimpleNamespace(base_url=runtime["base_url"])

    def resolve_client(_task, **kwargs):
        return (
            client,
            kwargs["resolved_model"],
            kwargs["resolved_provider"],
            kwargs["resolved_provider"],
        )

    with (
        patch(
            "agent.auxiliary_client._get_auxiliary_task_config",
            return_value={
                "inherit_main_when_incompatible": True,
                "context_length": 272_000,
            },
        ),
        patch(
            "agent.auxiliary_client._resolve_task_provider_model",
            return_value=static_route,
        ),
        patch(
            "agent.auxiliary_client._resolve_call_client",
            side_effect=resolve_client,
        ),
    ):
        request = _prepare_aux_request(
            "compression",
            provider=None,
            model=None,
            base_url=None,
            api_key=None,
            main_runtime=runtime,
            messages=[{"role": "user", "content": "summarize"}],
            temperature=None,
            max_tokens=None,
            tools=None,
            timeout=30,
            extra_body=None,
            reasoning_config=None,
            extra_headers=None,
            api_mode=None,
            route_info=None,
            async_mode=async_mode,
        )

    assert request.resolved_provider == runtime["provider"]
    assert request.resolved_model == runtime["model"]


def test_unavailable_compatibility_inherited_main_route_fails_without_rescue():
    runtime = {
        "provider": "openai-codex",
        "model": "gpt-5.6-sol-900k",
        "base_url": "https://chatgpt.com/backend-api/codex",
        "api_key": None,
        "api_mode": "codex_responses",
        "context_length": 900_000,
        "compression_threshold_tokens": 765_000,
    }
    static_route = (
        "openai-codex",
        "gpt-5.4-mini",
        runtime["base_url"],
        None,
        "codex_responses",
    )

    with (
        patch(
            "agent.auxiliary_client._get_auxiliary_task_config",
            return_value={
                "inherit_main_when_incompatible": True,
                "context_length": 272_000,
            },
        ),
        patch(
            "agent.auxiliary_client._resolve_task_provider_model",
            return_value=static_route,
        ),
        patch("agent.auxiliary_client._get_cached_client", return_value=(None, None)) as cached,
        patch(
            "agent.auxiliary_client._try_configured_fallback_for_unavailable_client"
        ) as configured_fallback,
    ):
        with pytest.raises(RuntimeError, match="pinned main route"):
            _prepare_aux_request(
                "compression",
                provider=None,
                model=None,
                base_url=None,
                api_key=None,
                main_runtime=runtime,
                messages=[{"role": "user", "content": "summarize"}],
                temperature=None,
                max_tokens=None,
                tools=None,
                timeout=30,
                extra_body=None,
                reasoning_config=None,
                extra_headers=None,
                api_mode=None,
                route_info=None,
                async_mode=False,
            )

    configured_fallback.assert_not_called()
    assert cached.call_count == 1
    assert cached.call_args.args[0] == runtime["provider"]


@pytest.mark.parametrize("async_mode", [False, True])
def test_equal_tuple_compatibility_inheritance_remains_pinned(async_mode):
    runtime = {
        "provider": "openai-codex",
        "model": "gpt-5.6-sol-900k",
        "base_url": "https://chatgpt.com/backend-api/codex",
        "api_key": None,
        "api_mode": "codex_responses",
        "context_length": 900_000,
        "compression_threshold_tokens": 765_000,
    }
    configured_route = tuple(
        runtime.get(field)
        for field in ("provider", "model", "base_url", "api_key", "api_mode")
    )

    with (
        patch(
            "agent.auxiliary_client._get_auxiliary_task_config",
            return_value={
                "inherit_main_when_incompatible": True,
                "context_length": 272_000,
            },
        ),
        patch(
            "agent.auxiliary_client._resolve_task_provider_model",
            return_value=configured_route,
        ),
        patch("agent.auxiliary_client._get_cached_client", return_value=(None, None)),
        patch(
            "agent.auxiliary_client._try_configured_fallback_for_unavailable_client"
        ) as configured_fallback,
    ):
        with pytest.raises(RuntimeError, match="pinned main route"):
            _prepare_aux_request(
                "compression",
                provider=None,
                model=None,
                base_url=None,
                api_key=None,
                main_runtime=runtime,
                messages=[{"role": "user", "content": "summarize"}],
                temperature=None,
                max_tokens=None,
                tools=None,
                timeout=30,
                extra_body=None,
                reasoning_config=None,
                extra_headers=None,
                api_mode=None,
                route_info=None,
                async_mode=async_mode,
            )

    configured_fallback.assert_not_called()


def test_pinned_main_route_recovery_never_reaches_provider_fallback():
    failure = ConnectionError("connection error")
    client = SimpleNamespace(base_url="https://chatgpt.com/backend-api/codex", api_key=None)

    with (
        patch("agent.auxiliary_client._recoverable_pool_provider", return_value=None),
        patch("agent.auxiliary_client._ladder_nous_rungs") as nous_rungs,
        patch("agent.auxiliary_client._ladder_credential_rungs") as credential_rungs,
        patch("agent.auxiliary_client._ladder_provider_fallback") as provider_fallback,
    ):
        ladder = _aux_recovery_ladder(
            failure,
            client=client,
            kwargs={"model": "gpt-5.6-sol-900k", "messages": []},
            task="compression",
            async_mode=False,
            base_info=client.base_url,
            resolved_provider="openai-codex",
            resolved_model="gpt-5.6-sol-900k",
            resolved_base_url=client.base_url,
            resolved_api_key=None,
            resolved_api_mode="codex_responses",
            final_model="gpt-5.6-sol-900k",
            max_tokens=None,
            main_runtime=None,
            route_info=None,
            pinned_main_route=True,
        )
        result = _drive_ladder(
            ladder,
            lambda step: pytest.fail(f"unexpected recovery step: {step}"),
        )

    assert result is _RERAISE_ORIGINAL
    nous_rungs.assert_not_called()
    credential_rungs.assert_not_called()
    provider_fallback.assert_not_called()


def test_explicit_compression_destination_overrides_compatibility_policy():
    runtime = {
        "provider": "openai-codex",
        "model": "gpt-5.6-sol-900k",
        "context_length": 900_000,
        "compression_threshold_tokens": 765_000,
    }
    client = SimpleNamespace(base_url="https://openrouter.ai/api/v1")

    def resolve_client(_task, **kwargs):
        return client, kwargs["resolved_model"], "openrouter", "openrouter"

    with (
        patch(
            "agent.auxiliary_client._get_auxiliary_task_config",
            return_value={
                "inherit_main_when_incompatible": True,
                "context_length": 272_000,
            },
        ),
        patch(
            "agent.auxiliary_client._resolve_task_provider_model",
            return_value=("openrouter", "explicit-model", None, None, None),
        ),
        patch(
            "agent.auxiliary_client._resolve_call_client",
            side_effect=resolve_client,
        ),
    ):
        request = _prepare_aux_request(
            "compression",
            provider="openrouter",
            model="explicit-model",
            base_url=None,
            api_key=None,
            main_runtime=runtime,
            messages=[{"role": "user", "content": "summarize"}],
            temperature=None,
            max_tokens=None,
            tools=None,
            timeout=30,
            extra_body=None,
            reasoning_config=None,
            extra_headers=None,
            api_mode=None,
            route_info=None,
            async_mode=False,
        )

    assert request.resolved_provider == "openrouter"
    assert request.resolved_model == "explicit-model"


def test_public_config_default_keeps_context_routing_disabled():
    from hermes_cli.config import DEFAULT_CONFIG

    assert (
        DEFAULT_CONFIG["auxiliary"]["compression"][
            "inherit_main_when_incompatible"
        ]
        is False
    )


def _resolved_route(task, task_config, main_runtime):
    static_route = (
        "openai-codex",
        "gpt-5.4-mini",
        "https://chatgpt.com/backend-api/codex",
        None,
        "codex_responses",
    )
    with (
        patch(
            "agent.auxiliary_client._get_auxiliary_task_config",
            return_value=task_config,
        ),
        patch(
            "agent.auxiliary_client._resolve_task_provider_model",
            return_value=static_route,
        ),
        patch(
            "agent.auxiliary_client.resolve_provider_client",
            return_value=(object(), "resolved"),
        ) as resolve,
    ):
        get_text_auxiliary_client(task, main_runtime=main_runtime)
    return resolve.call_args


@pytest.mark.parametrize(
    ("task_config", "main_threshold"),
    [
        (
            {"inherit_main_when_incompatible": True, "context_length": 272_000},
            231_200,
        ),
        (
            {"inherit_main_when_incompatible": False, "context_length": 272_000},
            765_000,
        ),
        ({"inherit_main_when_incompatible": "true", "context_length": 272_000}, 765_000),
    ],
)
def test_disabled_or_unneeded_policy_keeps_static_compression_route(
    task_config, main_threshold
):
    runtime = {
        "provider": "openai-codex",
        "model": "gpt-5.6-sol-900k",
        "base_url": "https://chatgpt.com/backend-api/codex",
        "api_key": None,
        "api_mode": "codex_responses",
        "context_length": 900_000,
        "compression_threshold_tokens": main_threshold,
    }

    call = _resolved_route("compression", task_config, runtime)

    assert call.args == ("openai-codex",)
    assert call.kwargs["model"] == "gpt-5.4-mini"
    assert call.kwargs["explicit_api_key"] is None


@pytest.mark.parametrize("aux_context", [None, "invalid", 0, -1, True])
def test_enabled_policy_treats_unknown_aux_capacity_as_incompatible(aux_context):
    runtime = {
        "provider": "openai-codex",
        "model": "gpt-5.6-sol-900k",
        "base_url": "https://chatgpt.com/backend-api/codex",
        "api_key": None,
        "api_mode": "codex_responses",
        "context_length": 900_000,
        "compression_threshold_tokens": 765_000,
    }

    call = _resolved_route(
        "compression",
        {
            "inherit_main_when_incompatible": True,
            "context_length": aux_context,
        },
        runtime,
    )

    assert call.args == (runtime["provider"],)
    assert call.kwargs["model"] == runtime["model"]
    assert call.kwargs["explicit_api_key"] == runtime["api_key"]


def test_exact_context_boundary_inherits_callable_main_credential():
    def token_provider():
        return "fixture"

    runtime = {
        "provider": "azure-foundry",
        "model": "custom-large",
        "base_url": "https://example.openai.azure.com/openai/v1",
        "api_key": token_provider,
        "api_mode": "chat_completions",
        "context_length": 900_000,
        "compression_threshold_tokens": 500_000,
    }

    call = _resolved_route(
        "compression",
        {"inherit_main_when_incompatible": True, "context_length": 500_000},
        runtime,
    )

    assert call.args == ("azure-foundry",)
    assert call.kwargs["model"] == "custom-large"
    assert call.kwargs["explicit_api_key"] is token_provider


def test_concurrent_inherited_routes_keep_runtime_credentials_isolated():
    def azure_token():
        return "fixture-a"

    def codex_token():
        return "fixture-b"

    runtimes = [
        {
            "provider": "azure-foundry",
            "model": "azure-large",
            "base_url": "https://example.openai.azure.com/openai/v1",
            "api_key": azure_token,
            "api_mode": "chat_completions",
            "context_length": 900_000,
            "compression_threshold_tokens": 765_000,
        },
        {
            "provider": "openai-codex",
            "model": "gpt-5.6-sol-900k",
            "base_url": "https://chatgpt.com/backend-api/codex",
            "api_key": codex_token,
            "api_mode": "codex_responses",
            "context_length": 900_000,
            "compression_threshold_tokens": 765_000,
        },
    ]
    static_route = (
        "openai-codex",
        "gpt-5.4-mini",
        "https://chatgpt.com/backend-api/codex",
        None,
        "codex_responses",
    )

    def resolve(runtime):
        client, model = get_text_auxiliary_client(
            "compression",
            main_runtime=runtime,
        )
        assert client is not None and model is not None
        provider, kwargs = client
        return provider, model, kwargs["explicit_base_url"], kwargs["explicit_api_key"]

    with (
        patch(
            "agent.auxiliary_client._get_auxiliary_task_config",
            return_value={
                "inherit_main_when_incompatible": True,
                "context_length": 272_000,
            },
        ),
        patch(
            "agent.auxiliary_client._resolve_task_provider_model",
            return_value=static_route,
        ),
        patch(
            "agent.auxiliary_client.resolve_provider_client",
            side_effect=lambda provider, **kwargs: ((provider, kwargs), kwargs["model"]),
        ),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        results = list(pool.map(resolve, runtimes))

    assert results == [
        (runtime["provider"], runtime["model"], runtime["base_url"], runtime["api_key"])
        for runtime in runtimes
    ]


def test_non_compression_task_never_uses_context_route():
    runtime = {
        "provider": "openai-codex",
        "model": "gpt-5.6-sol-900k",
        "context_length": 900_000,
        "compression_threshold_tokens": 765_000,
    }

    call = _resolved_route(
        "title_generation",
        {"inherit_main_when_incompatible": True, "context_length": 272_000},
        runtime,
    )

    assert call.kwargs["model"] == "gpt-5.4-mini"
