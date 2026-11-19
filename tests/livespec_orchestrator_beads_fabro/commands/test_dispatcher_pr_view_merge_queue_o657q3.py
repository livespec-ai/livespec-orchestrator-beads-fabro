"""The merge-queue read supplements an open, unarmed pull-request view (bd-ib-o657q3)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_view import view_pr

from tests.integration.test_merge_poll_budget_exhausted_scenario220 import _Journal, _plan

_VIEW = json.dumps(
    {
        "number": 299,
        "state": "OPEN",
        "autoMergeRequest": None,
        "mergeStateStatus": "CLEAN",
        "mergeCommit": None,
        "statusCheckRollup": [],
        "headRefOid": "8ad6cd7b2",
        "baseRefOid": "1c0ffee",
    }
)


def _queue_answer(*, entry: object) -> str:
    return json.dumps({"data": {"repository": {"pullRequest": {"mergeQueueEntry": entry}}}})


@dataclass(kw_only=True)
class _Forge:
    queue_result: CommandResult
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        if argv[:3] == ["gh", "api", "graphql"]:
            return self.queue_result
        return CommandResult(exit_code=0, stdout=_VIEW, stderr="")


def _read(*, queue_result: CommandResult, tmp_path: Path) -> bool:
    reading = view_pr(
        plan=_plan(repo=tmp_path),
        runner=_Forge(queue_result=queue_result),
        journal=_Journal(),
    )
    assert reading.view is not None
    return reading.view.merge_queue_entry


def test_a_queue_entry_in_the_graphql_answer_marks_the_view_queued(tmp_path: Path) -> None:
    answer = CommandResult(
        exit_code=0, stdout=_queue_answer(entry={"state": "QUEUED", "position": 1}), stderr=""
    )

    assert _read(queue_result=answer, tmp_path=tmp_path) is True


@pytest.mark.parametrize(
    "answer",
    [
        CommandResult(exit_code=0, stdout=_queue_answer(entry=None), stderr=""),
        CommandResult(exit_code=1, stdout="", stderr="HTTP 502"),
        CommandResult(exit_code=0, stdout="not json", stderr=""),
        CommandResult(exit_code=0, stdout=json.dumps({"data": []}), stderr=""),
    ],
    ids=["no-entry", "failed-read", "unparseable", "unexpected-shape"],
)
def test_a_missing_or_unreadable_queue_answer_reads_as_not_queued(
    answer: CommandResult, tmp_path: Path
) -> None:
    assert _read(queue_result=answer, tmp_path=tmp_path) is False
