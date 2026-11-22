"""A `release-spec-tier` press records the pressed heading where the dod_gate reads it.

The dod_gate's check 4 internal-ruling exception applies only when the item's newest
`livespec-spec-change-tier` record reads `tier: none` AND names the referenced heading
as its `generalization-target`. The attested decision a release writes carried a
`stated` verdict with NO generalization target, so the record read
`generalization-target: (none)` and the in-run gate refused a released item for want of
the very record the release was meant to supply.

EVERY CASE READS THE RECORD THROUGH ITS OWN PARSER, because the defect lived in the
disagreement between what the writer rendered and what the reader looks for, and a
value read off the decision object alone cannot show that.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._spec_change_tier import attested_decision
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_RELEASE,
    recorded_spec_change_tier,
    spec_change_tier_comment,
)

_PRESSED = "## Provisional fleet launch scripts"
_OTHER = "## Scenario 206 — The spec-change tier is decided by the spec-stated judgement"


def _recorded_after_press(*, heading: str) -> tuple[str, str, str | None]:
    """The tier, verdict kind and generalization target a press against `heading` leaves."""
    body = spec_change_tier_comment(
        item_id="bd-ib-released",
        stage=STAGE_RELEASE,
        decision=attested_decision(heading=heading),
        spec_version="389",
        digest="c513de0c",
    )
    recorded = recorded_spec_change_tier(comments=(body,))
    assert recorded is not None
    return recorded.tier, recorded.verdict_kind, recorded.generalization_target


def test_a_press_records_a_none_tier_naming_the_pressed_heading_as_its_target() -> None:
    tier, kind, target = _recorded_after_press(heading=_PRESSED)

    assert (tier, kind) == ("none", "stated")
    assert target == _PRESSED


def test_the_attested_decision_carries_the_pressed_heading_as_its_generalization_target() -> None:
    verdict = attested_decision(heading=_PRESSED).verdict

    assert verdict is not None
    assert verdict.generalization_target == _PRESSED
    assert verdict.stated_by == (_PRESSED,)


def test_a_press_against_another_heading_does_not_name_a_heading_it_was_not_pressed_against() -> (
    None
):
    _, _, target = _recorded_after_press(heading=_OTHER)

    assert target == _OTHER
    assert target != _PRESSED
