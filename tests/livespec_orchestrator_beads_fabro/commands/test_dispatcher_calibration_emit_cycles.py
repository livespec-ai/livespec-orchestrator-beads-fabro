"""Completed-cycle measurements reach the journaled calibration record.

Drives the production `emit_calibration` entry point against a real Git
repository carrying genuine Red-Green trailers, so the per-cycle measurements
are proven through the Dispatcher/calibration boundary rather than through the
gather helper called directly. Only the forge is stood in: it answers the
commit-series request, and every other forge request fails.

The measurements ride as flat sibling journal records (one summary and one per
cycle) rather than as keys on the `calibration` record, whose key set and flat
scalar shape are pinned by Scenario 12. They are journaled for an IDENTIFIED
series only: a series that could not be read already carries its reason on the
`calibration` record's `tdd.verified_pair_unobserved_reason`, and journaling a
second record for it would change every hermetic dispatch's journal.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration_emit import (
    emit_calibration,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_DISPATCH_ID = "5fe8e3dfbfd54faa979e85364d8e9863"
_ITEM_ID = "bd-ib-d3pdrv"
_PYPROJECT = '[tool.livespec_dev_tooling]\nsource_trees = ["src/pkg"]\n'


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _Forge:
    """Answer the commit-series request; fail every other forge request."""

    commits_stdout: str
    commit_requests: int = 0

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        if argv == ["gh", "pr", "view", "4242", "--json", "commits"]:
            self.commit_requests += 1
            return CommandResult(exit_code=0, stdout=self.commits_stdout, stderr="")
        return CommandResult(exit_code=1, stdout="", stderr="forge unavailable")


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="Measure each completed cycle",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-23T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_criteria="- One assertion.\n- Another assertion.\n- A third.\n",
    )


def _outcome() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="failed",
        stage="non-converged",
        pr_number=4242,
        merge_sha=None,
        detail="the run bounced",
    )


def _git(*, repo: Path, argv: list[str]) -> str:
    return subprocess.run(
        ["git", *argv], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(*, root: Path, declaration: str | None) -> Path:
    repo = root / "fixture"
    (repo / "src" / "pkg").mkdir(parents=True)
    _ = _git(repo=repo, argv=["init", "--initial-branch", "work"])
    _ = _git(repo=repo, argv=["config", "user.email", "fixture@example.com"])
    _ = _git(repo=repo, argv=["config", "user.name", "Fixture"])
    if declaration is not None:
        _ = (repo / "pyproject.toml").write_text(declaration, encoding="utf-8")
    _ = (repo / "src" / "pkg" / "thing.py").write_text("value = 1\n", encoding="utf-8")
    _ = _git(repo=repo, argv=["add", "-A"])
    _ = _git(repo=repo, argv=["commit", "-m", "chore: seed"])
    return repo


def _cycle(*, repo: Path, source: str, checksum: str, red_at: str, green_at: str) -> str:
    _ = (repo / "src" / "pkg" / "thing.py").write_text(source, encoding="utf-8")
    (repo / "tests").mkdir(exist_ok=True)
    _ = (repo / "tests" / f"test_{checksum}.py").write_text("assert True\n", encoding="utf-8")
    _ = _git(repo=repo, argv=["add", "-A"])
    message = "\n".join(
        (
            "feat(pkg): one assertion",
            "",
            f"TDD-Red-Test-File-Checksum: {checksum}",
            f"TDD-Red-Captured-At: {red_at}",
            f"Factory-Run-Id: {_DISPATCH_ID}",
            f"TDD-Green-Verified-At: {green_at}",
        )
    )
    _ = _git(repo=repo, argv=["commit", "-m", message])
    return _git(repo=repo, argv=["rev-parse", "HEAD"])


def _commits_payload(*, repo: Path, shas: list[str]) -> str:
    return json.dumps(
        {
            "commits": [
                {
                    "oid": sha,
                    "messageHeadline": _git(repo=repo, argv=["log", "-1", "--format=%s", sha]),
                    "messageBody": _git(repo=repo, argv=["log", "-1", "--format=%b", sha]),
                }
                for sha in shas
            ]
        }
    )


def _emit(
    *, root: Path, repo: Path, shas: list[str]
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object], _Forge]:
    journal_file = root / "journal.jsonl"
    _ = journal_file.write_text(
        json.dumps({"stage": "dispatch-id", "work_item_id": _ITEM_ID, "dispatch_id": _DISPATCH_ID})
        + "\n",
        encoding="utf-8",
    )
    forge = _Forge(commits_stdout=_commits_payload(repo=repo, shas=shas))
    journal = _Journal()
    emit_calibration(
        args=argparse.Namespace(journal=str(journal_file)),
        repo=repo,
        item=_item(),
        outcome=_outcome(),
        journal=journal,
        wall_clock_seconds=1.0,
        dispatch_context_size=1,
        runner=forge,
    )
    stages = [record.get("stage") for record in journal.records]
    assert "calibration-error" not in stages
    assert stages.count("calibration") == 1
    summaries = [
        record for record in journal.records if record.get("stage") == "calibration-cycles"
    ]
    calibration = next(r for r in journal.records if r.get("stage") == "calibration")
    cycles = [record for record in journal.records if record.get("stage") == "calibration-cycle"]
    return summaries, cycles, calibration, forge


def test_emit_calibration_journals_each_completed_cycle_measurement(tmp_path: Path) -> None:
    repo = _repo(root=tmp_path, declaration=_PYPROJECT)
    first = _cycle(
        repo=repo,
        source="value = 2\n",
        checksum="first",
        red_at="2026-11-23T10:00:00Z",
        green_at="2026-11-23T10:04:10Z",
    )
    second = _cycle(
        repo=repo,
        source="value = 2\nother = 3\n",
        checksum="second",
        red_at="2026-11-23T11:00:00Z",
        green_at="2026-11-23T11:01:00Z",
    )

    summaries, cycles, _, forge = _emit(root=tmp_path, repo=repo, shas=[second, first])

    assert len(summaries) == 1
    assert summaries[0].get("work_item_id") == _ITEM_ID
    assert summaries[0].get("completed_cycle_count") == 2
    assert summaries[0].get("completed_cycle_assertion_count") == 3
    assert [
        (
            cycle.get("ordinal"),
            cycle.get("pair_id"),
            cycle.get("commit"),
            cycle.get("product_lloc_changed"),
            cycle.get("elapsed_seconds"),
        )
        for cycle in cycles
    ] == [
        (1, "first@2026-11-23T10:00:00Z", first, 2, 250),
        (2, "second@2026-11-23T11:00:00Z", second, 1, 60),
    ]
    assert {cycle.get("work_item_id") for cycle in cycles} == {_ITEM_ID}
    assert forge.commit_requests == 1


def test_emit_calibration_keeps_the_pair_count_when_one_measurement_is_unobserved(
    tmp_path: Path,
) -> None:
    repo = _repo(root=tmp_path, declaration=None)
    sha = _cycle(
        repo=repo,
        source="value = 2\n",
        checksum="reversed",
        red_at="2026-11-23T10:05:00Z",
        green_at="2026-11-23T10:00:00Z",
    )

    summaries, cycles, _, _ = _emit(root=tmp_path, repo=repo, shas=[sha])

    assert [summary.get("completed_cycle_count") for summary in summaries] == [1]
    assert len(cycles) == 1
    cycle = cycles[0]
    assert cycle.get("product_lloc_changed") is None
    assert cycle.get("product_lloc_unobserved_reason") == "unsupported-counting"
    assert cycle.get("elapsed_seconds") is None
    assert cycle.get("elapsed_unobserved_reason") == "invalid-or-reversed-timestamps"


def test_emit_calibration_journals_an_observed_empty_series_as_zero(tmp_path: Path) -> None:
    repo = _repo(root=tmp_path, declaration=_PYPROJECT)
    _ = (repo / "src" / "pkg" / "thing.py").write_text("value = 2\n", encoding="utf-8")
    _ = _git(repo=repo, argv=["add", "-A"])
    _ = _git(
        repo=repo,
        argv=["commit", "-m", f"feat(pkg): suite-green only\n\nFactory-Run-Id: {_DISPATCH_ID}"],
    )
    sha = _git(repo=repo, argv=["rev-parse", "HEAD"])

    summaries, cycles, _, _ = _emit(root=tmp_path, repo=repo, shas=[sha])

    assert [summary.get("completed_cycle_count") for summary in summaries] == [0]
    assert [summary.get("completed_cycle_assertion_count") for summary in summaries] == [3]
    assert cycles == []


def test_emit_calibration_leaves_an_unreadable_series_to_the_verified_pair_reason(
    tmp_path: Path,
) -> None:
    repo = _repo(root=tmp_path, declaration=_PYPROJECT)

    summaries, cycles, calibration, _ = _emit(root=tmp_path, repo=repo, shas=[])

    assert summaries == []
    assert cycles == []
    assert calibration.get("tdd.verified_pair_count") is None
    assert calibration.get("tdd.verified_pair_unobserved_reason") is not None
