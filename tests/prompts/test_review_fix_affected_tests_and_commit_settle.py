"""Review-fix avoids duplicate aggregate checks and fences its live commit.

Scenario 255 assigns the review-fix turn the affected-tests gate and reserves
the one full aggregate for the following janitor visit.  The engine checkpoints
after the turn, so the prompt must wait a live commit runner to its own verdict
instead of handing it to the later settle node.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_GRAPH = _WORKFLOW / "workflow.fabro"
_PROMPTS = _WORKFLOW / "prompts"

_NODE_BLOCK = re.compile(
    r"^[ \t]*(?P<name>\w+)[ \t]*\[$(?P<body>.*?)^[ \t]*\]$",
    re.DOTALL | re.MULTILINE,
)
_PROMPT_ATTR = re.compile(r'prompt="@prompts/(?P<file>[\w.-]+\.md)"')

_AFFECTED_TESTS_RULE = (
    "Run only the tests your change touches; the commit hook runs the affected-tests gate."
)
_JANITOR_AGGREGATE_RULE = "Leave the one full check aggregate to the following janitor visit."
_LIVE_COMMIT_FENCE = (
    "Repeat that bounded wait until the runner reports a terminal",
    "Do not end this turn while a runner commit is still `running`",
    "not a handoff for a live runner commit",
)


def _review_fix_prompt() -> str:
    """Read the one prompt the committed review-fix graph node dispatches."""
    files: list[str] = []
    for block in _NODE_BLOCK.finditer(_GRAPH.read_text(encoding="utf-8")):
        if block.group("name") != "review_fix":
            continue
        prompt = _PROMPT_ATTR.search(block.group("body"))
        assert prompt is not None, "the review-fix node declares no prompt"
        files.append(prompt.group("file"))
    assert files == ["review-fix.md"], f"review-fix names unexpected prompts: {files}"
    return (_PROMPTS / files[0]).read_text(encoding="utf-8")


def test_review_fix_runs_only_affected_tests_and_leaves_the_aggregate_to_janitor() -> None:
    """The turn does not duplicate the one full aggregate owned by janitor."""
    prompt = _review_fix_prompt()

    assert _AFFECTED_TESTS_RULE in prompt
    assert _JANITOR_AGGREGATE_RULE in prompt
    assert "Re-run the repository's check suite" not in prompt


def test_review_fix_waits_a_live_commit_before_the_engine_checkpoint() -> None:
    """The later settle node only sees a terminal runner verdict."""
    prompt = _review_fix_prompt()

    for phrase in _LIVE_COMMIT_FENCE:
        assert phrase in prompt
