"""Tests for selecting the pull-request commits authored by one dispatch."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles import (
    UNOBSERVED_NO_PULL_REQUEST,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_series import (
    dispatch_commit_series,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)


@dataclass(kw_only=True)
class _Runner:
    """Return one commit-list response and retain the probe invocation."""

    stdout: str
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        assert cwd == Path("/repo")
        assert timeout_seconds > 0
        assert env is None
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


def test_series_contains_only_commits_for_the_requested_dispatch() -> None:
    """A prior dispatch on the same pull request cannot enter this series."""
    dispatch_id = "this-dispatch"
    runner = _Runner(
        stdout=json.dumps(
            {
                "commits": [
                    {
                        "oid": "ours",
                        "messageHeadline": "feat: ours",
                        "messageBody": f"Factory-Run-Id: {dispatch_id}",
                    },
                    {
                        "oid": "theirs",
                        "messageHeadline": "feat: prior dispatch",
                        "messageBody": "Factory-Run-Id: prior-dispatch",
                    },
                ]
            }
        )
    )

    series = dispatch_commit_series(
        repo=Path("/repo"),
        outcome=DispatchOutcome(
            work_item_id="bd-ib-defs3b",
            status="failed",
            stage="done",
            pr_number=42,
            merge_sha=None,
            detail="unmerged",
        ),
        dispatch_id=dispatch_id,
        runner=runner,
    )

    assert tuple(commit.oid for commit in series.commits) == ("ours",)
    assert series.unreadable_reason is None
    assert runner.calls == [["gh", "pr", "view", "42", "--json", "commits"]]


def test_series_without_a_pull_request_is_unobserved_for_that_reason() -> None:
    """A dispatch without a PR has no readable commit series to enumerate."""
    series = dispatch_commit_series(
        repo=Path("/repo"),
        outcome=DispatchOutcome(
            work_item_id="bd-ib-defs3b",
            status="failed",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="unmerged",
        ),
        dispatch_id="this-dispatch",
        runner=_Runner(stdout="{}"),
    )

    assert series.commits == ()
    assert series.unreadable_reason == UNOBSERVED_NO_PULL_REQUEST
