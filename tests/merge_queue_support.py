"""A scripted `gh` runner's answer to the merge-queue read (bd-ib-o657q3).

`view_pr` reads queue membership through `gh api graphql` for an open pull request that is not
armed. A runner that replays a fixed queue of results would have that extra call consume the next
scripted result, so each such runner answers the queue read first, as "not in the queue", without
recording it and without touching its script.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

__all__: list[str] = ["merge_queue_read_answer"]

_NOT_QUEUED = json.dumps({"data": {"repository": {"pullRequest": {"mergeQueueEntry": None}}}})


def merge_queue_read_answer(*, argv: list[str]) -> CommandResult | None:
    """The not-queued answer when `argv` is the merge-queue read, else None."""
    if argv[:3] == ["gh", "api", "graphql"] and "mergeQueueEntry" in argv[-1]:
        return CommandResult(exit_code=0, stdout=_NOT_QUEUED, stderr="")
    return None
