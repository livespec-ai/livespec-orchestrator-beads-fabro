"""The pull-request read asks `gh` only for fields it has, and finds a queue entry another way (bd-ib-o657q3).

Measured on hxi-saufim run 01M7SKSF7QEB (PR 299 merged 11:23:22Z, the drive ended rc=1 at stage
pr-view): `_dispatcher_fabro_argv.py` asked `gh pr view --json` for `mergeQueueEntry`, and gh 2.96.0
refuses it with `Unknown JSON field: "mergeQueueEntry"`; its field list has `autoMergeRequest`,
`mergeStateStatus` and `mergeCommit` but no queue entry. Every drive whose run merged therefore ended
at pr-view and the item never closed. Every test mocked `gh`, so none could see it.

Two guards follow. The fields the code requests are compared against `gh`'s own `--json` field list as
RECORDED from gh 2.96.0 (`tests/fixtures/gh_2.96.0_pr_view_json_fields.txt`), so a mock cannot hide a
field `gh` does not list. And queue membership is read through `gh api graphql`
(`pullRequest.mergeQueueEntry`), only for an open pull request that is not armed, so the common
reads pay no extra forge call.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_view import view_pr

from tests.integration.test_merge_poll_budget_exhausted_scenario220 import _Journal, _plan

_ROOT = Path(__file__).resolve().parents[2]
_RECORDED = _ROOT / "tests" / "fixtures" / "gh_2.96.0_pr_view_json_fields.txt"
_COMMANDS = "livespec_orchestrator_beads_fabro.commands."


def _recorded_fields() -> frozenset[str]:
    return frozenset(_RECORDED.read_text(encoding="utf-8").split())


def _pr_json(*, state: str, armed: bool) -> str:
    return json.dumps(
        {
            "number": 299,
            "state": state,
            "autoMergeRequest": {"enabledAt": "now"} if armed else None,
            "mergeStateStatus": "CLEAN",
            "mergeCommit": {"oid": "cafe05"} if state == "MERGED" else None,
            "statusCheckRollup": [],
            "headRefOid": "8ad6cd7b2",
            "baseRefOid": "1c0ffee",
        }
    )


@dataclass(kw_only=True)
class _Forge:
    """A forge that lists `gh`'s real fields, and answers the queue query when asked."""

    state: str
    armed: bool
    queued: bool = False
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
        if argv[:3] == ["gh", "pr", "view"]:
            requested = argv[argv.index("--json") + 1].split(",")
            unknown = [name for name in requested if name not in _recorded_fields()]
            if unknown:
                return CommandResult(
                    exit_code=1, stdout="", stderr=f'Unknown JSON field: "{unknown[0]}"'
                )
            return CommandResult(
                exit_code=0, stdout=_pr_json(state=self.state, armed=self.armed), stderr=""
            )
        if argv[:3] == ["gh", "api", "graphql"]:
            entry = {"state": "QUEUED", "position": 1} if self.queued else None
            payload = {"data": {"repository": {"pullRequest": {"mergeQueueEntry": entry}}}}
            return CommandResult(exit_code=0, stdout=json.dumps(payload), stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")


def _read(*, tmp_path: Path, forge: _Forge, include_publication: bool = False) -> object:
    reading = view_pr(
        plan=_plan(repo=tmp_path),
        runner=forge,
        journal=_Journal(),
        include_publication=include_publication,
    )
    assert reading.error is None, reading.error
    assert reading.view is not None
    return reading.view


@pytest.mark.parametrize("include_publication", [False, True])
def test_every_field_the_pull_request_read_asks_gh_for_is_one_gh_lists(
    *, tmp_path: Path, include_publication: bool
) -> None:
    forge = _Forge(state="MERGED", armed=False)

    _ = _read(tmp_path=tmp_path, forge=forge, include_publication=include_publication)

    views = [call for call in forge.calls if call[:3] == ["gh", "pr", "view"]]
    assert views, forge.calls
    requested = set(views[0][views[0].index("--json") + 1].split(","))
    assert requested - _recorded_fields() == set()


@pytest.mark.parametrize(
    ("module", "constant"),
    [
        ("_incident_authority_binding", "_PR_FIELDS"),
        ("_dispatcher_incident_pr", "_PR_FIELDS"),
        ("_drive_merge_hold_valve", "_PR_VIEW_FIELDS"),
    ],
)
def test_every_other_pull_request_view_field_list_is_one_gh_lists(
    module: str, constant: str
) -> None:
    fields = getattr(importlib.import_module(_COMMANDS + module), constant)

    assert set(fields.split(",")) - _recorded_fields() == set()


def test_an_open_unarmed_pull_request_in_the_merge_queue_reads_as_queued(tmp_path: Path) -> None:
    view = _read(tmp_path=tmp_path, forge=_Forge(state="OPEN", armed=False, queued=True))

    assert view.merge_queue_entry is True


def test_an_open_unarmed_pull_request_outside_the_queue_reads_as_not_queued(
    tmp_path: Path,
) -> None:
    view = _read(tmp_path=tmp_path, forge=_Forge(state="OPEN", armed=False, queued=False))

    assert view.merge_queue_entry is False


@pytest.mark.parametrize(("state", "armed"), [("MERGED", False), ("OPEN", True)])
def test_a_merged_or_armed_pull_request_costs_no_queue_read(
    *, tmp_path: Path, state: str, armed: bool
) -> None:
    forge = _Forge(state=state, armed=armed)

    _ = _read(tmp_path=tmp_path, forge=forge)

    assert [call for call in forge.calls if call[:3] == ["gh", "api", "graphql"]] == []
