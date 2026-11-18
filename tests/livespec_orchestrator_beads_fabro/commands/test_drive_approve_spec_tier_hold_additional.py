"""Approval behaviour for the spec-change-tier hold's remaining branches."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import _drive_approve_valve as approve
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_hold import (
    REASON_AWAITING_REJUDGEMENT,
    REASON_UNRATIFIED_TOPIC,
    SpecChangeHold,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-held-additional",
        type="bug",
        status="pending-approval",
        title="Approval hold branches",
        description="## Definition of Done\n\n- The hold is respected.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-18T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="test",
        prefix="bd-ib",
        server_user="test",
        database="test",
        bd_path="bd",
        fake=True,
    )


def _hold(*, reason: str) -> SpecChangeHold:
    return SpecChangeHold(
        work_item_id=_item().id,
        reason=reason,
        linked_proposal_topic="topic",
        verdict_kind="unstated",
        generalization_target="## Clause",
    )


def test_approve_refuses_an_unratified_hold_before_any_judgement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    judged: list[object] = []
    monkeypatch.setattr(approve, "ratified_proposal_topics", lambda **_kwargs: set())
    monkeypatch.setattr(
        approve, "standing_hold", lambda **_kwargs: _hold(reason=REASON_UNRATIFIED_TOPIC)
    )
    monkeypatch.setattr(
        approve,
        "judge_item_definition_of_done",
        lambda **_kwargs: judged.append(object()) or SimpleNamespace(holds=False, findings=()),
    )

    result = approve.approve_item(
        repo=tmp_path, config=_config(), item=_item(), action_id="approve:bd-ib-held-additional"
    )

    assert result["status"] == "failed"
    assert "topic" in result["summary"]
    assert "unratified-topic" in result["summary"]
    assert judged == []


def test_awaiting_rejudgement_reclassifies_then_admits_when_the_hold_releases(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    classifications: list[dict[str, object]] = []
    monkeypatch.setattr(approve, "ratified_proposal_topics", lambda **_kwargs: {"topic"})
    monkeypatch.setattr(
        approve,
        "standing_hold",
        lambda **_kwargs: _hold(reason=REASON_AWAITING_REJUDGEMENT),
    )
    monkeypatch.setattr(
        approve,
        "classify_and_hold",
        lambda **kwargs: classifications.append(kwargs) or None,
    )
    monkeypatch.setattr(approve, "_approval_size_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(approve, "_definition_of_done_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(
        approve,
        "_approval",
        lambda **_kwargs: SimpleNamespace(write_status=lambda **_more: None),
    )

    result = approve.approve_item(
        repo=tmp_path, config=_config(), item=_item(), action_id="approve:bd-ib-held-additional"
    )

    assert result["status"] == "green"
    assert classifications[0]["stage"] == "dispatch"


def test_awaiting_rejudgement_refuses_when_the_fresh_classification_still_holds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(approve, "ratified_proposal_topics", lambda **_kwargs: {"topic"})
    monkeypatch.setattr(
        approve,
        "standing_hold",
        lambda **_kwargs: _hold(reason=REASON_AWAITING_REJUDGEMENT),
    )
    monkeypatch.setattr(
        approve,
        "classify_and_hold",
        lambda **_kwargs: _hold(reason=REASON_UNRATIFIED_TOPIC),
    )

    result = approve.approve_item(
        repo=tmp_path, config=_config(), item=_item(), action_id="approve:bd-ib-held-additional"
    )

    assert result["status"] == "failed"
    assert "unratified-topic" in result["summary"]


def test_unreadable_history_fails_closed_for_a_recorded_spec_change_tier(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _unreadable(**_kwargs: object) -> set[str]:
        raise OSError("history unavailable")

    monkeypatch.setattr(approve, "ratified_proposal_topics", _unreadable)
    monkeypatch.setattr(approve, "item_comment_bodies", lambda **_kwargs: ("record",))
    monkeypatch.setattr(
        approve, "recorded_spec_change_tier", lambda **_kwargs: SimpleNamespace(is_spec_change=True)
    )

    result = approve.approve_item(
        repo=tmp_path, config=_config(), item=_item(), action_id="approve:bd-ib-held-additional"
    )

    assert result["status"] == "failed"
    assert result["domain_error"] == "spec-change-history-unreadable"


def test_unreadable_history_without_a_recorded_tier_proceeds_as_before(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _unreadable(**_kwargs: object) -> set[str]:
        raise OSError("history unavailable")

    monkeypatch.setattr(approve, "ratified_proposal_topics", _unreadable)
    monkeypatch.setattr(approve, "item_comment_bodies", lambda **_kwargs: ())
    monkeypatch.setattr(approve, "_approval_size_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(approve, "_definition_of_done_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(
        approve,
        "_approval",
        lambda **_kwargs: SimpleNamespace(write_status=lambda **_more: None),
    )

    result = approve.approve_item(
        repo=tmp_path, config=_config(), item=_item(), action_id="approve:bd-ib-held-additional"
    )

    assert result["status"] == "green"
