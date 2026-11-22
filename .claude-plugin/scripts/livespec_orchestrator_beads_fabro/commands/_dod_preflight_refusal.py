"""What the repository preflight prints and exits with once the judge has answered.

`dev-tooling/dod-preflight.sh` used to print the judge's reply and exit 1 on any
non-admitted verdict. Two things followed. A check 4 refusal named whatever the
judge chose to quote, so an operator could be told that "the assertions are
incoherent" with neither the offending assertion nor the heading they were graded
against, while the Definition-of-Done node's own failure reason names both. And
nothing in the script itself said that a finding from ANY check refuses: that was
true only because the script never looked at what failed.

This module is the one pure seam the script ends through. A check 4 finding that
leaves out the verbatim referenced heading, or quotes none of the item's
assertions, is followed by exactly the missing verbatim lines; a finding from any
other check (the proof-mode check included) is printed untouched and refuses all
the same. It adds no grading rule of its own: it never decides WHETHER an item is
coherent, only that a refusal says what it refused (`bd-ib-xqj7ov`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    DefinitionOfDone,
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    DodJudgement,
)

__all__: list[str] = ["PreflightRefusal", "preflight_refusal"]

# A finding is a check 4 finding when it says so by number or by its subject,
# coherence. `incoherent` and `coherence` both contain the stem.
_CHECK_FOUR = re.compile(r"check\s*4|coheren", re.IGNORECASE)
_HEADING_LINE = "check 4 refusal: referenced heading: {heading}"
_ASSERTION_LINE = "check 4 refusal: offending assertion: {assertion}"


@dataclass(frozen=True, kw_only=True)
class PreflightRefusal:
    """The exit code the preflight ends with and the extra lines it prints.

    `lines` is the whole refusal text in order: each finding the judge returned,
    each followed by the verbatim lines it was missing. It is empty for an
    admitted verdict.
    """

    exit_code: int
    lines: tuple[str, ...]


def preflight_refusal(*, description: str, judgement: DodJudgement) -> PreflightRefusal:
    """The preflight's exit code and refusal lines for one judgement of one item."""
    if judgement.outcome == JUDGEMENT_ADMITTED:
        return PreflightRefusal(exit_code=0, lines=())
    section = definition_of_done(description=description)
    lines: list[str] = []
    for finding in judgement.findings:
        lines.append(finding)
        if _CHECK_FOUR.search(finding) is not None:
            lines.extend(_missing_subject_lines(finding=finding, section=section))
    return PreflightRefusal(exit_code=1, lines=tuple(lines))


def _missing_subject_lines(*, finding: str, section: DefinitionOfDone) -> list[str]:
    missing = [
        _HEADING_LINE.format(heading=heading)
        for heading in section.references
        if heading not in finding
    ]
    if not any(one.text in finding for one in section.assertions):
        missing.extend(_ASSERTION_LINE.format(assertion=one.text) for one in section.assertions)
    return missing
