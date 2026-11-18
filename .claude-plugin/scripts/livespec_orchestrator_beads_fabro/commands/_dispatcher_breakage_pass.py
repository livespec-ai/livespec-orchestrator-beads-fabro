"""Capture failures from watched scheduled workflows as ledger work.

Each pass observes the forge exactly once through cached ``gh api`` requests.
When the host can reach the configured tenant, failed jobs are filed through
the ordinary capture seam and identified durably by their breakage key.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands import _dispatcher_breakage_filing as filing
from livespec_orchestrator_beads_fabro.commands import _dispatcher_breakage_forge as forge
from livespec_orchestrator_beads_fabro.commands import _jsonc
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    resolve_default_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner
from livespec_orchestrator_beads_fabro.intake_dor import file_captured_work_item
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "add_breakage_pass_arguments",
    "breakage_key",
    "breakage_pass",
    "register_breakage_pass",
    "run_breakage_pass_command",
]

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_FAILURE_LINE = re.compile(r"^(?:FAILED|ERROR)\s+([^\s]+)", re.MULTILINE)

# Compatibility aliases keep S1's focused forge-read probes stable.
_workflow_verdict = forge.workflow_verdict
_failed_jobs = forge.failed_jobs
_job_log = forge.job_log


@dataclass(frozen=True, kw_only=True)
class _FailedRun:
    """The observed failed run whose jobs are being filed."""

    workflow: str
    url: str
    head_sha: str
    repo: Path
    runner: CommandRunner


def breakage_key(*, workflow: str, job_name: str, head_sha: str) -> str:
    """Return the stable per-workflow-job-commit identity used for deduplication."""
    return filing.key(workflow=workflow, job_name=job_name, head_sha=head_sha)


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
        outcome = forge.workflow_verdict(repo=repo, runner=runner, workflow=workflow, branch=branch)
        if outcome is None:
            _verdict(workflow=workflow, detail="unreadable workflow run")
            failed = True
        else:
            failed = (
                _emit_outcome(workflow=workflow, outcome=outcome, repo=repo, runner=runner)
                or failed
            )
    return int(failed)


def _watched_workflows(*, repo: Path) -> tuple[str, ...] | None:
    path = repo / ".livespec.jsonc"
    if not path.is_file():
        return ()
    node: object = _jsonc.parse(text=path.read_text(encoding="utf-8"))
    for name in (_PLUGIN_BLOCK, "dispatcher", "breakage_workflows"):
        if not isinstance(node, Mapping):
            return None
        node = cast("Mapping[str, object]", node).get(name)
        if node is None:
            return ()
    if not isinstance(node, list):
        return None
    workflows = cast("list[object]", node)
    if any(not isinstance(item, str) or not item for item in workflows):
        return None
    return tuple(cast("str", item) for item in workflows)


def _emit_outcome(
    *, workflow: str, outcome: dict[str, object], repo: Path, runner: CommandRunner
) -> bool:
    if not outcome:
        _verdict(workflow=workflow, detail="no-completed-run")
        return False
    url = _string(value=outcome.get("html_url"))
    conclusion = outcome.get("conclusion")
    if conclusion == "success":
        _verdict(workflow=workflow, detail=f"run={url} green")
        return False
    if conclusion != "failure":
        _verdict(workflow=workflow, detail=f"run={url} not-concluded {conclusion}")
        return False
    return _handle_failed_run(workflow=workflow, outcome=outcome, repo=repo, runner=runner)


def _handle_failed_run(
    *, workflow: str, outcome: dict[str, object], repo: Path, runner: CommandRunner
) -> bool:
    """Return whether a failed run could not be fully observed or filed."""
    url = _string(value=outcome.get("html_url"))
    run_id = _string(value=outcome.get("id"))
    head_sha = _string(value=outcome.get("head_sha"))
    jobs = forge.failed_jobs(repo=repo, runner=runner, run_id=run_id)
    if not run_id or not head_sha or jobs is None:
        _verdict(workflow=workflow, detail="unreadable failed run")
        return True
    context, context_problem = filing.context(repo=repo, resolve_config=resolve_store_config)
    if context_problem is not None:
        _verdict(workflow=workflow, detail=f"unreadable {context_problem}")
        return True
    if context is None:
        return _preview_failed_jobs(
            workflow=workflow,
            url=url,
            head_sha=head_sha,
            jobs=jobs,
            repo=repo,
            runner=runner,
        )
    run = _FailedRun(workflow=workflow, url=url, head_sha=head_sha, repo=repo, runner=runner)
    filed: list[str] = []
    already_filed: list[str] = []
    for job in jobs:
        problem = _file_failed_job(
            context=context, run=run, job=job, filed=filed, already_filed=already_filed
        )
        if problem is not None:
            _verdict(workflow=workflow, detail=problem)
            return True
    _verdict_filing(workflow=workflow, url=url, filed=filed, already_filed=already_filed)
    return False


def _file_failed_job(
    *,
    context: filing.FilingContext,
    run: _FailedRun,
    job: dict[str, object],
    filed: list[str],
    already_filed: list[str],
) -> str | None:
    """File one failed job unless its key is known; return a verdict detail on a problem."""
    job_id = _string(value=job.get("id"))
    name = _string(value=job.get("name"))
    if not job_id or not name:
        return "unreadable failed job"
    key = filing.key(workflow=run.workflow, job_name=name, head_sha=run.head_sha)
    prior = context.existing.get(key)
    if prior is not None:
        already_filed.append(prior)
        return None
    log = forge.job_log(repo=run.repo, runner=run.runner, job_id=job_id)
    if log is None:
        return f"unreadable job log for {name}"
    item_id, problem = filing.file_job(
        context=context,
        record=filing.FilingRecord(
            workflow=run.workflow,
            job=job,
            url=run.url,
            head_sha=run.head_sha,
            tests=_failing_tests(log=log),
            breakage_key=key,
        ),
        capture=file_captured_work_item,
    )
    if problem is not None:
        return f"unreadable {problem}"
    if item_id is not None:
        filed.append(item_id)
        context.existing[key] = item_id
    return None


def _verdict_filing(*, workflow: str, url: str, filed: list[str], already_filed: list[str]) -> None:
    if filed:
        _verdict(workflow=workflow, detail=f"run={url} filed {', '.join(filed)}")
    elif already_filed:
        _verdict(workflow=workflow, detail=f"run={url} already-filed {', '.join(already_filed)}")


def _preview_failed_jobs(
    *,
    workflow: str,
    url: str,
    head_sha: str,
    jobs: list[dict[str, object]],
    repo: Path,
    runner: CommandRunner,
) -> bool:
    """Retain the read-only observation for an unconfigured local repository."""
    for job in jobs:
        job_id = _string(value=job.get("id"))
        name = _string(value=job.get("name"))
        log = forge.job_log(repo=repo, runner=runner, job_id=job_id)
        if not job_id or not name or log is None:
            _verdict(workflow=workflow, detail="unreadable failed job")
            return True
        tests = ",".join(_failing_tests(log=log)) or "no failing test named"
        _verdict(
            workflow=workflow,
            detail=(f"would-file job={name} run={url} head={head_sha} failing-tests={tests}"),
        )
    return False


def _failing_tests(*, log: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_FAILURE_LINE.findall(log)))


def _string(*, value: object) -> str:
    return str(value) if isinstance(value, str | int) else ""


def _verdict(*, workflow: str, detail: str) -> None:
    _ = write_stdout(text=f"breakage-pass workflow={workflow} {detail}\n")
