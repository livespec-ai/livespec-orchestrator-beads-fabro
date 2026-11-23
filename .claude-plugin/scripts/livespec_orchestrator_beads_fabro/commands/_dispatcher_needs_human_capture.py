"""Deliberately incomplete needs-human receipt seam for the Red test."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class NeedsHumanCapture:
    """The terminal needs-human ref and its diff against the default branch."""

    ref: str
    commit: str
    files: int | None
    insertions: int | None
    deletions: int | None


def needs_human_receipt_lines(*, capture: NeedsHumanCapture) -> tuple[str, ...]:
    """Return the wrong sentinel until the Green implementation is supplied."""
    _ = capture
    return ()
