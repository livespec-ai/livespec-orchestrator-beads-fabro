"""The repository preflight's refusal names what it refuses, and refuses on every check.

Two defects, one seam. `dev-tooling/dod-preflight.sh` printed the judge's reply
verbatim and exited 1 on any failed verdict, so what a refusal NAMED was whatever
the judge happened to quote, and an operator reading a check 4 refusal could be
told only that "the assertions are incoherent" with neither the offending
assertion nor the heading it was graded against. The Definition-of-Done node's
own failure reason names both (bd-ib-xqj7ov, split from bd-ib-a4gjc5).

`preflight_refusal` is the pure seam the script now ends through: it takes the
item's description and the parsed judgement and returns the exit code and the
lines to print. A check 4 finding that omits the verbatim referenced heading, or
omits every assertion, is supplemented with exactly those; a finding from ANY
other check (proof mode included) refuses with its text untouched.

THE DIGEST SHAPE is overseer-thrt4g's at dispatch: a `References: ## Scenarios`
line that does not govern the claims, and `factory_captured` bullets whose proof
surface is operator-host state. The launch-time preflight returned PASS for it
and the node refused it twice, once on check 4 and once on check 5
(bd-ib-xqj7ov body).
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    JUDGEMENT_HELD,
    JUDGEMENT_UNAVAILABLE,
    DodJudgement,
    parse_judgement_reply,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_prompt import (
    judgement_prompt,
    judgement_rubric,
)
from livespec_orchestrator_beads_fabro.commands._dod_preflight_refusal import (
    preflight_refusal,
)

_HEADING = "## Scenarios"
_FIRST = (
    "Descendant pids 100, 200 and 300 are live processes on the host and a lookup never collides."
)
_SECOND = "The HERDR_* variables of an agent session are read from the host environment."
_DESCRIPTION = f"""Preamble prose.

## Definition of Done

References: {_HEADING}

- {_FIRST}
- {_SECOND}
"""
_PLUGIN_ROOT = Path(__file__).resolve().parents[3] / ".claude-plugin"


def _held(*findings: str) -> DodJudgement:
    return DodJudgement(outcome=JUDGEMENT_HELD, findings=tuple(findings))


def test_a_passed_verdict_exits_zero_and_prints_nothing_of_its_own() -> None:
    refusal = preflight_refusal(
        description=_DESCRIPTION, judgement=DodJudgement(outcome=JUDGEMENT_ADMITTED)
    )

    assert (refusal.exit_code, refusal.lines) == (0, ())


def test_a_check_four_refusal_that_names_neither_is_supplemented_with_both_verbatim() -> None:
    finding = (
        "overseer-thrt4g: check 4 coherence: the assertions are incoherent against the reference."
    )

    refusal = preflight_refusal(description=_DESCRIPTION, judgement=_held(finding))

    assert refusal.exit_code == 1
    assert refusal.lines[0] == finding
    assert f"check 4 refusal: referenced heading: {_HEADING}" in refusal.lines
    assert f"check 4 refusal: offending assertion: {_FIRST}" in refusal.lines
    assert f"check 4 refusal: offending assertion: {_SECOND}" in refusal.lines


def test_a_check_four_refusal_that_quotes_both_is_not_padded() -> None:
    finding = (
        f'overseer-thrt4g: check 4 coherence: "{_SECOND}" is incoherent against `{_HEADING}`;'
        " add the governing heading."
    )

    refusal = preflight_refusal(description=_DESCRIPTION, judgement=_held(finding))

    assert (refusal.exit_code, refusal.lines) == (1, (finding,))


def test_a_check_four_refusal_that_quotes_only_the_assertion_gains_only_the_heading() -> None:
    finding = f'overseer-thrt4g: check 4 coherence: "{_FIRST}" is incoherent with its reference.'

    refusal = preflight_refusal(description=_DESCRIPTION, judgement=_held(finding))

    assert refusal.lines == (finding, f"check 4 refusal: referenced heading: {_HEADING}")


def test_a_proof_mode_refusal_alone_refuses_with_its_text_untouched() -> None:
    finding = (
        "overseer-thrt4g: check 5 proof mode: each factory_captured bullet's proof surface is"
        " operator-host state no sandbox capability provides; declare it Host-captured."
    )

    refusal = preflight_refusal(description=_DESCRIPTION, judgement=_held(finding))

    assert (refusal.exit_code, refusal.lines) == (1, (finding,))


def test_a_reply_failing_both_checks_is_read_back_as_both_findings_in_order() -> None:
    reply = (
        'noise\n{"outcome": "failed", "failure_reason": "check 4 coherence: incoherent against'
        ' the reference\\ncheck 5 proof mode: operator-host state"}'
    )

    refusal = preflight_refusal(
        description=_DESCRIPTION, judgement=parse_judgement_reply(reply=reply)
    )

    assert refusal.exit_code == 1
    findings = [line for line in refusal.lines if not line.startswith("check 4 refusal: ")]
    assert findings == [
        "check 4 coherence: incoherent against the reference",
        "check 5 proof mode: operator-host state",
    ]
    assert f"check 4 refusal: referenced heading: {_HEADING}" in refusal.lines


def test_an_unavailable_judgement_still_refuses_as_before() -> None:
    refusal = preflight_refusal(
        description=_DESCRIPTION, judgement=DodJudgement(outcome=JUDGEMENT_UNAVAILABLE)
    )

    assert refusal.exit_code == 1


def test_the_preflight_prompt_carries_every_numbered_check_of_the_rubric_bytes() -> None:
    rubric = judgement_rubric(payload_root=_PLUGIN_ROOT)
    assert rubric is not None
    checks = rubric.split("## What to check", 1)[1].split("## What you must not do", 1)[0]
    numbered = re.findall(r"^\d\. \*\*[^*]+\*\*", checks, re.MULTILINE)

    prompt = judgement_prompt(gate_prompt=rubric, subject="subject text")

    assert len(numbered) == 6
    assert [line for line in numbered if line not in prompt] == []
