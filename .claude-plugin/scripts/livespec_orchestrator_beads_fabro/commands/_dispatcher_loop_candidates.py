"""The drain's CANDIDATE ENUMERATION: which rows one pass may advertise.

Split out of `_dispatcher_loop_selection`, which keeps the readiness PREDICATES
(`ready_items`, `is_dispatch_candidate`) and the pass plumbing. The seam is the
question each side answers: a predicate asks whether ONE row is launchable at
all, while this asks which of the launchable rows THIS pass may pick — a
question that now consumes two independent filters and will consume more.

What pushed it out was the pre-dispatch Definition-of-Done judgement's own
filter, which made this the second composition point in the module and took the
file past its line ceiling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_eligibility import (
    acceptance_eligible_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_wall import (
    dod_unrefused_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import ready_items
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_ready_withdrawal import (
    withdraw_durable_spec_change_holds,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_wall import (
    spec_change_unrefused_candidates,
)

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import JournalWriter
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["candidates"]


def candidates(
    *,
    args: argparse.Namespace,
    items: list[WorkItem],
    repo: Path,
    journal: JournalWriter | None = None,
) -> list[WorkItem]:
    """The drain's selection for one pass, in the canonical ranked order.

    The AUTONOMOUS pass applies the shared acceptance-eligibility filter, which
    is what the ranking algorithm means by the drain consuming the same filtered
    set as `next`: a legacy row the wall would refuse is never selected, so it
    can neither spend the budget nor stop the queue behind it with a wave-level
    refusal.

    It then drops every row a standing pre-dispatch Definition-of-Done verdict
    REFUSES, which the clause requires "until its effective criteria or
    referenced headings change". That second filter takes no judgement of its
    own: it reads the verdict already recorded, so an unrepaired row cannot stop
    the queue behind it and a drain pass costs no model call per candidate. Both
    filters are handed the SAME `workflow_name`, because both are scoped to an
    implement-kind item and a groom candidate exempted by one of them while the
    other dropped it would be invisible to the drain either way.

    Before that filter, a durable recorded spec-change hold (no linked topic or
    an unratified topic) is journaled back to `backlog` with its reason.  That
    makes the intake door, rather than a permanently unlaunchable `ready` row,
    own its later release.  The filter remains the launch backstop for a claim
    race and for a row awaiting re-judgement; the latter stays `ready` so the
    wall can re-classify it against the ratified specification.

    A NAMED id is narrowed to and deliberately NOT filtered, after the durable
    hold repair above. The clause keeps the hand-picked path protected by the
    wall "even when candidate enumerations filtered the item earlier", and that
    only holds if a row not returned to intake still reaches it.
    """
    ranked = ready_items(items=items, repo=repo)
    if journal is not None:
        ranked = withdraw_durable_spec_change_holds(items=ranked, repo=repo, journal=journal)
    requested = set(args.items or [])
    if requested:
        return [item for item in ranked if item.id in requested]
    return spec_change_unrefused_candidates(
        items=dod_unrefused_candidates(
            items=acceptance_eligible_candidates(
                items=ranked, cwd=repo, workflow_name=args.workflow_name
            ),
            repo=repo,
            workflow_name=args.workflow_name,
        ),
        repo=repo,
        workflow_name=args.workflow_name,
    )
