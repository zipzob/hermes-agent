"""Crash-safe cross-process ownership for the local microphone."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

try:
    import fcntl
except ImportError:  # pragma: no cover - native Windows
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore[assignment]


_PROCESS_LOCK = threading.Lock()


def voice_capture_lock_path() -> Path:
    from hermes_constants import get_default_hermes_root

    return get_default_hermes_root() / "voice" / "capture.lock"


def _try_lock(handle: TextIO) -> bool:
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
                handle.fileno(), getattr(msvcrt, "LK_NBLCK"), 1
            )
            return True
        except OSError:
            return False
    raise RuntimeError("No supported file-lock implementation is available")


def _unlock(handle: TextIO) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    elif msvcrt is not None:  # pragma: no cover - native Windows
        handle.seek(0)
        getattr(msvcrt, "locking")(
            handle.fileno(), getattr(msvcrt, "LK_UNLCK"), 1
        )


class VoiceCaptureLease:
    def __init__(self, handle: TextIO) -> None:
        self._handle: TextIO | None = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            handle.seek(0)
            handle.truncate()
            handle.flush()
            _unlock(handle)
        finally:
            handle.close()
            _PROCESS_LOCK.release()


def acquire_voice_capture_lease(
    owner: str,
    *,
    session_id: str | None = None,
    lock_path: str | os.PathLike[str] | None = None,
) -> VoiceCaptureLease | None:
    """Acquire the microphone without waiting, or return ``None`` if busy."""
    if not _PROCESS_LOCK.acquire(blocking=False):
        return None

    path = Path(lock_path) if lock_path is not None else voice_capture_lock_path()
    handle: TextIO | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+", encoding="utf-8")
        if not _try_lock(handle):
            handle.close()
            _PROCESS_LOCK.release()
            return None
        metadata = {
            "acquired_at": datetime.now(timezone.utc).isoformat(),
            "owner": str(owner),
            "pid": os.getpid(),
            "session_id": str(session_id or ""),
        }
        handle.seek(0)
        handle.truncate()
        json.dump(metadata, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
        return VoiceCaptureLease(handle)
    except Exception:
        if handle is not None and not handle.closed:
            handle.close()
        _PROCESS_LOCK.release()
        raise
