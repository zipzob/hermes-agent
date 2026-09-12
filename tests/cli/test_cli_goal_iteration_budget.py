"""Per-run iteration exhaustion must continue an active CLI goal immediately."""

from __future__ import annotations

import queue
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from hermes_cli import goals
from hermes_cli.cli_loops_mixin import CLILoopsMixin


@pytest.fixture
def hermes_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    goals._DB_CACHE.clear()
    yield home
    goals._DB_CACHE.clear()


class _Cli(CLILoopsMixin):
    def __init__(self, mgr):
        self._pending_input = queue.Queue()
        self._mgr = mgr
        self._last_turn_interrupted = False
        self._last_turn_result = {
            "final_response": "Progress summary from the exhausted run.",
            "completed": False,
            "failed": False,
            "budget_exhausted": True,
            "budget_used": 60,
            "budget_max": 60,
        }
        self.conversation_history = [
            {"role": "assistant", "content": "Progress summary from the exhausted run."}
        ]
        self.session_id = mgr.session_id
        self.agent = SimpleNamespace(session_id=mgr.session_id)

    def _get_goal_manager(self):
        return self._mgr


def test_cli_goal_continues_exhausted_run_without_judging_or_spending_turn(hermes_home):
    mgr = goals.GoalManager(session_id="cli-budget-exhaustion")
    mgr.set("finish the current task")
    cli = _Cli(mgr)
    notices = []

    with patch("hermes_cli.goals.judge_goal", side_effect=AssertionError("must not judge")), patch(
        "cli._cprint", side_effect=notices.append
    ), patch("cli._DIM", ""), patch("cli._RST", ""):
        cli._maybe_continue_goal_after_turn()

    assert cli._pending_input.qsize() == 1
    assert "finish the current task" in cli._pending_input.get_nowait()
    assert mgr.state is not None and mgr.state.turns_used == 0
    assert any("60/60 iterations" in text and "continuing" in text for text in notices)


def test_cli_goal_does_not_continue_failed_exhausted_run(hermes_home):
    mgr = goals.GoalManager(session_id="cli-budget-exhaustion-failed")
    mgr.set("finish the current task")
    cli = _Cli(mgr)
    cli._last_turn_result["failed"] = True

    with patch("hermes_cli.goals.judge_goal", side_effect=AssertionError("must not judge")):
        cli._maybe_continue_goal_after_turn()

    assert cli._pending_input.empty()
    assert mgr.state is not None and mgr.state.turns_used == 0
