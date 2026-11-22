"""Integration coverage for Scenario 308's teardown-only recovery path.

The merge poll drives the production recovery path from a required-check failure
through job-log classification, the forge re-run request, its journal rows, and
the flake-item filing seam.  The forge and ledger transports are scripted; the
Dispatcher code that makes the decision is not.
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


def _failing_view() -> str:
    return json.dumps(
        {
            "number": 7,
            "headRefOid": "a" * 40,
            "state": "OPEN",
            "autoMergeRequest": {"enabledAt": "now"},
            "mergeStateStatus": "BLOCKED",
            "statusCheckRollup": [
                {
                    "name": "ci",
                    "conclusion": "FAILURE",
                    "detailsUrl": "https://x/actions/runs/42/job/12",
                }
            ],
        }
    )


def _required() -> str:
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
                                                "nodes": [{"name": "ci", "isRequired": True}]
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


def test_teardown_only_required_check_is_rerun_and_files_a_flake_item(
    tmp_path: Path,
) -> None:
    """Scenario 308: a teardown-only terminal failure retries and is owned."""
    (tmp_path / ".beads").mkdir()
    runner = _Runner(
        queue=[
            _ok(stdout=_failing_view()),
            _ok(stdout=_required()),
            _ok(
                stdout=json.dumps(
                    {
                        "attempt": 1,
                        "jobs": [
                            {
                                "databaseId": 12,
                                "name": "ci",
                                "conclusion": "failure",
                                "steps": [
                                    {"name": "Run checks", "conclusion": "success"},
                                    {"name": "Post Checkout", "conclusion": "failure"},
                                ],
                            }
                        ],
                    }
                )
            ),
            _ok(stdout="container implementation failed"),
            _ok(stdout="src/module.py\n"),
            _ok(),
            _ok(),
            _ok(
                stdout=json.dumps({"number": 7, "state": "MERGED", "mergeCommit": {"oid": "cafe"}})
            ),
        ]
    )
    journal = _Journal()

    merged = await_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=journal,
        sleep=lambda _: None,
        poll=PollPolicy(attempts=2, interval_seconds=0.5),
    )

    assert not isinstance(merged, DispatchOutcome)
    assert [call for call in runner.calls if call[:3] == ["gh", "run", "rerun"]] == [
        ["gh", "run", "rerun", "42", "--failed"]
    ]
    rerun_rows = [
        record
        for record in journal.records
        if record.get("stage") == "merge-poll-failed-jobs-rerun"
    ]
    assert rerun_rows == [
        {
            "work_item_id": "scenario-308",
            "stage": "merge-poll-failed-jobs-rerun",
            "workflow_run": "42",
            "pr_number": 7,
            "pr_head": "a" * 40,
            "prior_attempt": 1,
            "failed_jobs": [
                {
                    "name": "ci",
                    "class": "runner-teardown",
                    "evidence": (
                        "failed teardown steps: Post Checkout",
                        "log: container implementation failed",
                    ),
                }
            ],
            "outcome": "requested",
            "failure_reason": None,
        },
        {
            "work_item_id": "scenario-308",
            "stage": "merge-poll-failed-jobs-rerun",
            "workflow_run": "42",
            "outcome": "merged",
        },
    ]
    assert [call for call in runner.calls if call[:2] == ["bd", "create"]] == [
        [
            "bd",
            "create",
            "--type",
            "bug",
            "--title",
            "Flake: failed jobs re-run 42",
            "--description",
            "livespec-merge-poll-failed-jobs-rerun\nworkflow-run: 42\njob: ci\nclass: runner-teardown\nevidence: failed teardown steps: Post Checkout\nevidence: log: container implementation failed",
        ]
    ]
