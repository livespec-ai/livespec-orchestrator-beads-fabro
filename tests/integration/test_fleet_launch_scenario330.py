"""Integration coverage for Scenario 330's admission-time hold re-read."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_HARNESS = _REPOSITORY_ROOT / "fleet-launch" / "test" / "run-tests.sh"
_COVERAGE = _REPOSITORY_ROOT / "tests" / "heading-coverage.json"
_HEADING = (
    "## Scenario 330 — A hold set while a launched drive waits before admission stops the drive"
)
_NODE_ID = (
    "tests.integration.test_fleet_launch_scenario330"
    ".test_scenario330_re_reads_holds_until_admission"
)


def test_scenario330_re_reads_holds_until_admission() -> None:
    """The real harness proves every admission-time hold outcome against stub boards."""
    completed = subprocess.run(
        ["bash", str(_HARNESS), "scenario330"],
        cwd=_REPOSITORY_ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=180,
    )
    output = completed.stdout + completed.stderr

    assert completed.returncode == 0, output
    for assertion in (
        "a hold set before admission stops the drive, keeps ticket 100 and logs the hold text",
        "a hold set after the item reads active leaves the drive alone and the run lists",
        "with no hold file the drive proceeds from launch to the run listing",
        "a stopped drive that admitted its item (admitted) exits stopped-after-admission, re-takes no ticket and comments once",
    ):
        assert assertion in output, output

    coverage = json.loads(_COVERAGE.read_text(encoding="utf-8"))
    [entry] = [entry for entry in coverage if entry["heading"] == _HEADING]
    assert entry["test"] == _NODE_ID
