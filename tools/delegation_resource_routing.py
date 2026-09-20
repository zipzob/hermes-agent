"""Deterministic, quota-aware model selection for delegated children.

Strength and context capacity are independent axes.  A ``-900k`` alias is
selected only when an isolated child's declared/estimated working set needs it;
the parent's large transcript is never inherited by implication.  Operator
model pins always win, and Astra is intentionally absent from automatic lanes.
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent.model_metadata import estimate_tokens_rough, is_codex_900k_base, strip_codex_context_variant_suffix

logger = logging.getLogger("tools.delegate_tool")

_STATES = {"GREEN", "YELLOW", "UNKNOWN", "ORANGE", "RED", "EXHAUSTED"}
_WORKLOADS = {"simple", "volume", "substantive", "latency_critical", "judgment"}
_DEFAULT_MODELS = {
    # GPT-5.4 Mini is retired for ChatGPT/Codex sign-in. Keep it available
    # only through an explicit operator pin for API-key/legacy routes.
    "simple": "gpt-5.6-luna",
    "volume": "gpt-5.6-luna",
    "substantive": "gpt-5.6-terra",
    "latency_critical": "gpt-5.6-terra",
    "judgment": "gpt-5.6-terra",
}


@dataclass(frozen=True)
class DelegationRoute:
    model: str
    workload: str
    context_tier: str
    estimated_context_tokens: int
    reasons: tuple[str, ...]


def delegation_control_plane_diagnostics(
    route: DelegationRoute, *, configured_limit: int, occupied_slots: int, child_timeout_seconds: float | None,
    model_authorization_required: bool,
) -> dict[str, dict[str, Any]]:
    """Keep capacity, authorization, context, and provider observations separate."""
    return {
        "max_concurrent_children": {"configured_limit": configured_limit},
        "occupied_slots": {"current": occupied_slots},
        "child_timeout": {"seconds": child_timeout_seconds},
        "model_authorization": {"required": model_authorization_required},
        "context_tier": {
            "selected": route.context_tier,
            "estimated_context_tokens": route.estimated_context_tokens,
        },
        # Governor/routing state is advisory. Only a real provider response can
        # establish an exhausted or rate-limited provider quota.
        "provider_quota": {"status": "not_observed"},
    }


def _state(value: Any) -> str:
    normalized = str(value or "UNKNOWN").upper()
    return normalized if normalized in _STATES else "UNKNOWN"


def quota_pools(snapshot: Mapping[str, Any] | None) -> dict[str, str]:
    """Reduce a governor snapshot to worst general/Spark/Astra pool states."""
    if not snapshot:
        return {"general": "UNKNOWN", "spark": "UNKNOWN", "astra": "UNKNOWN"}
    direct = {key: _state(snapshot.get(key)) for key in ("general", "spark", "astra")}
    if any(key in snapshot for key in direct):
        return direct

    rank = {name: index for index, name in enumerate(("GREEN", "YELLOW", "UNKNOWN", "ORANGE", "RED", "EXHAUSTED"))}
    result: dict[str, list[str]] = {"general": [], "spark": [], "astra": []}
    windows = snapshot.get("quota_windows") if isinstance(snapshot, Mapping) else None
    forecasts = snapshot.get("quota_forecasts") if isinstance(snapshot, Mapping) else None
    forecasts_by_name = {
        str(item.get("name")): _state(item.get("state"))
        for item in forecasts or []
        if isinstance(item, Mapping)
    }
    for window in windows or []:
        if not isinstance(window, Mapping):
            continue
        raw_metadata = window.get("metadata")
        metadata: Mapping[str, Any] = raw_metadata if isinstance(raw_metadata, Mapping) else {}
        label = " ".join(
            str(value or "")
            for value in (window.get("name"), metadata.get("limit_id"), metadata.get("limit_name"))
        ).casefold()
        pool = "spark" if "spark" in label or "bengalfox" in label else "astra" if "astra" in label else "general"
        state = forecasts_by_name.get(str(window.get("name")))
        if state is None:
            used = window.get("used_percent")
            state = "EXHAUSTED" if window.get("hard_limit_reached") is True or isinstance(used, (int, float)) and used >= 100 else "UNKNOWN"
        result[pool].append(state)
    return {
        pool: max(states, key=lambda item: rank[item]) if states else "UNKNOWN"
        for pool, states in result.items()
    }


def load_quota_snapshot(policy: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Read one trusted governor snapshot; failure is conservative and non-fatal."""
    path = str(policy.get("quota_snapshot_file") or "").strip()
    command = policy.get("quota_snapshot_command")
    try:
        if path:
            payload = Path(path).expanduser().read_text(encoding="utf-8")
        elif command:
            argv = shlex.split(command) if isinstance(command, str) else [str(part) for part in command]
            if not argv:
                return None
            completed = subprocess.run(
                argv,
                check=True,
                capture_output=True,
                text=True,
                timeout=max(0.1, min(float(policy.get("quota_timeout_seconds", 3)), 10.0)),
            )
            payload = completed.stdout
        else:
            return None
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, Mapping) else None
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        logger.warning("Delegation resource-routing quota snapshot unavailable: %s", exc)
        return None


def _estimated_tokens(task: Mapping[str, Any]) -> int:
    declared = task.get("estimated_context_tokens")
    if isinstance(declared, int) and declared >= 0:
        return declared
    return estimate_tokens_rough(f"{task.get('goal', '')}\n{task.get('context', '')}")


def _base_model(workload: str, models: Mapping[str, Any]) -> tuple[str, bool]:
    configured = str(models.get(workload) or _DEFAULT_MODELS[workload]).strip()
    # Context aliases are selected below, not embedded in strength configuration.
    base = strip_codex_context_variant_suffix(configured)
    operator_only = any(name in base.casefold() for name in ("sol", "spark", "astra"))
    return (_DEFAULT_MODELS[workload] if operator_only else base), operator_only


def route_delegation_tasks(
    tasks: Sequence[Mapping[str, Any]],
    *,
    parent_model: str,
    policy: Mapping[str, Any] | None,
    quota_snapshot: Mapping[str, Any] | None = None,
    parent_context_tokens: int | None = None,
    explicit_model_pin: str | None = None,
) -> list[DelegationRoute]:
    """Return one deterministic route per isolated task.

    ``parent_context_tokens`` is accepted for observability/API stability but is
    deliberately not used: children receive only their own goal/context.
    """
    del parent_context_tokens
    policy = policy or {}
    enabled = str(policy.get("mode") or "off").casefold() == "automatic_safe"
    raw_models = policy.get("models")
    models: Mapping[str, Any] = raw_models if isinstance(raw_models, Mapping) else {}
    pools = quota_pools(quota_snapshot)
    trigger = max(16_000, int(policy.get("large_context_trigger_tokens") or 220_000))
    results: list[DelegationRoute] = []

    for task in tasks:
        workload = str(task.get("workload") or "substantive").casefold()
        if workload not in _WORKLOADS:
            workload = "substantive"
        estimated = _estimated_tokens(task)
        reasons: list[str] = []

        if explicit_model_pin:
            model = explicit_model_pin
            reasons.append("explicit_pin")
        elif not enabled:
            model = parent_model
            reasons.append("routing_off")
        else:
            def automatic_model(lane: str) -> str:
                selected, ignored = _base_model(lane, models)
                if ignored and "operator_only_model_ignored" not in reasons:
                    reasons.append("operator_only_model_ignored")
                return selected

            model = automatic_model(workload)
            if workload == "latency_critical":
                # Spark is a volatile preview pool. Automatic classification
                # never spends it; an explicit model pin remains authoritative.
                model = automatic_model("substantive")
                reasons.append("spark_explicit_only")
            if pools["general"] in {"ORANGE", "RED", "EXHAUSTED"}:
                if workload == "judgment":
                    model = automatic_model("substantive")
                elif workload == "substantive" and pools["general"] in {"RED", "EXHAUSTED"}:
                    model = automatic_model("volume")
                reasons.append(f"general_quota_{pools['general'].lower()}")
            reasons.append(f"workload_{workload}")

        requested_tier = str(task.get("context_window") or "auto").casefold()
        route_is_owned = enabled and not explicit_model_pin
        large_needed = route_is_owned and (
            requested_tier == "large" or requested_tier == "auto" and estimated >= trigger
        )
        base_model = strip_codex_context_variant_suffix(model)
        if large_needed and is_codex_900k_base(base_model):
            model = f"{base_model}-900k"
            tier = "large"
            reasons.append("large_context_required")
        else:
            tier = "large" if model.endswith("-900k") else "regular"
            if large_needed and tier == "regular":
                reasons.append("large_context_unavailable")

        results.append(DelegationRoute(model, workload, tier, estimated, tuple(reasons)))
    return results
