from unittest.mock import MagicMock, patch

import pytest

from agent import auxiliary_client as auxiliary
from agent import conversation_compression


class _ModelIncompatibleError(RuntimeError):
    status_code = 400


def _compression_route() -> auxiliary._LadderRoute:
    return auxiliary._LadderRoute(
        client=MagicMock(),
        task="compression",
        tag="",
        async_mode=False,
        base_info="https://chatgpt.com/backend-api/codex",
        resolved_provider="openai-codex",
        resolved_model="gpt-5.4-mini",
        resolved_base_url="https://chatgpt.com/backend-api/codex",
        resolved_api_key="synthetic-token",
        resolved_api_mode="codex_responses",
        final_model="gpt-5.4-mini",
        main_runtime={
            "provider": "openai-codex",
            "model": "gpt-5.6-sol",
            "base_url": "https://chatgpt.com/backend-api/codex",
        },
        route_info={},
        pinned_main_route=False,
    )


def test_compression_model_incompatibility_never_uses_implicit_main_model():
    error = _ModelIncompatibleError(
        "HTTP 400: model is not supported when using Codex with a ChatGPT account"
    )

    with (
        patch.object(
            auxiliary,
            "_try_configured_fallback_chain",
            return_value=(None, None, ""),
        ),
        patch.object(auxiliary, "_try_main_agent_model_fallback") as main_fallback,
    ):
        ladder = auxiliary._ladder_provider_fallback(error, _compression_route())
        with pytest.raises(StopIteration) as stopped:
            next(ladder)

    assert stopped.value.value is None
    main_fallback.assert_not_called()


def test_codex_model_incompatibility_records_account_scoped_negative_cache():
    error = _ModelIncompatibleError(
        "HTTP 400: model is not supported when using Codex with a ChatGPT account"
    )

    with (
        patch.object(
            auxiliary,
            "_try_configured_fallback_chain",
            return_value=(None, None, ""),
        ),
        patch(
            "agent.auxiliary_model_compatibility.record_codex_model_incompatibility"
        ) as record,
    ):
        ladder = auxiliary._ladder_provider_fallback(error, _compression_route())
        with pytest.raises(StopIteration):
            next(ladder)

    record.assert_called_once_with(
        "gpt-5.4-mini", access_token="synthetic-token"
    )


def test_aux_wait_status_hook_is_scoped():
    messages: list[str] = []

    assert auxiliary._emit_aux_wait_status("outside") is False
    with auxiliary.aux_wait_status_hook(messages.append):
        assert auxiliary._emit_aux_wait_status("queued") is True
    assert auxiliary._emit_aux_wait_status("after") is False

    assert messages == ["queued"]


def test_summary_dispatch_binds_auxiliary_wait_status_to_agent():
    messages: list[str] = []
    agent = MagicMock()
    agent.session_id = "session-compression"
    agent.context_compressor = MagicMock()
    agent._emit_wait_notice.side_effect = messages.append

    def compress(source, **_kwargs):
        assert auxiliary._emit_aux_wait_status("compression queued") is True
        return source

    result = conversation_compression._run_summary_dispatch(
        agent,
        ["original"],
        compress,
        {},
        commit_fence=None,
        attempt_generation=1,
        hard_cancel_event=None,
    )

    assert result == ["original"]
    assert messages == ["compression queued"]
