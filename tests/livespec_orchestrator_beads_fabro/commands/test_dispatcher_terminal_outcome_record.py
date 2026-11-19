"""The Dispatcher fails visibly when a finished run cannot be recorded."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_selection as selection
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    needs_human_cause_body,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import STAGE_FAILURE
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM_ID = "bd-ib-record"
_RUN_ID = "01M7RECORDTERMINAL"


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="record terminal outcome",
        description="",
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
        blocked_reason=None,
    )


def _failed_outcome(**overrides: object) -> DispatchOutcome:
    values: dict[str, object] = {
        "work_item_id": _ITEM_ID,
        "status": "failed",
        "stage": "fabro-run",
        "pr_number": None,
        "merge_sha": None,
        "detail": "the failed terminal returned",
        "fabro_run_id": _RUN_ID,
        "needs_human_kind": STAGE_FAILURE,
        "needs_human_stages": ("implement@2",),
        "needs_human_reason": "the assertion failed",
        "fabro_failure_cause": "LIVESPEC_IMPLEMENT_ASSERTION failed",
        "fabro_failure_signature": "foreign-engine-signature",
    }
    values.update(overrides)
    return DispatchOutcome(**values)


def test_failed_comment_uses_the_first_livespec_token_or_the_no_signature_literal() -> None:
    """A foreign engine signature cannot masquerade as a LIVESPEC signature."""
    body = needs_human_cause_body(outcome=_failed_outcome())

    assert "failure signature: LIVESPEC_IMPLEMENT_ASSERTION" in body
    assert "engine failure signature: foreign-engine-signature" in body


def test_missing_terminal_evidence_becomes_a_named_nonzero_dispatch_result() -> None:
    """No causal stage is a recording failure, not a silent failed run."""
    outcome = _failed_outcome(needs_human_stages=None)

    revised = selection.record_terminal_outcome(
        repo=Path("/unused"), item=_item(), outcome=outcome, journal=_Journal()
    )

    assert revised.status == "failed"
    assert revised.detail == (
        "the failed terminal returned\n"
        f"LIVESPEC_TERMINAL_RECORDING_FAILED: run {_RUN_ID}; could not record "
        "failing node and visit: the finished run supplied no causal stage"
    )


def test_refused_comment_write_becomes_a_named_nonzero_dispatch_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed append cannot leave an otherwise green drive exit successful."""
    outcome = _failed_outcome(status="green", detail="merged pull request #7")
    monkeypatch.setattr(
        selection,
        "record_needs_human_cause",
        lambda **_kwargs: "ledger comment: BeadsCommandError prevented the outcome record",
    )

    revised = selection.record_terminal_outcome(
        repo=Path("/unused"), item=_item(), outcome=outcome, journal=_Journal()
    )

    assert revised.status == "failed"
    assert _RUN_ID in revised.detail
    assert "ledger comment" in revised.detail
