"""The repository preflight leaves a reusable Definition-of-Done receipt."""

from __future__ import annotations

from pathlib import Path

_SCRIPT = Path("dev-tooling/dod-preflight.sh")


def test_a_completed_preflight_appends_the_shared_verdict_record() -> None:
    """The launch-time verdict names its stage and all three reuse digests."""
    text = _SCRIPT.read_text(encoding="utf-8")

    assert "verdict_comment" in text
    assert 'stage="repository-preflight"' in text
    assert "spec_identity=SpecIdentity(" in text
    assert "append_work_item_comment" in text


def test_a_preflight_prints_pass_only_for_an_admitted_shared_verdict() -> None:
    """A held, including unverified, verdict reaches the launcher's refusal path."""
    text = _SCRIPT.read_text(encoding="utf-8")

    assert "outcome = judgement.outcome" in text
    assert 'raise SystemExit(0 if outcome == "admitted" else 1)' in text
    assert "0) echo PASS ;;" in text
