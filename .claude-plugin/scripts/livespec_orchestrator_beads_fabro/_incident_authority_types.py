"""Immutable identities returned by the canonical incident ledger reader."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

from dataclasses import dataclass, field

from livespec_orchestrator_beads_fabro._incident_carrier import IncidentCarrier

__all__: list[str] = [
    "AuthorityRefusal",
    "IncidentAttempt",
    "IncidentReading",
    "RepaymentMasterCiEvidence",
    "RepaymentPreexistingJob",
]


@dataclass(frozen=True, kw_only=True)
class AuthorityRefusal:
    """A named refusal, never absence or successful normal fallback."""

    code: str
    detail: str


@dataclass(frozen=True, kw_only=True)
class RepaymentPreexistingJob:
    """The independently read reason one failed landed-run job was already failing."""

    job: str
    preexisting_run_id: str
    attributed_item_id: str
    attributed_landed_commit: str


@dataclass(frozen=True, kw_only=True)
class RepaymentMasterCiEvidence:
    """Forge and authority evidence for a descendant-run repayment admission."""

    admitted_run_id: str
    admitted_head: str
    landed_commit: str
    landed_failed_run_id: str
    preexisting_jobs: tuple[RepaymentPreexistingJob, ...]


@dataclass(frozen=True, kw_only=True)
class IncidentAttempt:
    """One committed immutable authority snapshot, distinct from normal proof."""

    repository: str
    item_id: str
    attempt_id: str
    phase: str
    operation_id: str
    generation: int
    owner: str
    base: str
    head: str
    pr_number: int
    landed_commits: tuple[str, ...]
    landed_trees: tuple[str, ...]
    original_paths: tuple[str, ...]
    deferred_work: tuple[str, ...]
    repayment_required: bool
    # None is a schema-1 record written before the explicit carrier model.
    carrier: IncidentCarrier | None = None
    # Present only when a descendant master run, rather than the landed commit's
    # own run, admitted repayment.  It keeps the exceptional admission auditable
    # in the same immutable authority history as the successor it authorized.
    repayment_master_ci_evidence: RepaymentMasterCiEvidence | None = None


@dataclass(frozen=True, kw_only=True)
class IncidentReading:
    """Authority read from a closed server token, with a current-generation fence."""

    attempt: IncidentAttempt
    committed_token_id: str
    current_token_id: str
    is_current: bool
    # The operations the read walked: the whole chain for a full-chain read, only the
    # segment after the item's head hint for a current one. Not part of identity.
    operation_ids: tuple[str, ...] = field(default=(), compare=False)
