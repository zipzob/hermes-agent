from __future__ import annotations

import concurrent.futures
from types import SimpleNamespace
from typing import Any, cast

from agent import tool_executor


class _PendingSequentialFuture:
    def __init__(self, agent) -> None:
        self.agent = agent
        self.calls = 0

    def result(self, *, timeout: float):
        self.calls += 1
        if self.calls > 1:
            self.agent._interrupt_requested = True
        raise concurrent.futures.TimeoutError


class _PendingConcurrentFuture:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class _Gate:
    def excluded_seconds(self) -> float:
        return 0.0

    def abandon(self) -> None:
        pass


def _agent():
    activity: list[str] = []
    liveness: list[str] = []
    return SimpleNamespace(
        _interrupt_requested=False,
        _touch_activity=activity.append,
        _touch_liveness=liveness.append,
        _vprint=lambda *args, **kwargs: None,
        log_prefix="",
        _tool_interrupt_reason=None,
    ), activity, liveness


def test_sequential_poll_heartbeat_is_liveness_not_semantic_progress(monkeypatch):
    agent, activity, liveness = _agent()
    future = _PendingSequentialFuture(agent)
    monkeypatch.setattr(tool_executor.time, "monotonic", lambda: 31.0)

    state, result = tool_executor._poll_sequential_future(
        agent,
        future,
        "slow_tool",
        deadline=None,
        started=0.0,
        authorization_gate=_Gate(),
    )

    assert (state, result) == ("interrupted", None)
    assert activity == []
    assert liveness == ["sequential tool running (31s): slow_tool"]


def test_concurrent_poll_heartbeat_is_liveness_not_semantic_progress(monkeypatch):
    agent, activity, liveness = _agent()
    future = _PendingConcurrentFuture()
    batch = object.__new__(tool_executor._ConcurrentBatch)
    batch.agent = agent
    batch.authorization_gate = cast(Any, _Gate())
    batch.gate = cast(Any, _Gate())
    batch.timeout_s = None
    batch.timed_out_indices = set()
    batch._flush_completed_prefix = cast(Any, lambda budget: True)
    batch._running_names = cast(Any, lambda not_done, future_to_index: ["slow_tool"])

    wait_calls = 0

    def fake_wait(_futures, *, timeout):
        nonlocal wait_calls
        wait_calls += 1
        if wait_calls == 2:
            agent._interrupt_requested = True
        return set(), {future}

    times = iter((0.0, 31.0))
    monkeypatch.setattr(tool_executor.concurrent.futures, "wait", fake_wait)
    monkeypatch.setattr(tool_executor.time, "time", lambda: next(times))

    abandoned = batch.await_completion(
        [future],
        {future: 0},
        deadline=None,
        budget=cast(Any, SimpleNamespace()),
    )

    assert abandoned is True
    assert future.cancelled is True
    assert activity == []
    assert liveness == ["concurrent tools running (31s, 1 remaining: slow_tool)"]
