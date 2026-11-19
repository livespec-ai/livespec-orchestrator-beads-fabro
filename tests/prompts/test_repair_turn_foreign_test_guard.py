"""Repair turns preserve tests that the dispatched item does not own."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_IMPLEMENT_PROMPTS = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/prompts"
_GROOM_PROMPTS = _ROOT / ".fabro/workflows/groom-work-item/prompts"
_GROOM_GRAPH = _ROOT / ".fabro/workflows/groom-work-item/workflow.fabro"


def test_repair_prompts_preserve_a_foreign_test_and_name_its_owner() -> None:
    """Every repair prompt directs an unowned test failure to a human."""
    for prompt in (
        _IMPLEMENT_PROMPTS / "fix.md",
        _IMPLEMENT_PROMPTS / "review-fix.md",
        _GROOM_PROMPTS / "fix.md",
        _GROOM_PROMPTS / "review-fix.md",
    ):
        text = " ".join(prompt.read_text(encoding="utf-8").split())
        assert "do not edit that test" in text or "preserve it unchanged" in text
        assert "needs-human protocol" in text
        assert "work-item identifier" in text


def test_groom_repair_failures_route_to_needs_human() -> None:
    """A groom repair that cannot touch a foreign test cannot fall through as fixed."""
    graph = _GROOM_GRAPH.read_text(encoding="utf-8")

    assert 'fix -> needs_human [label="Blocked", condition="outcome=failed"' in graph
    assert 'review_fix -> needs_human [label="Blocked", condition="outcome=failed"' in graph
