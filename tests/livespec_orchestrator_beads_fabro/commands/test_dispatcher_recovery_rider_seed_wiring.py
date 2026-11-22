"""The route row and its rider read carry the preserved-work label (bd-ib-e547bt).

`test_dispatcher_recovery_rider_seed` binds the decision itself. These bind where
it lands: the `recovery-route` row a launching item journals is labelled `seeded`
when its goal will carry preserved-work riders, names them, and asks for them
only on a `fresh` route; and the rider read takes the goal's own comments and the
claim bound that skips this dispatch's own claim.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro._store_comments import WorkItemComment
from livespec_orchestrator_beads_fabro.commands import _dispatcher_recovery_rider_read as read
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_launch import (
    journal_recovery_route,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    recovery_route_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    RecoveryRoute,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM_ID = "bd-ib-e547bt"


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A dispatch whose goal carries preserved-work riders",
        description="Label it.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-22T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _answer(value: object) -> Callable[..., object]:
    def _read(**_: object) -> object:
        return value

    return _read


def _rows(*, path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_a_fresh_route_row_carrying_preserved_work_riders_reads_seeded_and_names_them() -> None:
    row = recovery_route_record(
        work_item_id=_ITEM_ID,
        route="fresh",
        seeded_by_riders=("livespec-preserved-tree", "refs/heads/preserve/candidate-x"),
    )

    assert row["route"] == "seeded"
    assert row["seeded_by_riders"] == ["livespec-preserved-tree", "refs/heads/preserve/candidate-x"]


def test_a_fresh_route_row_carrying_no_preserved_work_rider_reads_fresh() -> None:
    row = recovery_route_record(work_item_id=_ITEM_ID, route="fresh")

    assert row["route"] == "fresh"
    assert row["seeded_by_riders"] == []


def test_the_journaled_fresh_route_row_reads_seeded_when_the_goal_carries_preserved_work(
    tmp_path: Path,
) -> None:
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    journal_recovery_route(
        route=RecoveryRoute(work_item_id=_ITEM_ID, route="fresh"),
        journal=journal,
        carried_riders=lambda: ("livespec-needs-human-cause",),
    )

    (row,) = _rows(path=journal.path)
    assert row["stage"] == "recovery-route"
    assert row["route"] == "seeded"
    assert row["seeded_by_riders"] == ["livespec-needs-human-cause"]


def test_a_route_other_than_fresh_never_asks_for_the_riders(tmp_path: Path) -> None:
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    asked: list[bool] = []

    def _riders() -> tuple[str, ...]:
        asked.append(True)
        return ("livespec-preserved-tree",)

    journal_recovery_route(
        route=RecoveryRoute(work_item_id=_ITEM_ID, route="seeded"),
        journal=journal,
        carried_riders=_riders,
    )

    (row,) = _rows(path=journal.path)
    assert row["route"] == "seeded"
    assert row["seeded_by_riders"] == []
    assert asked == []


def test_the_rider_read_bounds_at_the_claim_before_this_dispatchs_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal_path = tmp_path / "journal.jsonl"
    _ = journal_path.write_text(
        "".join(
            json.dumps(row) + "\n"
            for row in (
                {
                    "stage": "ledger-admit",
                    "work_item_id": _ITEM_ID,
                    "dispatch_id": "earlier",
                    "at": "2026-11-22T06:27:48Z",
                },
                {
                    "stage": "ledger-admit",
                    "work_item_id": _ITEM_ID,
                    "dispatch_id": "own",
                    "at": "2026-11-22T11:16:00Z",
                },
            )
        ),
        encoding="utf-8",
    )
    comments = (
        WorkItemComment(
            text="livespec-preserved-tree\n\nrun 01M80Z25N44T",
            author="dispatcher",
            created_at="2026-11-22T08:00:00Z",
        ),
        WorkItemComment(
            text="livespec-needs-human-cause\n\nan older run",
            author="dispatcher",
            created_at="2026-11-22T05:00:00Z",
        ),
    )
    monkeypatch.setattr(read, "read_dispatch_comments", _answer(comments))
    monkeypatch.setattr(read, "live_dispatch_lock", _answer(SimpleNamespace(dispatch_id="own")))

    riders = read.launching_preserved_work_riders(
        repo=tmp_path, item=_item(), journal_path=journal_path
    )

    assert riders == ("livespec-preserved-tree",)


def test_the_rider_read_bounds_at_the_newest_claim_when_no_live_lock_names_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    comments = (
        WorkItemComment(
            text="livespec-preserve-by-reference\n\nrun 01M80Z25N44T",
            author="dispatcher",
            created_at="2026-11-22T08:00:00Z",
        ),
    )
    monkeypatch.setattr(read, "read_dispatch_comments", _answer(comments))
    monkeypatch.setattr(read, "live_dispatch_lock", _answer(None))

    riders = read.launching_preserved_work_riders(
        repo=tmp_path, item=_item(), journal_path=tmp_path / "absent.jsonl"
    )

    assert riders == ("livespec-preserve-by-reference",)


def test_a_failed_comment_read_names_no_rider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(read, "read_dispatch_comments", _answer("ledger comments read failed"))

    riders = read.launching_preserved_work_riders(
        repo=tmp_path, item=_item(), journal_path=tmp_path / "journal.jsonl"
    )

    assert riders == ()
