import json

from tools.model_escalation import (
    consume_model_escalation_authorization,
    request_model_escalation,
    reset_for_tests,
)


def setup_function():
    reset_for_tests()


def test_approved_proposal_mints_one_session_bound_capability():
    asked = []

    def callback(question, choices):
        asked.append((question, choices))
        return "Approve gpt-6-astra"

    result = json.loads(request_model_escalation(
        target_model="gpt-6-astra", reason="independent architecture arbitration",
        scope="Review the bounded renderer patch", provider="openai-codex", session_key="session-a",
        callback=callback, context_window="regular", estimated_context_tokens=20_000,
    ))

    assert result["status"] == "approved"
    assert result["target_model"] == "gpt-6-astra"
    assert asked[0][1] == ["Approve gpt-6-astra", "Decline", "Defer"]
    assert "higher quota" in asked[0][0]
    assert consume_model_escalation_authorization(
        result["model_authorization"], session_key="session-a", provider="openai-codex",
        target_model="gpt-6-astra", scope="Review the bounded renderer patch",
    ) is None
    reused = consume_model_escalation_authorization(
        result["model_authorization"], session_key="session-a", provider="openai-codex",
        target_model="gpt-6-astra", scope="Review the bounded renderer patch",
    )
    assert reused is not None and "already used" in reused


def test_lower_decline_and_scope_mismatch_fail_closed():
    approved = json.loads(request_model_escalation(
        target_model="gpt-6-astra", lower_model="gpt-5.6-sol", reason="review",
        scope="Review one bounded change", provider="openai-codex", session_key="session-a",
        callback=lambda _q, _choices: "Use gpt-5.6-sol",
    ))
    assert approved["target_model"] == "gpt-5.6-sol"
    mismatch = consume_model_escalation_authorization(
        approved["model_authorization"], session_key="session-a", provider="openai-codex",
        target_model="gpt-5.6-sol", scope="Different task",
    )
    assert mismatch is not None and "does not match" in mismatch

    declined = json.loads(request_model_escalation(
        target_model="gpt-6-astra", reason="review", scope="Review a second bounded change",
        provider="openai-codex", session_key="session-b", callback=lambda _q, _choices: "Decline",
    ))
    assert declined["status"] == "declined"
    assert "error" in json.loads(request_model_escalation(
        target_model="gpt-6-astra", reason="review", scope="Review a third bounded change",
        provider="openai-codex", session_key="", callback=lambda _q, _choices: "Approve gpt-6-astra",
    ))


def test_disallowed_provider_and_model_are_rejected():
    for provider, model in [("openai", "gpt-6-astra"), ("openai-codex", "gpt-5.6-terra")]:
        result = json.loads(request_model_escalation(
            target_model=model, reason="review", scope="Review bounded work", provider=provider,
            session_key="session-a", callback=lambda _q, _choices: f"Approve {model}",
        ))
        assert "error" in result


def test_openai_codex_qualified_target_normalizes_but_foreign_provider_is_rejected():
    approved = json.loads(request_model_escalation(
        target_model="openai-codex/gpt-5.6-sol", reason="final judgment",
        scope="Review one bounded change", provider="openai-codex", session_key="session-a",
        callback=lambda _q, _choices: "Approve gpt-5.6-sol",
    ))

    assert approved["target_model"] == "gpt-5.6-sol"
    assert set(approved["delegation_diagnostics"]) == {
        "max_concurrent_children", "occupied_slots", "child_timeout", "model_authorization", "context_tier", "provider_quota",
    }
    assert approved["delegation_diagnostics"]["provider_quota"]["status"] == "not_observed"
    assert consume_model_escalation_authorization(
        approved["model_authorization"], session_key="session-a", provider="openai-codex",
        target_model="openai-codex/gpt-5.6-sol", scope="Review one bounded change",
    ) is None

    rejected = json.loads(request_model_escalation(
        target_model="other-provider/gpt-5.6-sol", reason="final judgment",
        scope="Review another bounded change", provider="openai-codex", session_key="session-b",
        callback=lambda _q, _choices: "Approve gpt-5.6-sol",
    ))
    assert "provider mismatch" in rejected["error"]


def test_900k_proposal_requires_a_large_isolated_context_estimate():
    rejected = json.loads(request_model_escalation(
        target_model="gpt-5.6-sol-900k", reason="corpus review", scope="Review the complete bounded corpus",
        provider="openai-codex", session_key="session-a", callback=lambda _q, _choices: "Approve gpt-5.6-sol-900k",
        estimated_context_tokens=219_999,
    ))
    assert "error" in rejected

    approved = json.loads(request_model_escalation(
        target_model="gpt-5.6-sol-900k", reason="corpus review", scope="Review the complete bounded corpus",
        provider="openai-codex", session_key="session-a", callback=lambda _q, _choices: "Approve gpt-5.6-sol-900k",
        estimated_context_tokens=220_000,
    ))
    assert approved["target_model"] == "gpt-5.6-sol-900k"


def test_conditional_free_text_does_not_authorize_and_lower_is_explicit():
    asked = []
    result = json.loads(request_model_escalation(
        target_model="gpt-6-astra", lower_model="gpt-5.6-sol", reason="review",
        scope="Review one bounded change", provider="openai-codex", session_key="session-a",
        callback=lambda question, choices: asked.append((question, choices)) or "Approve only after I review the cost",
    ))
    assert result == {"status": "declined", "target_model": "gpt-6-astra"}
    assert asked[0][1] == ["Approve gpt-6-astra", "Use gpt-5.6-sol", "Decline", "Defer"]


def test_lower_model_cannot_increase_context_capacity():
    result = json.loads(request_model_escalation(
        target_model="gpt-6-astra", lower_model="gpt-6-astra-900k", reason="review",
        scope="Review one bounded change", provider="openai-codex", session_key="session-a",
        callback=lambda _question, _choices: "Use gpt-6-astra-900k",
        estimated_context_tokens=220_000,
    ))
    assert "error" in result
