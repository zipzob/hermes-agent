from __future__ import annotations

import base64
import os
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any

from hermes_cli import provider_admission as admission_module
from hermes_cli.provider_admission import ProviderAdmissionRequest, provider_admission


_CHILD = r"""
import sys
import time
from pathlib import Path
from hermes_cli.provider_admission import ProviderAdmissionRequest, provider_admission

home = Path(sys.argv[1])
name = sys.argv[2]
request_class = sys.argv[3]
lane = sys.argv[4] if len(sys.argv) > 4 else "openai-codex:synthetic-account"
release = home / f"release-{name}"
request = ProviderAdmissionRequest(
    lane=lane,
    request_class=request_class,
    session_id=f"session-{name}",
    provider="openai-codex",
    model="gpt-5.6-sol",
)
with provider_admission(request, registry_home=home, poll_interval=0.01, timeout=5.0):
    (home / f"entered-{name}").touch()
    deadline = time.monotonic() + 5.0
    while not release.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
"""


def _wait_for(path: Path, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.01)
    return path.exists()


def _wait_for_registry_state(
    home: Path, session_id: str, state: str, timeout: float = 3.0
) -> bool:
    registry = home / "runtime" / "provider_admission.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            entries = json.loads(registry.read_text())["entries"]
        except (FileNotFoundError, KeyError, ValueError):
            entries = []
        if any(
            entry.get("session_id") == session_id and entry.get("state") == state
            for entry in entries
        ):
            return True
        time.sleep(0.01)
    return False


def test_snapshot_retains_attempt_as_bounded_status_metadata(tmp_path):
    request = ProviderAdmissionRequest(
        **{
            "lane": "openai-codex:synthetic-account",
            "request_class": "foreground",
            "session_id": "session-attempt",
            "provider": "openai-codex",
            "model": "gpt-5.6-sol",
            "attempt": 3,
        }
    )

    with provider_admission(request, registry_home=tmp_path):
        snapshot = admission_module.provider_admission_snapshot(registry_home=tmp_path)

    assert snapshot[0]["metadata"] == {"attempt": 3}


def test_same_lane_requests_are_serialized_across_processes(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(Path.cwd())}
    first = subprocess.Popen(
        [sys.executable, "-c", _CHILD, str(tmp_path), "first", "foreground"],
        env=env,
    )
    second = None
    try:
        assert _wait_for(tmp_path / "entered-first")
        second = subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(tmp_path), "second", "foreground"],
            env=env,
        )
        time.sleep(0.2)
        assert not (tmp_path / "entered-second").exists()

        (tmp_path / "release-first").touch()
        assert _wait_for(tmp_path / "entered-second")
        (tmp_path / "release-second").touch()
    finally:
        (tmp_path / "release-first").touch()
        (tmp_path / "release-second").touch()
        for child in (first, second):
            if child is not None:
                child.wait(timeout=10)

    assert first.returncode == 0
    assert second is not None and second.returncode == 0


def test_admission_lane_is_limited_to_openai_codex():
    assert admission_module.provider_admission_lane(
        "openai-codex", access_token="not-a-jwt"
    ) == "openai-codex:profile"
    assert admission_module.provider_admission_lane("ollama", access_token="") is None
    assert admission_module.provider_admission_lane("openrouter", access_token="") is None


def _codex_token(account_id: str, signature: str) -> str:
    claims = {"https://api.openai.com/auth": {"chatgpt_account_id": account_id}}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{payload}.{signature}"


def test_admission_lane_uses_stable_redacted_codex_account_identity():
    first = admission_module.provider_admission_lane(
        "openai-codex", access_token=_codex_token("account-a", "old")
    )
    refreshed = admission_module.provider_admission_lane(
        "openai-codex", access_token=_codex_token("account-a", "new")
    )
    other = admission_module.provider_admission_lane(
        "openai-codex", access_token=_codex_token("account-b", "new")
    )

    assert first == refreshed
    assert first != other
    assert "account-a" not in str(first)


def test_admission_snapshot_tracks_active_lease_and_cleanup(tmp_path):
    request = ProviderAdmissionRequest(
        lane="openai-codex:profile",
        request_class="foreground",
        session_id="session-snapshot",
        provider="openai-codex",
        model="gpt-5.6-sol",
    )

    assert admission_module.provider_admission_snapshot(registry_home=tmp_path) == []
    with provider_admission(request, registry_home=tmp_path):
        entries = admission_module.provider_admission_snapshot(registry_home=tmp_path)
        assert len(entries) == 1
        assert entries[0]["state"] == "active"
    assert admission_module.provider_admission_snapshot(registry_home=tmp_path) == []


def test_queue_wait_message_identifies_class_owner_attempt_and_elapsed():
    message = admission_module.format_provider_queue_wait(
        request_class="compression",
        blocker={
            "request_class": "foreground",
            "model": "gpt-5.6-sol",
            "session_id": "20260908_162215_70dd49",
        },
        attempt=2,
        queued_seconds=12.8,
    )

    assert message == (
        "Compression queued behind foreground gpt-5.6-sol request in session "
        "…70dd49 — attempt 2, 12s queued"
    )


def test_foreground_overtakes_queued_compression(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(Path.cwd())}
    children: list[subprocess.Popen] = []

    def start(name: str, request_class: str) -> subprocess.Popen:
        child = subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(tmp_path), name, request_class],
            env=env,
        )
        children.append(child)
        return child

    start("blocker", "foreground")
    try:
        assert _wait_for(tmp_path / "entered-blocker")
        start("compression", "compression")
        assert _wait_for_registry_state(
            tmp_path, "session-compression", "queued"
        )
        start("foreground", "foreground")
        assert _wait_for_registry_state(tmp_path, "session-foreground", "queued")

        (tmp_path / "release-blocker").touch()
        assert _wait_for(tmp_path / "entered-foreground")
        assert not (tmp_path / "entered-compression").exists()
        (tmp_path / "release-foreground").touch()
        assert _wait_for(tmp_path / "entered-compression")
        (tmp_path / "release-compression").touch()
    finally:
        for name in ("blocker", "foreground", "compression"):
            (tmp_path / f"release-{name}").touch()
        for child in children:
            child.wait(timeout=10)

    assert all(child.returncode == 0 for child in children)


def test_distinct_provider_lanes_run_concurrently(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(Path.cwd())}
    children = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                _CHILD,
                str(tmp_path),
                name,
                "foreground",
                lane,
            ],
            env=env,
        )
        for name, lane in (("codex", "openai-codex:account"), ("local", "ollama:local"))
    ]
    try:
        assert _wait_for(tmp_path / "entered-codex")
        assert _wait_for(tmp_path / "entered-local")
    finally:
        for name in ("codex", "local"):
            (tmp_path / f"release-{name}").touch()
        for child in children:
            child.wait(timeout=10)

    assert all(child.returncode == 0 for child in children)


def test_killed_owner_is_reclaimed_by_waiter(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(Path.cwd())}

    def start(name: str) -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(tmp_path), name, "foreground"],
            env=env,
        )

    owner = start("owner")
    waiter = None
    try:
        assert _wait_for(tmp_path / "entered-owner")
        waiter = start("waiter")
        assert _wait_for_registry_state(tmp_path, "session-waiter", "queued")
        owner.kill()
        owner.wait(timeout=10)
        assert _wait_for(tmp_path / "entered-waiter")
        (tmp_path / "release-waiter").touch()
        waiter.wait(timeout=10)
    finally:
        (tmp_path / "release-owner").touch()
        (tmp_path / "release-waiter").touch()
        for child in (owner, waiter):
            if child is not None and child.poll() is None:
                child.kill()
                child.wait(timeout=10)

    assert waiter is not None and waiter.returncode == 0


def test_queued_cancellation_removes_request_without_acquiring(tmp_path):
    blocker = ProviderAdmissionRequest(
        lane="openai-codex:profile",
        request_class="foreground",
        session_id="session-blocker",
        provider="openai-codex",
        model="gpt-5.6-sol",
    )
    waiting = ProviderAdmissionRequest(
        lane="openai-codex:profile",
        request_class="compression",
        session_id="session-cancelled",
        provider="openai-codex",
        model="gpt-5.4-mini",
    )
    cancel = threading.Event()
    outcome: dict[str, Any] = {}

    def acquire_waiter():
        try:
            outcome["lease"] = admission_module.acquire_provider_admission(
                waiting,
                registry_home=tmp_path,
                poll_interval=0.01,
                cancelled=cancel.is_set,
            )
        except BaseException as exc:
            outcome["error"] = exc

    with provider_admission(blocker, registry_home=tmp_path):
        worker = threading.Thread(target=acquire_waiter)
        worker.start()
        assert _wait_for_registry_state(tmp_path, "session-cancelled", "queued")
        cancel.set()
        worker.join(timeout=0.5)
        cancelled_while_blocked = not worker.is_alive()
        live = admission_module.provider_admission_snapshot(registry_home=tmp_path)
        queued_ids = {entry["session_id"] for entry in live if entry["state"] == "queued"}

    worker.join(timeout=5)
    lease = outcome.get("lease")
    if lease is not None:
        lease.release()

    assert cancelled_while_blocked
    assert isinstance(outcome.get("error"), InterruptedError)
    assert "session-cancelled" not in queued_ids


def test_queued_timeout_removes_request_without_acquiring(tmp_path):
    blocker = ProviderAdmissionRequest(
        lane="openai-codex:profile",
        request_class="foreground",
        session_id="session-blocker",
        provider="openai-codex",
        model="gpt-5.6-sol",
    )
    waiting = ProviderAdmissionRequest(
        lane="openai-codex:profile",
        request_class="compression",
        session_id="session-timeout",
        provider="openai-codex",
        model="gpt-5.4-mini",
    )
    outcome: dict[str, Any] = {}

    def acquire_waiter():
        try:
            outcome["lease"] = admission_module.acquire_provider_admission(
                waiting,
                registry_home=tmp_path,
                poll_interval=0.01,
                timeout=0.1,
            )
        except BaseException as exc:
            outcome["error"] = exc

    with provider_admission(blocker, registry_home=tmp_path):
        worker = threading.Thread(target=acquire_waiter)
        worker.start()
        assert _wait_for_registry_state(tmp_path, "session-timeout", "queued")
        worker.join(timeout=0.5)
        timed_out_while_blocked = not worker.is_alive()
        live = admission_module.provider_admission_snapshot(registry_home=tmp_path)
        queued_ids = {entry["session_id"] for entry in live if entry["state"] == "queued"}

    worker.join(timeout=5)
    lease = outcome.get("lease")
    if lease is not None:
        lease.release()

    assert timed_out_while_blocked
    assert isinstance(outcome.get("error"), TimeoutError)
    assert "session-timeout" not in queued_ids


def test_delegation_overtakes_queued_compression(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(Path.cwd())}
    children: list[subprocess.Popen] = []

    def start(name: str, request_class: str) -> subprocess.Popen:
        child = subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(tmp_path), name, request_class],
            env=env,
        )
        children.append(child)
        return child

    start("priority-blocker", "foreground")
    try:
        assert _wait_for(tmp_path / "entered-priority-blocker")
        start("priority-compression", "compression")
        assert _wait_for_registry_state(
            tmp_path, "session-priority-compression", "queued"
        )
        start("priority-delegation", "delegation")
        assert _wait_for_registry_state(
            tmp_path, "session-priority-delegation", "queued"
        )

        (tmp_path / "release-priority-blocker").touch()
        assert _wait_for(tmp_path / "entered-priority-delegation")
        assert not (tmp_path / "entered-priority-compression").exists()
        (tmp_path / "release-priority-delegation").touch()
        assert _wait_for(tmp_path / "entered-priority-compression")
        (tmp_path / "release-priority-compression").touch()
    finally:
        for name in (
            "priority-blocker",
            "priority-delegation",
            "priority-compression",
        ):
            (tmp_path / f"release-{name}").touch()
        for child in children:
            child.wait(timeout=10)

    assert all(child.returncode == 0 for child in children)


def test_distinct_codex_accounts_run_concurrently_across_processes(tmp_path):
    first_lane = admission_module.provider_admission_lane(
        "openai-codex", access_token=_codex_token("account-a", "signature")
    )
    second_lane = admission_module.provider_admission_lane(
        "openai-codex", access_token=_codex_token("account-b", "signature")
    )
    assert first_lane and second_lane and first_lane != second_lane

    env = {**os.environ, "PYTHONPATH": str(Path.cwd())}
    children = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                _CHILD,
                str(tmp_path),
                name,
                "foreground",
                lane,
            ],
            env=env,
        )
        for name, lane in (("account-a", first_lane), ("account-b", second_lane))
    ]
    try:
        assert _wait_for(tmp_path / "entered-account-a")
        assert _wait_for(tmp_path / "entered-account-b")
    finally:
        for name in ("account-a", "account-b"):
            (tmp_path / f"release-{name}").touch()
        for child in children:
            child.wait(timeout=10)

    assert all(child.returncode == 0 for child in children)
