"""The fail-soft ledger receipt for an ended run's newest WIP capture."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_comments import (
    append_work_item_comment,
    read_work_item_comments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import (
    minijinja_openers_in_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    ORIGIN_DEFAULT_REVISION,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    PRESERVED_TREE_MARKER,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    WorkItemNotFoundError,
)

__all__: list[str] = [
    "WipCapture",
    "WipCaptureUnobservable",
    "latest_wip_capture",
    "record_wip_capture_receipt",
]

_WIP_REF_PREFIX = "refs/livespec/wip"
_REMOTE = "origin"
_GIT_TIMEOUT_SECONDS = 5.0
_LS_REMOTE_FIELDS = 2
_RECEIPT_ERROR_STAGE = "wip-capture-receipt-error"
_LEDGER_ERRORS: tuple[type[Exception], ...] = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
)


@dataclass(frozen=True, kw_only=True)
class WipCapture:
    """One immutable work-in-progress ref and the commit origin reports at it."""

    ref: str
    commit: str


@dataclass(frozen=True, kw_only=True)
class WipCaptureUnobservable:
    """Origin declined the capture listing, so absence cannot be claimed."""

    detail: str


@dataclass(frozen=True, kw_only=True)
class NeedsHumanCapture:
    """The terminal needs-human ref and its diff against the default branch."""

    ref: str
    commit: str
    files: int | None
    insertions: int | None
    deletions: int | None


def latest_wip_capture(
    *, work_item_id: str, run_id: str, refs: dict[str, str]
) -> WipCapture | None:
    """The highest numeric capture in this exact work-item/run namespace."""
    prefix = f"{_WIP_REF_PREFIX}/{work_item_id}/{run_id}/"
    captures = [
        (int(suffix), WipCapture(ref=ref, commit=commit))
        for ref, commit in refs.items()
        if ref.startswith(prefix) and (suffix := ref.removeprefix(prefix)).isdecimal()
    ]
    return None if not captures else max(captures, key=lambda capture: capture[0])[1]


def record_wip_capture_receipt(
    *,
    repo: Path,
    work_item_id: str,
    run_id: str,
    factory: str,
    journal: JournalWriter,
    runner: CommandRunner | None = None,
) -> None:
    """Name this non-merged run's capture without delaying its disposition."""
    try:
        _record_wip_capture_receipt(
            repo=repo,
            work_item_id=work_item_id,
            run_id=run_id,
            factory=factory,
            journal=journal,
            runner=runner,
        )
    except (*_LEDGER_ERRORS, OSError):
        return


def _record_wip_capture_receipt(
    *,
    repo: Path,
    work_item_id: str,
    run_id: str,
    factory: str,
    journal: JournalWriter,
    runner: CommandRunner | None,
) -> None:
    """Read, deduplicate and append one receipt, letting the caller fail soft."""
    active_runner = runner if runner is not None else ShellCommandRunner()
    observed = _read_capture(
        runner=active_runner, repo=repo, work_item_id=work_item_id, run_id=run_id
    )
    body = _receipt_body(
        work_item_id=work_item_id,
        run_id=run_id,
        factory=factory,
        observed=observed,
        needs_human=_needs_human_capture(runner=active_runner, repo=repo, run_id=run_id)
        if observed is None
        else None,
    )
    if _already_recorded(repo=repo, work_item_id=work_item_id, body=body):
        return
    findings = minijinja_openers_in_text(source=PRESERVED_TREE_MARKER, text=body)
    if findings:
        _error(journal=journal, work_item_id=work_item_id, run_id=run_id, reason="template-opener")
        return
    append_work_item_comment(path=store_config(repo=repo), work_item_id=work_item_id, body=body)


def _read_capture(
    *, runner: CommandRunner, repo: Path, work_item_id: str, run_id: str
) -> WipCapture | WipCaptureUnobservable | None:
    result = runner.run(
        argv=["git", "ls-remote", _REMOTE, f"{_WIP_REF_PREFIX}/{work_item_id}/{run_id}/*"],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return WipCaptureUnobservable(detail=f"git ls-remote exited {result.exit_code}")
    refs = {
        fields[1]: fields[0]
        for line in result.stdout.splitlines()
        if len(fields := line.split()) == _LS_REMOTE_FIELDS
    }
    return latest_wip_capture(work_item_id=work_item_id, run_id=run_id, refs=refs)


def _needs_human_capture(
    *, runner: CommandRunner, repo: Path, run_id: str
) -> NeedsHumanCapture | None:
    """Read a no-WIP ending's needs-human ref and its measurable work, if any.

    This is deliberately a best-effort receipt: a failed read is rendered as an
    unobservable diff, never as an empty one.  The receipt is written after an
    ending, so no failure here may alter that ending's disposition.
    """
    ref = f"refs/heads/needs-human/{run_id}"
    listed = runner.run(
        argv=["git", "ls-remote", _REMOTE, ref], cwd=repo, timeout_seconds=_GIT_TIMEOUT_SECONDS
    )
    if listed.exit_code != 0:
        return None
    lines = [line.split() for line in listed.stdout.splitlines()]
    match = next(
        (fields for fields in lines if len(fields) == _LS_REMOTE_FIELDS and fields[1] == ref),
        None,
    )
    if match is None:
        return None
    commit = match[0]
    base = runner.run(
        argv=["git", "merge-base", ORIGIN_DEFAULT_REVISION, commit],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if base.exit_code != 0 or not (base_commit := base.stdout.strip()):
        return _unmeasurable_needs_human(ref=ref, commit=commit)
    diff = runner.run(
        argv=["git", "diff", "--numstat", base_commit, commit, "--", ".", ":(exclude).fabro"],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if diff.exit_code != 0:
        return _unmeasurable_needs_human(ref=ref, commit=commit)
    stats = [line.split() for line in diff.stdout.splitlines() if line.strip()]
    if any(
        len(fields) < _LS_REMOTE_FIELDS or not fields[0].isdigit() or not fields[1].isdigit()
        for fields in stats
    ):
        return _unmeasurable_needs_human(ref=ref, commit=commit)
    return NeedsHumanCapture(
        ref=ref,
        commit=commit,
        files=len(stats),
        insertions=sum(int(fields[0]) for fields in stats),
        deletions=sum(int(fields[1]) for fields in stats),
    )


def _unmeasurable_needs_human(*, ref: str, commit: str) -> NeedsHumanCapture:
    """Represent a readable ref whose change measurement could not be read."""
    return NeedsHumanCapture(ref=ref, commit=commit, files=None, insertions=None, deletions=None)


def _receipt_body(
    *,
    work_item_id: str,
    run_id: str,
    factory: str,
    observed: WipCapture | WipCaptureUnobservable | None,
    needs_human: NeedsHumanCapture | None,
) -> str:
    lines = [
        PRESERVED_TREE_MARKER,
        "",
        f"work-item: {work_item_id}",
        f"run id: {run_id}",
        f"factory: {factory}",
    ]
    if isinstance(observed, WipCapture):
        lines.extend(
            [
                f"work-in-progress ref: {observed.ref}",
                f"commit id: {observed.commit}",
            ]
        )
    elif isinstance(observed, WipCaptureUnobservable):
        lines.append("work-in-progress preservation could not be determined")
    elif needs_human is not None:
        lines.extend(
            [
                "the run has no work-in-progress ref",
                f"needs-human ref: {needs_human.ref}",
                f"commit id: {needs_human.commit}",
            ]
        )
        if needs_human.files is None:
            lines.append("needs-human diff could not be determined")
        else:
            files = needs_human.files
            adds = needs_human.insertions
            deletes = needs_human.deletions
            prefix = "needs-human diff:"
            diff_summary = f"{prefix} {files} files changed, {adds} insertions, {deletes} deletions"
            lines.append(diff_summary)
    else:
        lines.append("the run has no work-in-progress ref")
    return "\n".join(lines)


def _already_recorded(*, repo: Path, work_item_id: str, body: str) -> bool:
    comments = attempt(
        action=lambda: read_work_item_comments(
            path=store_config(repo=repo), work_item_id=work_item_id
        ),
        exceptions=(*_LEDGER_ERRORS, OSError),
    )
    return not isinstance(comments, AttemptFailure) and any(
        comment.text == body for comment in comments
    )


def _error(*, journal: JournalWriter, work_item_id: str, run_id: str, reason: str) -> None:
    try:
        journal.append(
            record={
                "stage": _RECEIPT_ERROR_STAGE,
                "work_item_id": work_item_id,
                "run_id": run_id,
                "reason": reason,
            }
        )
    except OSError:
        return
