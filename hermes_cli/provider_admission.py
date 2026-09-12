"""Cross-process admission for subscription-backed provider requests.

The coordinator is intentionally transport-agnostic. Callers derive a lane that
represents one shared subscription surface, then hold the returned lease only
while the provider request is in flight. Different lanes never block each other.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
import errno
import hashlib
import logging
import math
import os
from pathlib import Path
import time
import threading
from typing import Any
import uuid

from hermes_cli.active_sessions import (
    _FileLock,
    _process_start_time,
    _prune_dead,
    _read_entries,
    _write_entries,
)
from hermes_constants import get_hermes_home


logger = logging.getLogger(__name__)


@contextmanager
def _registry_lock(
    path: Path, *, deadline: float | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Iterator[None]:
    # Reuse the cross-platform lock, but never block a cancellation-aware waiter
    # inside flock/msvcrt. Cleanup/status get their own bounded two-second budget.
    if deadline is None:
        deadline = time.monotonic() + 2.0
    lock = _FileLock(path, blocking=False)
    while True:
        if cancelled is not None and cancelled():
            raise InterruptedError("provider admission cancelled waiting for registry lock")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("provider admission registry lock timed out")
        try:
            lock.__enter__()
            break
        except RuntimeError as exc:
            cause = exc.__cause__
            if not isinstance(cause, OSError) or cause.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            time.sleep(min(0.01, remaining))
    try:
        yield
    finally:
        lock.__exit__(None, None, None)


def _live_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Queue deadlines share the host's monotonic clock. Process identity pruning
    # handles reboot/PID reuse. Never time-evict an active physical worker.
    now = time.monotonic()
    return [entry for entry in _prune_dead(entries, strict=True)
            if entry.get("state") != "queued"
            or entry.get("queue_deadline_monotonic", float("inf")) > now]


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
        with _registry_lock(self.lock_path):
            entries = _live_entries(_read_entries(self.state_path, strict=True))
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
    with _registry_lock(lock_path):
        entries = _read_entries(state_path, strict=True)
        live = _live_entries(entries)
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
    with _registry_lock(lock_path):
        entries = _live_entries(_read_entries(state_path, strict=True))
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
) -> ProviderAdmissionLease | None:
    from hermes_cli.config import load_config_readonly

    config = load_config_readonly().get("provider_admission", {})
    if not isinstance(config, dict):
        raise ValueError("provider_admission must be a mapping")
    capacity = config.get("max_in_flight", 0)
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 0:
        raise ValueError("provider_admission.max_in_flight must be a nonnegative integer")
    if cancelled is not None and cancelled():
        raise InterruptedError("provider admission cancelled before dispatch")
    if capacity == 0:
        return None  # ponytail: no proven universal account limit; opt in after measurement.
    if timeout is None:
        timeout = config.get("queue_timeout", 120.0)
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0):
        raise ValueError("provider_admission.queue_timeout must be a positive finite number")
    if not request.lane.strip():
        raise ValueError("provider admission lane must not be blank")
    if not request.session_id.strip():
        raise ValueError("provider admission session_id must not be blank")

    state_path, lock_path = _paths(registry_home)
    request_id = uuid.uuid4().hex
    own_entry = _entry(request_id, request)
    started = time.monotonic()
    deadline = started + timeout
    own_entry["queue_deadline_monotonic"] = deadline
    registered = False

    try:
        while True:
            if cancelled is not None and cancelled():
                raise InterruptedError("provider admission cancelled while queued")
            if time.monotonic() - started >= timeout:
                raise TimeoutError("provider admission timed out while queued")
            blocker: dict[str, Any] | None = None
            with _registry_lock(lock_path, deadline=deadline, cancelled=cancelled):
                # Check again after lock acquisition: cancellation must not become dispatch.
                if cancelled is not None and cancelled():
                    raise InterruptedError("provider admission cancelled while queued")
                if time.monotonic() - started >= timeout:
                    raise TimeoutError("provider admission timed out while queued")
                stored = _read_entries(state_path, strict=True)
                entries = _live_entries(stored)
                changed = entries != stored
                current = next(
                    (entry for entry in entries if entry.get("lease_id") == request_id),
                    None,
                )
                if current is None:
                    entries.append(dict(own_entry))
                    current = entries[-1]
                    changed = True

                lane_entries = [
                    entry for entry in entries if entry.get("lane") == request.lane
                ]
                active = [entry for entry in lane_entries if entry.get("state") == "active"]
                queued = sorted(
                    (entry for entry in lane_entries if entry.get("state") == "queued"),
                    key=lambda entry: (
                        int(entry.get("priority", 2)),
                        float(entry.get("created_at", 0.0)),
                        str(entry.get("lease_id", "")),
                    ),
                )
                if len(active) < capacity and queued and queued[0].get("lease_id") == request_id:
                    current["state"] = "active"
                    registered = True
                    _write_entries(state_path, entries)
                    return ProviderAdmissionLease(request_id, state_path, lock_path)

                blocker = active[0] if active else (queued[0] if queued else None)
                if changed:
                    registered = True
                    _write_entries(state_path, entries)

            if cancelled is not None and cancelled():
                raise InterruptedError("provider admission cancelled while queued")
            if timeout is not None and time.monotonic() - started >= timeout:
                raise TimeoutError("provider admission timed out while queued")
            if on_wait is not None and blocker is not None:
                on_wait(dict(blocker))
            time.sleep(min(max(0.001, poll_interval), max(0.0, timeout - (time.monotonic() - started))))
    except BaseException:
        if registered:
            try:
                _drop_request(state_path, lock_path, request_id)
            except Exception:
                # Preserve cancellation/timeout. An unavailable registry cannot be
                # mutated safely; the queued deadline lets the next reader prune it.
                logger.warning("Provider admission cleanup failed; queued request will expire", exc_info=True)
        raise


@contextmanager
def provider_admission(
    request: ProviderAdmissionRequest,
    **kwargs: Any,
) -> Iterator[ProviderAdmissionLease | None]:
    lease = acquire_provider_admission(request, **kwargs)
    try:
        yield lease
    finally:
        if lease is not None:
            lease.release()


@asynccontextmanager
async def provider_admission_async(
    request: ProviderAdmissionRequest, **kwargs: Any,
) -> AsyncIterator[ProviderAdmissionLease | None]:
    """Keep blocking registry I/O off-loop; drain ownership even on repeated cancel.

    Cancelling to_thread's awaiter cannot stop its thread. Shield acquisition,
    signal the queue loop explicitly, then join and release before propagating.
    """
    stop = threading.Event()
    cancelled = kwargs.pop("cancelled", None)
    pending = asyncio.create_task(asyncio.to_thread(
        acquire_provider_admission, request,
        cancelled=lambda: stop.is_set() or (cancelled is not None and cancelled()),
        **kwargs,
    ))
    try:
        yield await asyncio.shield(pending)
    finally:
        stop.set()

        async def release() -> None:
            try:
                lease = await pending
            except InterruptedError:
                return  # The stopped waiter removed its own queue entry.
            if lease is not None:
                await asyncio.to_thread(lease.release)

        cleanup = asyncio.create_task(release())
        cancellation = None
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError as exc:
                cancellation = exc
        cleanup.result()
        if cancellation is not None:
            raise cancellation
