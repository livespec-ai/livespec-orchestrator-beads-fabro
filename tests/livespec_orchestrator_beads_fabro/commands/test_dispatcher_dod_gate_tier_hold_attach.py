"""The attach seam places the hold, journals it, and fails open on every unreadable input.

Wiring half of `bd-ib-dfqrc7`: `attach_dod_gate_tier_hold` reads the blocked item, its
comments and the specification, writes the hold through the one record writer, and
returns the outcome UNCHANGED. Each unreadable input leaves the item blocked exactly
as before, because an outage must not hold an item for a proposal nobody can name.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_dod_gate_tier_hold as module
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import STAGE_FAILURE
from livespec_orchestrator_beads_fabro.types import WorkItem

_DESCRIPTION = "## Definition of Done\n\nReferences: ## Some heading\n\n- A claim.\n"


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-x",
        type="task",
        status="blocked",
        title="t",
        description=_DESCRIPTION,
        origin="freeform",
        gap_id=None,
        rank="m",
        assignee=None,
        depends_on=(),
        captured_at="2026-01-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _outcome(*, cause: str = "check 4 refused") -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-x",
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="d",
        fabro_run_id="run",
        fabro_failure_cause=cause,
        needs_human_kind=STAGE_FAILURE,
        needs_human_stages=("dod_gate@1",),
    )


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    items: list[WorkItem] | None = None,
    comments: tuple[str, ...] | None = (),
) -> list[str]:
    written: list[str] = []
    listed = [_item()] if items is None else items

    def store_config(*, repo: Path) -> Path:
        return repo

    def read_work_items(**_kwargs: object) -> Iterator[WorkItem]:
        return iter(listed)

    def item_comment_bodies(**_kwargs: object) -> tuple[str, ...] | None:
        return comments

    def read_spec(**_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(files=True, version=7)

    def append_comment(**kwargs: object) -> None:
        written.append(str(kwargs["body"]))

    monkeypatch.setattr(module, "store_config", store_config)
    monkeypatch.setattr(module, "read_work_items", read_work_items)
    monkeypatch.setattr(module, "item_comment_bodies", item_comment_bodies)
    monkeypatch.setattr(module, "read_current_specification", read_spec)
    monkeypatch.setattr(module, "append_work_item_comment", append_comment)
    return written


def test_a_check_4_refusal_places_and_journals_the_hold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    written = _wire(monkeypatch)
    journal = _Journal()
    outcome = _outcome()
    assert (
        module.attach_dod_gate_tier_hold(outcome=outcome, repo=tmp_path, journal=journal) is outcome
    )
    assert len(written) == 1
    assert "tier: spec-change" in written[0]
    assert journal.records[0]["heading"] == "## Some heading"


def test_an_ending_that_is_not_a_check_4_refusal_touches_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    written = _wire(monkeypatch)
    journal = _Journal()
    _ = module.attach_dod_gate_tier_hold(
        outcome=_outcome(cause="other"), repo=tmp_path, journal=journal
    )
    assert written == []
    assert journal.records == []


@pytest.mark.parametrize("arm", ["no-item", "no-comments", "no-spec"])
def test_each_unreadable_input_fails_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, arm: str
) -> None:
    written = _wire(
        monkeypatch,
        items=[] if arm == "no-item" else None,
        comments=None if arm == "no-comments" else (),
    )
    if arm == "no-spec":

        def unreadable(*, spec_root: Path) -> object:
            raise OSError(str(spec_root))

        monkeypatch.setattr(module, "read_current_specification", unreadable)
    journal = _Journal()
    _ = module.attach_dod_gate_tier_hold(outcome=_outcome(), repo=tmp_path, journal=journal)
    assert written == []
    assert journal.records == []


def test_a_standing_hold_is_not_journaled_again(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = _wire(monkeypatch)
    _ = module.attach_dod_gate_tier_hold(outcome=_outcome(), repo=tmp_path, journal=_Journal())
    written = _wire(monkeypatch, comments=(first[0],))
    journal = _Journal()
    _ = module.attach_dod_gate_tier_hold(outcome=_outcome(), repo=tmp_path, journal=journal)
    assert written == []
    assert journal.records == []
