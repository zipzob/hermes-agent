"""A terminal notification must not masquerade as a stopped worker."""
import threading
import time

import pytest

from tools import async_delegation as ad


@pytest.fixture(autouse=True)
def isolated_registry():
    ad._reset_for_tests()
    yield
    ad._reset_for_tests()


def test_stalled_runner_keeps_capacity_and_session_warning_until_it_returns():
    entered, release = threading.Event(), threading.Event()

    def runner():
        entered.set()
        assert release.wait(5)
        return {"results": [{"status": "completed"}]}

    handle = ad.dispatch_async_delegation_batch(
        goals=["one", "two"], context=None, toolsets=None, role="leaf", model=None,
        session_key="route-a", origin_ui_session_id="tab-a", runner=runner,
        max_async_children=1,
    )
    try:
        assert entered.wait(2)
        delegation_id = handle["delegation_id"]
        ad._finalize(delegation_id, {"error": "unresponsive runner"}, "stalled")
        rejected = ad.dispatch_async_delegation(
            goal="must not queue behind a wedged runner", context=None, toolsets=None,
            role="leaf", model=None, session_key="route-a", runner=lambda: {},
            max_async_children=1,
        )
        assert rejected["status"] == "rejected"
        snapshot = ad.status_snapshot(origin_ui_session_id="tab-a")
        assert snapshot["active_tasks"] == 0
        assert snapshot["stalled_tasks"] == 2
        assert ad.status_snapshot(origin_ui_session_id="tab-b")["stalled_tasks"] == 0
    finally:
        release.set()
    deadline = time.monotonic() + 2
    while ad.status_snapshot(origin_ui_session_id="tab-a")["stalled_tasks"] and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ad.status_snapshot(origin_ui_session_id="tab-a")["stalled_tasks"] == 0
    assert ad.list_async_delegations()[0]["status"] == "stalled"


def test_finalizing_and_unsettled_records_are_not_pruned(monkeypatch):
    monkeypatch.setattr(ad, "_MAX_RETAINED_COMPLETED", 0)
    with ad._records_lock:
        ad._records.update({
            "persisting": {"delegation_id": "persisting", "status": "finalizing"},
            "wedged": {"delegation_id": "wedged", "status": "stalled", "_runner_settled": False},
            "finished": {"delegation_id": "finished", "status": "completed", "_runner_settled": True},
        })
        ad._prune_completed_locked()
        assert set(ad._records) == {"persisting", "wedged"}
