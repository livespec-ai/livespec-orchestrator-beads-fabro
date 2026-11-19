"""An unreadable merge-queue answer reads as membership UNKNOWN, a third state, and is journaled (bd-ib-o657q3).

Definition of Done: a pull-request read reports merge-queue membership as unknown when it cannot read it.
Reading an unreadable answer as "not queued" would return a plausible wrong answer without telling anyone,
so a failed or malformed GraphQL answer sets `merge_queue_unknown`, journals `pr-merge-queue-unknown`, and a
genuine "no entry" answer stays known-not-queued.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_view import view_pr

from tests.integration.test_merge_poll_budget_exhausted_scenario220 import _Journal, _plan
from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_pr_view_merge_queue_o657q3 import (
    _Forge,
    _queue_answer,
)

_UNREADABLE = [
    CommandResult(exit_code=1, stdout="", stderr="HTTP 502"),
    CommandResult(exit_code=0, stdout="not json", stderr=""),
    CommandResult(exit_code=0, stdout=json.dumps({"data": []}), stderr=""),
]


def _read(*, answer: CommandResult, tmp_path: Path) -> tuple[object, list[str]]:
    journal = _Journal()
    reading = view_pr(
        plan=_plan(repo=tmp_path), runner=_Forge(queue_result=answer), journal=journal
    )
    assert reading.view is not None
    unknown = getattr(reading.view, "merge_queue_unknown", None)
    return unknown, [str(record["stage"]) for record in journal.records]


@pytest.mark.parametrize("answer", _UNREADABLE, ids=["failed-read", "unparseable", "wrong-shape"])
def test_an_unreadable_membership_answer_is_unknown_and_journaled(
    answer: CommandResult, tmp_path: Path
) -> None:
    unknown, stages = _read(answer=answer, tmp_path=tmp_path)

    assert unknown is True
    assert "pr-merge-queue-unknown" in stages


def test_a_readable_answer_is_never_unknown(tmp_path: Path) -> None:
    absent = CommandResult(exit_code=0, stdout=_queue_answer(entry=None), stderr="")
    present = CommandResult(
        exit_code=0, stdout=_queue_answer(entry={"state": "QUEUED", "position": 1}), stderr=""
    )

    for answer in (absent, present):
        unknown, stages = _read(answer=answer, tmp_path=tmp_path)
        assert unknown is False
        assert "pr-merge-queue-unknown" not in stages
