"""A terminal lost sandbox returns its claim to recovery without a human gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_lost_sandbox_disposition as subject,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_lost_sandbox_disposition import (
    LOST_SANDBOX_RELEASE_STAGE,
    dispose_lost_sandbox_release,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_lost_sandbox_outcome import (
    LOST_SANDBOX_RELEASE_STATUS,
    lost_sandbox_release_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_release import (
    RELEASE_STAGES,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM = "bd-ib-xqgeav"
_RUN = "01M7A7G3APRTWPMSAS30MYAB7K"


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="bug",
        status="active",
        title="lost sandbox",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-22T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id=_ITEM,
        branch=f"feat/{_ITEM}",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="petri",
        fabro_factory_server="https://petri.example:32276",
        fabro_factory_dev_token=None,
        janitor=(),
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/livespec-ai/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _lost_outcome() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM,
        status=LOST_SANDBOX_RELEASE_STATUS,
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="lost sandbox",
        fabro_run_id=_RUN,
        fabro_factory_name="petri",
        fabro_failure_cause=f"lost sandbox for run {_RUN}: petri-run-l0",
        fabro_failure_category="lost_sandbox",
    )


def test_lost_sandbox_terminal_is_distinct_from_failure_and_names_its_cause(
    *, tmp_path: Path
) -> None:
    inspect = FabroInspectResult(
        command=CommandResult(exit_code=0, stdout="", stderr=""),
        payload=None,
        status_kind="failed",
        failure=FabroFailureDetail(
            cause=f"lost sandbox for run {_RUN}: petri-run-l0",
            category="lost_sandbox",
            signature="implement|lost_sandbox|abc",
        ),
    )

    outcome = lost_sandbox_release_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id=_RUN,
        inspect=inspect,
        stderr="",
    )

    assert outcome is not None
    assert outcome.status == LOST_SANDBOX_RELEASE_STATUS
    assert outcome.fabro_failure_category == "lost_sandbox"
    assert _RUN in outcome.detail
    assert "released to ready" in outcome.detail
    assert (
        lost_sandbox_release_outcome(
            outcome_type=DispatchOutcome,
            plan=_plan(tmp_path=tmp_path),
            run_id=_RUN,
            inspect=None,
            stderr="",
        )
        is None
    )


def test_lost_sandbox_release_returns_the_claim_to_ready(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict[str, object]] = []

    def fake_store_config(*, repo: Path) -> StoreConfig:
        _ = repo
        return cast("StoreConfig", object())

    def record_release(**kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(subject, "store_config", fake_store_config)
    monkeypatch.setattr(subject, "claim_status_write", record_release)
    journal = _Journal()

    dispose_lost_sandbox_release(
        repo=tmp_path,
        item=_item(),
        outcome=_lost_outcome(),
        journal=journal,  # type: ignore[arg-type]
    )

    assert journal.records == [
        {
            "stage": LOST_SANDBOX_RELEASE_STAGE,
            "work_item_id": _ITEM,
            "run_id": _RUN,
            "factory": "petri",
            "cause": f"lost sandbox for run {_RUN}: petri-run-l0",
        }
    ]
    assert calls[0]["status"] == "ready"
    assert calls[0]["clear_assignee"] is True
    assert LOST_SANDBOX_RELEASE_STAGE in RELEASE_STAGES


def test_a_failed_release_is_journaled_and_another_status_is_ignored(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_store_config(*, repo: Path) -> StoreConfig:
        _ = repo
        return cast("StoreConfig", object())

    monkeypatch.setattr(subject, "store_config", fake_store_config)

    def fail(**_: object) -> None:
        raise BeadsConnectionError(detail="offline")

    monkeypatch.setattr(subject, "claim_status_write", fail)
    journal = _Journal()
    dispose_lost_sandbox_release(
        repo=tmp_path,
        item=_item(),
        outcome=_lost_outcome(),
        journal=journal,  # type: ignore[arg-type]
    )
    ignored = DispatchOutcome(
        work_item_id=_ITEM,
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="ordinary failure",
    )
    dispose_lost_sandbox_release(
        repo=tmp_path,
        item=_item(),
        outcome=ignored,
        journal=journal,  # type: ignore[arg-type]
    )

    assert journal.records[-1] == {
        "stage": "lost-sandbox-release-error",
        "work_item_id": _ITEM,
        "run_id": _RUN,
        "reason": "BeadsConnectionError",
    }
