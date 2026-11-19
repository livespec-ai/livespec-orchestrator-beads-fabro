"""Reconcile a succeeded factory claim when its separately published PR has merged."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import FALLBACK_SOURCE
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_effects import (
    claim_row,
    claim_unchanged,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_fence import (
    claim_recovery_fence,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade import (
    ACTION_SUCCEEDED_RUN_RECONCILE_MERGED,
    HOLD_CLAIM_CHANGED,
    HOLD_EFFECT_UNOBSERVABLE,
    HOLD_RUN_SUCCEEDED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    STRANDED_CLAIM_HANDOFF_STAGE,
    HeldClaim,
    RecoveredClaim,
    recovery_journal_record,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "SucceededRunRecoveryRequest",
    "reconcile_merged_for_claim",
    "recover_succeeded_merged_claim",
]

_ACTIVE_STATUS = "active"


@dataclass(frozen=True, kw_only=True)
class SucceededRunRecoveryRequest:
    """A succeeded claim whose independently published pull request merged."""

    item: WorkItem
    run_id: str
    factory_name: str
    factory_server_url: str | None
    action: str = ACTION_SUCCEEDED_RUN_RECONCILE_MERGED


def reconcile_merged_for_claim(*, args: argparse.Namespace) -> int:
    """Drive the ordinary acceptance valve without duplicating its lifecycle."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged import (
        run_reconcile_merged_command,
    )

    return run_reconcile_merged_command(args=args)


def recover_succeeded_merged_claim(
    *,
    repo: Path,
    journal: JournalFile,
    request: SucceededRunRecoveryRequest,
    now_iso: str,
) -> RecoveredClaim | HeldClaim:
    """Fence the claim and let ``reconcile-merged`` close or accept it."""
    _ = now_iso
    with claim_recovery_fence(
        repo=repo, work_item_id=request.item.id, run_id=request.run_id
    ) as fenced:
        if not fenced:
            return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
        row = claim_row(repo=repo, work_item_id=request.item.id)
        if row is None:
            return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
        if not claim_unchanged(row=row, run_id=request.run_id):
            return _held(request=request, reason=HOLD_CLAIM_CHANGED)
        journal.append(
            record=recovery_journal_record(
                stage=STRANDED_CLAIM_HANDOFF_STAGE,
                recovered=_recovered(
                    request=request, status=row.status or _ACTIVE_STATUS, effects=()
                ),
            )
        )
        return _reconcile(repo=repo, journal=journal, request=request)


def _reconcile(
    *, repo: Path, journal: JournalFile, request: SucceededRunRecoveryRequest
) -> RecoveredClaim | HeldClaim:
    identity = journal.identity
    exit_code = reconcile_merged_for_claim(
        args=argparse.Namespace(
            repo=str(repo),
            item=request.item.id,
            janitor=None,
            journal=str(journal.path),
            invoker=None if identity.invoker_source == FALLBACK_SOURCE else identity.invoker,
            force=True,
            regrade=False,
            handed_off_rework=request.item.rework_pending,
            as_json=False,
        )
    )
    if exit_code != 0:
        return _held(
            request=request,
            reason=HOLD_RUN_SUCCEEDED,
            detail=(
                f"a pull request matching the item merged but reconcile-merged did not "
                f"complete (exit {exit_code}); read its stderr"
            ),
        )
    row = claim_row(repo=repo, work_item_id=request.item.id)
    return _recovered(
        request=request,
        status=_ACTIVE_STATUS if row is None else row.status or _ACTIVE_STATUS,
        effects=("reconcile-merged",),
    )


def _recovered(
    *, request: SucceededRunRecoveryRequest, status: str, effects: tuple[str, ...]
) -> RecoveredClaim:
    return RecoveredClaim(
        work_item_id=request.item.id,
        run_id=request.run_id,
        factory_name=request.factory_name,
        factory_server_url=request.factory_server_url,
        reason="merged",
        route=request.action,
        status=status,
        effects_written=effects,
    )


def _held(
    *, request: SucceededRunRecoveryRequest, reason: str, detail: str | None = None
) -> HeldClaim:
    return HeldClaim(
        work_item_id=request.item.id,
        run_id=request.run_id,
        factory_name=request.factory_name,
        factory_server_url=request.factory_server_url,
        dispatching_host=None,
        hold_reason=reason,
        remedy=None,
        detail=detail,
    )
