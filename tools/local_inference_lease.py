"""Cross-process lease for GPU-bound local inference workloads.

The kernel lock is authoritative. JSON metadata is diagnostic only and may be
left behind by a crashed owner; the next successful owner overwrites it.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

try:  # POSIX / WSL
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

try:  # Native Windows
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore[assignment]


class LocalInferenceLeaseTimeout(TimeoutError):
    """Raised when the shared local-inference lease cannot be acquired."""


_PROCESS_LOCK = threading.RLock()
_THREAD_STATE = threading.local()


def shared_local_inference_lock_path() -> Path:
    """Return a per-user lock path shared by all Hermes profiles/processes."""
    from hermes_constants import get_default_hermes_root

    return get_default_hermes_root() / "local-inference" / "lease.lock"


def _acquire_file_lock(handle) -> bool:
    if fcntl is not None:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (BlockingIOError, OSError):
            return False
    if msvcrt is not None:  # pragma: no cover - native Windows
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write("\0")
                handle.flush()
            handle.seek(0)
            getattr(msvcrt, "locking")(
                handle.fileno(),
                getattr(msvcrt, "LK_NBLCK"),
                1,
            )
            return True
        except OSError:
            return False
    raise RuntimeError("No supported file-lock implementation is available")


def _release_file_lock(handle) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    elif msvcrt is not None:  # pragma: no cover - native Windows
        handle.seek(0)
        getattr(msvcrt, "locking")(
            handle.fileno(),
            getattr(msvcrt, "LK_UNLCK"),
            1,
        )


@contextmanager
def local_inference_lease(
    owner: str,
    *,
    timeout: float = 120.0,
    lock_path: str | os.PathLike[str] | None = None,
    poll_interval: float = 0.05,
) -> Iterator[None]:
    """Exclusively lease local inference across threads and Hermes processes.

    The lease is re-entrant within one thread. A crashed process cannot strand
    it because the operating system releases the file lock on descriptor exit.
    """
    path = Path(lock_path) if lock_path is not None else shared_local_inference_lock_path()
    path = path.expanduser()
    deadline = time.monotonic() + max(0.0, float(timeout))

    depth = int(getattr(_THREAD_STATE, "depth", 0))
    if depth:
        active_path = getattr(_THREAD_STATE, "path", None)
        if active_path != path:
            raise RuntimeError("Cannot nest local inference leases with different lock paths")
        _THREAD_STATE.depth = depth + 1
        try:
            yield
        finally:
            _THREAD_STATE.depth -= 1
        return

    remaining = max(0.0, deadline - time.monotonic())
    if not _PROCESS_LOCK.acquire(timeout=remaining):
        raise LocalInferenceLeaseTimeout(
            f"Timed out after {timeout:.1f}s waiting for local inference lease ({owner})"
        )

    handle = None
    acquired = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+", encoding="utf-8")
        while not _acquire_file_lock(handle):
            if time.monotonic() >= deadline:
                raise LocalInferenceLeaseTimeout(
                    f"Timed out after {timeout:.1f}s waiting for local inference lease ({owner})"
                )
            time.sleep(max(0.001, poll_interval))
        acquired = True
        metadata = {
            "owner": str(owner),
            "pid": os.getpid(),
            "acquired_at": datetime.now(timezone.utc).isoformat(),
        }
        handle.seek(0)
        handle.truncate()
        json.dump(metadata, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
        _THREAD_STATE.depth = 1
        _THREAD_STATE.path = path
        try:
            yield
        finally:
            _THREAD_STATE.depth = 0
            _THREAD_STATE.path = None
            handle.seek(0)
            handle.truncate()
            handle.flush()
    finally:
        if handle is not None:
            if acquired:
                _release_file_lock(handle)
            handle.close()
        _PROCESS_LOCK.release()


def normalize_ollama_base_url(base_url: str) -> str:
    """Convert an Ollama OpenAI-compatible URL to its native API origin."""
    normalized = str(base_url or "").strip().rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return normalized.rstrip("/")


def unload_ollama_models(base_url: str, *, timeout: float = 10.0) -> list[str]:
    """Expire every model currently resident in one Ollama server."""
    origin = normalize_ollama_base_url(base_url)
    if not origin:
        return []

    request = urllib.request.Request(f"{origin}/api/ps", method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))

    names: list[str] = []
    for item in payload.get("models", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "").strip()
        if name and name not in names:
            names.append(name)

    for name in names:
        body = json.dumps({"model": name, "keep_alive": 0}).encode("utf-8")
        expire = urllib.request.Request(
            f"{origin}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(expire, timeout=timeout) as response:  # noqa: S310
            response.read()
    return names
