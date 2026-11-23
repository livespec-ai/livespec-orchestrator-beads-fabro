"""Read the pull-request commit series attributable to one dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)

UNOBSERVED_COMMITS_UNREADABLE = "commits-unreadable"


@dataclass(frozen=True, kw_only=True)
class _Commit:
    message: str
    oid: str | None


@dataclass(frozen=True, kw_only=True)
class DispatchCommitSeries:
    commits: tuple[_Commit, ...] = ()
    unreadable_reason: str | None = None


def dispatch_commit_series(
    *,
    repo: Path,
    outcome: DispatchOutcome,
    dispatch_id: str | None,
    runner: CommandRunner,
) -> DispatchCommitSeries:
    """Stub used to establish the extractor's Red test."""
    _ = (repo, outcome, dispatch_id, runner)
    return DispatchCommitSeries(unreadable_reason=UNOBSERVED_COMMITS_UNREADABLE)
