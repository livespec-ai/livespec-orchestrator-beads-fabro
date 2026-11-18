"""Cached GitHub Actions reads used by the breakage pass."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast
from urllib.parse import quote

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)

__all__: list[str] = ["api", "failed_jobs", "job_log", "workflow_verdict"]

_CACHE_DURATION = "1h"
_TIMEOUT_SECONDS = 30.0
_JOBS_PAGE_SIZE = 100


def workflow_verdict(
    *, repo: Path, runner: CommandRunner, workflow: str, branch: str
) -> dict[str, object] | None:
    result = api(
        repo=repo,
        runner=runner,
        endpoint=(
            f"repos/{{owner}}/{{repo}}/actions/workflows/{quote(workflow, safe='')}/runs"
            f"?branch={quote(branch, safe='')}&status=completed&per_page=1"
        ),
    )
    if result.exit_code != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    document = cast("dict[str, object]", payload)
    runs = document.get("workflow_runs")
    if not isinstance(runs, list):
        return None
    if not runs:
        return {}
    return cast("dict[str, object]", runs[0]) if isinstance(runs[0], dict) else None


def failed_jobs(
    *, repo: Path, runner: CommandRunner, run_id: str
) -> list[dict[str, object]] | None:
    if not run_id:
        return None
    failed: list[dict[str, object]] = []
    page = 1
    while True:
        jobs = _jobs_page(repo=repo, runner=runner, run_id=run_id, page=page)
        if jobs is None:
            return None
        failed.extend(
            cast("dict[str, object]", job)
            for job in jobs
            if isinstance(job, dict)
            and cast("Mapping[str, object]", job).get("conclusion") == "failure"
        )
        if len(jobs) < _JOBS_PAGE_SIZE:
            return failed
        page += 1


def job_log(*, repo: Path, runner: CommandRunner, job_id: str) -> str | None:
    if not job_id:
        return None
    result = api(
        repo=repo,
        runner=runner,
        endpoint=f"repos/{{owner}}/{{repo}}/actions/jobs/{job_id}/logs",
    )
    return result.stdout if result.exit_code == 0 else None


def _jobs_page(*, repo: Path, runner: CommandRunner, run_id: str, page: int) -> list[object] | None:
    result = api(
        repo=repo,
        runner=runner,
        endpoint=(
            f"repos/{{owner}}/{{repo}}/actions/runs/{run_id}/jobs"
            f"?filter=latest&per_page={_JOBS_PAGE_SIZE}&page={page}"
        ),
    )
    if result.exit_code != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    document = cast("dict[str, object]", payload) if isinstance(payload, dict) else {}
    jobs = document.get("jobs")
    return cast("list[object]", jobs) if isinstance(jobs, list) else None


def api(*, repo: Path, runner: CommandRunner, endpoint: str) -> CommandResult:
    return runner.run(
        argv=["gh", "api", "--cache", _CACHE_DURATION, endpoint],
        cwd=repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
