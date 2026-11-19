"""The host-side wall's filing findings, and the governing-heading judgement they grade by.

The filing findings and the pre-admission judgement both grade by the item's
governing-heading verdict, the one `dod_gate` takes. They live apart from
`intake_dor` so that module's size stays on the routing it owns; it re-exports
`FilingFindings` and `filing_findings`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_advisories import (
    advisory_definition_of_done_findings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_findings import (
    definition_of_done_findings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display import (
    ADVISORY_FINDING_PREFIX,
    MECHANICAL_FINDING_PREFIX,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    governing_heading_findings,
    governing_heading_holds,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    host_governing_heading_reader,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
        GoverningHeadingVerdict,
    )
    from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
        GoverningHeadingReader,
    )
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "FilingFindings",
    "filing_findings",
    "governing_heading_mismatch",
    "taken_once",
]


@dataclass(frozen=True, kw_only=True)
class FilingFindings:
    """One filed item's Definition-of-Done findings, split by what they DO.

    The two tuples are kept apart rather than merged behind a flag because their
    consequences are opposite: `mechanical` withholds `ready` and `advisory` is
    forbidden to. A single list carrying a kind marker is one dropped marker away
    from either holding every item out of the queue or admitting a malformed one.
    """

    mechanical: tuple[str, ...]
    advisory: tuple[str, ...]

    @property
    def withholds_ready(self) -> bool:
        """Whether an outstanding finding keeps this item out of `ready`."""
        return bool(self.mechanical)

    def comment_bodies(self) -> tuple[str, ...]:
        """One ledger-comment body per finding, mechanical ones first.

        The wording is the display's, imported rather than re-spelled, so the
        comment an operator finds on the item is the sentence the filing display
        showed them. Mechanical ones lead because they are the ones holding the
        item back.
        """
        return tuple(
            f"{MECHANICAL_FINDING_PREFIX} {finding}" for finding in self.mechanical
        ) + tuple(f"{ADVISORY_FINDING_PREFIX} {finding}" for finding in self.advisory)


def filing_findings(
    *, item: WorkItem, repo_root: Path | None, governing: GoverningHeadingReader | None = None
) -> FilingFindings:
    """Both halves of the host-side wall for one filed item.

    A `None` repository root yields EMPTY findings rather than a refusal: both
    halves are graded against the governed spec tree, and with no repository
    there is no tree to grade against. That is not a fail-open on the `ready`
    approval — the approval branch raises `TypeError` on a `None` root before it
    can admit anything.

    The governing-heading judgement is the SAME one `dod_gate` takes and the
    filing display shows, and a References line that names none of the headings
    it returns is a MECHANICAL finding here, so the intake route's own
    `withholds_ready` gate stops on it rather than admitting an item whose run
    would end at `dod_gate`. `governing` DEFAULTS TO THIS HOST'S OWN READER, for
    the reason `filing_display`'s does; a caller that must not spend the
    judgement passes `unjudged_governing_heading`, which yields no verdict and so
    no finding (a judgement that could not be taken is not evidence).
    """
    if repo_root is None:
        return FilingFindings(mechanical=(), advisory=())
    mechanical = definition_of_done_findings(item=item, cwd=repo_root)
    # A lexical finding already withholds `ready`, so the judgement is not spent
    # on an item a free parse holds back: it would buy nothing.
    if mechanical:
        return FilingFindings(
            mechanical=mechanical,
            advisory=advisory_definition_of_done_findings(item=item, cwd=repo_root),
        )
    verdict, mismatch = governing_heading_mismatch(
        item=item, repo_root=repo_root, governing=governing
    )
    return FilingFindings(
        mechanical=mechanical + mismatch,
        advisory=advisory_definition_of_done_findings(item=item, cwd=repo_root, governing=verdict),
    )


def governing_heading_mismatch(
    *, item: WorkItem, repo_root: Path, governing: GoverningHeadingReader | None
) -> tuple[GoverningHeadingVerdict | None, tuple[str, ...]]:
    """The verdict the judgement returns for this item, and the findings it holds.

    The findings are one per governing heading a References line that names NONE
    of them omits, verbatim, so the filer can add it. They are empty where no
    verdict was taken, because a judgement that could not be taken is not evidence
    that a citation fails to govern. `governing` DEFAULTS TO THIS HOST'S OWN
    READER, for the reason `filing_display`'s does.
    """
    reader = (
        host_governing_heading_reader(runner=ShellCommandRunner())
        if governing is None
        else governing
    )
    verdict = reader(item=item, repo=repo_root)
    section = definition_of_done(description=item.description)
    if not governing_heading_holds(section=section, verdict=verdict):
        return verdict, ()
    return verdict, governing_heading_findings(item=item, section=section, verdict=verdict)


def taken_once() -> GoverningHeadingReader:
    """A host reader that puts the judgement to the judge once and then replays it.

    The filing findings and the pre-admission judgement both need this item's
    governing-heading verdict, and each takes it when it is not handed one. One
    routing pass hands both the same reader, so the verdict they grade by is one
    taking, and a pass spends no more of the model than it did before the
    findings read the verdict.
    """
    host = host_governing_heading_reader(runner=ShellCommandRunner())
    taken: list[GoverningHeadingVerdict | None] = []

    def read(*, item: WorkItem, repo: Path) -> GoverningHeadingVerdict | None:
        if not taken:
            taken.append(host(item=item, repo=repo))
        return taken[0]

    return read
