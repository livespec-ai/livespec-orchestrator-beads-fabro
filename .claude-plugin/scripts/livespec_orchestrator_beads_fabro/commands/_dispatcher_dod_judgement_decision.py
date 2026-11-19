"""The result and unavailable-outcome arm of a Definition-of-Done taking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_HELD,
    JUDGEMENT_UNAVAILABLE,
    first_remedy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    did_not_run_comment,
    recorded_did_not_run_causes,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import (
    SpecIdentity,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_candidate_attempt import (
        CandidateAttempt,
    )
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__ = ["DodJudgementDecision", "unavailable_decision"]


@dataclass(frozen=True, kw_only=True)
class DodJudgementDecision:
    """What one call site learned, and whether anything was spent learning it."""

    work_item_id: str
    outcome: str
    findings: tuple[str, ...] = ()
    reused: bool = False
    spec_identity: SpecIdentity | None = None
    workflow_graph_digest: str | None = None
    recorded_spec_identity: str | None = None
    recorded_workflow_graph_digest: str | None = None

    @property
    def holds(self) -> bool:
        """Whether this decision rests the item at needs-human."""
        return self.outcome == JUDGEMENT_HELD

    @property
    def first_remedy(self) -> str | None:
        """The remedy a refusal and a hygiene fact name."""
        return first_remedy(findings=self.findings)


def unavailable_decision(  # noqa: PLR0913 - each argument is one field of the record it writes.
    *,
    item: WorkItem,
    stage: str,
    digest: str,
    rubric: str,
    cause: str | None,
    comments: Sequence[str],
    append: Callable[..., None],
    bound_ended_candidates: Sequence[str] = (),
    attempts: Sequence[CandidateAttempt] = (),
    subject_characters: int | None = None,
    carried_rider_count: int | None = None,
    spec_identity: SpecIdentity | None = None,
    workflow_graph_digest: str | None = None,
    recorded_spec_identity: str | None = None,
    recorded_workflow_graph_digest: str | None = None,
) -> DodJudgementDecision:
    """Record an unavailable taking once per cause, then return its decision."""
    if cause is not None and cause not in recorded_did_not_run_causes(comments=comments):
        append(
            body=did_not_run_comment(
                item_id=item.id,
                stage=stage,
                digest=digest,
                rubric_digest=rubric,
                cause=cause,
                subject_characters=subject_characters,
                carried_rider_count=carried_rider_count,
                bound_ended_candidates=bound_ended_candidates,
                attempts=attempts,
            )
        )
    return DodJudgementDecision(
        work_item_id=item.id,
        outcome=JUDGEMENT_UNAVAILABLE,
        spec_identity=spec_identity,
        workflow_graph_digest=workflow_graph_digest,
        recorded_spec_identity=recorded_spec_identity,
        recorded_workflow_graph_digest=recorded_workflow_graph_digest,
    )
