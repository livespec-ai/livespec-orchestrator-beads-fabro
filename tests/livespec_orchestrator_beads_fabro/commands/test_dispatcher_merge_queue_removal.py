"""A merge-queue removal is recorded from the merge poll's reread.

The factory must distinguish a pull request that was queued from one whose
queue entry vanished while the merge wait was running.  The reread is the
authoritative observation: its journal row preserves both when the removal was
observed and the mergeability GitHub reported at that moment, so the later
refresh-or-rearm decision is auditable rather than inferred from a stranded
pull request.
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_merge import settle_merge_wait
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan

_ITEM_ID = "bd-ib-aujlop"


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_ITEM_ID,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text='{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}',
        default_branch="master",
        fabro_factory_name="petri",
    )


def _view(*, queued: bool, armed: bool, merge_state: str) -> CommandResult:
    return CommandResult(
        exit_code=0,
        stdout=json.dumps(
            {
                "number": 5522,
                "state": "OPEN",
                "autoMergeRequest": {"enabledAt": "2026-11-18T12:50:52Z"} if armed else None,
                "mergeQueueEntry": {"enqueuedAt": "2026-11-18T13:14:12Z"} if queued else None,
                "mergeStateStatus": merge_state,
                "mergeCommit": None,
                "headRefOid": "098658d0",
                "baseRefOid": "11b7ad2d",
                "statusCheckRollup": [],
            }
        ),
        stderr="",
    )


@dataclass(kw_only=True)
class _Forge:
    views: list[CommandResult]
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
        assert argv[:3] == ["gh", "pr", "view"]
        return self.views.pop(0) if len(self.views) > 1 else self.views[0]


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_a_queue_removal_is_reread_and_journaled_with_its_observation_time_and_merge_state(
    tmp_path: Path,
) -> None:
    forge = _Forge(
        views=[
            _view(queued=True, armed=True, merge_state="CLEAN"),
            _view(queued=False, armed=False, merge_state="DIRTY"),
            _view(queued=False, armed=False, merge_state="DIRTY"),
        ]
    )
    journal = _Journal()

    _ = settle_merge_wait(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=forge,
        journal=journal,
        sleep=lambda _: None,
        poll=PollPolicy(attempts=2, interval_seconds=0.0),
        pr_number=5522,
        run_id="01M7Q76A2EYA",
    )

    removals = [
        record for record in journal.records if record.get("stage") == "merge-queue-removed"
    ]
    assert len(removals) == 1
    removal = removals[0]
    assert removal["work_item_id"] == _ITEM_ID
    assert removal["pr_number"] == 5522
    assert isinstance(removal["removed_at"], str)
    assert removal["removed_at"] != ""
    assert removal["merge_state_status"] == "DIRTY"
    assert len([argv for argv in forge.calls if argv[:3] == ["gh", "pr", "view"]]) >= 2


def test_a_removal_between_polls_is_recovered_when_the_first_view_is_already_dequeued(
    tmp_path: Path,
) -> None:
    class _RearmForge(_Forge):
        def run(
            self,
            *,
            argv: list[str],
            cwd: Path,
            timeout_seconds: float,
            env: dict[str, str] | None = None,
            stdin: int | None = None,
        ) -> CommandResult:
            if argv[:3] == ["gh", "pr", "merge"]:
                self.calls.append(argv)
                return CommandResult(exit_code=0, stdout="", stderr="")
            if argv[:2] == ["gh", "api"]:
                self.calls.append(argv)
                return CommandResult(exit_code=0, stdout='[{"number": 5522}]', stderr="")
            return super().run(
                argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env, stdin=stdin
            )

    forge = _RearmForge(
        views=[
            _view(queued=False, armed=False, merge_state="CLEAN"),
            _view(queued=True, armed=True, merge_state="CLEAN"),
            CommandResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "number": 5522,
                        "state": "MERGED",
                        "autoMergeRequest": None,
                        "mergeQueueEntry": None,
                        "mergeStateStatus": "CLEAN",
                        "mergeCommit": {"oid": "a" * 40},
                        "headRefOid": "098658d0",
                        "baseRefOid": "11b7ad2d",
                        "statusCheckRollup": [],
                    }
                ),
                stderr="",
            ),
        ]
    )
    journal = _Journal()

    _ = settle_merge_wait(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=forge,
        journal=journal,
        sleep=lambda _: None,
        poll=PollPolicy(attempts=3, interval_seconds=0.0),
        pr_number=5522,
        run_id="01M7Q76A2EYA",
    )

    removals = [
        record for record in journal.records if record.get("stage") == "merge-queue-removed"
    ]
    assert len(removals) == 1
    assert removals[0]["merge_state_status"] == "CLEAN"
    assert any(argv[:3] == ["gh", "pr", "merge"] for argv in forge.calls)


def test_a_conflicting_first_view_without_queue_or_arming_hands_off_to_pr_refresh(
    tmp_path: Path,
) -> None:
    forge = _Forge(views=[_view(queued=False, armed=False, merge_state="DIRTY")])
    journal = _Journal()

    outcome = settle_merge_wait(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=forge,
        journal=journal,
        sleep=lambda _: None,
        poll=PollPolicy(attempts=2, interval_seconds=0.0),
        pr_number=5522,
        run_id="01M7Q76A2EYA",
    )

    assert outcome.base_advanced is not None
    assert outcome.base_advanced.cause == "merge-queue-removed-after-arming"
