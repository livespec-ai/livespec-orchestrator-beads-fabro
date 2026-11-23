"""Acceptance coverage for the release-roll canary coverage record.

The roll workflow is the enforcement boundary: it is the only path that can
move ``release``.  This test deliberately reads that workflow rather than a
parallel helper, so a tag cannot bypass split-pair detection by reaching the
push step through an unguarded call site.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ROLL_WORKFLOW = _REPO_ROOT / ".github/workflows/fast-forward-release-branch.yml"


def test_roll_workflow_requires_a_coverage_record_for_a_revert_reland_split_pair() -> None:
    """A tag ending between a revert and its reland cannot roll unchecked."""
    workflow = _ROLL_WORKFLOW.read_text(encoding="utf-8")

    assert "canary-coverage.json" in workflow
    assert "This reverts commit" in workflow
    assert "Relands:" in workflow
    assert "proof_capture" in workflow
