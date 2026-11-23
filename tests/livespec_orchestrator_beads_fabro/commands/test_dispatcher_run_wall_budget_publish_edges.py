"""The edges of the budget publication that the main module's cases do not reach (bd-ib-ds4yrm).

Split from `test_dispatcher_run_wall_budget_publish.py` because these were found
by a coverage measurement taken after that module's Red was authored, and a
Red's test bytes are fixed across its Red-to-Green pair.

Three claims. The real publisher parents the preservation commit on the base the
JOURNAL names (not this host's head) and hands the factory's own HTTP face to the
publication; a factory declaring no server fails its own step; and a ref listing
that cannot be taken is named beside the publication's failure rather than
replaced by it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_run_wall_budget_publish as mod
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_base import (
    SOURCE_STAGE,
    STAGED_AT_KEY,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    PreservedTree,
    PublishFailure,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import RunWallBudget
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RUN_WALL_BUDGET_HELD_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
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
_ITEM = "bd-ib-ds4yrm"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_BASE = "3fd93cba8feea4c249e0be2c2a0b2a8a360654d9"
_BUDGET = RunWallBudget(seconds=3600.0, layer=REPOSITORY_LAYER)
_START = 1_791_892_800.0
_INSPECT = f'[{{"run_id": "{_RUN_ID}", "status": {{"kind": "running"}}}}]'


def _plan(*, repo: Path, server: str | None = _SERVER) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_ITEM,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server=server,
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        run_wall_budget=_BUDGET,
    )


@dataclass(kw_only=True)
class _Runner:
    ls_remote_exit: int = 0
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
        exit_code = self.ls_remote_exit if verb == "ls-remote" else 0
        return CommandResult(
            exit_code=exit_code, stdout=_INSPECT if verb == "inspect" else "", stderr=""
        )


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _staged_journal(*, tmp_path: Path) -> JournalFile:
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.append(record={"stage": SOURCE_STAGE, "work_item_id": _ITEM, STAGED_AT_KEY: _BASE})
    return journal


def test_the_publisher_parents_the_tree_on_the_journals_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The base handed to the publication is the staged commit the journal names."""
    seen: dict[str, Any] = {}
    tree = PreservedTree(ref="refs/x", commit="d" * 40, file_count=1, scope=None, source=None)

    def fake_publish(**kwargs: Any) -> PreservedTree:
        seen.update(kwargs)
        return tree

    monkeypatch.setattr(mod, "publish_run_tree", fake_publish)
    outcome = mod.BudgetPublisher().publish(
        plan=_plan(repo=tmp_path),
        runner=cast("Any", _Runner()),
        journal=_staged_journal(tmp_path=tmp_path),
        run_id=_RUN_ID,
    )
    assert outcome is tree
    assert seen["base_commit"] == _BASE
    assert seen["run_id"] == _RUN_ID
    assert seen["work_item_id"] == _ITEM
    assert seen["port"].target.server_url == _SERVER


def test_a_factory_without_a_server_fails_its_own_step(tmp_path: Path) -> None:
    """No server url means no route to the run's files, and the step says so."""
    outcome = mod.BudgetPublisher().publish(
        plan=_plan(repo=tmp_path, server=None),
        runner=cast("Any", _Runner()),
        journal=_staged_journal(tmp_path=tmp_path),
        run_id=_RUN_ID,
    )
    assert isinstance(outcome, PublishFailure)
    assert outcome.step == mod.STEP_FACTORY_SERVER


def test_an_unobservable_ref_listing_is_named_beside_the_publication_failure(
    tmp_path: Path,
) -> None:
    """Both measurements reach the held record; neither replaces the other."""
    runner = _Runner(ls_remote_exit=2)

    @dataclass(kw_only=True)
    class _Failing:
        def publish(self, *, plan: object, runner: object, journal: object, run_id: str) -> Any:
            _ = (plan, runner, journal, run_id)
            return PublishFailure(step="blob", detail="forge refused")

    journal = _Journal()
    verdict = cancel_run_past_budget(
        dispatch_id=None,
        plan=_plan(repo=tmp_path),
        port=FabroPort(
            fabro_bin="fabro",
            target=FabroTarget(server_url=_SERVER),
            runner=runner,
            cwd=tmp_path,
        ),
        runner=cast("Any", runner),
        journal=cast("Any", journal),
        run_id=_RUN_ID,
        start=RunWallStart(epoch=_START, source=RUN_RECORD_SOURCE),
        now_epoch=_START + 7200.0,
        ledger=None,
        publisher=cast("Any", _Failing()),
    )
    assert verdict == RunWallVerdict.HELD
    assert "rm" not in runner.calls
    held = [r for r in journal.records if r.get("stage") == RUN_WALL_BUDGET_HELD_STAGE]
    measurement = str(held[0]["failed_measurement"])
    assert "git ls-remote" in measurement
    assert "publication step blob failed: forge refused" in measurement
