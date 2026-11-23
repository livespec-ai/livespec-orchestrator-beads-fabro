"""A run past its wall budget has its committed tree published before the cancel (bd-ib-ds4yrm).

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget" and Scenario 175: a budget cancel parks the run "with its
work preserved". The preserve-by-reference pointer carries only stage diff
artifacts, which can be empty (78 bytes each) while the run's committed tree is
the only copy of hours of work, so the pointer alone must not release the
cancel: the run's committed changes are published to a preservation ref first,
and when that publication fails the run is HELD with the failed step named.

WHY THE CASES ARE SPLIT THIS WAY. The success case asserts the publication
happened BEFORE `rm` (a publisher that runs after the destruction publishes
nothing) and that the ref and commit reach the `run-wall-budget-exceeded`
record. The failure case keeps a pointer that DOES read back, so a build that
still released on the pointer alone cancels here and fails the assertion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    PreservedTree,
    PublishFailure,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import RunWallBudget
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_publish import (
    STEP_BASE_COMMIT,
    BudgetPublisher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RUN_WALL_BUDGET_EXCEEDED_STAGE,
    RUN_WALL_BUDGET_HELD_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
    RunWallBudgetWatch,
    RunWallVerdict,
    cancel_run_past_budget,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_clock import (
    RUN_RECORD_SOURCE,
    RunWallStart,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._node_timeouts import REPOSITORY_LAYER

_RUN_ID = "01RUN"
_WORK_ITEM_ID = "bd-ib-ds4yrm"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_BUDGET = RunWallBudget(seconds=3600.0, layer=REPOSITORY_LAYER)
_START_EPOCH = 1_791_892_800.0
_NOW_EPOCH = _START_EPOCH + 7200.0
_REF = f"refs/livespec/preserved-publish/{_WORK_ITEM_ID}/" + "b" * 40
_COMMIT = "b" * 40
_EVENTS = '[{"type": "stage.started", "node_id": "implement", "timestamp": "2026-10-13T12:00:00Z"}]'
_INSPECT = f'[{{"run_id": "{_RUN_ID}", "status": {{"kind": "running"}}}}]'


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _ScriptedRunner:
    calls: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        verb = argv[1] if len(argv) > 1 else ""
        self.calls.append(verb)
        stdout = {"events": _EVENTS, "inspect": _INSPECT}.get(verb, "")
        return CommandResult(exit_code=0, stdout=stdout, stderr="")


@dataclass(kw_only=True)
class _FakeLedger:
    comments: list[dict[str, Any]] = field(default_factory=list)

    def list_comments(self, *, issue_id: str) -> list[dict[str, Any]]:
        _ = issue_id
        return list(self.comments)

    def add_comment(self, *, issue_id: str, body: str) -> None:
        _ = issue_id
        self.comments.append({"id": "comment-9173", "text": body})


@dataclass(kw_only=True)
class _Publisher:
    """Stands in for `BudgetPublisher`: records when it ran relative to `rm`."""

    runner: _ScriptedRunner
    outcome: PreservedTree | PublishFailure
    calls_at_publish: list[list[str]] = field(default_factory=list)

    def publish(self, *, plan: object, runner: object, journal: object, run_id: str) -> Any:
        _ = (plan, runner, journal, run_id)
        self.calls_at_publish.append(list(self.runner.calls))
        return self.outcome


def _tree() -> PreservedTree:
    return PreservedTree(ref=_REF, commit=_COMMIT, file_count=3, scope="committed", source="run")


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_WORK_ITEM_ID,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server=_SERVER,
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        run_wall_budget=_BUDGET,
    )


def _port(*, repo: Path, runner: _ScriptedRunner) -> FabroPort:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url=_SERVER),
        runner=runner,
        cwd=repo,
    )


def _cancel(
    *, tmp_path: Path, publisher: _Publisher, runner: _ScriptedRunner
) -> tuple[Any, _RecordingJournal]:
    journal = _RecordingJournal()
    verdict = cancel_run_past_budget(
        dispatch_id="dispatch-01",
        plan=_plan(repo=tmp_path),
        port=_port(repo=tmp_path, runner=runner),
        runner=cast("Any", runner),
        journal=cast("Any", journal),
        run_id=_RUN_ID,
        start=RunWallStart(epoch=_START_EPOCH, source=RUN_RECORD_SOURCE),
        now_epoch=_NOW_EPOCH,
        ledger=cast("Any", _FakeLedger()),
        publisher=cast("Any", publisher),
    )
    return verdict, journal


def test_the_tree_is_published_before_the_run_is_cancelled_and_named_on_the_record(
    tmp_path: Path,
) -> None:
    """The publication precedes `rm`, and its ref and commit reach the exceeded record."""
    runner = _ScriptedRunner()
    publisher = _Publisher(runner=runner, outcome=_tree())
    verdict, journal = _cancel(tmp_path=tmp_path, publisher=publisher, runner=runner)
    assert verdict == RunWallVerdict.CANCELLED
    assert len(publisher.calls_at_publish) == 1
    assert "rm" not in publisher.calls_at_publish[0]
    assert "rm" in runner.calls
    exceeded = [r for r in journal.records if r.get("stage") == RUN_WALL_BUDGET_EXCEEDED_STAGE]
    assert len(exceeded) == 1
    assert exceeded[0]["preserved_ref"] == _REF
    assert exceeded[0]["preserved_ref_commit"] == _COMMIT


def test_a_failed_publication_holds_the_run_even_when_the_pointer_reads_back(
    tmp_path: Path,
) -> None:
    """A pointer to empty stage diffs does not release the cancel on its own."""
    runner = _ScriptedRunner()
    failure = PublishFailure(
        step="files-read",
        detail=(
            "run-files read reported zero changed files, but the run state retains"
            " 8 non-empty stage diff artifact(s)"
        ),
        discrepancy=True,
    )
    publisher = _Publisher(runner=runner, outcome=failure)
    verdict, journal = _cancel(tmp_path=tmp_path, publisher=publisher, runner=runner)
    assert verdict == RunWallVerdict.HELD
    assert "rm" not in runner.calls
    assert all(r.get("stage") != RUN_WALL_BUDGET_EXCEEDED_STAGE for r in journal.records)
    held = [r for r in journal.records if r.get("stage") == RUN_WALL_BUDGET_HELD_STAGE]
    assert len(held) == 1
    measurement = str(held[0]["failed_measurement"])
    assert "files-read" in measurement
    assert "8 non-empty stage diff" in measurement


def test_the_watch_hands_its_publisher_to_every_budget_decision(tmp_path: Path) -> None:
    """`RunWallBudgetWatch` carries the publisher, so both callers get the same rule."""
    runner = _ScriptedRunner()
    publisher = _Publisher(runner=runner, outcome=_tree())
    budget = RunWallBudgetWatch(ledger=cast("Any", _FakeLedger()), publisher=cast("Any", publisher))
    verdict = budget.verdict(
        dispatch_id="dispatch-01",
        plan=_plan(repo=tmp_path),
        port=_port(repo=tmp_path, runner=runner),
        runner=cast("Any", runner),
        journal=cast("Any", _RecordingJournal()),
        run_id=_RUN_ID,
        recorded_epoch=_START_EPOCH,
        now_epoch=_NOW_EPOCH,
    )
    assert verdict == RunWallVerdict.CANCELLED
    assert len(publisher.calls_at_publish) == 1


def test_a_journal_without_a_staging_row_publishes_nothing_and_names_the_base(
    tmp_path: Path,
) -> None:
    """The preservation commit's parent is the run's staged base; none known, no publication."""
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.append(record={"stage": "unrelated", "work_item_id": _WORK_ITEM_ID})
    outcome = BudgetPublisher().publish(
        plan=_plan(repo=tmp_path),
        runner=cast("Any", _ScriptedRunner()),
        journal=journal,
        run_id=_RUN_ID,
    )
    assert isinstance(outcome, PublishFailure)
    assert outcome.step == STEP_BASE_COMMIT
    assert "staged" in outcome.detail


def test_a_journal_that_cannot_be_read_back_names_the_base_step(tmp_path: Path) -> None:
    """A journal writer with no file behind it cannot establish the base."""
    outcome = BudgetPublisher().publish(
        plan=_plan(repo=tmp_path),
        runner=cast("Any", _ScriptedRunner()),
        journal=cast("Any", _RecordingJournal()),
        run_id=_RUN_ID,
    )
    assert isinstance(outcome, PublishFailure)
    assert outcome.step == STEP_BASE_COMMIT
    assert "journal" in outcome.detail
