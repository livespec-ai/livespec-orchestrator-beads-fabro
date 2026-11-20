"""Authenticated forge reads used by exceptional repayment admission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    MASTER_CI_WORKFLOW_DEFAULT,
    ORIGIN_DEFAULT_BRANCH,
)
from livespec_orchestrator_beads_fabro.effects import parse_json

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentReading
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

__all__: list[str] = [
    "Run",
    "api",
    "failed_jobs",
    "is_ancestor",
    "latest_landed_ancestor",
    "normal_runs",
    "run",
    "runs_at",
]

_FAILURE = "failure"
_TIMEOUT_SECONDS = 60.0
_PUSH = "push"
_PAGE_SIZE = 100
_MAX_PAGES = 100


@dataclass(frozen=True, kw_only=True)
class Run:
    """The complete forge facts needed to assess one master run."""

    run_id: str
    head: str
    status: str
    conclusion: str
    jobs: tuple[tuple[str, str], ...]


def api(*, runner: CommandRunner, repo: Path, path: str) -> dict[str, object] | None:
    """Read one authenticated GitHub API object, or report it unreadable."""
    result = runner.run(
        argv=["gh", "api", f"repos/{path}"], cwd=repo, timeout_seconds=_TIMEOUT_SECONDS
    )
    value = parse_json(text=result.stdout) if result.exit_code == 0 else None
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def run(*, runner: CommandRunner, repo: Path, repository: str, run_id: str) -> Run | None:
    """Read a run with its job conclusions; partial forge data remains unreadable."""
    result = runner.run(
        argv=[
            "gh",
            "run",
            "view",
            run_id,
            "--repo",
            repository,
            "--json",
            "databaseId,headSha,status,conclusion,jobs",
        ],
        cwd=repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    value = parse_json(text=result.stdout) if result.exit_code == 0 else None
    row = cast("dict[str, object]", value) if isinstance(value, dict) else {}
    head, status, conclusion = (row.get(key) for key in ("headSha", "status", "conclusion"))
    identifier, jobs = row.get("databaseId", run_id), row.get("jobs")
    if not isinstance(head, str) or not isinstance(status, str) or not isinstance(conclusion, str):
        return None
    if not isinstance(identifier, int | str) or not isinstance(jobs, list):
        return None
    parsed: list[tuple[str, str]] = []
    for raw in cast("list[object]", jobs):
        if not isinstance(raw, dict):
            return None
        job = cast("dict[str, object]", raw)
        name, job_conclusion = job.get("name"), job.get("conclusion")
        if not isinstance(name, str) or not isinstance(job_conclusion, str):
            return None
        parsed.append((name, job_conclusion))
    return Run(
        run_id=str(identifier), head=head, status=status, conclusion=conclusion, jobs=tuple(parsed)
    )


def normal_runs(
    *, runner: CommandRunner, repo: Path, repository: str, head: str | None
) -> tuple[dict[str, object], ...] | None:
    """Every normal master CI run, at one commit or on the whole branch, read page by page.

    A history the forge reports as larger than what could be read, or any malformed
    record, is unreadable rather than a shorter answer.
    """
    scope = f"&head_sha={head}" if head is not None else ""
    collected: list[dict[str, object]] = []
    for page in range(1, _MAX_PAGES + 1):
        response = api(
            runner=runner,
            repo=repo,
            path=(
                f"{repository}/actions/runs?branch={ORIGIN_DEFAULT_BRANCH}&event={_PUSH}"
                f"{scope}&per_page={_PAGE_SIZE}&page={page}"
            ),
        )
        rows = response.get("workflow_runs") if response else None
        total = response.get("total_count") if response else None
        if not isinstance(rows, list) or not isinstance(total, int):
            return None
        for raw in cast("list[object]", rows):
            if not isinstance(raw, dict):
                return None
            collected.append(cast("dict[str, object]", raw))
        if len(collected) >= total:
            return tuple(row for row in collected if _is_normal_master_ci(row=row))
        if not rows:
            return None
    return None


def _is_normal_master_ci(*, row: dict[str, object]) -> bool:
    return (
        row.get("name") == MASTER_CI_WORKFLOW_DEFAULT
        and row.get("head_branch") == ORIGIN_DEFAULT_BRANCH
        and row.get("event") == _PUSH
    )


def runs_at(
    *, runner: CommandRunner, repo: Path, repository: str, head: str
) -> tuple[str, ...] | None:
    """List every normal master CI run ID at a commit, accepting no malformed records."""
    rows = normal_runs(runner=runner, repo=repo, repository=repository, head=head)
    if rows is None:
        return None
    ids: list[str] = []
    for row in rows:
        run_id = row.get("id")
        if not isinstance(run_id, int):
            return None
        ids.append(str(run_id))
    return tuple(ids)


def is_ancestor(
    *, runner: CommandRunner, repo: Path, repository: str, ancestor: str, descendant: str
) -> bool | None:
    """Return a forge-proven ancestry relation; unreadable is distinct from false."""
    if ancestor == descendant:
        return True
    response = api(runner=runner, repo=repo, path=f"{repository}/compare/{ancestor}...{descendant}")
    status = response.get("status") if response else None
    return status in {"ahead", "identical"} if isinstance(status, str) else None


def latest_landed_ancestor(
    *, runner: CommandRunner, repo: Path, repository: str, reading: IncidentReading, head: str
) -> str | None:
    """Select the latest landed commit that the candidate descends from."""
    for landed in reversed(reading.attempt.landed_commits):
        relation = is_ancestor(
            runner=runner, repo=repo, repository=repository, ancestor=landed, descendant=head
        )
        if relation is None:
            return None
        if relation:
            return landed
    return None


def failed_jobs(*, run: Run) -> tuple[str, ...]:
    """The named failed jobs from one complete forge run."""
    return tuple(name for name, conclusion in run.jobs if conclusion == _FAILURE)
