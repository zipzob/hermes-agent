"""User-authorized, child-scoped model escalation for ``delegate_task``.

The agent may propose a more capable child route, but it cannot select one from
prose alone. A successful interactive decision mints a short-lived, one-use
capability bound to the current session, provider, exact target model and a
normalized task scope hash. ``delegate_task`` consumes that capability before
building the child.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from tools.registry import registry, tool_error

logger = logging.getLogger("tools.model_escalation")

_ALLOWED_MODELS = frozenset({
    "gpt-5.3-codex-spark",
    "gpt-5.6-sol",
    "gpt-5.6-sol-900k",
    "gpt-6-astra",
    "gpt-6-astra-900k",
})
_MODEL_STRENGTH = {
    "gpt-5.3-codex-spark": 0,
    "gpt-5.6-sol": 1,
    "gpt-5.6-sol-900k": 1,
    "gpt-6-astra": 2,
    "gpt-6-astra-900k": 2,
}
_DEFAULT_TTL_SECONDS = 300
_DEFAULT_COOLDOWN_SECONDS = 120
_DEFAULT_MAX_REQUESTS = 3
_MAX_SCOPE_CHARS = 2_000
_DEFAULT_LARGE_CONTEXT_TRIGGER_TOKENS = 220_000


@dataclass(frozen=True)
class _Authorization:
    session_key: str
    provider: str
    target_model: str
    scope_hash: str
    expires_at: float


_lock = threading.Lock()
_authorizations: dict[str, _Authorization] = {}
_request_times: dict[str, list[float]] = {}
_last_request_at: dict[str, float] = {}


def _scope_hash(scope: str) -> str:
    normalized = " ".join(scope.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _bounded_int(raw: Any, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        return default


def _policy(raw: Any = None) -> dict[str, int | bool]:
    value = raw if isinstance(raw, dict) else {}
    return {
        "enabled": value.get("enabled", True) is not False,
        "authorization_ttl_seconds": _bounded_int(value.get("authorization_ttl_seconds"), _DEFAULT_TTL_SECONDS, 30),
        "cooldown_seconds": _bounded_int(value.get("cooldown_seconds"), _DEFAULT_COOLDOWN_SECONDS, 0),
        "max_requests_per_session": _bounded_int(value.get("max_requests_per_session"), _DEFAULT_MAX_REQUESTS, 1),
        "large_context_trigger_tokens": _bounded_int(
            value.get("large_context_trigger_tokens"), _DEFAULT_LARGE_CONTEXT_TRIGGER_TOKENS, 1,
        ),
    }


def _audit(event: str, *, session_key: str, target_model: str = "", scope_hash: str = "") -> None:
    # Log only hashes: raw scope can contain private material and must not become
    # a second durable transcript through this safety mechanism.
    logger.info(
        "model_escalation event=%s session=%s target=%s scope=%s",
        event,
        hashlib.sha256(session_key.encode("utf-8")).hexdigest()[:12] if session_key else "",
        target_model,
        scope_hash[:12],
    )


def _clean_model(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _is_valid_lower_model(lower: str, target: str) -> bool:
    """A lower choice may not silently increase model strength or capacity."""
    return (
        _MODEL_STRENGTH.get(lower, -1) < _MODEL_STRENGTH.get(target, -1)
        and (not lower.endswith("-900k") or target.endswith("-900k"))
    )


def _validate_request(
    target_model: Any, scope: Any, provider: Any, policy: dict[str, int | bool], estimated_context_tokens: Any,
) -> tuple[str, str, str | None]:
    target = _clean_model(target_model)
    normalized_scope = " ".join(str(scope or "").split())
    if not policy["enabled"]:
        return "", "", "Model-escalation proposals are disabled by delegation.resource_routing.escalation.enabled."
    if str(provider or "") != "openai-codex":
        return "", "", "Model escalation is available only for inherited openai-codex child routes."
    if target not in _ALLOWED_MODELS:
        return "", "", "The requested target is not an operator-only escalation model."
    if target.endswith("-900k") and (
        not isinstance(estimated_context_tokens, int)
        or estimated_context_tokens < policy["large_context_trigger_tokens"]
    ):
        return "", "", (
            "A 900k child requires an isolated context estimate at or above "
            f"{policy['large_context_trigger_tokens']} tokens."
        )
    if not normalized_scope or len(normalized_scope) > _MAX_SCOPE_CHARS:
        return "", "", f"scope must contain 1-{_MAX_SCOPE_CHARS} non-whitespace characters."
    return target, normalized_scope, None


def _choice(response: Any) -> str:
    return " ".join(str(response or "").casefold().split())


def request_model_escalation(
    *, target_model: str, reason: str, scope: str, provider: str, session_key: str,
    callback: Optional[Callable], lower_model: Optional[str] = None, context_window: str = "auto",
    estimated_context_tokens: Optional[int] = None, policy: Any = None,
) -> str:
    """Ask the user to authorize one bounded delegated-child route.

    This function intentionally does not change the active session model and
    returns an opaque capability only after an affirmative user decision.
    """
    effective_policy = _policy(policy)
    target, normalized_scope, error = _validate_request(
        target_model, scope, provider, effective_policy, estimated_context_tokens,
    )
    if error:
        return tool_error(error)
    if callback is None or not session_key:
        return tool_error("Model escalation requires an interactive session with a bound session identity.")

    lower = _clean_model(lower_model)
    if lower and lower not in _ALLOWED_MODELS:
        return tool_error("lower_model must be an operator-only escalation model when supplied.")
    if lower and not _is_valid_lower_model(lower, target):
        return tool_error(
            "lower_model must have lower model strength and no greater context capacity than target_model."
        )
    if lower.endswith("-900k") and (
        not isinstance(estimated_context_tokens, int)
        or estimated_context_tokens < effective_policy["large_context_trigger_tokens"]
    ):
        return tool_error(
            "A 900k lower model requires an isolated context estimate at or above "
            f"{effective_policy['large_context_trigger_tokens']} tokens."
        )
    scope_digest = _scope_hash(normalized_scope)
    now = time.monotonic()
    with _lock:
        history = [at for at in _request_times.get(session_key, []) if now - at < 3_600]
        _request_times[session_key] = history
        if len(history) >= effective_policy["max_requests_per_session"]:
            return tool_error("Model-escalation proposal limit reached for this session; continue with the current route.")
        last = _last_request_at.get(session_key)
        if last is not None and now - last < effective_policy["cooldown_seconds"]:
            return tool_error("Model-escalation proposal cooldown is active; continue with the current route.")
        history.append(now)
        _last_request_at[session_key] = now

    context_note = f" Context tier: {context_window or 'auto'}"
    if isinstance(estimated_context_tokens, int) and estimated_context_tokens >= 0:
        context_note += f" Estimated isolated context: {estimated_context_tokens} tokens."
    question = (
        f"Propose {target} for one delegated child? Reason: {str(reason or '').strip() or 'higher-confidence review requested'}. "
        f"Scope: {normalized_scope}.{context_note} This uses higher quota; it does not switch this session's model."
    )
    approve_choice = f"Approve {target}"
    lower_choice = f"Use {lower}" if lower else None
    choices = [approve_choice, *( [lower_choice] if lower_choice else []), "Decline", "Defer"]
    _audit("proposed", session_key=session_key, target_model=target, scope_hash=scope_digest)
    try:
        response = callback(question, choices)
    except Exception as exc:  # user interaction is an external boundary
        _audit("undeliverable", session_key=session_key, target_model=target, scope_hash=scope_digest)
        return tool_error(f"Model-escalation proposal could not be delivered: {exc}")

    response_choice = _choice(response)
    selected = target if response_choice == _choice(approve_choice) else lower if lower_choice and response_choice == _choice(lower_choice) else ""
    if not selected:
        event = "deferred" if response_choice == _choice("Defer") else "declined"
        _audit(event, session_key=session_key, target_model=target, scope_hash=scope_digest)
        return json.dumps({"status": event, "target_model": target}, ensure_ascii=False)
    if not lower and selected != target:
        _audit("lower_unavailable", session_key=session_key, target_model=target, scope_hash=scope_digest)
        return json.dumps({"status": "declined", "target_model": target}, ensure_ascii=False)

    authorization = secrets.token_urlsafe(24)
    expires_at = time.monotonic() + effective_policy["authorization_ttl_seconds"]
    with _lock:
        _authorizations[authorization] = _Authorization(
            session_key=session_key, provider=provider, target_model=selected,
            scope_hash=scope_digest, expires_at=expires_at,
        )
    _audit("approved" if selected == target else "lower_selected", session_key=session_key, target_model=selected, scope_hash=scope_digest)
    return json.dumps({
        "status": "approved", "target_model": selected, "model_authorization": authorization,
        "expires_in_seconds": effective_policy["authorization_ttl_seconds"],
    }, ensure_ascii=False)


def consume_model_escalation_authorization(
    authorization: Any, *, session_key: str, provider: str, target_model: Any, scope: str,
) -> Optional[str]:
    """Consume exactly one capability, returning an error string on mismatch."""
    token = _clean_model(authorization)
    target = _clean_model(target_model)
    scope_digest = _scope_hash(scope)
    if not token:
        return "An explicit task model requires a user-authorized model escalation."
    with _lock:
        record = _authorizations.pop(token, None)
    if record is None:
        _audit("rejected_missing_or_reused", session_key=session_key, target_model=target, scope_hash=scope_digest)
        return "The model-escalation authorization is missing, expired, or already used."
    if time.monotonic() >= record.expires_at:
        _audit("expired", session_key=session_key, target_model=target, scope_hash=scope_digest)
        return "The model-escalation authorization expired."
    if (record.session_key != session_key or record.provider != provider or record.target_model != target or record.scope_hash != scope_digest):
        _audit("rejected_mismatch", session_key=session_key, target_model=target, scope_hash=scope_digest)
        return "The model-escalation authorization does not match this session, provider, model, or task scope."
    _audit("consumed", session_key=session_key, target_model=target, scope_hash=scope_digest)
    return None


def reset_for_tests() -> None:
    with _lock:
        _authorizations.clear()
        _request_times.clear()
        _last_request_at.clear()


MODEL_ESCALATION_SCHEMA = {
    "name": "request_model_escalation",
    "description": (
        "Propose a more capable model for ONE bounded delegated child. The user authorizes, chooses a lower model, "
        "declines, or defers. Never changes the active session model. On approval, use the returned target_model and "
        "model_authorization together in exactly one delegate_task task."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target_model": {"type": "string"},
            "reason": {"type": "string"},
            "scope": {"type": "string"},
            "lower_model": {"type": "string"},
            "context_window": {"type": "string", "enum": ["auto", "regular", "large"]},
            "estimated_context_tokens": {"type": "integer", "minimum": 0},
        },
        "required": ["target_model", "reason", "scope"],
    },
}


registry.register(
    name="request_model_escalation",
    toolset="delegation",
    schema=MODEL_ESCALATION_SCHEMA,
    handler=lambda args, **_kw: tool_error("request_model_escalation requires an active interactive agent session."),
    emoji="↗",
)
