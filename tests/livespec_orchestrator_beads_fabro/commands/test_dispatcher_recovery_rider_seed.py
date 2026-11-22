"""A dispatch whose goal carries an earlier run's preserved work is never labelled fresh.

Measured 2026-11-22 on run 01M81FHNK5J3: the goal carried five riders appended
after the prior claim, among them `livespec-preserved-tree`,
`livespec-preserve-by-reference`, `livespec-needs-human-cause` and an operator
rider naming `refs/heads/preserve/candidate-01M80Z25N44T-mwh6o5`, while the
`recovery-route` row read route `fresh`. The agent restored the preserved ref
itself, so the run was seeded under a fresh label.

These bind the decision: which carried riders hand the agent preserved work, and
which route label a dispatch carrying them takes.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._store_comments import WorkItemComment
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_rider_seed import (
    preserved_work_riders,
    rider_route_label,
)

_CLAIM_AT = "2026-11-22T06:27:48Z"
_AFTER = "2026-11-22T07:00:00Z"
_BEFORE = "2026-11-22T05:00:00Z"
_PRESERVE_REF = "refs/heads/preserve/candidate-01M80Z25N44T-mwh6o5"


def _comment(*, text: str, created_at: str = _AFTER) -> WorkItemComment:
    return WorkItemComment(text=text, author="operator", created_at=created_at)


def test_each_carried_preserved_work_marker_comment_is_a_preserved_work_rider() -> None:
    comments = (
        _comment(text="livespec-preserve-by-reference\n\nrun: 01M80Z25N44T"),
        _comment(text="livespec-needs-human-cause\n\nrun: 01M80Z25N44T"),
        _comment(text="livespec-preserved-tree\n\nthe run has no work-in-progress ref"),
    )

    assert preserved_work_riders(comments=comments, claim_at=_CLAIM_AT) == (
        "livespec-preserve-by-reference",
        "livespec-needs-human-cause",
        "livespec-preserved-tree",
    )


def test_an_operator_rider_naming_a_preserve_or_needs_human_ref_is_a_preserved_work_rider() -> None:
    comments = (
        _comment(
            text=f"Two commits (red then green) on origin {_PRESERVE_REF}; seed from this ref."
        ),
        _comment(text="Restore needs-human/01M80Z25N44T before continuing."),
    )

    assert preserved_work_riders(comments=comments, claim_at=_CLAIM_AT) == (
        _PRESERVE_REF,
        "needs-human/01M80Z25N44T",
    )


def test_a_rider_left_out_of_the_goal_or_naming_no_preserved_work_is_not_one() -> None:
    comments = (
        _comment(text="livespec-preserved-tree\n\nan older run", created_at=_BEFORE),
        _comment(text=f"Older pointer: {_PRESERVE_REF}", created_at=_BEFORE),
        _comment(text="Please also cover the empty-journal case."),
    )

    assert preserved_work_riders(comments=comments, claim_at=_CLAIM_AT) == ()


def test_a_fresh_route_whose_goal_carries_preserved_work_riders_is_labelled_seeded() -> None:
    assert rider_route_label(route="fresh", riders=("livespec-preserved-tree",)) == "seeded"


def test_a_fresh_route_carrying_no_preserved_work_rider_stays_fresh() -> None:
    assert rider_route_label(route="fresh", riders=()) == "fresh"


def test_a_route_other_than_fresh_keeps_its_own_label() -> None:
    assert rider_route_label(route="resume", riders=("livespec-preserved-tree",)) == "resume"
    assert rider_route_label(route="seeded", riders=()) == "seeded"
