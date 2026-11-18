"""Merge and post-merge janitor flow for the Dispatcher engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance import (
    CONSECUTIVE_CONFLICTING_REPORTS,
    BaseAdvancedAfterArming,
    base_advanced_detail,
    reports_base_advanced_after_arming,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance_record_files import (
    measure_conflicted_paths,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_confirm import confirm_pr
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_exhaustion import (
    outcome_at_exhaustion,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_merge_queue import (
    MergeQueueObservation,
    queue_removal_result,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_merge_pr_association import (
    pr_view_for_merge_sha,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    pr_update_branch_argv,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_view import (
    GH_TIMEOUT_SECONDS,
    view_pr,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_required_check_failure import (
    RequiredCheckFailureContext,
    RerunPollState,
    journal_rerun_merged,
    required_check_failure,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
        PollPolicy,
        SleepFn,
    )

__all__: list[str] = ["await_merge", "confirm_pr", "outcome_after_await", "settle_merge_wait"]


def await_merge(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    sleep: SleepFn,
    poll: PollPolicy,
) -> PrView | DispatchOutcome | None:
    # The streak of CONSECUTIVE polls that reported an armed, OPEN pull request
    # conflicting with the default branch. Reset by any poll that reported
    # otherwise AND by any poll whose view could not be read, per
    # `_dispatcher_base_advance`'s own rule that an absent reading is not a
    # report in either direction.
    conflicting_reports = 0
    merge_queue = MergeQueueObservation()
    rerun_state = RerunPollState(attempts_before_rerun={})
    required_check_context = RequiredCheckFailureContext(
        outcome_type=outcome_type,
        plan=plan,
        runner=runner,
        journal=journal,
    )
    for attempt in range(poll.attempts):
        reading = view_pr(
            plan=plan,
            runner=runner,
            journal=journal,
        )
        view = reading.view if reading.error is None else None
        merged_view = _merged_view(
            view=view,
            context=required_check_context,
            rerun_state=rerun_state,
        )
        if merged_view is not None:
            return merged_view
        queue_result = queue_removal_result(
            outcome_type=outcome_type,
            plan=plan,
            runner=runner,
            journal=journal,
            observation=merge_queue,
            view=view,
        )
        if queue_result is not None and not isinstance(queue_result, PrView):
            return queue_result
        view = queue_result
        denied_merge = _merged_after_integration_denial(
            error=reading.error,
            plan=plan,
            runner=runner,
            journal=journal,
            context=required_check_context,
            rerun_state=rerun_state,
        )
        if denied_merge is not None:
            return denied_merge
        if view is not None and _reports_overtaken_arming(view=view):
            conflicting_reports += 1
            if conflicting_reports >= CONSECUTIVE_CONFLICTING_REPORTS:
                measurement = measure_conflicted_paths(
                    repo=plan.repo,
                    runner=runner,
                    pr_head=view.head or "",
                    default_branch_tip=view.base or "",
                )
                return outcome_type(
                    work_item_id=plan.work_item_id,
                    status="blocked",
                    stage="merge-poll",
                    pr_number=view.number,
                    merge_sha=None,
                    detail=base_advanced_detail(work_item_id=plan.work_item_id),
                    base_advanced=BaseAdvancedAfterArming(
                        factory=plan.fabro_factory_name,
                        pr_head=view.head,
                        default_branch_tip=view.base,
                        conflicted_paths=measurement.paths,
                        conflict_measurement_failure=(
                            "git-merge-tree" if measurement.failure is not None else None
                        ),
                    ),
                )
        else:
            conflicting_reports = 0
        if view is not None and view.merge_state_status == "BEHIND":
            update = runner.run(
                argv=pr_update_branch_argv(plan=plan, number=view.number),
                cwd=plan.repo,
                timeout_seconds=GH_TIMEOUT_SECONDS,
            )
            journal_stage(journal=journal, plan=plan, stage="pr-update-branch", result=update)
        elif (
            failure := required_check_failure(
                context=required_check_context,
                view=view,
                rerun_state=rerun_state,
                may_keep_polling=attempt + 1 < poll.attempts,
            )
        ) is not None:
            return failure
        if attempt + 1 < poll.attempts:
            sleep(poll.interval_seconds)
    return None


def settle_merge_wait(  # noqa: PLR0913 — kw-only stage; each field is an independent caller input.
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    sleep: SleepFn,
    poll: PollPolicy,
    pr_number: int,
    run_id: str | None,
) -> DispatchOutcome:
    """Wait for the merge, then dispose of whatever the wait ended with.

    The seconds the wait spent are measured HERE, on the poll policy's clock,
    because only a handoff states them and only this function sees both ends of
    the wait.
    """
    waiting_since = poll.clock()
    merged = await_merge(
        outcome_type=outcome_type,
        plan=plan,
        runner=runner,
        journal=journal,
        sleep=sleep,
        poll=poll,
    )
    return outcome_after_await(
        outcome_type=outcome_type,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=merged,
        pr_number=pr_number,
        run_id=run_id,
        waited_seconds=int(poll.clock() - waiting_since),
    )


def outcome_after_await(  # noqa: PLR0913 — kw-only disposition; each field is an independent caller input.
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    merged: PrView | DispatchOutcome | None,
    pr_number: int,
    run_id: str | None,
    waited_seconds: int,
) -> DispatchOutcome:
    """One terminal outcome from `await_merge`'s three-way answer.

    The poll reports a MERGED view, a terminal failure it already decided (a
    required check that failed for good), or an exhausted budget, and each is a
    different outcome. It lives beside the poll rather than inside `run_dispatch`
    so that function stays one readable list of stages rather than a stage list
    with a disposition tree hanging off its end.
    """
    if merged is None:
        merged = outcome_at_exhaustion(
            outcome_type=outcome_type,
            plan=plan,
            runner=runner,
            journal=journal,
            pr_number=pr_number,
            run_id=run_id,
            waited_seconds=waited_seconds,
        )
    # Discriminated on `PrView` rather than on `outcome_type`, which is a
    # runtime PARAMETER and so narrows nothing for the reader or the checker.
    if isinstance(merged, PrView):
        return post_merge(
            outcome_type=outcome_type,
            plan=plan,
            runner=runner,
            journal=journal,
            merged=pr_view_for_merge_sha(
                repo=plan.repo,
                work_item_id=plan.work_item_id,
                merged=merged,
                runner=runner,
                journal=journal,
            ),
        )
    return merged


def _reports_overtaken_arming(*, view: PrView) -> bool:
    """One poll's reading, routed through the pure decision that owns the rule."""
    return reports_base_advanced_after_arming(
        state=view.state,
        auto_merge_armed=view.auto_merge_armed,
        merge_state_status=view.merge_state_status,
    )


def _is_integration_access_denied(*, error: str | None) -> bool:
    """Recognize GitHub App authorization denial without retrying transient reads."""
    return error is not None and "resource not accessible by integration" in error.lower()


def _merged_view(
    *,
    view: PrView | None,
    context: RequiredCheckFailureContext,
    rerun_state: RerunPollState,
) -> PrView | None:
    """Record a merged observation, or leave the poll's ordinary path alone."""
    if view is None or view.state != "MERGED":
        return None
    journal_rerun_merged(context=context, rerun_state=rerun_state)
    return view


def _merged_after_integration_denial(
    *,
    error: str | None,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    context: RequiredCheckFailureContext,
    rerun_state: RerunPollState,
) -> PrView | None:
    """Use a rollup-free read only to establish a merge hidden by app scope."""
    if not _is_integration_access_denied(error=error):
        return None
    merged_reading = view_pr(
        plan=plan,
        runner=runner,
        journal=journal,
        include_status_checks=False,
    )
    return _merged_view(view=merged_reading.view, context=context, rerun_state=rerun_state)
