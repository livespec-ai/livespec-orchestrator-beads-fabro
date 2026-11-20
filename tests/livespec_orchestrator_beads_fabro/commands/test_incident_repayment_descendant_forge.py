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
