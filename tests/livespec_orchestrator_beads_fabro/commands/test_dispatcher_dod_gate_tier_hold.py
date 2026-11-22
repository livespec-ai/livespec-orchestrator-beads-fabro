"""An in-run check 4 refusal leaves the item blocked AND held, so release-spec-tier reaches it.

Binds `bd-ib-dfqrc7` (ruling a', legacy-coordinator-agent R301): the contract in
`SPECIFICATION/contracts.md` (the work-item state semantics) makes `release-spec-tier`
valid on a blocked item "only while the item carries a spec-change-tier hold". An
item the in-run `dod_gate` refused on check 4 rested blocked with a `tier: none`
record, so the valve refused it as `not-held` and no sanctioned primitive could
give it the record the check 4 internal-ruling exception reads. The hold is the
tier record itself, derived by `spec_change_hold` from the newest record, so the
fix is one record write at the step that blocks the item: `tier: spec-change`,
stage `dod-gate`, naming the item's References heading and quoting the refusal.

The negative arms sit beside the positive one because a writer that held every
blocked item would satisfy the positive arm exactly as a correct one does: a
refusal at another node, a dod_gate failure that is not check 4, an agent-request
ending, and an item with no References line each place nothing, and a hold that
already stands is not written twice.
"""

from __future__ import annotations

from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _drive_release_spec_tier_valve as valve
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    reference_line_headings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_gate_tier_hold import (
    dod_gate_check4_refusal,
    place_dod_gate_tier_hold,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import (
    AGENT_REQUEST,
    STAGE_FAILURE,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    SPEC_CHANGE_TIER,
    decide_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_hold import spec_change_hold
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_FILING,
    recorded_spec_change_tier,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.types import WorkItem
from livespec_runtime.spec_stated import SpecStatedVerdict

_HEADING = "## Provisional fleet launch scripts"
_DESCRIPTION = (
    "## Definition of Done\n\n"
    f"References: {_HEADING}\n\n"
    "- A launcher binds an item by priority band.\n"
)
_REFUSAL = (
    "bd-ib-eu3lea: Definition of Done assertion 2 is incoherent under check 4. The referenced "
    "'## Provisional fleet launch scripts' states only one FIFO ticket order."
)
_SPEC_VERSION = "398"


def _item(*, description: str = _DESCRIPTION, status: str = "blocked") -> WorkItem:
    base: dict[str, Any] = {
        "id": "bd-ib-eu3lea",
        "type": "task",
        "status": status,
        "title": "Launch ordering by priority band",
        "description": description,
        "origin": "freeform",
        "gap_id": None,
        "rank": "m",
        "assignee": None,
        "depends_on": (),
        "captured_at": "2026-01-01T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
    }
    return WorkItem(**base)  # pyright: ignore[reportArgumentType]


def _outcome(
    *,
    kind: str | None = STAGE_FAILURE,
    stages: tuple[str, ...] | None = ("dod_gate@1",),
    cause: str | None = _REFUSAL,
) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-eu3lea",
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="dod_gate refused",
        fabro_run_id="01M828XBDHX8X2SB3V6R6K37N9",
        fabro_failure_cause=cause,
        needs_human_kind=kind,
        needs_human_stages=stages,
    )


def _place(
    *, outcome: DispatchOutcome, item: WorkItem, comments: tuple[str, ...] = ()
) -> list[str]:
    bodies: list[str] = []
    _ = place_dod_gate_tier_hold(
        outcome=outcome,
        item=item,
        spec_version=_SPEC_VERSION,
        comments=comments,
        append=lambda *, body: bodies.append(body),
    )
    return bodies


def _none_record(*, item: WorkItem) -> str:
    verdict = SpecStatedVerdict(
        kind="stated", stated_by=(), generalization_target=None, rationale="internal"
    )
    return spec_change_tier_comment(
        item_id=item.id,
        stage=STAGE_FILING,
        decision=decide_spec_change_tier(item=item, classification="bug", verdict=verdict),
        spec_version=_SPEC_VERSION,
        digest="d",
    )


def test_a_check_4_refusal_at_dod_gate_places_a_spec_change_hold_naming_the_heading() -> None:
    item = _item()
    bodies = _place(outcome=_outcome(), item=item, comments=(_none_record(item=item),))

    assert len(bodies) == 1
    recorded = recorded_spec_change_tier(comments=(_none_record(item=item), *bodies))
    assert recorded is not None
    assert recorded.tier == SPEC_CHANGE_TIER
    assert recorded.generalization_target == reference_line_headings(text=item.description)[0]
    assert "dod-gate" in bodies[0]
    assert "incoherent under check 4" in bodies[0]
    hold = spec_change_hold(work_item_id=item.id, recorded=recorded, ratified_topics=())
    assert hold is not None


def test_the_refusal_reader_names_a_dod_gate_check_4_ending_and_nothing_else() -> None:
    assert dod_gate_check4_refusal(outcome=_outcome()) is not None
    assert dod_gate_check4_refusal(outcome=_outcome(stages=("fix@2",))) is None
    assert dod_gate_check4_refusal(outcome=_outcome(cause="assertion 3 needs a host proof")) is None
    assert dod_gate_check4_refusal(outcome=_outcome(kind=AGENT_REQUEST)) is None


@pytest.mark.parametrize(
    "outcome",
    [
        _outcome(stages=("fix@2",)),
        _outcome(cause="Definition of Done check 5: assertion 3 needs a host proof"),
        _outcome(kind=AGENT_REQUEST),
    ],
)
def test_no_hold_is_placed_for_an_ending_that_is_not_a_dod_gate_check_4_refusal(
    outcome: DispatchOutcome,
) -> None:
    assert _place(outcome=outcome, item=_item()) == []


def test_no_hold_is_placed_for_an_item_with_no_references_line() -> None:
    item = _item(description="## Definition of Done\n\n- A claim with no reference.\n")
    assert _place(outcome=_outcome(), item=item) == []


def test_a_hold_that_already_stands_is_not_written_twice() -> None:
    item = _item()
    first = _place(outcome=_outcome(), item=item)
    assert len(first) == 1
    assert _place(outcome=_outcome(), item=item, comments=(*first,)) == []


def test_release_spec_tier_reaches_the_placed_hold_and_still_refuses_an_item_with_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _item()
    none_comments = (_none_record(item=item),)
    held_comments = (*none_comments, *_place(outcome=_outcome(), item=item, comments=none_comments))

    monkeypatch.setattr(valve, "item_comment_bodies", lambda **_kwargs: none_comments)
    refused = valve._standing_refusal(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        config=None,  # pyright: ignore[reportArgumentType]
        item=item,
        aid="release-spec-tier",
    )
    assert refused is not None
    assert refused["domain_error"] == "not-held"

    monkeypatch.setattr(valve, "item_comment_bodies", lambda **_kwargs: held_comments)
    assert (
        valve._standing_refusal(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            config=None,  # pyright: ignore[reportArgumentType]
            item=item,
            aid="release-spec-tier",
        )
        is None
    )
