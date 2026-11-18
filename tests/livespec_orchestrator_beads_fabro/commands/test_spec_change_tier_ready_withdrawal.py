"""Durable spec-change holds are returned from ``ready`` to intake."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _spec_change_tier_ready_withdrawal as withdrawal,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_hold import (
    REASON_AWAITING_REJUDGEMENT,
    REASON_NO_LINKED_TOPIC,
    REASON_UNRATIFIED_TOPIC,
    SpecChangeHold,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


@dataclass
class _Journal:
    records: list[dict[str, object]]

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _item(item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
        title="Held ready item",
        description="Held by the recorded spec-change tier.",
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


def _hold(*, item: WorkItem, reason: str, topic: str | None) -> SpecChangeHold:
    return SpecChangeHold(
        work_item_id=item.id,
        reason=reason,
        linked_proposal_topic=topic,
        verdict_kind="unstated",
        generalization_target="## Governing clause",
    )


def test_withdraws_durable_holds_and_journals_the_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    no_topic = _item("bd-ib-no-topic")
    unratified = _item("bd-ib-unratified")
    awaiting = _item("bd-ib-awaiting")
    free = _item("bd-ib-free")
    holds = {
        no_topic.id: _hold(item=no_topic, reason=REASON_NO_LINKED_TOPIC, topic=None),
        unratified.id: _hold(
            item=unratified, reason=REASON_UNRATIFIED_TOPIC, topic="new-contract-rule"
        ),
        awaiting.id: _hold(
            item=awaiting, reason=REASON_AWAITING_REJUDGEMENT, topic="ratified-rule"
        ),
    }
    comments: list[tuple[str, str]] = []
    writes: list[dict[str, object]] = []
    journal = _Journal(records=[])

    monkeypatch.setattr(withdrawal, "store_config", lambda **_kwargs: _config())
    monkeypatch.setattr(withdrawal, "ratified_proposal_topics", lambda **_kwargs: {"ratified-rule"})
    monkeypatch.setattr(
        withdrawal,
        "standing_hold",
        lambda *, item, **_kwargs: holds.get(item.id),
    )
    monkeypatch.setattr(
        withdrawal,
        "claim_status_write",
        lambda **kwargs: writes.append(kwargs) or None,
    )
    monkeypatch.setattr(
        withdrawal.store,
        "append_work_item_comment",
        lambda *, work_item_id, body, **_kwargs: comments.append((work_item_id, body)),
    )

    remaining = withdrawal.withdraw_durable_spec_change_holds(
        items=[no_topic, unratified, awaiting, free], repo=tmp_path, journal=journal
    )

    assert [item.id for item in remaining] == [awaiting.id, free.id]
    assert [write["item_id"] for write in writes] == [no_topic.id, unratified.id]
    assert all(write["status"] == "backlog" for write in writes)
    assert comments == [
        (
            no_topic.id,
            "Spec-change hold returned bd-ib-no-topic from ready to backlog; linked proposed-change topic: (none linked). Hold reason: no-linked-topic.",
        ),
        (
            unratified.id,
            "Spec-change hold returned bd-ib-unratified from ready to backlog; linked proposed-change topic: new-contract-rule. Hold reason: unratified-topic.",
        ),
    ]
    assert [record["reason"] for record in journal.records] == [
        REASON_NO_LINKED_TOPIC,
        REASON_UNRATIFIED_TOPIC,
    ]


def test_a_claim_refusal_keeps_the_ready_item_visible_to_the_existing_backstop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item = _item("bd-ib-contended")
    journal = _Journal(records=[])
    monkeypatch.setattr(withdrawal, "store_config", lambda **_kwargs: _config())
    monkeypatch.setattr(withdrawal, "ratified_proposal_topics", lambda **_kwargs: set())
    monkeypatch.setattr(
        withdrawal,
        "standing_hold",
        lambda **_kwargs: _hold(item=item, reason=REASON_UNRATIFIED_TOPIC, topic="topic"),
    )
    monkeypatch.setattr(withdrawal, "claim_status_write", lambda **_kwargs: "claim-lost")
    comment = monkeypatch.setattr(
        withdrawal.store,
        "append_work_item_comment",
        lambda **_kwargs: pytest.fail("a refused move must not comment"),
    )
    _ = comment

    remaining = withdrawal.withdraw_durable_spec_change_holds(
        items=[item], repo=tmp_path, journal=journal
    )

    assert remaining == [item]
    assert journal.records == []


def test_an_unreadable_history_leaves_the_pass_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    items = [_item("bd-ib-history-fault")]

    def _unreadable(**_kwargs: object) -> set[str]:
        raise OSError("history unavailable")

    monkeypatch.setattr(withdrawal, "store_config", lambda **_kwargs: _config())
    monkeypatch.setattr(withdrawal, "ratified_proposal_topics", _unreadable)

    assert (
        withdrawal.withdraw_durable_spec_change_holds(
            items=items, repo=tmp_path, journal=_Journal(records=[])
        )
        == items
    )
