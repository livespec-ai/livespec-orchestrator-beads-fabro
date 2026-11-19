"""Unit coverage for the materialized implement gate-preview helper."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_gate_preview_program import (
    gate_preview_program_source,
)


def test_preview_worktree_is_outside_tmp_so_coverage_measures_its_changed_modules() -> None:
    """The disposable checkout uses the home worktree root, not coverage's omitted `/tmp`."""
    source = gate_preview_program_source()

    assert 'preview_parent = Path.home() / ".worktrees" / root.name' in source
    assert 'tempfile.mkdtemp(prefix="gate-preview-", dir=preview_parent)' in source
