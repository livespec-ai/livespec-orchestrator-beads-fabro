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

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DIR = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_PROMPT = _WORKFLOW_DIR / "prompts" / "proof-capture.md"

_STEP_FIVE = re.compile(r"^## Step 5 — publish the record$.*?(?=^## |\Z)", re.DOTALL | re.MULTILINE)

# The final read has to happen at the posting boundary.  Reading ``headRefOid``
# earlier in Step 5 is the stale observation that caused the recapture loop.
_FINAL_HEAD_RULE = (
    "including a recapture after `review_fix`",
    "Immediately before the broker `comment` request, read `headRefOid` from the forge again",
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


# ---- Static guard: no agent-stage prompt names a direct forge write ----
# No agent-stage prompt names a direct forge write (bd-ib-w64kr3 plan, 0.346.3 canary lesson).
#
# An agent stage holds no publication-capable credential (SPECIFICATION/contracts.md, "Publication is
# mechanically confined to the scripted publication stages"). The ONLY forge writes an agent stage may
# make are a new comment on the run's pull request and a proof-asset upload, and both go through the
# publication broker. A prompt that still tells the agent to run `gh pr comment`, `gh release upload`,
# a write-verb `gh api` call or `git push` sends that stage into a 403 the moment its direct token is
# withdrawn: the 0.346.3 canary's `proof_capture` failed that way (run 01M84JVE3YV9) because only the
# `proof_verify` and `review` prompts had been re-routed. This test is the mechanical guard: it reads
# EVERY stage prompt of every workflow and fails on a direct write. A line that forbids the command
# ("never run `git push`") is not a use of it and is skipped.

_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS = sorted(
    path
    for base in (_ROOT / ".claude-plugin" / ".fabro" / "workflows", _ROOT / ".fabro" / "workflows")
    if base.is_dir()
    for path in base.glob("*/prompts/*.md")
)
_WRITES = (
    re.compile(r"\bgh\s+pr\s+(comment|edit|create|merge|review|ready|close|reopen)\b"),
    re.compile(r"\bgh\s+release\s+(upload|create|edit|delete)\b"),
    re.compile(r"\bgh\s+issue\s+(comment|create|edit|close|reopen|delete)\b"),
    re.compile(r"\bgh\s+label\b"),
    re.compile(r"\bgh\s+api\b.*(-X|--method)[ =]*(POST|PATCH|PUT|DELETE)\b", re.IGNORECASE),
    re.compile(r"\bgit\s+push\b"),
)
_FORBIDS = re.compile(r"\b(never|not|no|refus\w*|forbid\w*|must not)\b", re.IGNORECASE)
_BROKER_STAGES = {
    "proof-capture.md": "proof_capture",
    "proof-verify.md": "proof_verify",
    "review.md": "review",
}


def _direct_writes(*, path: Path) -> list[str]:
    found: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if _FORBIDS.search(line):
            continue
        if any(pattern.search(line) for pattern in _WRITES):
            found.append(f"{path.relative_to(_ROOT)}:{number}: {line.strip()}")
    return found


def test_the_scan_finds_the_workflow_prompts() -> None:
    names = {path.name for path in _PROMPTS}

    assert set(_BROKER_STAGES) <= names
    assert len(_PROMPTS) >= 8


@pytest.mark.parametrize("prompt", _PROMPTS, ids=lambda path: str(path.relative_to(_ROOT)))
def test_a_stage_prompt_names_no_direct_forge_write(prompt: Path) -> None:
    assert _direct_writes(path=prompt) == []


@pytest.mark.parametrize("name", sorted(_BROKER_STAGES))
def test_a_stage_that_writes_to_the_forge_routes_it_through_the_broker(name: str) -> None:
    prompt = next(path for path in _PROMPTS if path.name == name)
    text = prompt.read_text(encoding="utf-8")

    assert "publication_broker.py" in text
    assert f'"stage": "{_BROKER_STAGES[name]}"' in text or "<stage>" in text


def test_the_scan_would_catch_a_direct_write(tmp_path: Path) -> None:
    sample = tmp_path / "sample.md"
    lines = [
        "Never run `git push`.",
        "    gh pr comment 5 --body-file x",
        "    gh api -X PATCH repos/o/r/pulls/5",
    ]
    _ = sample.write_text("\n".join(lines) + "\n", encoding="utf-8")

    caught = [line for line in lines if not _FORBIDS.search(line)]
    assert len([line for line in caught if any(p.search(line) for p in _WRITES)]) == 2
