"""The terminal non-convergence bounce disposition."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import LEDGER_WRITE_ERRORS
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion_claims import CompletionClaim
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_non_convergence_cap import (
    NON_CONVERGENCE_BOUNCE_STAGE,
    non_convergence_cap,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import is_non_convergence_outcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_window import resolve_stall_window
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__ = ["bounce_non_convergence_to_backlog"]


def bounce_non_convergence_to_backlog(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
    store_config_resolver: Callable[..., Any],
    status_writer: Callable[..., None],
) -> None:
    """Bounce a non-converging terminal to backlog without changing its verdict."""
    if not is_non_convergence_outcome(outcome=outcome):
        return
    cap = non_convergence_cap(outcome=outcome, stall_seconds=resolve_stall_window(cwd=repo).seconds)
    updated = attempt(
        action=lambda: CompletionClaim(
            repo=repo,
            path=store_config_resolver(repo=repo),
            item=item,
            outcome=outcome,
            journal=journal,
        ).bounce(write=status_writer),
        exceptions=LEDGER_WRITE_ERRORS,
    )
    if isinstance(updated, AttemptFailure):
        journal.append(
            record={
                "stage": "non-convergence-bounce-error",
                "work_item_id": item.id,
                "reason": type(updated.error).__name__,
                **cap.as_record(),
            }
        )
        return
    if updated is not None:
        return
    journal.append(
        record={
            "stage": NON_CONVERGENCE_BOUNCE_STAGE,
            "work_item_id": item.id,
            "outcome_stage": outcome.stage,
            "outcome_status": outcome.status,
            **cap.as_record(),
        }
    )
    _ = write_stderr(
        text=(
            f"SURFACE: work-item {item.id} did not converge through the janitor gate "
            f"({outcome.status} at {outcome.stage}); bounced to backlog and surfaced "
            "for re-grooming — NOT infinite-retried.\n"
        )
    )
