"""A pull-request read that gh rejects field-by-field degrades or blocks, never fails the drive (bd-ib-o657q3).

`gh pr view --json` refuses a field its build does not list with `Unknown JSON field: "X"`. That is a
deterministic tool incompatibility, not a run failure. An OPTIONAL field is dropped and the read retried
once, so a merged pull request still reports its state and merge commit. A field the read cannot do
without ends the drive as `blocked` naming the field, not as `failed`, because a failed outcome would
feed the retry and stop-at-second counting.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_view import view_pr

from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher import (
    _dispatch,
    _err,
    _FakeRunner,
    _ok,
    _plan,
    _pr_json,
    _RecordingJournal,
)


def _unknown(*, field: str) -> str:
    return f'Unknown JSON field: "{field}"\nAvailable fields:\n  number\n  state\n'


def test_an_optional_field_gh_rejects_is_dropped_and_the_read_retried_once(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _err(stderr=_unknown(field="additions")),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe07")),
        ]
    )
    journal = _RecordingJournal()

    reading = view_pr(plan=_plan(repo=tmp_path), runner=runner, journal=journal)

    assert reading.error is None
    assert reading.view is not None
    assert (reading.view.state, reading.view.merge_sha) == ("MERGED", "cafe07")
    first, second = runner.calls[0][0], runner.calls[1][0]
    assert "additions" in first[-1].split(",")
    assert "additions" not in second[-1].split(",")
    assert [record["stage"] for record in journal.records] == [
        "pr-view",
        "pr-view-field-dropped",
        "pr-view",
    ]


def test_a_field_the_read_cannot_do_without_ends_the_drive_blocked_naming_it(
    tmp_path: Path,
) -> None:
    runner = _FakeRunner(queue=[_ok(), _err(stderr=_unknown(field="mergeCommit"))])

    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)

    assert (outcome.status, outcome.stage) == ("blocked", "pr-view")
    assert "mergeCommit" in (outcome.detail or "")
