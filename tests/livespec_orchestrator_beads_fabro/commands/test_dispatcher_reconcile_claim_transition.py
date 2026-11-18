"""The cleanup lane settles a finished token decision before claim recovery."""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_claim_lane as lane
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    ClaimLaneResult,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_survey import (
    StrandedClaimSurvey,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="active",
        title="A stranded claim",
        description="Repair it.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-18T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _inputs(*, tmp_path: Path) -> ReconcileInputs:
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    return ReconcileInputs(
        repo=tmp_path,
        fabro_bin="fabro",
        id_prefix="bd-ib",
        items=(_item(item_id="bd-ib-first"), _item(item_id="bd-ib-second")),
        journaled=lambda **_: (),
        runner=object(),  # type: ignore[arg-type]
        journal=journal,
        ledger=object(),  # type: ignore[arg-type]
        claim_journal=journal,
    )


def test_live_reconcile_pass_settles_each_transition_before_the_claim_survey(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inputs = _inputs(tmp_path=tmp_path)
    settled: list[str] = []

    def _settle(*, client: object, work_item_id: str) -> bool:
        _ = client
        settled.append(work_item_id)
        return True

    def _survey(*, inputs: object) -> StrandedClaimSurvey:
        _ = inputs
        return StrandedClaimSurvey(recovered=(), held=())

    monkeypatch.setattr(lane, "make_beads_client", lambda **_: object())
    monkeypatch.setattr(lane, "store_config", lambda **_: object())
    monkeypatch.setattr(lane, "settle_unapplied_transition", _settle)
    monkeypatch.setattr(lane, "survey_stranded_claims", _survey)

    result = lane.reconcile_claim_lane(inputs=inputs, factories=(), observed={}, dry_run=False)

    assert settled == ["bd-ib-first", "bd-ib-second"]
    assert result == ClaimLaneResult()


def test_dry_pass_does_not_settle_and_a_single_ledger_fault_does_not_stop_the_lane(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inputs = _inputs(tmp_path=tmp_path)
    calls: list[str] = []

    def _survey(*, inputs: object) -> StrandedClaimSurvey:
        _ = inputs
        return StrandedClaimSurvey(recovered=(), held=())

    monkeypatch.setattr(lane, "make_beads_client", lambda **_: object())
    monkeypatch.setattr(lane, "store_config", lambda **_: object())

    def _settle(*, client: object, work_item_id: str) -> bool:
        _ = client
        calls.append(work_item_id)
        if work_item_id == "bd-ib-first":
            raise BeadsCommandError(command="bd update", exit_code=1, stderr="offline")
        return True

    monkeypatch.setattr(lane, "settle_unapplied_transition", _settle)
    monkeypatch.setattr(lane, "survey_stranded_claims", _survey)

    _ = lane.reconcile_claim_lane(inputs=inputs, factories=(), observed={}, dry_run=False)
    assert calls == ["bd-ib-first", "bd-ib-second"]

    calls.clear()
    _ = lane.reconcile_claim_lane(inputs=inputs, factories=(), observed={}, dry_run=True)
    assert calls == []
