"""Task cancellation must not leave a physical dispatch or a lease behind."""
import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from agent import auxiliary_client as aux
from hermes_cli.provider_admission import ProviderAdmissionRequest, provider_admission, provider_admission_snapshot


@pytest.mark.parametrize("enabled", [False, True])
def test_async_admission_scope_releases_with_or_without_limit(tmp_path, monkeypatch, enabled):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        f"provider_admission:\n  max_in_flight: {int(enabled)}\n", encoding="utf-8"
    )

    async def run():
        async with aux._aux_provider_admission_scope_async(
            SimpleNamespace(), provider="openai-codex", model="model",
            request_class="compression", attempt=1,
        ) as lease:
            assert (lease is not None) == enabled

    asyncio.run(run())
    assert provider_admission_snapshot() == []


def test_async_cancellation_drains_waiter_before_owner_releases(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "provider_admission:\n  max_in_flight: 1\n  queue_timeout: 2\n", encoding="utf-8"
    )
    queued = threading.Event()
    notices = []

    def notice(text):
        notices.append(text)
        if text:
            queued.set()
        return True

    monkeypatch.setattr(aux, "_emit_aux_wait_status", notice)
    blocker = ProviderAdmissionRequest("openai-codex:profile", "foreground", "blocker", "openai-codex", "model")

    async def request():
        async with aux._aux_provider_admission_scope_async(
            SimpleNamespace(), provider="openai-codex", model="model",
            request_class="compression", attempt=1,
        ):
            pytest.fail("cancelled waiter dispatched")

    async def run():
        task = asyncio.create_task(request())
        try:
            assert await asyncio.to_thread(queued.wait, 2)
            task.cancel()
            # Cancellation may recur while the worker cleans up; neither may be swallowed.
            asyncio.get_running_loop().call_soon(task.cancel)
            with pytest.raises(asyncio.CancelledError):
                await task
            entries = provider_admission_snapshot()
            assert len(entries) == 1 and entries[0]["session_id"] == "blocker"
            assert notices[-1] == ""
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    with provider_admission(blocker):
        asyncio.run(run())
    assert provider_admission_snapshot() == []


def test_cancelled_aux_owner_cannot_release_a_still_running_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "provider_admission:\n  max_in_flight: 1\n", encoding="utf-8"
    )
    entered, finish, cancel = threading.Event(), threading.Event(), threading.Event()
    outcome = []

    def dispatch(_request):
        entered.set()
        assert finish.wait(5)
        return SimpleNamespace(choices=[])

    def owner():
        try:
            with aux.aux_interrupt_protection(cancel_event=cancel), aux._relay_aux_call_scope(("compression",), {}):
                aux._relay_sync_completion(
                    SimpleNamespace(), {"model": "model", "messages": []},
                    provider="openai-codex", create=dispatch,
                )
        except BaseException as exc:
            outcome.append(exc)

    thread = threading.Thread(target=owner)
    thread.start()
    try:
        assert entered.wait(2)
        cancel.set()
        thread.join(2)
        assert not thread.is_alive()
        assert len(outcome) == 1 and isinstance(outcome[0], aux.AuxiliaryExplicitCancellation)
        assert len(provider_admission_snapshot()) == 1, "physical worker still owns the slot"
    finally:
        finish.set()
        thread.join(5)
        deadline = time.monotonic() + 2
        while provider_admission_snapshot() and time.monotonic() < deadline:
            time.sleep(0.01)
    assert provider_admission_snapshot() == []
