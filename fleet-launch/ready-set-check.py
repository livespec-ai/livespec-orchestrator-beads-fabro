#!/usr/bin/env python3
# PROVISIONAL / EXPERIMENTAL — part of fleet-launch/, a stopgap whose first-class
# replacements are the livespec console application and the committed launch-loop
# tool bd-ib-jr6w7v (see fleet-launch/README.md).
"""Report whether a work-item is in the Dispatcher's own ready set.

It asks the installed plugin build's ``ready_items()`` and read-only rework
projection, so the answer cannot diverge from the Dispatcher's ``--item``
selection.

Usage: ready-set-check.py <plugin-root> <repo-path> <item-id>
Exit 0: dispatchable (in the ready set, or pending-approval with clear dependencies,
which the loop admits itself). Exit 3: not in the ready set, with the reason printed.
Exit 2: usage error.

The repository's counted-claims count is NOT read here: wip-claimed-count.py, the
launcher's WIP-gate helper, reads it through the Dispatcher's capacity projection.
"""

import sys
from dataclasses import replace
from pathlib import Path

__all__: list[str] = ["main"]

NOT_READY = 3
USAGE_ERROR = 2
ARGC = 4


def main(*, argv: list[str]) -> int:
    if len(argv) != ARGC:
        print(__doc__)
        return USAGE_ERROR
    plugin, repo, item_id = argv[1], Path(argv[2]), argv[3]
    sys.path.insert(0, f"{plugin}/scripts/bin")
    from _bootstrap import bootstrap

    bootstrap()
    from livespec_orchestrator_beads_fabro.commands._config import (
        resolve_store_config,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
        ready_items,
    )
    from livespec_orchestrator_beads_fabro.store import read_work_items

    items = list(read_work_items(path=resolve_store_config(cwd=repo, work_items_arg=None)))
    me = next((i for i in items if i.id == item_id), None)
    if me is None:
        print(f"READY-CHECK {item_id}: not found")
        return NOT_READY
    if me.status == "pending-approval":
        # The loop admits a pending-approval row only when its dependencies are clear, so ask the
        # same ready predicate of a projection that reads the row as ready rather than passing it
        # blindly (bd-ib-w4hqe2, 2026-10-27).
        projected = [replace(i, status="ready") if i.id == item_id else i for i in items]
        if item_id in {i.id for i in ready_items(items=projected, repo=repo)}:
            print(
                f"READY-CHECK {item_id}: pending-approval with clear dependencies "
                "(the loop admits it)"
            )
            return 0
    if item_id in {i.id for i in ready_items(items=items, repo=repo)}:
        print(f"READY-CHECK {item_id}: in the ready set")
        return 0
    if getattr(me, "rework_pending", False):
        from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
        from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import (
            rework_redispatch_eligible_ids,
        )

        if item_id in rework_redispatch_eligible_ids(
            repo=repo,
            items=items,
            journal=JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl"),
        ):
            print(f"READY-CHECK {item_id}: eligible for rework re-dispatch")
            return 0
    by_id = {i.id: i for i in items}
    deps = [
        getattr(d, "work_item_id", None)
        or (d.get("work_item_id") if isinstance(d, dict) else str(d))
        for d in (me.depends_on or ())
    ]
    # The beads projection reports a closed item as `done`, so a dependency at either status is
    # satisfied and is never an open blocker.
    blockers = [
        f"{d}={by_id[d].status}"
        for d in deps
        if d in by_id and by_id[d].status not in ("closed", "done")
    ]
    print(
        f"READY-CHECK {item_id}: NOT in the ready set (status={me.status} "
        f"assignee={me.assignee} open blockers: {blockers or 'none visible'})"
    )
    return NOT_READY


if __name__ == "__main__":
    sys.exit(main(argv=sys.argv))
