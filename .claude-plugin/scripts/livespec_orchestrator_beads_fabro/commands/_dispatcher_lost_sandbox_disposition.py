"""Return a lost-sandbox terminal's claim to the ordinary recovery queue."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import terminal_claim
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import (
    LEDGER_WRITE_ERRORS,
    claim_status_write,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_lost_sandbox_outcome import (
    LOST_SANDBOX_RELEASE_STATUS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.store import update_work_item_status
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["LOST_SANDBOX_RELEASE_STAGE", "dispose_lost_sandbox_release"]

LOST_SANDBOX_RELEASE_STAGE = "lost-sandbox-release"


def dispose_lost_sandbox_release(
    *, repo: Path, item: WorkItem, outcome: DispatchOutcome, journal: JournalFile
) -> None:
    """Journal and release the terminal's claim without turning it into a human gate."""
    if outcome.status != LOST_SANDBOX_RELEASE_STATUS:
        return
    journal.append(
        record={
            "stage": LOST_SANDBOX_RELEASE_STAGE,
            "work_item_id": item.id,
            "run_id": outcome.fabro_run_id,
            "factory": outcome.fabro_factory_name,
            "cause": outcome.fabro_failure_cause,
        }
    )
    released = attempt(
        action=lambda: claim_status_write(
            repo=repo,
            path=store_config(repo=repo),
            intent="lost-sandbox-release",
            write=update_work_item_status,
            item_id=item.id,
            status="ready",
            clear_assignee=True,
            journal=journal,
            still_as_decided=terminal_claim(item=item, run_id=outcome.fabro_run_id),
        ),
        exceptions=LEDGER_WRITE_ERRORS,
    )
    if isinstance(released, AttemptFailure):
        journal.append(
            record={
                "stage": "lost-sandbox-release-error",
                "work_item_id": item.id,
                "run_id": outcome.fabro_run_id,
                "reason": type(released.error).__name__,
            }
        )
