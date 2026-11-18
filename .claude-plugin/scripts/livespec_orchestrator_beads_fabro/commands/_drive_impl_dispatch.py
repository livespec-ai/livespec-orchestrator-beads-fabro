"""The `impl:<id>` dispatch transport of the drive operator surface.

Split out of `drive.py` along its cohesion seam: `drive.py` is the CLI
supervisor and action ROUTER (parse, refuse, pick a handler, render), while
this module is the one handler that shells out — it builds the
`dispatcher.py loop` argv, runs it through the injected `CommandRunner`, and
maps the Dispatcher's exit code and JSON onto a drive result payload.

`CommandRun` and the `CommandRunner` protocol live here because they are the
transport's own vocabulary; `drive.py` imports them back so its published
surface is unchanged.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from livespec_orchestrator_beads_fabro.commands import _drive_impl_scope as scope
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    FALLBACK_SOURCE,
    INVOKER_FLAG,
    InvokerIdentity,
    default_invoker_identity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_reconcile_hook import (
    dispatch_journal_path,
)
from livespec_orchestrator_beads_fabro.commands._drive_impl_delivery import (
    MergedPullRequestLookup,
    delivered_merged_pull_request,
)
from livespec_orchestrator_beads_fabro.commands._drive_impl_result import (
    dispatch_status,
    dispatch_summary,
    goal_template_refusal,
    parse_dispatcher_json,
)
from livespec_orchestrator_beads_fabro.effects import attempt

__all__: list[str] = [
    "CommandRun",
    "CommandRunner",
    "build_dispatcher_argv",
    "run_impl_dispatch",
]


@dataclass(frozen=True, kw_only=True)
class CommandRun:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        """Run argv and return captured output."""
        ...


def run_impl_dispatch(  # noqa: PLR0913 — kw-only transport; `workflow_name` is one more independent per-dispatch input forwarded verbatim, not a coupled one.
    *,
    repo: Path,
    work_item_ref: str,
    runner: CommandRunner | None,
    dispatcher_bin: Path | None,
    acp_nodes: tuple[str, ...],
    workflow_name: str | None,
    identity: InvokerIdentity | None,
    merged_pull_request_lookup: MergedPullRequestLookup | None = None,
) -> dict[str, Any]:
    """Run one `impl:<id>` action as a `dispatcher.py loop` subprocess."""
    resolved_runner = _SubprocessRunner() if runner is None else runner
    resolved_dispatcher = _resolve_dispatcher_bin(dispatcher_bin=dispatcher_bin)
    argv = build_dispatcher_argv(
        repo=repo,
        dispatcher_bin=resolved_dispatcher,
        work_item_ref=work_item_ref,
        acp_nodes=acp_nodes,
        workflow_name=workflow_name,
        identity=identity,
    )
    plan = scope.scope_plan(host=scope.default_scope_host())
    unit: str | None = None
    detail: str | None = None
    launch = scope.LAUNCH_UNSCOPED
    result: CommandRun | None = None
    if plan is not None:
        unit = scope.scope_unit_name(work_item_ref=work_item_ref)
        scoped = resolved_runner(argv=scope.scoped_argv(plan=plan, unit=unit, argv=argv), cwd=repo)
        detail = scope.scope_launch_failure(
            unit=unit, returncode=scoped.returncode, stderr=scoped.stderr
        )
        if detail is None:
            launch = scope.LAUNCH_SCOPED
            result = scoped
        else:
            unit = None
    if result is None:
        result = resolved_runner(argv=argv, cwd=repo)
    _record_launch(
        repo=repo,
        identity=identity,
        work_item_ref=work_item_ref,
        launch=launch,
        scope_unit=unit,
        detail=detail,
    )
    parsed = parse_dispatcher_json(text=result.stdout)
    status = dispatch_status(returncode=result.returncode, parsed=parsed)
    goal_template_refusal_detail = goal_template_refusal(parsed=parsed)
    merged_pull_request = delivered_merged_pull_request(
        repo=repo,
        work_item_ref=work_item_ref,
        returncode=result.returncode,
        stderr=result.stderr,
        lookup=merged_pull_request_lookup,
    )
    return {
        "action_id": f"impl:{work_item_ref}",
        "kind": "impl",
        "work_item_ref": work_item_ref,
        "status": status,
        "launch": launch,
        **({} if unit is None else {"scope_unit": unit}),
        "dispatcher": {
            "argv": list(argv),
            "exit_code": result.returncode,
            "stdout_json": parsed,
            "stderr": result.stderr,
        },
        "summary": dispatch_summary(
            status=status,
            work_item_ref=work_item_ref,
            goal_template_refusal_detail=goal_template_refusal_detail,
            merged_pull_request=merged_pull_request,
        ),
        "goal_template_refusal": goal_template_refusal_detail,
    }


def _record_launch(
    *,
    repo: Path,
    identity: InvokerIdentity | None,
    work_item_ref: str,
    launch: str,
    scope_unit: str | None,
    detail: str | None,
) -> None:
    """Append the launch's journal record; a journal fault never fails the dispatch."""
    journal = JournalFile(
        path=dispatch_journal_path(repo=repo),
        identity=default_invoker_identity() if identity is None else identity,
    )
    record = scope.launch_record(
        work_item_id=work_item_ref, launch=launch, scope_unit=scope_unit, detail=detail
    )
    _ = attempt(action=lambda: journal.append(record=record), exceptions=(OSError,))


def build_dispatcher_argv(
    *,
    repo: Path,
    dispatcher_bin: Path,
    work_item_ref: str,
    acp_nodes: tuple[str, ...] = (),
    workflow_name: str | None = None,
    identity: InvokerIdentity | None = None,
) -> tuple[str, ...]:
    """Build the `dispatcher.py loop` argv one `impl:<id>` action runs.

    Each ACP adapter override becomes its own `--acp-node NODE=ADAPTER`
    pair, so the value reaches the Dispatcher as a single argv element and
    an adapter carrying spaces survives without quoting games.

    `--workflow-name` is re-emitted the same way and for the same reason the
    ACP overrides are: the workflow-variant selector is a recorded ARGUMENT
    and never an environment variable, so the only route from this operator
    surface to the Dispatcher is the argv this function builds — which is
    also what the drive result payload publishes back. Omitted entirely when
    unselected, so the Dispatcher's own ledger-then-default precedence
    resolves it rather than being pre-empted by an empty string.

    An ASSERTED identity (flag or environment) is forwarded as an explicit
    `--invoker` so the spawned Dispatcher records the operator, not the shell
    that spawned it. A FALLBACK identity is deliberately NOT forwarded: it is a
    mark meaning "nobody asserted", and passing it as a flag would relabel it
    `flag`-sourced — laundering an unattributed act into an asserted one, and
    defeating `require_invoker` downstream into the bargain.
    """
    overrides = tuple(element for override in acp_nodes for element in ("--acp-node", override))
    return (
        "python3",
        str(dispatcher_bin),
        "loop",
        *_forwarded_invoker(identity=identity),
        "--repo",
        str(repo),
        "--budget",
        "1",
        "--parallel",
        "1",
        "--item",
        work_item_ref,
        *_forwarded_workflow_name(workflow_name=workflow_name),
        *overrides,
        "--json",
    )


class _SubprocessRunner:
    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        completed = subprocess.run(  # noqa: S603 - argv is constructed without shell.
            argv,
            check=False,
            cwd=cwd,
            text=True,
            capture_output=True,
        )
        return CommandRun(
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def _forwarded_workflow_name(*, workflow_name: str | None) -> tuple[str, ...]:
    if workflow_name is None or workflow_name == "":
        return ()
    return ("--workflow-name", workflow_name)


def _forwarded_invoker(*, identity: InvokerIdentity | None) -> tuple[str, ...]:
    if identity is None or identity.invoker_source == FALLBACK_SOURCE:
        return ()
    return (INVOKER_FLAG, identity.invoker)


def _resolve_dispatcher_bin(*, dispatcher_bin: Path | None) -> Path:
    if dispatcher_bin is not None:
        return dispatcher_bin
    return _scripts_root() / "bin" / "dispatcher.py"


def _scripts_root() -> Path:
    return Path(__file__).resolve().parents[2]
