"""Integration acceptance for every remaining Scenario 308 merge-poll path.

The forge and work-item transports are scripted, but each case drives the real
``await_merge`` recovery surface.  Together with the seeded teardown journey,
these cases cover every Then clause in Scenario 308.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    PollPolicy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_merge import await_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan


@dataclass(kw_only=True)
class _Runner:
    queue: list[CommandResult]
    calls: list[list[str]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        _ = cwd, timeout_seconds
        self.calls.append(argv)
        return self.queue.pop(0)


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _ok(*, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _failure(*names: str) -> str:
    return json.dumps(
        {
            "number": 7,
            "headRefOid": "a" * 40,
            "state": "OPEN",
            "autoMergeRequest": {"enabledAt": "now"},
            "mergeStateStatus": "BLOCKED",
            "statusCheckRollup": [
                {
                    "name": name,
                    "conclusion": "FAILURE",
                    "detailsUrl": "https://x/actions/runs/42/job/12",
                }
                for name in names
            ],
        }
    )


def _required(*names: str) -> str:
    return json.dumps(
        {
            "data": {
                "repository": {
                    "pullRequest": {
                        "commits": {
                            "nodes": [
                                {
                                    "commit": {
                                        "statusCheckRollup": {
                                            "contexts": {
                                                "nodes": [
                                                    {"name": name, "isRequired": True}
                                                    for name in names
                                                ]
                                            }
                                        }
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        }
    )


def _jobs(*jobs: dict[str, object]) -> str:
    return json.dumps({"attempt": 1, "jobs": list(jobs)})


def _job(*, identifier: int, name: str = "ci") -> dict[str, object]:
    return {"databaseId": identifier, "name": name, "conclusion": "failure"}


def _plan(*, repo: Path):
    return build_plan(
        repo=repo,
        work_item_id="scenario-308",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text='{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}',
        default_branch="master",
    )


def _await(*, tmp_path: Path, queue: list[CommandResult], attempts: int = 2, remaining: int = 0):
    (tmp_path / ".beads").mkdir(exist_ok=True)
    runner = _Runner(queue=queue)
    journal = _Journal()
    outcome = await_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=journal,
        sleep=lambda _: None,
        poll=PollPolicy(attempts=attempts, interval_seconds=0.01),
    )
    assert (
        len(runner.queue) == remaining
    ), "the scripted forge did not reach its expected terminal state"
    return outcome, runner, journal


def _infrastructure_queue(*, log: str) -> list[CommandResult]:
    return [
        _ok(stdout=_failure("ci")),
        _ok(stdout=_required("ci")),
        _ok(stdout=_jobs(_job(identifier=12))),
        _ok(stdout=log),
        _ok(stdout="docs/unchanged.md\n"),
        _ok(),
        _ok(),
    ]


def _rerun_calls(runner: _Runner) -> list[list[str]]:
    return [call for call in runner.calls if call[:3] == ["gh", "run", "rerun"]]


def _rerun_rows(journal: _Journal) -> list[dict[str, object]]:
    return [
        record
        for record in journal.records
        if record.get("stage") == "merge-poll-failed-jobs-rerun"
    ]


def _blocked(outcome: object) -> DispatchOutcome:
    assert isinstance(outcome, DispatchOutcome)
    assert (outcome.status, outcome.stage) == ("blocked", "merge-poll")
    assert "required check failed terminally: ci" in outcome.detail
    assert "resolve-blocked:scenario-308:ready" in outcome.detail
    assert "resume --item scenario-308" in outcome.detail
    return outcome


def test_scenario308_all_infrastructure_rerun_outcomes(tmp_path: Path) -> None:  # noqa: PLR0915
    """Exercise all seven Scenario 308 sub-scenarios against merge polling."""
    teardown = _infrastructure_queue(log="container implementation failed")
    teardown.append(
        _ok(stdout=json.dumps({"number": 7, "state": "MERGED", "mergeCommit": {"oid": "cafe"}}))
    )
    outcome, runner, journal = _await(tmp_path=tmp_path, queue=teardown)
    assert not isinstance(outcome, DispatchOutcome)
    assert _rerun_calls(runner) == [["gh", "run", "rerun", "42", "--failed"]]
    assert _rerun_rows(journal)[0]["failed_jobs"] == [
        {
            "name": "ci",
            "class": "runner-teardown",
            "evidence": ("log: container implementation failed",),
        }
    ]
    assert any(call[:2] == ["bd", "create"] for call in runner.calls)

    oom = _infrastructure_queue(log="pytest tests/untouched.py::test_memory\noom-kill")
    oom.append(
        _ok(stdout=json.dumps({"number": 7, "state": "MERGED", "mergeCommit": {"oid": "cafe"}}))
    )
    outcome, runner, journal = _await(tmp_path=tmp_path, queue=oom)
    assert not isinstance(outcome, DispatchOutcome)
    assert _rerun_calls(runner) == [["gh", "run", "rerun", "42", "--failed"]]
    assert _rerun_rows(journal)[0]["failed_jobs"] == [
        {"name": "ci", "class": "oom-kill", "evidence": ("oom-kill: oom-kill",)}
    ]

    rerun_fails = [
        *_infrastructure_queue(log="container implementation failed"),
        _ok(stdout=_failure("ci")),
        _ok(stdout=_required("ci")),
        _ok(stdout=json.dumps({"attempt": 2})),
    ]
    outcome, runner, journal = _await(tmp_path=tmp_path, queue=rerun_fails)
    _blocked(outcome)
    assert len(_rerun_calls(runner)) == 1
    assert _rerun_rows(journal)[-1]["outcome"] == "required-check-failed"

    rejected = _infrastructure_queue(log="container implementation failed")
    rejected[-2] = CommandResult(exit_code=1, stdout="", stderr="forge rejected rerun")
    outcome, runner, journal = _await(tmp_path=tmp_path, queue=rejected, remaining=1)
    _blocked(outcome)
    assert len(_rerun_calls(runner)) == 1
    assert _rerun_rows(journal)[-1]["outcome"] == "rejected"
    assert _rerun_rows(journal)[-1]["failure_reason"] == "forge rejected rerun"

    touched_oom = [
        _ok(stdout=_failure("ci")),
        _ok(stdout=_required("ci")),
        _ok(stdout=_jobs(_job(identifier=12))),
        _ok(stdout="FAILED tests/touched.py::test_memory\noom-kill"),
        _ok(stdout="tests/touched.py\n"),
    ]
    outcome, runner, _ = _await(tmp_path=tmp_path, queue=touched_oom)
    _blocked(outcome)
    assert not _rerun_calls(runner)
    assert not any(call[:2] == ["bd", "create"] for call in runner.calls)

    unattributed = [
        _ok(stdout=_failure("ci", "lint")),
        _ok(stdout=_required("ci", "lint")),
        _ok(stdout=_jobs(_job(identifier=12, name="ci"), _job(identifier=13, name="lint"))),
        _ok(stdout="container implementation failed"),
        _ok(stdout="FAILED tests/ordinary.py::test_failure - AssertionError"),
    ]
    outcome, runner, _ = _await(tmp_path=tmp_path, queue=unattributed)
    _blocked(outcome)
    assert not _rerun_calls(runner)

    pytest_failure = [
        _ok(stdout=_failure("ci")),
        _ok(stdout=_required("ci")),
        _ok(stdout=_jobs(_job(identifier=12))),
        _ok(stdout="FAILED tests/ordinary.py::test_failure - AssertionError"),
    ]
    outcome, runner, _ = _await(tmp_path=tmp_path, queue=pytest_failure)
    _blocked(outcome)
    assert not _rerun_calls(runner)
