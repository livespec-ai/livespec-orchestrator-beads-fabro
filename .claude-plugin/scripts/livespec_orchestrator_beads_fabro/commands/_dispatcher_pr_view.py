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

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import (
    failed_outcome,
    journal_stage,
)
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
        DispatchOutcome,
        JournalWriter,
    )

__all__: list[str] = [
    "GH_TIMEOUT_SECONDS",
    "PrViewReading",
    "merge_queue_entry_argv",
    "pr_view_unobservable_outcome",
    "unknown_json_field",
    "view_pr",
]

GH_TIMEOUT_SECONDS = 300.0
# `headRefOid` already rides the ordinary view, so only the branch name and the
# owning repository have to be added for a publication comparison.
_PUBLICATION_FIELDS = ",headRefName,headRepository"
# The fields the engine cannot route without: a pull request's identity, state and merge commit.
# Every other requested field is optional, so a gh build that does not list it is read around.
_ESSENTIAL_FIELDS = frozenset({"number", "state", "mergeCommit"})
_UNKNOWN_FIELD = re.compile(r'Unknown JSON field: "(?P<field>[A-Za-z]+)"')
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
    rejected = unknown_json_field(error=result.stderr) if result.exit_code != 0 else None
    if (
        rejected is not None
        and rejected not in _ESSENTIAL_FIELDS
        and rejected in argv[-1].split(",")
    ):
        # gh's refusal of a field its build does not list is a tool incompatibility, not an
        # absent or unreadable pull request: drop that one optional field and read once more.
        kept = ",".join(field for field in argv[-1].split(",") if field != rejected)
        argv = [*argv[:-1], kept]
        journal.append(
            record={
                "work_item_id": plan.work_item_id,
                "stage": "pr-view-field-dropped",
                "field": rejected,
            }
        )
        result = runner.run(argv=argv, cwd=plan.repo, timeout_seconds=GH_TIMEOUT_SECONDS)
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


def unknown_json_field(*, error: str | None) -> str | None:
    """The field gh named in an `Unknown JSON field` refusal, or None for any other error."""
    match = _UNKNOWN_FIELD.search(error or "")
    return match.group("field") if match else None


def pr_view_unobservable_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    error: str,
    fabro_run_id: str | None,
) -> DispatchOutcome:
    """The ending for a pull-request read that could not be taken.

    A gh refusal of a field its build does not list is a deterministic tool incompatibility, not a
    run failure, so it ends `blocked` naming the field: a failed outcome would feed retry and
    stop-at-second counting for a fault no retry can change. Any other unreadable read stays failed.
    """
    field = unknown_json_field(error=error)
    if field is None:
        return failed_outcome(
            outcome_type=outcome_type,
            plan=plan,
            stage="pr-view",
            detail=f"pull-request read unobservable: {error}",
            fabro_run_id=fabro_run_id,
        )
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="blocked",
        stage="pr-view",
        pr_number=None,
        merge_sha=None,
        detail=f"pull-request read blocked: the host gh does not list the field {field}: {error}",
        fabro_run_id=fabro_run_id,
    )


def _pr_view_error(*, result: CommandResult) -> str | None:
    """Return a non-absence forge failure without reclassifying it as no PR."""
    stderr = result.stderr
    if "no pr" in stderr.lower() or "no pull request" in stderr.lower():
        return None
    return stderr
