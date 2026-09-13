from __future__ import annotations

from tools.delegate_tool import DELEGATE_TASK_SCHEMA, _route_task_credentials
from tools.delegation_resource_routing import route_delegation_tasks


def policy(**overrides):
    value = {
        "mode": "automatic_safe",
        "large_context_trigger_tokens": 220_000,
        "models": {
            "simple": "gpt-5.6-luna",
            "volume": "gpt-5.6-luna",
            "substantive": "gpt-5.6-terra",
            "latency_critical": "gpt-5.6-terra",
            "judgment": "gpt-5.6-sol",
        },
    }
    value.update(overrides)
    return value


def test_routes_each_task_by_workload_without_inheriting_parent_context_pressure():
    tasks = [
        {"goal": "format deterministic fixtures", "workload": "simple"},
        {"goal": "transform the bounded corpus", "workload": "volume"},
        {"goal": "implement the repository repair", "workload": "substantive"},
        {"goal": "perform final high-judgment review", "workload": "judgment"},
    ]

    routes = route_delegation_tasks(
        tasks,
        parent_model="gpt-5.6-sol-900k",
        policy=policy(),
        quota_snapshot={"general": "GREEN", "spark": "GREEN"},
        parent_context_tokens=700_000,
    )

    assert [route.model for route in routes] == [
        "gpt-5.6-luna",
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "gpt-5.6-sol",
    ]
    assert all(route.context_tier == "regular" for route in routes)


def test_900k_is_selected_only_for_large_isolated_child_working_set():
    tasks = [
        {"goal": "review a compact patch", "workload": "judgment", "estimated_context_tokens": 80_000},
        {"goal": "review the complete corpus", "workload": "judgment", "estimated_context_tokens": 240_000},
        {"goal": "review explicitly large material", "workload": "substantive", "context_window": "large"},
    ]

    routes = route_delegation_tasks(
        tasks,
        parent_model="gpt-5.6-sol",
        policy=policy(),
        quota_snapshot={"general": "GREEN", "spark": "GREEN"},
    )

    assert [route.model for route in routes] == [
        "gpt-5.6-sol",
        "gpt-5.6-sol-900k",
        "gpt-5.6-terra-900k",
    ]
    assert [route.context_tier for route in routes] == ["regular", "large", "large"]


def test_simple_lane_uses_luna_900k_for_large_isolated_working_set():
    [route] = route_delegation_tasks(
        [{"goal": "format a huge mechanical dump", "workload": "simple", "context_window": "large"}],
        parent_model="gpt-5.6-sol",
        policy=policy(),
        quota_snapshot={"general": "GREEN", "spark": "GREEN"},
    )
    assert route.model == "gpt-5.6-luna-900k"
    assert route.context_tier == "large"
    assert "large_context_required" in route.reasons


def test_preview_spark_is_never_spent_by_automatic_latency_routing():
    routes = route_delegation_tasks(
        [
            {"goal": "fast bounded iteration", "workload": "latency_critical"},
            {"goal": "normal implementation", "workload": "substantive"},
        ],
        parent_model="gpt-5.6-sol",
        policy=policy(),
        quota_snapshot={"general": "GREEN", "spark": "GREEN"},
    )
    assert [route.model for route in routes] == ["gpt-5.6-terra", "gpt-5.6-terra"]
    assert "spark_explicit_only" in routes[0].reasons


def test_general_pressure_avoids_optional_frontier_but_preserves_large_context_need():
    routes = route_delegation_tasks(
        [
            {"goal": "optional final wording", "workload": "judgment"},
            {
                "goal": "large correctness review",
                "workload": "judgment",
                "estimated_context_tokens": 300_000,
            },
        ],
        parent_model="gpt-5.6-sol",
        policy=policy(),
        quota_snapshot={"general": "ORANGE", "spark": "GREEN"},
    )
    assert routes[0].model == "gpt-5.6-terra"
    assert routes[1].model == "gpt-5.6-terra-900k"
    assert "general_quota_orange" in routes[0].reasons


def test_off_mode_and_explicit_pin_preserve_configured_route():
    tasks = [{"goal": "review", "workload": "judgment", "context_window": "large"}]
    off = route_delegation_tasks(tasks, parent_model="gpt-5.6-terra", policy={"mode": "off"})
    pinned = route_delegation_tasks(
        tasks,
        parent_model="gpt-5.6-terra",
        policy=policy(),
        explicit_model_pin="gpt-5.4-mini",
    )
    assert off[0].model == "gpt-5.6-terra"
    assert pinned[0].model == "gpt-5.4-mini"
    assert "explicit_pin" in pinned[0].reasons


def test_explicit_pin_can_select_preview_spark_without_automatic_routing():
    [route] = route_delegation_tasks(
        [{"goal": "latency-critical bounded edit", "workload": "latency_critical"}],
        parent_model="gpt-5.6-terra",
        policy=policy(),
        quota_snapshot={"general": "GREEN", "spark": "EXHAUSTED"},
        explicit_model_pin="gpt-5.3-codex-spark",
    )
    assert route.model == "gpt-5.3-codex-spark"
    assert route.reasons == ("explicit_pin",)


def test_astra_is_never_automatically_selected_even_if_parent_uses_it():
    [route] = route_delegation_tasks(
        [{"goal": "final arbitration", "workload": "judgment"}],
        parent_model="gpt-6-astra-900k",
        policy=policy(),
        quota_snapshot={"general": "GREEN", "spark": "GREEN", "astra": "GREEN"},
    )
    assert route.model == "gpt-5.6-sol"
    assert "astra" not in route.model


def test_operator_only_models_cannot_be_injected_into_automatic_lanes():
    configured = policy(models={
        "simple": "gpt-5.3-codex-spark",
        "volume": "gpt-5.6-luna",
        "substantive": "gpt-6-astra",
        "latency_critical": "gpt-5.3-codex-spark",
        "judgment": "gpt-6-astra-900k",
    })
    routes = route_delegation_tasks(
        [
            {"goal": "mechanical", "workload": "simple"},
            {"goal": "implementation", "workload": "substantive"},
            {"goal": "arbitration", "workload": "judgment", "context_window": "large"},
        ],
        parent_model="gpt-5.6-sol",
        policy=configured,
        quota_snapshot={"general": "GREEN", "spark": "GREEN", "astra": "GREEN"},
    )

    assert [route.model for route in routes] == [
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "gpt-5.6-sol-900k",
    ]
    assert all("operator_only_model_ignored" in route.reasons for route in routes)


def test_delegate_integration_builds_per_task_credentials_without_leaking_secrets(monkeypatch):
    monkeypatch.setattr(
        "tools.delegation_resource_routing.load_quota_snapshot",
        lambda _policy: {"general": "GREEN", "spark": "GREEN"},
    )
    base = {
        "provider": "openai-codex",
        "model": "gpt-5.6-sol-900k",
        "api_key": "never-write-this",
        "base_url": "",
        "api_mode": "codex_responses",
    }
    routed, metadata = _route_task_credentials(
        [
            {"goal": "mechanical check", "workload": "simple"},
            {"goal": "large review", "workload": "judgment", "context_window": "large"},
        ],
        base,
        {"resource_routing": policy()},
        object(),
    )

    assert [item["model"] for item in routed] == ["gpt-5.6-luna", "gpt-5.6-sol-900k"]
    assert base["model"] == "gpt-5.6-sol-900k"
    assert routed[0]["api_key"] == "never-write-this"
    assert "never-write-this" not in repr(metadata)
    assert metadata[1]["context_tier"] == "large"


def test_delegate_schema_advertises_task_axes_not_direct_model_selection():
    task_props = DELEGATE_TASK_SCHEMA["parameters"]["properties"]["tasks"]["items"]["properties"]
    assert task_props["workload"]["enum"] == [
        "simple", "volume", "substantive", "latency_critical", "judgment",
    ]
    assert task_props["context_window"]["enum"] == ["auto", "regular", "large"]
    assert task_props["estimated_context_tokens"]["minimum"] == 0
    assert "model" not in task_props


def test_delegate_integration_bypasses_quota_io_when_routing_is_off_or_pinned(monkeypatch):
    def unexpected(_policy):
        raise AssertionError("quota snapshot must not be read")

    monkeypatch.setattr("tools.delegation_resource_routing.load_quota_snapshot", unexpected)
    creds = {"provider": "openai-codex", "model": "gpt-5.6-terra"}
    tasks = [{"goal": "review", "workload": "judgment"}]

    off_creds, off_metadata = _route_task_credentials(
        tasks, creds, {"resource_routing": {"mode": "off"}}, object()
    )
    pinned_creds, pinned_metadata = _route_task_credentials(
        tasks,
        creds,
        {"model": "gpt-5.6-terra", "resource_routing": policy()},
        object(),
    )

    assert off_creds == [creds]
    assert pinned_creds == [creds]
    assert off_metadata == pinned_metadata == []
