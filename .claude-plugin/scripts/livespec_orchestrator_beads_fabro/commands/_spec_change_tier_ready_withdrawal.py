"""Return durable spec-change holds from ``ready`` to the intake door.

The candidate filter still keeps a held row from launching.  This module owns
the additional state repair: a row held for a missing or unratified topic must
not rest in ``ready`` between drain passes.  A ratified row awaiting its fresh
classification is deliberately left alone, because the wall's classification
is the path that releases it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro import store
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import status_is
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import (
    WRITER_ADMISSION,
    claim_status_write,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_lifecycle_writes import (
    write_work_item_status_and_reconcile,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_spec_commitments import (
    ratified_proposal_topics,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_hold import (
    REASON_AWAITING_REJUDGEMENT,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_wall import standing_hold

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import JournalWriter
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["withdraw_durable_spec_change_holds"]

_BACKLOG_STATUS = "backlog"
_READY_STATUS = "ready"
_WITHDRAW_INTENT = "withdraw-spec-change-hold"


def withdraw_durable_spec_change_holds(
    *, items: Sequence[WorkItem], repo: Path, journal: JournalWriter
) -> list[WorkItem]:
    """Move no-topic and unratified held rows out of ``ready`` before selection.

    A failure to read the history does not manufacture a hold reason or a
    transition.  The pre-existing filter remains the conservative launch
    backstop, and an explicit approval has its own fail-closed history error.
    """
    config = store_config(repo=repo)
    try:
        ratified = ratified_proposal_topics(spec_root=repo / "SPECIFICATION")
    except OSError:
        return list(items)
    remaining: list[WorkItem] = []
    for item in items:
        hold = standing_hold(
            item=item,
            config=config,
            spec_root=repo / "SPECIFICATION",
            ratified_topics=ratified,
        )
        if hold is None or hold.reason == REASON_AWAITING_REJUDGEMENT:
            remaining.append(item)
            continue
        reason = _withdrawal_comment(
            item_id=item.id,
            hold_reason=hold.reason,
            topic=hold.linked_proposal_topic,
        )
        refused = claim_status_write(
            repo=repo,
            path=config,
            intent=_WITHDRAW_INTENT,
            write=write_work_item_status_and_reconcile,
            item_id=item.id,
            status=_BACKLOG_STATUS,
            clear_assignee=True,
            reconcile=write_work_item_status_and_reconcile,
            writer=WRITER_ADMISSION,
            journal=journal,
            still_as_decided=status_is(status=_READY_STATUS),
        )
        if refused is not None:
            remaining.append(item)
            continue
        store.append_work_item_comment(path=config, work_item_id=item.id, body=reason)
        journal.append(
            record={
                "stage": "spec-change-hold-withdrawal",
                "work_item_id": item.id,
                "status": _BACKLOG_STATUS,
                "reason": hold.reason,
                "topic": hold.linked_proposal_topic,
            }
        )
    return remaining


def _withdrawal_comment(*, item_id: str, hold_reason: str, topic: str | None) -> str:
    """Render the durable reason for the intake route without concealing no topic."""
    rendered_topic = topic or "(none linked)"
    return (
        f"Spec-change hold returned {item_id} from ready to backlog; linked proposed-change "
        f"topic: {rendered_topic}. Hold reason: {hold_reason}."
    )
