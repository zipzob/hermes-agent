"""Admission policy must not impose an undocumented provider concurrency limit."""
import threading
import time
from contextlib import ExitStack
from dataclasses import replace

import pytest

from hermes_cli import provider_admission as admission
from hermes_cli.provider_admission import (
    ProviderAdmissionRequest, provider_admission, provider_admission_snapshot,
)


def test_default_allows_parallel_models_without_registry_io(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    request = ProviderAdmissionRequest("account", "foreground", "first", "openai-codex", "model-a")
    entered = threading.Event()
    outcome = []

    def second():
        try:
            with provider_admission(replace(request, model="model-b"), registry_home=tmp_path, timeout=0.1):
                entered.set()
        except BaseException as exc:
            outcome.append(exc)

    with provider_admission(request, registry_home=tmp_path):
        thread = threading.Thread(target=second)
        thread.start()
        thread.join(2)
        concurrent = entered.is_set()
    thread.join(2)
    assert concurrent, outcome
    assert not (tmp_path / "runtime" / "provider_admission.json").exists()


@pytest.mark.parametrize("capacity", [1, 2, 4])
def test_configured_limit_is_bounded_and_cancellation_precedes_dispatch(tmp_path, monkeypatch, capacity):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        f"provider_admission:\n  max_in_flight: {capacity}\n  queue_timeout: 0.05\n",
        encoding="utf-8",
    )
    request = ProviderAdmissionRequest("account", "foreground", "first", "openai-codex", "model")
    with pytest.raises(InterruptedError):
        with provider_admission(request, cancelled=lambda: True):
            pytest.fail("cancelled request dispatched on a free lane")
    with ExitStack() as stack:
        for _ in range(capacity):
            stack.enter_context(provider_admission(request, timeout=0.1))
        assert len(provider_admission_snapshot()) == capacity
        with pytest.raises(TimeoutError):
            with provider_admission(request):
                pytest.fail("limit exceeded")
        assert len(provider_admission_snapshot()) == capacity
    assert provider_admission_snapshot() == []


@pytest.mark.parametrize("cancelled", [False, True])
def test_registry_lock_wait_obeys_cancellation_and_deadline(tmp_path, monkeypatch, cancelled):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "provider_admission:\n  max_in_flight: 1\n", encoding="utf-8"
    )
    request = ProviderAdmissionRequest("account", "foreground", "waiter", "openai-codex", "model")
    stop = threading.Event()
    outcome = []

    def wait():
        try:
            with provider_admission(request, timeout=0.1, cancelled=stop.is_set):
                outcome.append("dispatched")
        except BaseException as exc:
            outcome.append(exc)

    _, lock_path = admission._paths(tmp_path)
    with admission._FileLock(lock_path):
        thread = threading.Thread(target=wait)
        thread.start()
        if cancelled:
            stop.set()
        thread.join(2)
        finished_while_locked = not thread.is_alive()
    thread.join(3)
    assert finished_while_locked, "registry lock ignored queue deadline/cancellation"
    assert len(outcome) == 1
    assert isinstance(outcome[0], InterruptedError if cancelled else TimeoutError)
    assert provider_admission_snapshot() == []


def test_expired_queue_entry_is_pruned_but_live_active_worker_is_never_evicted(tmp_path):
    request = ProviderAdmissionRequest("account", "foreground", "owner", "openai-codex", "model")
    expired = time.monotonic() - 60
    active = {**admission._entry("active", request), "state": "active", "queue_deadline_monotonic": expired}
    queued = {**admission._entry("queued", request), "queue_deadline_monotonic": expired}
    state_path, lock_path = admission._paths(tmp_path)
    with admission._FileLock(lock_path):
        admission._write_entries(state_path, [active, queued])
    snapshot = provider_admission_snapshot(registry_home=tmp_path)
    assert [entry["lease_id"] for entry in snapshot] == ["active"]
