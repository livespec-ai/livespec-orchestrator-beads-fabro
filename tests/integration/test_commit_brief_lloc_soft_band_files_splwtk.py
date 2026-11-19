"""A commit-refusal brief names each LLOC soft-band file the failed target reported (bd-ib-splwtk).

`SPECIFICATION/contracts.md` section "ACP node timeouts" -> "Every commit-refusal re-entry
brief names the failing files from the full recorded output". Measured on livespec-overseer
run 01M7S13EJKJ5 (overseer-nerus6): three settled fix commit runs failed on
`check-no-lloc-soft-warnings` and each brief read `failing files: none reported in the
recorded output`, because the runner's failing-file reader knew only the hard-ceiling `file
LLOC exceeds` event of `check-file-lloc`. The soft-band target logs two failing events at
level error with `failing=true`, and one accepted event with `failing=false` that must not
be named.

The landed runner's own `brief_text` is run on a recorded output shaped like the aggregate's.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.integration.test_commit_run_brief_failed_target_output_2bombh import _brief

_NO_MARKER = {
    "file": "overseer/_no_marker.py",
    "lloc": 209,
    "soft_ceiling": 200,
    "hard_ceiling": 250,
    "failing": True,
    "event": "file in 201-250 LLOC soft band with no owning work-item marker",
    "level": "error",
}
_DEAD_OWNER = {
    "file": "overseer/_dead_owner.py",
    "lloc": 240,
    "work_item": "overseer-1",
    "resolved_status": "closed",
    "failing": True,
    "event": (
        "file in 201-250 LLOC soft band whose owning work-item is closed or nonexistent; "
        "the owed REFACTOR has no live owner"
    ),
    "level": "error",
}
_ACCEPTED = {
    "file": "overseer/_accepted.py",
    "lloc": 230,
    "work_item": "overseer-2",
    "failing": False,
    "event": (
        "file in 201-250 LLOC soft band accepted: REFACTOR IS OWED by the named work-item; "
        "carrying this debt is permitted, not blessed"
    ),
    "level": "warning",
}
_TIMING_ROWS = tuple(f"  0.{index % 10}s  check-passing-{index}" for index in range(95))


def _output(*, events: tuple[dict[str, object], ...]) -> str:
    lines = [
        "::: just check-no-lloc-soft-warnings [FAILED, wall: 1.0s]",
        *(json.dumps(event) for event in events),
        "",
        "--- parallel check summary ---",
        "passed: 1, failed: 1, skipped: 0",
        "",
        "per-target wall times (longest first):",
        *_TIMING_ROWS,
        "",
        "Failed targets (1):",
        "  - check-no-lloc-soft-warnings",
    ]
    return "\n".join(lines) + "\n"


def _failing_section(*, tmp_path: Path, events: tuple[dict[str, object], ...]) -> str:
    """The brief's failing-files section, which ends at its first blank line."""
    brief = _brief(tmp_path=tmp_path, recorded=_output(events=events))
    return brief.split("\n\n")[0]


def test_a_soft_band_file_with_no_owner_marker_is_named_with_its_lloc(tmp_path: Path) -> None:
    section = _failing_section(tmp_path=tmp_path, events=(_NO_MARKER,))

    assert "- overseer/_no_marker.py: LLOC 209 in the soft band, no owning work-item marker" in (
        section
    )


def test_a_soft_band_file_whose_owner_is_closed_is_named_with_its_lloc(tmp_path: Path) -> None:
    section = _failing_section(tmp_path=tmp_path, events=(_DEAD_OWNER,))

    assert (
        "- overseer/_dead_owner.py: LLOC 240 in the soft band, owning work-item closed or"
        " nonexistent" in section
    )


def test_the_two_failure_kinds_are_told_apart_in_one_brief(tmp_path: Path) -> None:
    section = _failing_section(tmp_path=tmp_path, events=(_NO_MARKER, _DEAD_OWNER))

    assert "failing files (2):" in section
    assert "no owning work-item marker" in section
    assert "owning work-item closed or nonexistent" in section


def test_an_accepted_soft_band_file_is_not_named_as_failing(tmp_path: Path) -> None:
    section = _failing_section(tmp_path=tmp_path, events=(_NO_MARKER, _ACCEPTED))

    assert "overseer/_accepted.py" not in section
    assert "failing files (1):" in section
