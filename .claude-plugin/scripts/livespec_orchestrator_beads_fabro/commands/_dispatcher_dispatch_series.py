"""Read the pull-request commit series attributable to one dispatch.

Split out of `_dispatcher_tdd_probe` so that module stays under the file
logical-line ceiling. The selection is EXACT per dispatch: a commit joins the
series only when its `Factory-Run-Id` trailer equals the dispatch id, so a
re-dispatch of the same item, or a human commit pushed onto the same branch,
cannot contribute to it. An empty selection is unobservable, never zero.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles import (
    UNOBSERVED_COMMITS_UNREADABLE,
    UNOBSERVED_NO_DISPATCH_ID,
    UNOBSERVED_NO_PULL_REQUEST,
    UNOBSERVED_SERIES_NOT_IDENTIFIED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_commits import commit_trailers

__all__: list[str] = [
    "COMMITS_PROBE_TIMEOUT_SECONDS",
    "FACTORY_RUN_ID_TRAILER_KEY",
    "DispatchCommitSeries",
    "PrCommit",
    "commits_from_payload",
    "dispatch_commit_series",
]

# The trailer the sandbox's `livespec.factoryRunId` git config stamps on every
# commit the run authors. Its VALUE is the Dispatcher's `dispatch_id`, which is
# what makes this a per-run selector rather than a per-item one.
FACTORY_RUN_ID_TRAILER_KEY = "Factory-Run-Id"

# The commit-series probe budget, matching the sibling merged-PR diff-size
# probe: fail-soft to None rather than hold up an already-final verdict.
COMMITS_PROBE_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class PrCommit:
    """The PR-list evidence needed to inspect one authored commit's files."""

    message: str
    oid: str | None


@dataclass(frozen=True, kw_only=True)
class DispatchCommitSeries:
    """This dispatch's attributable commits, or why they could not be read."""

    commits: tuple[PrCommit, ...] = ()
    unreadable_reason: str | None = None


def dispatch_commit_series(
    *,
    repo: Path,
    outcome: DispatchOutcome,
    dispatch_id: str | None,
    runner: CommandRunner,
) -> DispatchCommitSeries:
    """Read and identify this dispatch's commit series, or report why not.

    The empty tuple is not an observed empty series: commits must carry this
    dispatch's provenance trailer to establish that the PR series belongs to
    the dispatch at all.
    """
    if outcome.pr_number is None:
        return _unreadable(reason=UNOBSERVED_NO_PULL_REQUEST)
    if dispatch_id is None:
        return _unreadable(reason=UNOBSERVED_NO_DISPATCH_ID)
    result = runner.run(
        argv=["gh", "pr", "view", str(outcome.pr_number), "--json", "commits"],
        cwd=repo,
        timeout_seconds=COMMITS_PROBE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return _unreadable(reason=UNOBSERVED_COMMITS_UNREADABLE)
    commits = commits_from_payload(stdout=result.stdout)
    if commits is None:
        return _unreadable(reason=UNOBSERVED_COMMITS_UNREADABLE)
    mine = tuple(
        commit
        for commit in commits
        if commit_trailers(message=commit.message).get(FACTORY_RUN_ID_TRAILER_KEY) == dispatch_id
    )
    if not mine:
        return _unreadable(reason=UNOBSERVED_SERIES_NOT_IDENTIFIED)
    return DispatchCommitSeries(commits=mine)


def _unreadable(*, reason: str) -> DispatchCommitSeries:
    return DispatchCommitSeries(unreadable_reason=reason)


def commits_from_payload(*, stdout: str) -> tuple[PrCommit, ...] | None:
    """Parse PR commits while retaining the object id needed for file evidence."""
    try:
        payload_raw: object = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload_raw, dict):
        return None
    payload = cast("dict[str, object]", payload_raw)
    raw_commits = payload.get("commits")
    if not isinstance(raw_commits, list):
        return None
    commits: list[PrCommit] = []
    for raw in cast("list[object]", raw_commits):
        if not isinstance(raw, dict):
            continue
        entry = cast("dict[str, object]", raw)
        headline = entry.get("messageHeadline")
        if not isinstance(headline, str):
            continue
        body = entry.get("messageBody")
        oid = entry.get("oid")
        commits.append(
            PrCommit(
                message=f"{headline}\n\n{body if isinstance(body, str) else ''}",
                oid=oid if isinstance(oid, str) and oid else None,
            )
        )
    return tuple(commits)
