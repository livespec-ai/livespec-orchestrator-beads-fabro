"""The proof-verify turn sends its required forge writes through the broker."""

from pathlib import Path

_PROMPT = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "prompts"
    / "proof-verify.md"
)


def test_proof_verify_posts_its_record_and_uploads_assets_through_the_broker() -> None:
    """The stage retains its two required writes without using its ambient `gh` client."""
    prompt = _PROMPT.read_text(encoding="utf-8")

    assert "publication_broker.py" in prompt
    assert "gh pr comment <number> --body-file <file>" not in prompt
    assert 'gh release upload "$LIVESPEC_PROOF_ASSETS_RELEASE_TAG"' not in prompt
