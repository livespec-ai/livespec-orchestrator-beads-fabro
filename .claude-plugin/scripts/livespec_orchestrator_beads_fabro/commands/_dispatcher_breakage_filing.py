"""Ledger filing and durable deduplication for scheduled-workflow failures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_runtime.work_items.rank import key_between
from returns.io import IOResult
from returns.pipeline import is_successful

from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import minijinja_openers_in_text
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import utc_now_iso
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.intake_dor import DefinitionOfReadyChecklist
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["FilingContext", "FilingRecord", "context", "file_job", "key"]

_BREAKAGE_KEY = "breakage_key"
_CHECKLIST = DefinitionOfReadyChecklist(
    single_coherent_done=True,
    autonomously_verifiable=True,
    autonomy_tiered=True,
    dependency_linked=True,
    repo_targeted=True,
    above_floor=True,
)
_LEDGER_ERRORS = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    LivespecConfigUnreadableError,
    OSError,
    RuntimeError,
    ValueError,
)


@dataclass(frozen=True, kw_only=True)
class FilingContext:
    """The capture seam and one all-status snapshot of its tenant."""

    config: StoreConfig
    client: BeadsClient | None
    existing: dict[str, str]


@dataclass(frozen=True, kw_only=True)
class FilingRecord:
    """One failed workflow job, as the ledger item that reports it."""

    workflow: str
    job: dict[str, object]
    url: str
    head_sha: str
    tests: tuple[str, ...]
    breakage_key: str


def context(
    *, repo: Path, resolve_config: Callable[..., object]
) -> tuple[FilingContext | None, str | None]:
    """Open the configured tenant and index prior keys, including closed work."""
    try:
        config = resolve_config(cwd=repo, work_items_arg=None)
    except ConnectionPrefixMissingError:
        return None, None
    except _LEDGER_ERRORS as error:
        return None, f"ledger: {error}"
    if not isinstance(config, StoreConfig):
        return FilingContext(config=cast("StoreConfig", config), client=None, existing={}), None
    try:
        client = make_beads_client(config=config)
        return FilingContext(config=config, client=client, existing=_existing(client=client)), None
    except _LEDGER_ERRORS as error:
        return None, f"ledger dedupe: {error}"


def key(*, workflow: str, job_name: str, head_sha: str) -> str:
    """Return the stable workflow-job-commit identity."""
    return f"{workflow}:{job_name}:{head_sha}"


def file_job(
    *,
    context: FilingContext,
    record: FilingRecord,
    capture: Callable[..., IOResult[object, object]],
) -> tuple[str | None, str | None]:
    """File and annotate one failed job via the capture seam."""
    workflow, breakage_key = record.workflow, record.breakage_key
    name = _string(value=record.job.get("name"))
    if not name:
        return None, "failed job has no name"
    description = _description(record=record, job_name=name)
    if minijinja_openers_in_text(source="breakage-pass", text=description):
        return None, f"unfiled {breakage_key}: description contains a template opener"
    item = _work_item(
        config=context.config,
        workflow=workflow,
        job_name=name,
        description=description,
    )
    problem = _capture(capture=capture, config=context.config, item=item)
    if context.client is None:
        return (None, f"unfiled {breakage_key}: {problem}") if problem else (item.id, None)
    # Stamp even when capture failed: it may have created the item before failing, and an
    # unstamped item is invisible to the key scan, so a later pass would file a duplicate.
    try:
        context.client.update_issue(
            issue_id=item.id,
            add_labels=[f"breakage:{workflow}"],
            metadata={_BREAKAGE_KEY: breakage_key},
        )
    except _LEDGER_ERRORS as error:
        problems = "; ".join(filter(None, (problem, f"record breakage key: {error}")))
        return None, f"unfiled {breakage_key}: {problems}"
    return (None, f"unfiled {breakage_key}: {problem}") if problem else (item.id, None)


def _capture(
    *, capture: Callable[..., IOResult[object, object]], config: StoreConfig, item: WorkItem
) -> str | None:
    """Return why capture did not route the item, or None when it did."""
    try:
        routed = is_successful(capture(path=config, item=item, checklist=_CHECKLIST))
    except _LEDGER_ERRORS as error:
        return f"capture work item: {error}"
    return None if routed else "capture work item was not routed"


def _work_item(*, config: StoreConfig, workflow: str, job_name: str, description: str) -> WorkItem:
    return WorkItem(
        id=new_work_item_id(prefix=getattr(config, "prefix", "bd-ib")),
        type="bug",
        status="backlog",
        title=f"{workflow}: {job_name}",
        description=description,
        origin="freeform",
        gap_id=None,
        rank=key_between(a=None, b=None),
        assignee=None,
        depends_on=(),
        captured_at=utc_now_iso(),
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _description(*, record: FilingRecord, job_name: str) -> str:
    workflow, url, head_sha = record.workflow, record.url, record.head_sha
    failed_step = _failed_step(job=record.job)
    lines = "\n".join(f"- Failing test: {test}" for test in record.tests)
    if not lines:
        lines = f"- No failing test was named in the log; failing step: {failed_step}"
    return (
        "## Definition of Done\n\n"
        "References: ## Dispatcher admission, WIP cap, and post-merge acceptance, "
        "## Scenario 313 — A failed scheduled default-branch workflow run becomes one ledger item"
        " per failed job\n\n"
        f"- The failure in scheduled workflow {workflow}, job {job_name}, is corrected and the job"
        " passes.\n\n"
        f"Run URL: {url}\nHead commit: {head_sha}\nFailed job: {job_name}\n{lines}\n"
    )


def _existing(*, client: BeadsClient) -> dict[str, str]:
    found: dict[str, str] = {}
    for record in client.list_issues():
        record = cast("dict[str, object]", record)
        metadata, item_id = record.get("metadata"), record.get("id")
        value = (
            cast("dict[str, object]", metadata).get(_BREAKAGE_KEY)
            if isinstance(metadata, dict)
            else None
        )
        if isinstance(value, str) and isinstance(item_id, str):
            found[value] = item_id
    return found


def _failed_step(*, job: dict[str, object]) -> str:
    steps = job.get("steps")
    if isinstance(steps, list):
        for step in cast("list[object]", steps):
            if isinstance(step, dict):
                record = cast("dict[str, object]", step)
                if record.get("conclusion") != "failure":
                    continue
                name = _string(value=record.get("name"))
                if name:
                    return name
    return "unnamed failing step"


def _string(*, value: object) -> str:
    return str(value) if isinstance(value, str | int) else ""
