"""Focused coverage for needs-human receipt formatting."""

from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_capture import (
    NeedsHumanCapture,
    needs_human_receipt_lines,
)


def test_needs_human_receipt_lines_report_a_measured_diff() -> None:
    capture = NeedsHumanCapture(
        ref="refs/heads/needs-human/run-1",
        commit="abc123",
        files=2,
        insertions=153,
        deletions=12,
    )

    assert needs_human_receipt_lines(capture=capture) == (
        "the run has no work-in-progress ref",
        "needs-human ref: refs/heads/needs-human/run-1",
        "commit id: abc123",
        "needs-human diff: 2 files changed, 153 insertions, 12 deletions",
    )
    assert len(needs_human_receipt_lines(capture=capture)) == 4


def test_needs_human_receipt_lines_report_an_unmeasurable_diff() -> None:
    capture = NeedsHumanCapture(
        ref="refs/heads/needs-human/run-1",
        commit="abc123",
        files=None,
        insertions=None,
        deletions=None,
    )

    assert needs_human_receipt_lines(capture=capture) == (
        "the run has no work-in-progress ref",
        "needs-human ref: refs/heads/needs-human/run-1",
        "commit id: abc123",
        "needs-human diff could not be determined",
    )
