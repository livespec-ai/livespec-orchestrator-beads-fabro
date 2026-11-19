"""A recapture declares the head that is current when its record is posted.

bd-ib-chonmf: a capture record can be composed from a publish head observed
before ``review_fix`` and the following ``publish_draft`` have moved the pull
request.  A later capture then posts the old declaration, so review correctly
finds a different tree and sends the run through the same recapture lap again.

The proof-capture agent writes this declaration from prompt prose; no Python
publisher re-resolves it.  This test therefore binds the final forge read in
the dispatched prompt, scoped to Step 5 rather than to another mention of a
pull-request head.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DIR = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_PROMPT = _WORKFLOW_DIR / "prompts" / "proof-capture.md"

_STEP_FIVE = re.compile(r"^## Step 5 — publish the record$.*?(?=^## |\Z)", re.DOTALL | re.MULTILINE)

# The final read has to happen at the posting boundary.  Reading ``headRefOid``
# earlier in Step 5 is the stale observation that caused the recapture loop.
_FINAL_HEAD_RULE = (
    "including a recapture after `review_fix`",
    "Immediately before `gh pr comment`, read `headRefOid` from the forge again",
    "If that fresh sha differs from the provisional one, replace the one `Publish-branch head:` declaration",
    're-run `git fetch --quiet origin "refs/pull/<number>/head"` and `git diff --quiet FETCH_HEAD HEAD`',
)


def _step_five() -> str:
    """Return Step 5 with hard-wrap whitespace normalised for its prose rules."""
    sections = _STEP_FIVE.findall(_PROMPT.read_text(encoding="utf-8"))
    assert (
        len(sections) == 1
    ), f"proof-capture prompt carries {len(sections)} Step 5 sections; expected one"
    return " ".join(sections[0].split())


def test_recapture_redeclares_the_forge_head_immediately_before_posting() -> None:
    """A review-fix recapture cannot repost the head observed before republishing."""
    step_five = _step_five()

    for rule in _FINAL_HEAD_RULE:
        assert rule in step_five, (
            f"Step 5 omits {rule!r}, so a recapture can post a proof record naming "
            "the old publish head after review_fix has republished the reviewed tree"
        )
