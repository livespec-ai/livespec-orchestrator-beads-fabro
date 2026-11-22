"""Which carried riders hand a dispatch's agent an earlier run's preserved work.

`contracts.md` section "Factory-configurable ACP fallback priority" → "Recovery
from the failed run's preserved work" gives a dispatch one route, and its
`recovery-route` record names it. A `fresh` route starts from the default branch
past every preserved tree. But the goal carries every CARRIED rider (section
"Dispatch-brief lessons injection" → "A goal carries a bounded rider set"), and
the records a failed run leaves — `livespec-preserved-tree`,
`livespec-preserve-by-reference`, `livespec-needs-human-cause` — and an
operator's own restore pointer are riders like any other. Measured 2026-11-22 on
run 01M81FHNK5J3: the goal carried four such riders, the route row read `fresh`,
and the agent restored the preserved ref itself, so a seeded run ran under a
fresh label and outside every seeded-run guard (bd-ib-e547bt).

WHY ONLY THE LABEL MOVES. Whether such riders should reach the goal at all is a
separate, deferred question (bd-ib-ycvwxn). Until it is settled the goal still
carries them, so the one thing that can be made true now is the label: a
dispatch whose goal hands its agent preserved work is recorded `seeded`, and the
journal can never read `fresh` for a run that was handed a seed. The launch
itself is unchanged — a fresh-routed dispatch still starts from the default
branch, because nothing here verified the rider's ref.

WHY THE SAME RIDER BOUND AS THE GOAL. The rider set is taken through
`bound_riders`, at the claim before this dispatch's own, which is exactly the set
`render_goal` carries. A second spelling of "carried" is how the label and the
goal would come to disagree, which is the defect this module exists to close.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_markers import (
    comment_marker,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    NEEDS_HUMAN_CAUSE_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference_body import (
    PRESERVE_POINTER_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    PRESERVED_TREE_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    ROUTE_SEEDED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rider_bound import bound_riders

if TYPE_CHECKING:
    from collections.abc import Sequence

    from livespec_orchestrator_beads_fabro.store import WorkItemComment

__all__: list[str] = ["preserved_work_riders", "rider_route_label"]

_PRESERVED_WORK_MARKERS = frozenset(
    {PRESERVED_TREE_MARKER, PRESERVE_POINTER_MARKER, NEEDS_HUMAN_CAUSE_MARKER}
)

# A ref an operator rider can point an agent at to restore an earlier run's work:
# a hand-pushed `preserve/...` or `needs-human/...` branch, with or without its
# `refs/heads/` prefix. A trailing sentence period is not part of the ref.
_PRESERVED_WORK_REF = re.compile(
    r"(?<![\w/.-])(?:refs/heads/)?(?:preserve|needs-human)/[\w./-]*[\w-]"
)


def preserved_work_riders(
    *, comments: Sequence[WorkItemComment], claim_at: str | None
) -> tuple[str, ...]:
    """Each carried rider that hands the agent preserved work, as its marker or ref.

    A rider opening with one of the three preserved-work markers is named by that
    marker; any other carried rider is named by the first preserve or needs-human
    ref it mentions. A rider the goal leaves out is never one, because the agent
    never reads it.
    """
    found: list[str] = []
    for comment in bound_riders(comments=comments, claim_at=claim_at).carried:
        marker = comment_marker(body=comment.text)
        if marker in _PRESERVED_WORK_MARKERS:
            found.append(marker)
            continue
        ref = _PRESERVED_WORK_REF.search(comment.text)
        if ref is not None:
            found.append(ref.group(0))
    return tuple(found)


def rider_route_label(*, route: str, riders: tuple[str, ...]) -> str:
    """The route a dispatch is recorded under, given the preserved-work riders it carries.

    Only `fresh` moves: a `seeded` or `resume` route already starts from earlier
    work, and a `fresh` one whose goal hands over preserved work is not fresh.
    """
    if route == ROUTE_FRESH and riders:
        return ROUTE_SEEDED
    return route
