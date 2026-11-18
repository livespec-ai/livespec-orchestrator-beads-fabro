"""Proof-aware hold calculation for stale publish-branch reclamation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    read_pull_request_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_VERIFIED,
    latest_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import published_head
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_forge import (
    branch_pull_request,
)

HELD_PROOF_UNOBSERVABLE = "proof-unobservable"
HELD_VERIFIED_PROOF = "verified-proof-on-open-pull-request"


@dataclass(frozen=True, kw_only=True)
class ReclaimHold:
    """One reason no reclaim was performed and the facts its journal row names."""

    reason: str
    detail: str
    branch: str | None = None
    head: str | None = None
    live_run_ids: tuple[str, ...] = ()


def verified_proof_hold(
    *, runner: CommandRunner, repo: Path, branch: str, head: str
) -> ReclaimHold | None:
    """Return a hold when an open pull request proves or cannot disprove its head."""
    observed = branch_pull_request(repo=repo, branch=branch, runner=runner)
    pull_request = observed.pull_request
    if not observed.observed or (pull_request is not None and pull_request.head is None):
        return _unobservable(branch=branch, head=head, what="the open pull request")
    if pull_request is None or pull_request.state != "OPEN" or pull_request.head != head:
        return None
    records = read_pull_request_records(repo=repo, pr_number=pull_request.number, runner=runner)
    if records is None:
        return _unobservable(branch=branch, head=head, what="its Proof of Done records")
    latest = latest_proof_record(records=records, verdict=VERDICT_VERIFIED)
    if latest is None or published_head(body=latest.body) != head:
        return None
    return ReclaimHold(
        reason=HELD_VERIFIED_PROOF,
        detail=(
            "the open pull request at the surviving publish head carries a verified "
            "Proof of Done record declaring that head, so reclaim leaves the proved "
            "branch available for recovery"
        ),
        branch=branch,
        head=head,
    )


def _unobservable(*, branch: str, head: str, what: str) -> ReclaimHold:
    return ReclaimHold(
        reason=HELD_PROOF_UNOBSERVABLE,
        detail=(
            f"the forge could not be read for {what} of the surviving publish branch, so "
            "whether it carries a verified Proof of Done record could not be established "
            "and the branch is left exactly as it stands"
        ),
        branch=branch,
        head=head,
    )
