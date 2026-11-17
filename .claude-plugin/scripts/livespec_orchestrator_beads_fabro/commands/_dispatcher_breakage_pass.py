"""Read scheduled-workflow verdicts without filing their follow-up work.

This is S1 of the scheduled-workflow breakage pass.  It deliberately has no
ledger dependency: S2 owns filing and deduplication.  Every forge read is a
single cached ``gh api`` request, so one invocation is one observation rather
than a poll loop.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast
from urllib.parse import quote

from livespec_orchestrator_beads_fabro.commands import _jsonc
from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    resolve_default_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "add_breakage_pass_arguments",
    "breakage_pass",
    "register_breakage_pass",
    "run_breakage_pass_command",
]

_CACHE_DURATION = "1h"
_TIMEOUT_SECONDS = 30.0
_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_FAILURE_LINE = re.compile(r"^(?:FAILED|ERROR)\s+([^\s]+)", re.MULTILINE)


def add_breakage_pass_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Register the host-only, read-only breakage pass flags."""
    _ = parser.add_argument("--repo", required=True)
    _ = parser.add_argument("--dry-run", action="store_true")


def register_breakage_pass(
    *, add_parser: Callable[..., argparse.ArgumentParser], handlers: dict[str, Callable[..., int]]
) -> None:
    """Install the breakage-pass parser and handler in the dispatcher hub."""
    add_breakage_pass_arguments(parser=add_parser("breakage-pass"))
    handlers["breakage-pass"] = run_breakage_pass_command


def run_breakage_pass_command(*, args: argparse.Namespace) -> int:
    """Run one read-only pass over a governed repository's watched workflows."""
    return breakage_pass(repo=Path(args.repo), runner=ShellCommandRunner())


def breakage_pass(*, repo: Path, runner: CommandRunner) -> int:
    """Print each declared workflow's latest completed default-branch verdict."""
    workflows = _watched_workflows(repo=repo)
    if workflows is None:
        _ = write_stderr(text="breakage-pass unreadable dispatcher.breakage_workflows\n")
        return 1
    if not workflows:
        return 0
    branch = resolve_default_branch(repo=repo, runner=runner)
    if branch is None:
        for workflow in workflows:
            _verdict(workflow=workflow, detail="unreadable default branch")
        return 1
    failed = False
    for workflow in workflows:
        outcome = _workflow_verdict(repo=repo, runner=runner, workflow=workflow, branch=branch)
        if outcome is None:
            _verdict(workflow=workflow, detail="unreadable workflow run")
            failed = True
        else:
            failed = (
                _emit_outcome(workflow=workflow, outcome=outcome, repo=repo, runner=runner)
                or failed
            )
    return int(failed)


def _watched_workflows(*, repo: Path) -> tuple[str, ...] | None:  # noqa: PLR0911
    path = repo / ".livespec.jsonc"
    if not path.is_file():
        return ()
    parsed = _jsonc.parse(text=path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        return None
    document = cast("dict[str, object]", parsed)
    plugin = document.get(_PLUGIN_BLOCK)
    if plugin is None:
        return ()
    if not isinstance(plugin, Mapping):
        return None
    plugin_block = cast("Mapping[str, object]", plugin)
    dispatcher = plugin_block.get("dispatcher")
    if dispatcher is None:
        return ()
    if not isinstance(dispatcher, Mapping):
        return None
    dispatcher_block = cast("Mapping[str, object]", dispatcher)
    value = dispatcher_block.get("breakage_workflows")
    if value is None:
        return ()
    if not isinstance(value, list):
        return None
    workflows = cast("list[object]", value)
    if any(not isinstance(item, str) or not item for item in workflows):
        return None
    return tuple(cast("str", item) for item in workflows)


def _workflow_verdict(
    *, repo: Path, runner: CommandRunner, workflow: str, branch: str
) -> dict[str, object] | None:
    result = _api(
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
    raw_runs = document.get("workflow_runs")
    if not isinstance(raw_runs, list):
        return None
    runs = cast("list[object]", raw_runs)
    if not runs:
        return {}
    return cast("dict[str, object]", runs[0]) if isinstance(runs[0], dict) else None


def _emit_outcome(
    *, workflow: str, outcome: dict[str, object], repo: Path, runner: CommandRunner
) -> bool:
    if not outcome:
        _verdict(workflow=workflow, detail="no-completed-run")
        return False
    conclusion = outcome.get("conclusion")
    url = _string(value=outcome.get("html_url"))
    if conclusion == "success":
        _verdict(workflow=workflow, detail=f"run={url} green")
        return False
    if conclusion != "failure":
        _verdict(workflow=workflow, detail=f"run={url} not-concluded {conclusion}")
        return False
    run_id = _string(value=outcome.get("id"))
    head_sha = _string(value=outcome.get("head_sha"))
    jobs = _failed_jobs(repo=repo, runner=runner, run_id=run_id)
    if not run_id or not head_sha or jobs is None:
        _verdict(workflow=workflow, detail="unreadable failed run")
        return True
    for job in jobs:
        job_id = _string(value=job.get("id"))
        name = _string(value=job.get("name"))
        log = _job_log(repo=repo, runner=runner, job_id=job_id)
        if not job_id or not name or log is None:
            _verdict(workflow=workflow, detail="unreadable failed job")
            return True
        tests = ",".join(_FAILURE_LINE.findall(log)) or "no failing test named"
        _verdict(
            workflow=workflow,
            detail=(f"would-file job={name} run={url} head={head_sha} failing-tests={tests}"),
        )
    return False


def _failed_jobs(
    *, repo: Path, runner: CommandRunner, run_id: str
) -> list[dict[str, object]] | None:
    if not run_id:
        return None
    result = _api(
        repo=repo,
        runner=runner,
        endpoint=f"repos/{{owner}}/{{repo}}/actions/runs/{run_id}/jobs?filter=latest",
    )
    if result.exit_code != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    document = cast("dict[str, object]", payload) if isinstance(payload, dict) else {}
    jobs = document.get("jobs")
    if not isinstance(jobs, list):
        return None
    raw_jobs = cast("list[object]", jobs)
    return [
        cast("dict[str, object]", job)
        for job in raw_jobs
        if isinstance(job, dict)
        and cast("Mapping[str, object]", job).get("conclusion") == "failure"
    ]


def _job_log(*, repo: Path, runner: CommandRunner, job_id: str) -> str | None:
    if not job_id:
        return None
    result = _api(
        repo=repo,
        runner=runner,
        endpoint=f"repos/{{owner}}/{{repo}}/actions/jobs/{job_id}/logs",
    )
    return result.stdout if result.exit_code == 0 else None


def _api(*, repo: Path, runner: CommandRunner, endpoint: str) -> CommandResult:
    return runner.run(
        argv=["gh", "api", "--cache", _CACHE_DURATION, endpoint],
        cwd=repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )


def _string(*, value: object) -> str:
    return str(value) if isinstance(value, str | int) else ""


def _verdict(*, workflow: str, detail: str) -> None:
    _ = write_stdout(text=f"breakage-pass workflow={workflow} {detail}\n")
