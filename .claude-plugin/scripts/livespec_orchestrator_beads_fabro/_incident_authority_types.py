"""Immutable identities returned by the canonical incident ledger reader."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

from dataclasses import InitVar, dataclass, field
from typing import ClassVar, cast

from livespec_orchestrator_beads_fabro._incident_carrier import IncidentCarrier

__all__: list[str] = ["AuthorityRefusal", "IncidentAttempt", "IncidentReading"]


@dataclass(frozen=True, kw_only=True)
class AuthorityRefusal:
    """A named refusal, never absence or successful normal fallback."""

    code: str
    detail: str


@dataclass(frozen=True, kw_only=True)
class IncidentAttempt:
    """One committed immutable authority snapshot, distinct from normal proof."""

    _workflow_paths: ClassVar[tuple[str, ...]]
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
    # An InitVar preserves the legacy dataclass/asdict shape while allowing an
    # immutable scope to participate in construction and dataclasses.replace.
    workflow_paths: InitVar[tuple[str, ...]] = ()

    def __post_init__(self, workflow_paths: tuple[str, ...]) -> None:
        object.__setattr__(self, "_workflow_paths", workflow_paths)

    def workflow_scope(self) -> tuple[str, ...]:
        """The maintainer-attested exact workflow scope for this snapshot."""
        return cast("tuple[str, ...]", object.__getattribute__(self, "_workflow_paths"))


IncidentAttempt.workflow_paths = property(IncidentAttempt.workflow_scope)  # type: ignore[attr-defined]


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
