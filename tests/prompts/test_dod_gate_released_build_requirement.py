"""The dod_gate prompt's check 5 makes the finding name the released-build requirement.

Scenario 272's second scenario: an item that changes a stage prompt file under `.claude-plugin/.fabro/`
and carries a factory-captured assertion naming that prompt's behaviour ends through the structured
needs-human ending, and the finding names the released-build requirement. Listing the class among the
proof surfaces no sandbox capability provides is not enough; the prompt has to tell the gate what the
finding must say.
"""

from __future__ import annotations

import re
from pathlib import Path

_PROMPT = (
    Path(__file__).parents[2]
    / ".claude-plugin/.fabro/workflows/implement-work-item/prompts/dod-gate.md"
)
_CHECK_FIVE = re.compile(
    r"^5\. \*\*Every `factory_captured` assertion.*?^6\. \*\*", re.DOTALL | re.MULTILINE
)


def _check_five_paragraphs() -> list[str]:
    section = _CHECK_FIVE.search(_PROMPT.read_text(encoding="utf-8"))
    assert section is not None
    return [" ".join(block.split()) for block in re.split(r"\n\s*\n", section.group(0))]


def test_check_five_has_the_finding_name_the_released_build_requirement() -> None:
    naming = [p for p in _check_five_paragraphs() if "the released-build requirement" in p]

    assert len(naming) == 1
    paragraph = naming[0]
    assert "finding" in paragraph
    assert "prompt or workflow file the item itself changes" in paragraph
