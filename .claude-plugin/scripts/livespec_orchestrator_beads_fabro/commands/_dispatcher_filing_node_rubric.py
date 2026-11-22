"""The dod_gate node rubric's findings, rendered where the item is filed.

Scenario 140 has the filing display show "the finding" before the filing is
confirmed, and Scenario 239 makes every taking of the Definition-of-Done
judgement grade by the dod_gate node's own rubric bytes. The display printed the
host wall's mechanical and advisory findings and never the node's per-assertion
check 4 coherence finding or its check 5 proof-surface finding, so a weak item
was filed with `findings: none` and refused only at dispatch.

WHY THIS IS ITS OWN MODULE. `filing_display` already carries the parse, the modes,
the capabilities and the wall's findings; the node judgement is a second model
call with its own three outcomes, and keeping its rendering apart is what lets the
display stay a function of text.

WHY A PASS IS A LINE. An absent line would be indistinguishable from a display that
never took the judgement, which is exactly the reading `findings: none` already
allowed. WHY A FAILED TAKING IS NOT A PASS. The three outcomes render three
distinct shapes so a filer can tell a clean item from an unjudged one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    JUDGEMENT_HELD,
    DodJudgement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    run_dod_judgement,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
        GoverningHeadingVerdict,
    )
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "NODE_RUBRIC_FINDING_PREFIX",
    "NODE_RUBRIC_NOT_TAKEN_PREFIX",
    "NODE_RUBRIC_PASSED_REPORT",
    "NodeJudgementTaker",
    "host_node_judgement_taker",
    "node_rubric_lines",
]

NODE_RUBRIC_FINDING_PREFIX = "definition-of-done finding (node rubric):"
NODE_RUBRIC_PASSED_REPORT = "node-rubric judgement: passed"
NODE_RUBRIC_NOT_TAKEN_PREFIX = "node-rubric judgement not taken:"
_CALLER = "dod_judgement_filing_display"
_UNKNOWN_CAUSE = "no cause was reported"


class NodeJudgementTaker(Protocol):
    """The seam through which a caller names how the node judgement is taken."""

    def __call__(
        self, *, item: WorkItem, cwd: Path, governing: GoverningHeadingVerdict | None
    ) -> DodJudgement:
        """Take the node judgement for one item."""
        ...


def host_node_judgement_taker(*, runner: CommandRunner | None = None) -> NodeJudgementTaker:
    """This host's own taking: the node's rubric bytes, the filing's subject."""

    def take(
        *, item: WorkItem, cwd: Path, governing: GoverningHeadingVerdict | None
    ) -> DodJudgement:
        return run_dod_judgement(
            item=item, cwd=cwd, runner=runner, governing=governing, caller=_CALLER
        )

    return take


def node_rubric_lines(*, judgement: DodJudgement) -> list[str]:
    """One judgement as display lines: a line per finding, a pass line, or the cause."""
    if judgement.outcome == JUDGEMENT_ADMITTED:
        return [NODE_RUBRIC_PASSED_REPORT]
    if judgement.outcome == JUDGEMENT_HELD:
        return [f"{NODE_RUBRIC_FINDING_PREFIX} {finding}" for finding in judgement.findings]
    return [f"{NODE_RUBRIC_NOT_TAKEN_PREFIX} {judgement.cause or _UNKNOWN_CAUSE}"]
