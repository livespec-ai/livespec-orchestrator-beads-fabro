"""The one read a launching item's route label needs: the riders its goal will carry.

`_dispatcher_recovery_rider_seed` decides, from an item's comments and the claim
bound, which carried riders hand the agent preserved work. This module takes the
two inputs exactly as the goal render takes them, so the label is computed over
the same rider set the goal carries (bd-ib-e547bt):

- the comments, through `read_dispatch_comments`, the goal's own ledger read;
- the bound, through `prior_claim_instant` skipping THIS dispatch's own claim, by
  the dispatch id the admission valve wrote into the item's live dispatch lock —
  the id `dispatch_one` later inherits from that same lock.

WHY A FAILED READ ANSWERS NONE. A comment read that fails here fails the goal's
own read too, which refuses the dispatch at its `ledger-comments` stage before
any run exists, so no goal carries anything and no label can be false. Refusing
here instead would move that refusal to a stage with no remedy of its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    live_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_item_ledger_reads import (
    read_dispatch_comments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_rider_seed import (
    preserved_work_riders,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rider_bound import (
    prior_claim_instant,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["launching_preserved_work_riders"]


def launching_preserved_work_riders(
    *, repo: Path, item: WorkItem, journal_path: Path
) -> tuple[str, ...]:
    """The preserved-work riders the goal of the item's admitted dispatch will carry."""
    comments = read_dispatch_comments(repo=repo, item=item)
    if isinstance(comments, str):
        return ()
    lock = live_dispatch_lock(repo=repo, work_item_id=item.id)
    claim_at = prior_claim_instant(
        journal_path=journal_path,
        item_id=item.id,
        own_dispatch_id=None if lock is None else lock.dispatch_id,
    )
    return preserved_work_riders(comments=comments, claim_at=claim_at)
