"""Queue-removal observation and recovery within the merge poll."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance import (
    MERGE_QUEUE_REMOVED_AFTER_ARMING,
    BaseAdvancedAfterArming,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    merge_queue_retry_argv,
    pr_arm_argv,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_view import (
    GH_TIMEOUT_SECONDS,
    view_pr,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
    )

__all__: list[str] = ["MergeQueueObservation", "queue_removal_result"]

_CONFLICTING_STATES = frozenset({"DIRTY", "CONFLICTING"})


@dataclass
class MergeQueueObservation:
    """The queue-presence transition accumulated across one merge poll."""

    was_present: bool = False
    removal_observed: bool = False


def queue_removal_result(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    observation: MergeQueueObservation,
    view: PrView | None,
) -> PrView | DispatchOutcome | None:
    """Journal and repair a dequeue after the authoritative pull-request reread."""
    if view is None:
        return None
    if observation.was_present and not view.merge_queue_queued:
        observation.removal_observed = True
        journal.append(
            record={
                "stage": "merge-queue-removed",
                "work_item_id": plan.work_item_id,
                "pr_number": view.number,
                "removed_at": utc_now_iso(),
                "merge_state_status": view.merge_state_status,
            }
        )
    observation.was_present = view.merge_queue_queued
    if not observation.removal_observed or view.state != "OPEN":
        return view
    if view.merge_state_status in _CONFLICTING_STATES:
        return _conflict_outcome(outcome_type=outcome_type, plan=plan, view=view)
    if not view.merge_queue_queued and not view.auto_merge_armed:
        return _rearm(plan=plan, runner=runner, journal=journal, view=view)
    return view


def _conflict_outcome(
    *, outcome_type: type[DispatchOutcome], plan: DispatchPlan, view: PrView
) -> DispatchOutcome:
    """Stop polling so the normal resume route enters ``pr_refresh``."""
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="blocked",
        stage="merge-poll",
        pr_number=view.number,
        merge_sha=None,
        detail=(
            "merge-queue-removed-after-arming: the merge queue removed the factory pull "
            "request while GitHub reported it conflicting; the factory will resume at "
            "pr_refresh before spending the remaining merge-poll budget."
        ),
        base_advanced=BaseAdvancedAfterArming(
            factory=plan.fabro_factory_name,
            pr_head=view.head,
            default_branch_tip=view.base,
            cause=MERGE_QUEUE_REMOVED_AFTER_ARMING,
        ),
    )


def _rearm(
    *, plan: DispatchPlan, runner: CommandRunner, journal: JournalWriter, view: PrView
) -> PrView | None:
    """Re-arm and authoritatively reread a dequeue-cleared auto-merge request."""
    argv = pr_arm_argv(plan=plan, number=view.number)
    if not argv:
        return view
    arm = runner.run(argv=argv, cwd=plan.repo, timeout_seconds=GH_TIMEOUT_SECONDS)
    journal_stage(journal=journal, plan=plan, stage="merge-queue-rearm", result=arm)
    retry = None if arm.exit_code == 0 else merge_queue_retry_argv(argv=argv, stderr=arm.stderr)
    if retry is not None:
        arm = runner.run(argv=retry, cwd=plan.repo, timeout_seconds=GH_TIMEOUT_SECONDS)
        journal_stage(journal=journal, plan=plan, stage="merge-queue-rearm", result=arm)
    return view_pr(plan=plan, runner=runner, journal=journal, include_status_checks=False).view
