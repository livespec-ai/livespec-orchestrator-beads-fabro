"""Deriving the one normal repayment operation from a recorded successful attempt.

Pure. `SPECIFICATION/contracts.md` section "Expedited incident lifecycle": after
the expedited merge's complete normal master CI succeeds, the incident enters
ONE same-item normal factory repayment whose eligibility derives from the
recorded successful attempt and the outstanding repayment. The operation id is
a digest of that attempt and the master run, so a restart or duplicate delivery
derives the same operation instead of a second one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import cast

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
    RepaymentMasterCiEvidence,
)
from livespec_orchestrator_beads_fabro._incident_carrier import BranchReserved
from livespec_orchestrator_beads_fabro._incident_phases import REPAYMENT_PHASES, lifecycle_state_for

__all__: list[str] = [
    "REPAYMENT_ENTRY_FROM",
    "REPAYMENT_ENTRY_PHASE",
    "REPAYMENT_ENTRY_STATE",
    "REPAYMENT_OWNER",
    "MasterCiRun",
    "RepaymentPlan",
    "plan_repayment",
    "repayment_operation_id",
]

# The factory owns every repayment phase; the host owner ends at master-observation.
REPAYMENT_OWNER = "fabro"
REPAYMENT_ENTRY_FROM = "master-observation"
REPAYMENT_ENTRY_PHASE = REPAYMENT_PHASES[0]
REPAYMENT_ENTRY_STATE = lifecycle_state_for(phase=REPAYMENT_ENTRY_PHASE) or ""
_SUCCESS = "success"


@dataclass(frozen=True, kw_only=True)
class MasterCiRun:
    """The complete normal master run observed for one landed incident commit."""

    run_id: str
    head: str
    conclusion: str
    complete: bool
    # These are populated only after the forge verifier proves exceptional descendant admission.
    landed_commit: str | None = None
    evidence: RepaymentMasterCiEvidence | None = None


@dataclass(frozen=True, kw_only=True)
class RepaymentPlan:
    """The one repayment operation a successful attempt makes eligible."""

    operation_id: str
    attempt: IncidentAttempt
    lifecycle_state: str


def repayment_operation_id(*, attempt: IncidentAttempt, master_ci: MasterCiRun) -> str:
    """The deterministic operation id: a restart or duplicate delivery derives the same one."""
    digest = hashlib.sha256(
        json.dumps(
            {
                "item_id": attempt.item_id,
                "operation_id": attempt.operation_id,
                "generation": attempt.generation,
                "master_run_id": master_ci.run_id,
                "head": master_ci.head,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return f"repayment-{digest[:24]}"


def _eligible(*, attempt: IncidentAttempt) -> bool:
    return (
        attempt.phase == REPAYMENT_ENTRY_FROM
        and attempt.pr_number > 0
        and bool(attempt.landed_commits)
        and attempt.repayment_required
    )


def _landed_commit(*, attempt: IncidentAttempt, master_ci: MasterCiRun) -> str | None:
    """The landed tree this admission may carry, never the descendant's tree."""
    if master_ci.head in attempt.landed_commits:
        return master_ci.head
    landed = getattr(master_ci, "landed_commit", None)
    return landed if isinstance(landed, str) and landed in attempt.landed_commits else None


def _master_ci_complete(*, attempt: IncidentAttempt, master_ci: MasterCiRun) -> bool:
    return (
        master_ci.complete
        and master_ci.conclusion == _SUCCESS
        and _landed_commit(attempt=attempt, master_ci=master_ci) is not None
    )


def plan_repayment(
    *, reading: IncidentReading, master_ci: MasterCiRun, target_ref: str
) -> RepaymentPlan | AuthorityRefusal:
    """Derive the eligible repayment from the recorded successful attempt, or refuse by name."""
    attempt = reading.attempt
    if not reading.is_current:
        return AuthorityRefusal(code="incident-repayment-stale-observation", detail=attempt.item_id)
    if not _eligible(attempt=attempt):
        return AuthorityRefusal(
            code="incident-repayment-not-eligible",
            detail=f"{attempt.item_id}: phase {attempt.phase} has no merged repair owing repayment",
        )
    if not _master_ci_complete(attempt=attempt, master_ci=master_ci):
        return AuthorityRefusal(
            code="incident-repayment-master-ci-outstanding",
            detail=(
                f"{attempt.item_id}: complete normal master CI success for a landed commit "
                f"remains an outstanding obligation (run {master_ci.run_id}: "
                f"{master_ci.conclusion}, complete={master_ci.complete})"
            ),
        )
    operation_id = repayment_operation_id(attempt=attempt, master_ci=master_ci)
    landed_commit = cast(str, _landed_commit(attempt=attempt, master_ci=master_ci))
    staged_tree = attempt.landed_trees[attempt.landed_commits.index(landed_commit)]
    successor = replace(
        attempt,
        attempt_id=operation_id,
        phase=REPAYMENT_ENTRY_PHASE,
        operation_id=f"{operation_id}#{REPAYMENT_ENTRY_PHASE}",
        generation=attempt.generation + 1,
        owner=REPAYMENT_OWNER,
        base=landed_commit,
        head=landed_commit,
        pr_number=0,
        landed_commits=(),
        landed_trees=(),
        carrier=BranchReserved(
            target_ref=target_ref, input_parent=landed_commit, staged_tree=staged_tree
        ),
        repayment_master_ci_evidence=master_ci.evidence,
    )
    return RepaymentPlan(
        operation_id=operation_id, attempt=successor, lifecycle_state=REPAYMENT_ENTRY_STATE
    )
