"""Repair turns wait for their runner commits before the engine checkpoint.

The engine checkpoints immediately after an ACP node.  The repair prompts must
therefore keep a runner commit in the turn until it reaches its own verdict;
the settle nodes only process terminal outcomes.  The prompts are derived from
their committed graph nodes, so a later prompt rewire cannot leave one stage
untested.
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
_STAGES = {"fix": "fix_commit_settle", "review_fix": "review_fix_commit_settle"}


def _prompt(*, stage: str) -> str:
    """The prompt bytes the committed graph dispatches for one repair stage."""
    matches = [
        _PROMPT_ATTR.search(block.group("body"))
        for block in _NODE_BLOCK.finditer(_GRAPH.read_text(encoding="utf-8"))
        if block.group("name") == stage
    ]
    assert len(matches) == 1 and matches[0] is not None, f"{stage} has no unique prompt"
    return (_PROMPTS / matches[0].group("file")).read_text(encoding="utf-8")


def test_repair_prompts_wait_for_a_terminal_commit_before_the_checkpoint() -> None:
    """A hook outlasting one tool call cannot escape either repair turn."""
    for stage, settle in _STAGES.items():
        prompt = _prompt(stage=stage)

        assert "Repeat that bounded wait until the runner reports a terminal" in prompt
        assert "Do not end this turn while a runner commit is still `running`" in prompt
        assert f"`{settle}`" in prompt
        assert "not a handoff for a live runner commit" in prompt
