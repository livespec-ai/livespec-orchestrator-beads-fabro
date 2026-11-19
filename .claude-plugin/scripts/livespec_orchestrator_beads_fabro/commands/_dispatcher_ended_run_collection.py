"""Collect ended, owned runs once their work-item has closed, or is back at ready or backlog.

The normal reconciliation join deliberately considers non-terminal runs: its
job is to release active scheduler slots.  A terminal run carries no slot, but
its Petri sandbox is only stopped, not deleted.  This separate collector owns
that retention boundary.  It reads the same recorded attribution as the run
reconciler, so clearance, availability-probe, and item-less runs cannot become
collectable merely because they appear in a shared factory inventory.

A run whose item rests at `ready` or `backlog` is collected too, but only when origin holds the
run's committed tree (bd-ib-jshkjz): its pod otherwise held a reservation for as long as the item
waited. Such a run keeps its preservation refs, because a re-dispatch seeds from them, and a run
whose tree origin does not hold, or whose record cannot say, keeps its sandbox and is journaled as
retained for unpublished work. An item at `blocked`, `needs-human` or in flight keeps its sandbox.

The collector serves ONE dispatching repository per call: `repo` is the
repository whose journal and ledger the inventory was attributed against, which
is also the repository whose forge origin holds the run's preservation refs.
`_dispatcher_fleet_run_collection` calls it once per other repository that
dispatches to the same factory, so a repository's runs never depend on a pass of
that repository's own.

Every ended run the inventory attributes and the collector does NOT collect is
a REFUSAL, journaled with the run, its dispatching repository, its work-item and
the status read -- or `None` where no status could be read, which is also what an
unreadable ledger looks like.  A refusal already journaled for the same run at the
same status is not journaled again, because the periodic pass would otherwise
append every standing refusal on every tick.
"""

from __future__ import annotations

import time
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_ended_run_export import (
    disk_pressure,
    export_ended_run,
    prune_expired_exports,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_tail import (
    journal_tail_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preservation_ref_deletion import (
    delete_ended_run_refs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    AttributedRun,
    FactoryRunInventory,
    attributed_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_refs import (
    VerifiedPreservationRef,
    committed_tip,
    verified_preservation_ref,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = [
    "JOURNAL_STAGE_COLLECTION_REFUSED",
    "collect_closed_ended_runs",
    "journaled_refusals",
]

_CLOSED_ITEM_STATUSES = frozenset({"closed", "done"})
_PUBLISHED_ITEM_STATUSES = frozenset({"ready", "backlog"})
_ENDED_STATUS_KINDS = frozenset({"canceled", "cancelled", "dead", "failed", "succeeded"})
_COLLECTION_STAGE = "ended-run-collected"
_EXPORTED_STAGE = "ended-run-exported"
_EXPORT_FAILED_STAGE = "ended-run-export-failed"
_EXPORT_SKIPPED_STAGE = "ended-run-export-skipped-disk-pressure"
JOURNAL_STAGE_COLLECTION_REFUSED = "ended-run-collection-refused"
_REASON_NOT_CLOSED = "item-not-closed"
_REASON_NO_STATUS = "item-status-unreadable"
_REASON_UNPUBLISHED = "retained-for-unpublished-work"
_INSPECT_TIMEOUT_SECONDS = 120.0
_RM_TIMEOUT_SECONDS = 120.0
_RM_OUTPUT_EXCERPT_CHARS = 2000


def collect_closed_ended_runs(
    *,
    inventory: FactoryRunInventory,
    port: FabroPort,
    runner: CommandRunner,
    repo: Path,
    journal: JournalWriter,
    dry_run: bool,
) -> None:
    """Delete ended sandboxes whose recorded work-item is closed, or at ready or backlog with
    its run's committed tree held on origin.

    The run's preservation refs are deleted from origin FIRST: once the item is
    closed and the run has ended nothing can push to them or seed from them. A
    deletion the forge refuses is journaled by the deletion and the run is left
    standing, so the next pass finds it again and retries; the item's state is
    never touched here.

    `fabro rm` is deliberately unforced: the server's provider-delete route
    is the collection operation, and its exit code and bounded response are
    journaled so a Cleaned, Preserved or Absent result and any lease-prune
    problem stay visible for diagnosis and for the next periodic pass to retry.
    A targeted inventory collects only its own item's runs.

    The run's whole record is exported BEFORE the `rm` (`_dispatcher_ended_run_export`),
    because the deletion takes the run's event journal and stage logs with it. A
    failed export is journaled with its failing step and the run is STILL removed:
    the ratified collection duty deletes a closed item's run unconditionally.
    Exports past the retention constant are pruned on every pass. When the export
    root's filesystem is under the free-space floor the export is SKIPPED with an
    `ended-run-export-skipped-disk-pressure` row and the run is removed all the same,
    because a full disk must never stop the deletion the contract mandates.
    """
    if not dry_run:
        prune_expired_exports(repo=repo, now_epoch=time.time())
    for row in attributed_runs(inventory=inventory, include_terminal=True):
        if inventory.only_work_item_id not in (None, row.work_item_id):
            continue
        if row.run.status_kind not in _ENDED_STATUS_KINDS or dry_run:
            continue
        if row.work_item_status in _CLOSED_ITEM_STATUSES:
            if not delete_ended_run_refs(
                runner=runner,
                repo=repo,
                journal=journal,
                work_item_id=row.work_item_id,
                run_id=row.run.run_id,
            ):
                continue
        else:
            kept = _retention(port=port, runner=runner, repo=repo, row=row)
            if kept is not None:
                if (row.run.run_id, row.work_item_status) not in inventory.refused_before:
                    _journal_refusal(
                        inventory=inventory, repo=repo, journal=journal, row=row, kept=kept
                    )
                continue
        _journal_export(inventory=inventory, port=port, repo=repo, journal=journal, row=row)
        removed = port.rm(
            run_id=row.run.run_id,
            timeout_seconds=_RM_TIMEOUT_SECONDS,
            force=False,
        )
        journal.append(
            record={
                "stage": _COLLECTION_STAGE,
                "run_id": row.run.run_id,
                "factory_name": inventory.factory_name,
                "factory_server_url": inventory.factory_server_url,
                "dispatching_repository": repo.name,
                "work_item_id": row.work_item_id,
                "work_item_status": row.work_item_status,
                "rm_exit_code": removed.command.exit_code,
                "rm_stdout": removed.command.stdout.strip()[:_RM_OUTPUT_EXCERPT_CHARS],
                "rm_stderr": removed.command.stderr.strip()[:_RM_OUTPUT_EXCERPT_CHARS],
            }
        )


def _journal_export(
    *,
    inventory: FactoryRunInventory,
    port: FabroPort,
    repo: Path,
    journal: JournalWriter,
    row: AttributedRun,
) -> None:
    """Export the run's record and journal where it went, or why it was not taken."""
    base: dict[str, object] = {
        "run_id": row.run.run_id,
        "factory_name": inventory.factory_name,
        "dispatching_repository": repo.name,
        "work_item_id": row.work_item_id,
    }
    pressure = disk_pressure(repo=repo)
    if pressure is not None:
        journal.append(
            record={
                "stage": _EXPORT_SKIPPED_STAGE,
                **base,
                "free_bytes": pressure.free_bytes,
                "total_bytes": pressure.total_bytes,
                "min_free_fraction": pressure.min_free_fraction,
                "min_free_bytes": pressure.min_free_bytes,
            }
        )
        return
    exported = export_ended_run(port=port, repo=repo, run_id=row.run.run_id)
    if exported.ok:
        journal.append(
            record={
                "stage": _EXPORTED_STAGE,
                **base,
                "export_location": str(exported.location),
                "export_bytes": exported.total_bytes,
                "export_sha256": exported.sha256,
            }
        )
        return
    journal.append(
        record={
            "stage": _EXPORT_FAILED_STAGE,
            **base,
            "export_failed_step": exported.failed_step,
            "export_detail": exported.detail,
        }
    )


def journaled_refusals(*, journal_path: Path | None) -> frozenset[tuple[str, str | None]]:
    """The (run id, item status) pairs whose refusal the journal already holds."""
    if journal_path is None:
        return frozenset()
    refused: set[tuple[str, str | None]] = set()
    for record in journal_tail_records(journal_path=journal_path):
        run_id = record.get("run_id")
        status = record.get("work_item_status")
        if record.get("stage") != JOURNAL_STAGE_COLLECTION_REFUSED or not isinstance(run_id, str):
            continue
        refused.add((run_id, status if isinstance(status, str) else None))
    return frozenset(refused)


def _retention(
    *, port: FabroPort, runner: CommandRunner, repo: Path, row: AttributedRun
) -> tuple[str, str | None] | None:
    """Why this run's sandbox stays, as (reason, detail), or None when it is collectable.

    An item at ready or backlog is collectable only while origin holds the run's committed
    tree; a record that names no tip, or a listing that cannot answer, retains the sandbox.
    """
    status = row.work_item_status
    if status is None:
        return _REASON_NO_STATUS, None
    if status not in _PUBLISHED_ITEM_STATUSES:
        return _REASON_NOT_CLOSED, None
    inspected = port.inspect(run_id=row.run.run_id, timeout_seconds=_INSPECT_TIMEOUT_SECONDS)
    tip = committed_tip(record=inspected.payload)
    if tip is None:
        return _REASON_UNPUBLISHED, "the run's record names no committed tip"
    held = verified_preservation_ref(
        runner=runner,
        repo=repo,
        work_item_id=row.work_item_id,
        run_id=row.run.run_id,
        tip_commit=tip,
    )
    if isinstance(held, VerifiedPreservationRef):
        return None
    return _REASON_UNPUBLISHED, None if held is None else held.detail


def _journal_refusal(
    *,
    inventory: FactoryRunInventory,
    repo: Path,
    journal: JournalWriter,
    row: AttributedRun,
    kept: tuple[str, str | None],
) -> None:
    reason, detail = kept
    journal.append(
        record={
            "stage": JOURNAL_STAGE_COLLECTION_REFUSED,
            "run_id": row.run.run_id,
            "factory_name": inventory.factory_name,
            "factory_server_url": inventory.factory_server_url,
            "dispatching_repository": repo.name,
            "work_item_id": row.work_item_id,
            "work_item_status": row.work_item_status,
            "reason": reason,
            **({} if detail is None else {"detail": detail}),
        }
    )
