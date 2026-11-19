"""Write a whole-run-wall-budget cancellation after its export precondition held.

The watchdog decides whether to cancel and obtains the whole-record export.
This helper performs the final removal and journals the evidence that describes
that removal, keeping the watch loop under its file-size ceiling.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    run_wall_budget_exceeded_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_refs import (
    VerifiedPreservationRef,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_clock import RunWallStart
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel import (
    FABRO_RM_TIMEOUT_SECONDS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_run_reading import (
    executing_stage,
    last_publish_draft_publication,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog_run_probe import (
    WatchdogRunReading,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = ["record_wall_budget_cancel"]


def record_wall_budget_cancel(  # noqa: PLR0913 -- cancellation evidence has independent fields.
    *,
    dispatch_id: str | None,
    plan: DispatchPlan,
    port: FabroPort,
    journal: JournalWriter,
    run_id: str,
    elapsed_seconds: float,
    start: RunWallStart,
    reading: WatchdogRunReading,
    pointer: str | None,
    verified_ref: VerifiedPreservationRef | None,
    export_failure: str,
    whole_record_export_location: str,
    whole_record_export_sha256: str | None,
) -> None:
    """Remove the run only after its whole-record export has read back."""
    removed = port.rm(run_id=run_id, timeout_seconds=FABRO_RM_TIMEOUT_SECONDS)
    journal.append(
        record={
            **run_wall_budget_exceeded_record(
                work_item_id=plan.work_item_id,
                dispatch_id=dispatch_id,
                run_id=run_id,
                factory=plan.fabro_factory_name,
                executing_stage=executing_stage(events_json=reading.events_json),
                publication=last_publish_draft_publication(
                    events_json=reading.events_json,
                    record_text=reading.record_text,
                ),
                elapsed_seconds=elapsed_seconds,
                budget=plan.run_wall_budget,
                start_source=start.source,
                preserved_pointer=pointer,
                preserved_ref=None if verified_ref is None else verified_ref.ref,
                preserved_ref_commit=None if verified_ref is None else verified_ref.commit,
                export_failed_measurement=export_failure,
                whole_record_export_location=whole_record_export_location,
                whole_record_export_sha256=whole_record_export_sha256,
            ),
            "rm_exit_code": removed.command.exit_code,
        }
    )
