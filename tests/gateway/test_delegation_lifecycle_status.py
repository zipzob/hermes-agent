from types import SimpleNamespace

from tools import async_delegation as ad
from tui_gateway import server


def test_status_rpc_and_usage_share_session_scoped_unsettled_state(monkeypatch):
    monkeypatch.setattr(ad, "_records", {
        "a": {"delegation_id": "a", "origin_ui_session_id": "tab-a", "parent_session_id": "parent-a",
              "status": "stalled", "goals": ["one", "two"], "_runner_settled": False},
        "b": {"delegation_id": "b", "origin_ui_session_id": "tab-b", "parent_session_id": "parent-b",
              "status": "running", "goals": ["one", "two", "three"], "_runner_settled": False},
    })
    monkeypatch.setitem(server._sessions, "tab-a", {"agent": SimpleNamespace(session_id="parent-a")})
    response = server.handle_request({"id": 1, "method": "delegation.status", "params": {"session_id": "tab-a"}})
    snapshot = response["result"]["lifecycle"]
    usage = server._get_usage(SimpleNamespace(session_id="parent-a", model="test"))
    assert snapshot["active_tasks"] == usage["active_subagents"] == 0
    assert snapshot["stalled_tasks"] == usage["stalled_subagents"] == 2
    assert [batch["delegation_id"] for batch in snapshot["batches"]] == ["a"]
    missing = server.handle_request({"id": 2, "method": "delegation.status", "params": {"session_id": "missing"}})
    assert "error" in missing
