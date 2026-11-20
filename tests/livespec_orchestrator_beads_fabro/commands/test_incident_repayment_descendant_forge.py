"""Failure boundaries for forge facts used by descendant repayment admission."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro.commands import _incident_repayment_descendant_forge as forge
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandResult


@dataclass
class _Runner:
    reply: object

    def run(self, **_: object) -> CommandResult:
        return CommandResult(exit_code=0, stdout=json.dumps(self.reply), stderr="")


def _attempt() -> IncidentAttempt:
    return IncidentAttempt(
        repository="owner/repository",
        item_id="incident",
        attempt_id="attempt",
        phase="master-observation",
        operation_id="operation",
        generation=1,
        owner="operator:alice",
        base="a" * 40,
        head="b" * 40,
        pr_number=1,
        landed_commits=("c" * 40,),
        landed_trees=("d" * 40,),
        original_paths=("app.py",),
        deferred_work=(),
        repayment_required=True,
    )


@pytest.mark.parametrize(
    "reply",
    [
        {},
        {"headSha": "a", "status": "completed", "conclusion": "success"},
        {
            "headSha": "a",
            "status": "completed",
            "conclusion": "success",
            "databaseId": 1,
            "jobs": [None],
        },
        {
            "headSha": "a",
            "status": "completed",
            "conclusion": "success",
            "databaseId": 1,
            "jobs": [{}],
        },
    ],
)
def test_run_refuses_incomplete_forge_shapes(reply: object) -> None:
    assert (
        forge.run(
            runner=_Runner(reply=reply), repo=Path.cwd(), repository="owner/repository", run_id="1"
        )
        is None
    )


@pytest.mark.parametrize(
    "reply",
    [None, {"workflow_runs": [None]}, {"workflow_runs": [{"id": "1"}]}],
)
def test_runs_at_refuses_unreadable_run_lists(
    monkeypatch: pytest.MonkeyPatch, reply: object
) -> None:
    monkeypatch.setattr(forge, "api", lambda **_: reply)
    assert (
        forge.runs_at(
            runner=_Runner(reply={}), repo=Path.cwd(), repository="owner/repository", head="a" * 40
        )
        is None
    )


@pytest.mark.parametrize(("relation", "expected"), [(None, None), (False, None)])
def test_latest_landed_ancestor_keeps_unreadable_and_absent_distinct(
    monkeypatch: pytest.MonkeyPatch, relation: bool | None, expected: str | None
) -> None:
    monkeypatch.setattr(forge, "is_ancestor", lambda **_: relation)

    class _Reading:
        attempt = _attempt()

    assert (
        forge.latest_landed_ancestor(
            runner=_Runner(reply={}),
            repo=Path.cwd(),
            repository="owner/repository",
            reading=cast("IncidentReading", _Reading()),
            head="e" * 40,
        )
        == expected
    )


_REPOSITORY = "owner/repository"


def _row(run_id: int, **changes: object) -> dict[str, object]:
    return {
        "id": run_id,
        "name": "CI",
        "head_branch": "master",
        "event": "push",
        "head_sha": "a" * 40,
        "status": "completed",
        "conclusion": "success",
    } | changes


@dataclass
class _Pages:
    """A forge that serves `actions/runs` one page at a time, recording each request."""

    pages: dict[int, list[dict[str, object]]]
    total: int
    requested: list[str]

    def run(self, *, argv: list[str], **_: object) -> CommandResult:
        path = argv[2]
        self.requested.append(path)
        page = int(path.rsplit("page=", 1)[1].split("&")[0])
        reply = {"total_count": self.total, "workflow_runs": self.pages.get(page, [])}
        return CommandResult(exit_code=0, stdout=json.dumps(reply), stderr="")


def _pages(*pages: list[dict[str, object]], total: int | None = None) -> _Pages:
    return _Pages(
        pages={number: rows for number, rows in enumerate(pages, start=1)},
        total=sum(len(rows) for rows in pages) if total is None else total,
        requested=[],
    )


def _runs_at(forge_double: _Pages) -> tuple[str, ...] | None:
    return forge.runs_at(
        runner=forge_double, repo=Path.cwd(), repository=_REPOSITORY, head="a" * 40
    )


def test_runs_at_reads_every_page_of_the_run_history() -> None:
    first = [_row(number) for number in range(1, 101)]
    second = [_row(number) for number in range(101, 151)]
    double = _pages(first, second)
    assert _runs_at(double) == tuple(str(number) for number in range(1, 151))
    assert len(double.requested) == 2


def test_runs_at_keeps_only_the_normal_master_ci_runs() -> None:
    double = _pages(
        [
            _row(1),
            _row(2, name="Release Please"),
            _row(3, head_branch="feature"),
            _row(4, event="pull_request"),
            _row(5),
        ]
    )
    assert _runs_at(double) == ("1", "5")


def test_runs_at_asks_the_forge_for_master_push_runs_at_the_commit() -> None:
    double = _pages([_row(1)])
    assert _runs_at(double) == ("1",)
    (path,) = double.requested
    assert f"head_sha={'a' * 40}" in path
    assert "branch=master" in path
    assert "event=push" in path


def test_runs_at_refuses_a_history_the_forge_truncated() -> None:
    double = _pages([_row(number) for number in range(1, 101)], total=150)
    assert _runs_at(double) is None


def test_normal_runs_without_a_head_pages_the_whole_master_history() -> None:
    double = _pages([_row(1, head_sha="b" * 40)], [_row(2, name="Other")], total=2)
    rows = forge.normal_runs(runner=double, repo=Path.cwd(), repository=_REPOSITORY, head=None)
    assert rows is not None
    assert [row["id"] for row in rows] == [1]
    assert not any("head_sha" in path for path in double.requested)
