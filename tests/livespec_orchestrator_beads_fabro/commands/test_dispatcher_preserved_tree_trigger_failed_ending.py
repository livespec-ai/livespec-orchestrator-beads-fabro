"""Any failed ending that nothing else carries gets its tree preserved (bd-ib-nckst7.1).

Measured on run 01M7KR00K1FP: it ended failed at commit_green, not on an engine
checkpoint, left no needs-human ref, and its committed work had no route off the
sandbox. The trigger therefore also preserves a plain failed ending whose
terminal event carries no patch, unless a needs-human ref on origin already
carries the tree.
"""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_trigger import (
    preservation_trigger,
)

_GREEN_FAILURE = "commit_green failed: the Red lap could not be committed"
_PATCH = "diff --git a/a.py b/a.py\n+changed\n"


def _events(*, patch: str | None) -> tuple[dict[str, Any], ...]:
    failed: dict[str, Any] = {"type": "run.failed", "reason": _GREEN_FAILURE}
    if patch is not None:
        failed["patch"] = patch
    return ({"type": "stage.failed", "node": "commit_green"}, failed)


def test_a_run_failed_at_commit_green_with_no_needs_human_ref_preserves_its_tree() -> None:
    decided = preservation_trigger(
        failure_text=_GREEN_FAILURE,
        records=_events(patch=None),
        failed_ending=True,
        needs_human_ref_on_origin=False,
    )
    assert decided.preserves is True
    assert decided.terminal_patch_bytes is None


def test_a_failed_run_whose_needs_human_ref_is_on_origin_is_not_published_again() -> None:
    decided = preservation_trigger(
        failure_text=_GREEN_FAILURE,
        records=_events(patch=None),
        failed_ending=True,
        needs_human_ref_on_origin=True,
    )
    assert decided.preserves is False


def test_a_failed_run_whose_terminal_event_carries_a_patch_is_not_published() -> None:
    decided = preservation_trigger(
        failure_text=_GREEN_FAILURE,
        records=_events(patch=_PATCH),
        failed_ending=True,
        needs_human_ref_on_origin=False,
    )
    assert decided.preserves is False
    assert decided.terminal_patch_bytes == len(_PATCH.encode("utf-8"))


def test_an_unobservable_ref_listing_or_event_stream_still_attempts_the_publication() -> None:
    unknown_ref = preservation_trigger(
        failure_text=_GREEN_FAILURE,
        records=_events(patch=None),
        failed_ending=True,
        needs_human_ref_on_origin=None,
    )
    unreadable = preservation_trigger(
        failure_text=_GREEN_FAILURE,
        records=None,
        failed_ending=True,
        needs_human_ref_on_origin=False,
    )
    assert unknown_ref.preserves is True
    assert unreadable.preserves is True


def test_a_run_that_did_not_fail_preserves_no_tree_whatever_the_ref_listing_says() -> None:
    decided = preservation_trigger(
        failure_text="LIVESPEC_NEEDS_HUMAN: run terminated",
        records=_events(patch=None),
        failed_ending=False,
        needs_human_ref_on_origin=False,
    )
    assert decided.preserves is False
