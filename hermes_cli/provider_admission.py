"""Cross-process admission for subscription-backed provider requests.

The coordinator is intentionally transport-agnostic. Callers derive a lane that
represents one shared subscription surface, then hold the returned lease only
while the provider request is in flight. Different lanes never block each other.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import time
from typing import Any, Callable, Iterator
import uuid

from hermes_cli.active_sessions import (
    _FileLock,
    _process_start_time,
    _prune_dead,
    _read_entries,
    _write_entries,
)
from hermes_constants import get_hermes_home


_PRIORITY = {
    "foreground": 0,
    "delegation": 1,
    "compression": 2,
    "background_review": 2,
    "goal_judge": 2,
}


def provider_admission_lane(provider: str, *, access_token: str = "") -> str | None:
    """Return the shared subscription lane, or ``None`` for unconstrained providers."""
    if str(provider or "").strip().lower() != "openai-codex":
        return None
    if access_token:
        from agent.codex_headers import codex_cloudflare_headers

        account_id = codex_cloudflare_headers(access_token).get("ChatGPT-Account-ID")
        if account_id:
            digest = hashlib.sha256(account_id.encode("utf-8")).hexdigest()[:16]
            return f"openai-codex:account-{digest}"
    return "openai-codex:profile"


def format_provider_queue_wait(
    *,
    request_class: str,
    blocker: dict[str, Any],
    attempt: int,
    queued_seconds: float,
) -> str:
    """Build a concise truthful queue notice without exposing account identity."""
    requester = str(request_class or "request").replace("_", " ").capitalize()
    owner_class = str(blocker.get("request_class") or "request").replace("_", " ")
    owner_model = str(blocker.get("model") or "provider")
    owner_session = str(blocker.get("session_id") or "unknown")
    session_suffix = f"…{owner_session[-6:]}" if len(owner_session) > 6 else owner_session
    return (
        f"{requester} queued behind {owner_class} {owner_model} request in session "
        f"{session_suffix} — attempt {max(1, int(attempt))}, "
        f"{max(0, int(queued_seconds))}s queued"
    )


@dataclass(frozen=True)
class ProviderAdmissionRequest:
    lane: str
    request_class: str
    session_id: str
    provider: str
    model: str
    attempt: int = 1

    @property
    def priority(self) -> int:
        return _PRIORITY.get(self.request_class, 2)


@dataclass
class ProviderAdmissionLease:
    request_id: str
    state_path: Path
    lock_path: Path
    released: bool = False

    def release(self) -> None:
        if self.released:
            return
        with _FileLock(self.lock_path):
            entries = _prune_dead(_read_entries(self.state_path, strict=True), strict=True)
            kept = [entry for entry in entries if entry.get("lease_id") != self.request_id]
            _write_entries(self.state_path, kept)
        self.released = True


def _paths(registry_home: str | Path | None) -> tuple[Path, Path]:
    home = Path(registry_home) if registry_home is not None else Path(get_hermes_home())
    runtime = home / "runtime"
    return runtime / "provider_admission.json", runtime / "provider_admission.lock"


def provider_admission_snapshot(
    *, registry_home: str | Path | None = None
) -> list[dict[str, Any]]:
    """Return live admission requests and prune dead process owners."""
    state_path, lock_path = _paths(registry_home)
    with _FileLock(lock_path):
        entries = _read_entries(state_path, strict=True)
        live = _prune_dead(entries, strict=True)
        if live != entries:
            _write_entries(state_path, live)
        return [dict(entry) for entry in live]


def _entry(request_id: str, request: ProviderAdmissionRequest) -> dict[str, Any]:
    return {
        "lease_id": request_id,
        "session_id": request.session_id,
        "surface": "provider_admission",
        "pid": os.getpid(),
        "process_start_time": _process_start_time(os.getpid()),
        "track_liveness": True,
        "metadata": {"attempt": max(1, int(request.attempt))},
        "lane": request.lane,
        "request_class": request.request_class,
        "provider": request.provider,
        "model": request.model,
        "priority": request.priority,
        "created_at": time.time(),
        "state": "queued",
    }


def _drop_request(state_path: Path, lock_path: Path, request_id: str) -> None:
    with _FileLock(lock_path):
        entries = _prune_dead(_read_entries(state_path, strict=True), strict=True)
        _write_entries(
            state_path,
            [entry for entry in entries if entry.get("lease_id") != request_id],
        )


def acquire_provider_admission(
    request: ProviderAdmissionRequest,
    *,
    registry_home: str | Path | None = None,
    poll_interval: float = 0.05,
    timeout: float | None = None,
    cancelled: Callable[[], bool] | None = None,
    on_wait: Callable[[dict[str, Any]], None] | None = None,
) -> ProviderAdmissionLease:
    if not request.lane.strip():
        raise ValueError("provider admission lane must not be blank")
    if not request.session_id.strip():
        raise ValueError("provider admission session_id must not be blank")

    state_path, lock_path = _paths(registry_home)
    request_id = uuid.uuid4().hex
    own_entry = _entry(request_id, request)
    started = time.monotonic()

    try:
        while True:
            blocker: dict[str, Any] | None = None
            with _FileLock(lock_path):
                entries = _prune_dead(
                    _read_entries(state_path, strict=True), strict=True
                )
                current = next(
                    (entry for entry in entries if entry.get("lease_id") == request_id),
                    None,
                )
                if current is None:
                    entries.append(dict(own_entry))
                    current = entries[-1]

                lane_entries = [
                    entry for entry in entries if entry.get("lane") == request.lane
                ]
                active = next(
                    (entry for entry in lane_entries if entry.get("state") == "active"),
                    None,
                )
                queued = sorted(
                    (entry for entry in lane_entries if entry.get("state") == "queued"),
                    key=lambda entry: (
                        int(entry.get("priority", 2)),
                        float(entry.get("created_at", 0.0)),
                        str(entry.get("lease_id", "")),
                    ),
                )
                if active is None and queued and queued[0].get("lease_id") == request_id:
                    current["state"] = "active"
                    _write_entries(state_path, entries)
                    return ProviderAdmissionLease(request_id, state_path, lock_path)

                blocker = active or (queued[0] if queued else None)
                _write_entries(state_path, entries)

            if cancelled is not None and cancelled():
                raise InterruptedError("provider admission cancelled while queued")
            if timeout is not None and time.monotonic() - started >= timeout:
                raise TimeoutError("provider admission timed out while queued")
            if on_wait is not None and blocker is not None:
                on_wait(dict(blocker))
            time.sleep(max(0.001, poll_interval))
    except BaseException:
        _drop_request(state_path, lock_path, request_id)
        raise


@contextmanager
def provider_admission(
    request: ProviderAdmissionRequest,
    **kwargs: Any,
) -> Iterator[ProviderAdmissionLease]:
    lease = acquire_provider_admission(request, **kwargs)
    try:
        yield lease
    finally:
        lease.release()
