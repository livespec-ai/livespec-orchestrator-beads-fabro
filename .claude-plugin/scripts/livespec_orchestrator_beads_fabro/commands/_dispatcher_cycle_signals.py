"""Completed-cycle measurements as the journal carries them.

Plan slice S6 (`bd-ib-z2y4ca`). `_dispatcher_cycle_probe` measures a dispatch's
completed cycles; this module flattens the measured series into sibling journal
records that calibration appends beside its `calibration` record.

WHY SIBLING RECORDS AND NOT KEYS ON THE `calibration` RECORD. That record's key
set and flat-scalar shape are pinned (Scenario 12), and one cycle is a variable
number of rows, which a flat record cannot hold. The same shape as the
`pr-open-diff` record: the stage that observed the value writes it down.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_measure import (
    PRODUCT_LLOC_MEASUREMENT_METHOD,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_probe import (
    CompletedCycle,
    gather_completed_cycle_series,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_probe import dispatch_id_for
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["CYCLE_STAGE", "SUMMARY_STAGE", "completed_cycle_records"]

SUMMARY_STAGE = "calibration-cycles"
CYCLE_STAGE = "calibration-cycle"


def completed_cycle_records(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    records: tuple[dict[str, object], ...],
    runner: CommandRunner,
) -> tuple[dict[str, object], ...]:
    """The flat journal records for this dispatch's IDENTIFIED series.

    A summary, then one record per cycle. An unreadable series journals nothing
    here: its reason is already on the `calibration` record as
    `tdd.verified_pair_unobserved_reason`, and a second record for it would
    change the journal of every dispatch that never published a pull request. An
    observed empty series IS journaled, as a summary whose count is `0`, so the
    comparison can tell it from an unreadable one. Every record is a flat scalar
    map so the egress leg promotes each key as it does for any other stage.
    """
    cycles = gather_completed_cycle_series(
        repo=repo,
        item=item,
        pr_number=outcome.pr_number,
        dispatch_id=dispatch_id_for(records=records, work_item_id=item.id),
        runner=runner,
    )
    if not cycles.observed:
        return ()
    summary: dict[str, object] = {
        "stage": SUMMARY_STAGE,
        "work_item_id": item.id,
        "completed_cycle_count": cycles.completed_count,
        "completed_cycle_assertion_count": cycles.assertion_count,
    }
    return (summary, *(_cycle_record(work_item_id=item.id, cycle=c) for c in cycles.cycles))


def _cycle_record(*, work_item_id: str, cycle: CompletedCycle) -> dict[str, object]:
    return {
        "stage": CYCLE_STAGE,
        "work_item_id": work_item_id,
        "ordinal": cycle.ordinal,
        "pair_id": cycle.pair_id,
        "commit": cycle.commit,
        "product_lloc_changed": cycle.product_lloc_changed,
        "product_lloc_unobserved_reason": cycle.product_lloc_unobserved_reason,
        "product_lloc_method": PRODUCT_LLOC_MEASUREMENT_METHOD,
        "elapsed_seconds": cycle.elapsed_seconds,
        "elapsed_unobserved_reason": cycle.elapsed_unobserved_reason,
    }
