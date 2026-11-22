"""The recovery terminal for a run that ended after its sandbox disappeared."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_failure import (
    fabro_failure_outcome_detail,
)
from livespec_orchestrator_beads_fabro.commands._fabro_sandbox_termination import (
    LOST_SANDBOX_CATEGORY,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
    from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult

__all__: list[str] = [
    "LOST_SANDBOX_RELEASE_STATUS",
    "lost_sandbox_release_outcome",
]

# This deliberately has its own status.  `failed` would be consumed by the
# non-convergence route and `blocked` would be escalated for a human, while a
# lost sandbox is a recoverable host failure whose claim must return to ready.
LOST_SANDBOX_RELEASE_STATUS = "lost-sandbox-release"


def lost_sandbox_release_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str | None,
    inspect: FabroInspectResult | None,
    stderr: str,
) -> DispatchOutcome | None:
    """Release a terminal missing-sandbox failure, or decline every other run."""
    failure = None if inspect is None else inspect.failure
    if failure is None or failure.category != LOST_SANDBOX_CATEGORY:
        return None
    detail = fabro_failure_outcome_detail(failure=failure, fallback=stderr)
    return outcome_type(
        work_item_id=plan.work_item_id,
        status=LOST_SANDBOX_RELEASE_STATUS,
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=(
            f"{detail}; the run ended after its sandbox was lost and its dispatch claim "
            "is released to ready for recovery"
        ),
        fabro_run_id=run_id,
        fabro_factory_name=plan.fabro_factory_name,
        fabro_failure_cause=failure.cause,
        fabro_failure_category=failure.category,
        fabro_failure_signature=failure.signature,
        provider_usage_limit=failure.provider_usage_limit,
        provider_usage_limit_provider=failure.provider_usage_limit_provider,
    )
