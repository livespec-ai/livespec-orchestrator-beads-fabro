"""Fail-closed forge verification for exceptional descendant repayment admission."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentReading,
    RepaymentMasterCiEvidence,
    RepaymentPreexistingJob,
)
from livespec_orchestrator_beads_fabro._incident_repayment_plan import (
    MasterCiRun,
)
from livespec_orchestrator_beads_fabro.commands._incident_repayment_descendant_forge import (
    api,
    failed_jobs,
    is_ancestor,
    latest_landed_ancestor,
    run,
    runs_at,
)
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import read_history

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

_TIMEOUT_SECONDS = 60.0
_COMPLETE = "completed"
_SUCCESS = "success"
_FAILURE = "failure"

__all__: list[str] = ["verify_descendant_master_ci"]


def _refuse(*, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code="incident-repayment-master-ci-outstanding", detail=detail)


def verify_descendant_master_ci(  # noqa: C901, PLR0911, PLR0912, PLR0913, PLR0915 - ordered spec gate.
    *,
    client: BeadsClient,
    runner: CommandRunner,
    repo: Path,
    repository: str,
    reading: IncidentReading,
    master_ci: MasterCiRun,
    attributed_item_ids: tuple[str, ...],
) -> MasterCiRun | AuthorityRefusal:
    """Return a signed-in-effect descendant run only after all four contract conditions hold."""
    if master_ci.head in reading.attempt.landed_commits:
        return master_ci
    if not (master_ci.complete and master_ci.conclusion == _SUCCESS):
        return master_ci
    landed = latest_landed_ancestor(
        runner=runner, repo=repo, repository=repository, reading=reading, head=master_ci.head
    )
    if landed is None:
        return master_ci
    landed_run_ids = runs_at(runner=runner, repo=repo, repository=repository, head=landed)
    if landed_run_ids is None:
        return _refuse(detail="condition-1: landed run history is unreadable")
    landed_runs = tuple(
        observed
        for run_id in landed_run_ids
        if (observed := run(runner=runner, repo=repo, repository=repository, run_id=run_id))
        is not None
    )
    if len(landed_runs) != len(landed_run_ids):
        return _refuse(detail="condition-1: landed run jobs are unreadable")
    complete = tuple(run for run in landed_runs if run.status == _COMPLETE)
    failed = tuple(run for run in complete if run.conclusion == _FAILURE)
    if not failed or any(run.conclusion == _SUCCESS for run in complete):
        return _refuse(
            detail="condition-1: landed commit has no exclusively failed complete master run"
        )
    landed_failed = failed[0]
    parent_response = api(runner=runner, repo=repo, path=f"{repository}/commits/{landed}")
    parents = parent_response.get("parents") if parent_response else None
    parent = (
        cast("dict[str, object]", parents[0]).get("sha")
        if isinstance(parents, list) and parents and isinstance(parents[0], dict)
        else None
    )
    if not isinstance(parent, str):
        return _refuse(detail="condition-2: landed commit first parent is unreadable")
    parent_ids = runs_at(runner=runner, repo=repo, repository=repository, head=parent)
    if parent_ids is None:
        return _refuse(detail="condition-2: first-parent run history is unreadable")
    parent_runs = tuple(
        observed
        for run_id in parent_ids
        if (observed := run(runner=runner, repo=repo, repository=repository, run_id=run_id))
        is not None
    )
    if len(parent_runs) != len(parent_ids):
        return _refuse(detail="condition-2: first-parent run jobs are unreadable")
    preexisting_by_job = {
        job: run.run_id
        for run in parent_runs
        if run.status == _COMPLETE
        for job in failed_jobs(run=run)
    }
    evidence: list[RepaymentPreexistingJob] = []
    for job in failed_jobs(run=landed_failed):
        preexisting_run = preexisting_by_job.get(job)
        matching: tuple[str, str, str | None] | None = None
        for item_id in attributed_item_ids:
            if item_id == reading.attempt.item_id:
                continue
            history = read_history(client=client, repository=repository, item_id=item_id)
            if isinstance(history, AuthorityRefusal) or any(
                attempt.repository != repository for attempt in history
            ):
                continue
            for attempt in history:
                retained = attempt.repayment_master_ci_evidence
                retained_run = (
                    retained.landed_failed_run_id
                    if retained is not None
                    and any(record.job == job for record in retained.preexisting_jobs)
                    else None
                )
                for fix in attempt.landed_commits:
                    reaches_run = is_ancestor(
                        runner=runner,
                        repo=repo,
                        repository=repository,
                        ancestor=fix,
                        descendant=master_ci.head,
                    )
                    predates_landed = is_ancestor(
                        runner=runner,
                        repo=repo,
                        repository=repository,
                        ancestor=fix,
                        descendant=landed,
                    )
                    if reaches_run is None or predates_landed is None:
                        return _refuse(
                            detail=f"condition-3: job {job} attribution ancestry is unreadable"
                        )
                    if reaches_run and not predates_landed:
                        matching = item_id, fix, retained_run
                        break
                if matching is not None:
                    break
            if matching is not None:
                break
        if preexisting_run is None and matching is not None:
            preexisting_run = matching[2]
        if preexisting_run is None:
            return _refuse(detail=f"condition-2: job {job} is not pre-existing")
        if matching is None:
            return _refuse(detail=f"condition-3: job {job} has no attributed incident fix")
        evidence.append(
            RepaymentPreexistingJob(
                job=job,
                preexisting_run_id=preexisting_run,
                attributed_item_id=matching[0],
                attributed_landed_commit=matching[1],
            )
        )
    all_runs = api(runner=runner, repo=repo, path=f"{repository}/actions/runs?per_page=100")
    candidates = all_runs.get("workflow_runs") if all_runs else None
    if not isinstance(candidates, list):
        return _refuse(detail="condition-4: successful master-run history is unreadable")
    for raw in cast("list[object]", candidates):
        if not isinstance(raw, dict):
            return _refuse(detail="condition-4: successful master-run history is unreadable")
        row = cast("dict[str, object]", raw)
        head, status, conclusion = (
            row.get("head_sha"),
            row.get("status"),
            row.get("conclusion"),
        )
        if (
            not isinstance(head, str)
            or not isinstance(status, str)
            or not isinstance(conclusion, str)
            or head == master_ci.head
        ):
            continue
        if status != _COMPLETE or conclusion != _SUCCESS:
            continue
        from_landed = is_ancestor(
            runner=runner, repo=repo, repository=repository, ancestor=landed, descendant=head
        )
        before_candidate = is_ancestor(
            runner=runner,
            repo=repo,
            repository=repository,
            ancestor=head,
            descendant=master_ci.head,
        )
        if from_landed is None or before_candidate is None:
            return _refuse(detail="condition-4: successful master-run ancestry is unreadable")
        if from_landed and before_candidate:
            return _refuse(detail="condition-4: an earlier successful descendant master run exists")
    return MasterCiRun(
        run_id=master_ci.run_id,
        head=master_ci.head,
        conclusion=master_ci.conclusion,
        complete=master_ci.complete,
        landed_commit=landed,
        evidence=RepaymentMasterCiEvidence(
            admitted_run_id=master_ci.run_id,
            admitted_head=master_ci.head,
            landed_commit=landed,
            landed_failed_run_id=landed_failed.run_id,
            preexisting_jobs=tuple(evidence),
        ),
    )
