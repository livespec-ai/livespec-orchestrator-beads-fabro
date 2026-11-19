"""The ONE journaled forge read of a publish branch's pull request.

Split out of `_dispatcher_engine_merge` by cohesion once pull-request
CONFIRMATION and merge POLLING became separate modules: both are public entry
points and both need this read, so it is a properly-named public interface
rather than a private helper either of them owns. A cross-module private import
is the thing that must not happen here — pyright strict (`reportPrivateUsage`)
and the `private_calls` check both reject it.

`include_publication` is the only dimension the read has. The ordinary view
already carries `headRefOid`, so a publication comparison needs just the branch
NAME and the owning REPOSITORY added; the fields are asked for only when a
caller is going to compare them, so the ordinary green dispatch pays nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    parse_pr_view,
    pr_view_argv,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandResult,
        CommandRunner,
        JournalWriter,
    )

__all__: list[str] = [
    "GH_TIMEOUT_SECONDS",
    "PrViewReading",
    "merge_queue_entry_argv",
    "view_pr",
]

GH_TIMEOUT_SECONDS = 300.0
# `headRefOid` already rides the ordinary view, so only the branch name and the
# owning repository have to be added for a publication comparison.
_PUBLICATION_FIELDS = ",headRefName,headRepository"
_MERGE_QUEUE_QUERY = (
    "query($owner: String!, $name: String!, $number: Int!) {"
    " repository(owner: $owner, name: $name) {"
    " pullRequest(number: $number) { mergeQueueEntry { state position } } } }"
)


@dataclass(frozen=True, kw_only=True)
class PrViewReading:
    """One pull-request read, including an observation failure when it had one."""

    view: PrView | None
    error: str | None


def view_pr(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    include_publication: bool = False,
    include_status_checks: bool = True,
) -> PrViewReading:
    argv = pr_view_argv(plan=plan, include_status_checks=include_status_checks)
    if include_publication:
        argv[-1] = f"{argv[-1]}{_PUBLICATION_FIELDS}"
    result = runner.run(
        argv=argv,
        cwd=plan.repo,
        timeout_seconds=GH_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="pr-view", result=result)
    if result.exit_code != 0:
        return PrViewReading(view=None, error=_pr_view_error(result=result))
    view = parse_pr_view(stdout=result.stdout)
    if view is not None and _queue_read_wanted(view=view):
        queued = _merge_queue_entry(plan=plan, number=view.number, runner=runner, journal=journal)
        if queued:
            view = replace(view, merge_queue_entry=True)
    return PrViewReading(
        view=view,
        error=None if view is not None else "pull-request view returned unreadable JSON",
    )


def _queue_read_wanted(*, view: PrView) -> bool:
    """Only an open pull request that is not armed can be in the queue unseen.

    A merged pull request is past it and an armed one is already reported as handed to the
    forge's merge, so neither pays the extra forge call.
    """
    return view.state == "OPEN" and not view.auto_merge_armed and not view.merge_queue_entry


def _merge_queue_entry(
    *,
    plan: DispatchPlan,
    number: int,
    runner: CommandRunner,
    journal: JournalWriter,
) -> bool:
    """True when the forge reports a merge-queue entry for the pull request.

    `gh pr view --json` has no queue-entry field (gh 2.96.0 refuses `mergeQueueEntry`), so the
    entry is read from GraphQL `pullRequest.mergeQueueEntry`. A read that fails or answers in
    an unexpected shape reads as not queued: the view it supplements has already been taken,
    and the failed read is journaled under its own stage.
    """
    result = runner.run(
        argv=merge_queue_entry_argv(number=number),
        cwd=plan.repo,
        timeout_seconds=GH_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="pr-merge-queue", result=result)
    if result.exit_code != 0:
        return False
    parsed = parse_json(text=result.stdout)
    if isinstance(parsed, JsonParseFailure):
        return False
    node: object = parsed
    for key in ("data", "repository", "pullRequest", "mergeQueueEntry"):
        if not isinstance(node, dict):
            return False
        node = cast("dict[str, object]", node).get(key)
    return node is not None


def merge_queue_entry_argv(*, number: int) -> list[str]:
    """The `gh api graphql` call, repository resolved from the working directory."""
    return [
        "gh",
        "api",
        "graphql",
        "-F",
        "owner=:owner",
        "-F",
        "name=:repo",
        "-F",
        f"number={number}",
        "-f",
        f"query={_MERGE_QUEUE_QUERY}",
    ]


def _pr_view_error(*, result: CommandResult) -> str | None:
    """Return a non-absence forge failure without reclassifying it as no PR."""
    stderr = result.stderr
    if "no pr" in stderr.lower() or "no pull request" in stderr.lower():
        return None
    return stderr
