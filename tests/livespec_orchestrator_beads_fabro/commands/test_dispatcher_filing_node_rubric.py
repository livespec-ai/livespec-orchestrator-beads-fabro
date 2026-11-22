"""The filing display reports the dod_gate node rubric's findings, not only the wall's.

`SPECIFICATION/scenarios.md` Scenario 140 has the filing display show "the
finding" for the item before the filing is confirmed, and Scenario 239 makes
every taking of the Definition-of-Done judgement grade by the dod_gate node's own
rubric bytes. Before this module the display printed the host wall's mechanical
findings, its advisory findings and a "not taken" line, and never the node's
per-assertion check 4 coherence finding or its check 5 proof-surface finding:
four hand-read items in forty-seven read clean, because a weak item was filed
with `findings: none` and refused only at dispatch.

WHY THE MODULE IS IMPORTED INSIDE EACH TEST BODY. A top-level import of a name the
module does not export yet makes the Red a COLLECTION error, which proves only
unimportability; an attribute read inside the body fails on a real assertion.
"""

from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    JUDGEMENT_HELD,
    JUDGEMENT_UNAVAILABLE,
    DodJudgement,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_NODE_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_filing_node_rubric"
_DISPLAY_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display"
_HEADING = "## Effective acceptance criteria"
_CHECK_FOUR = (
    "check 4: assertion 2 is incoherent against `## Effective acceptance criteria`; "
    "its section never states the refusal text."
)
_CHECK_FIVE = "check 5: assertion 1 needs operator-host state, which no factory sandbox provides."


def _item() -> WorkItem:
    return replace(
        WorkItem(
            id="bd-ib-node",
            type="task",
            status="backlog",
            title="A freshly filed task",
            description=(
                "## Definition of Done\n"
                "\n"
                "- The accept valve refuses an item with no verified record.\n"
                "\n"
                f"References: {_HEADING}\n"
            ),
            origin="freeform",
            gap_id=None,
            rank="a2",
            assignee=None,
            depends_on=(),
            captured_at="2026-10-04T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy="auto",
            acceptance_policy="ai-only",
        )
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    return repo


def _clean_governing(*, item: WorkItem, repo: Path) -> GoverningHeadingVerdict:
    del item, repo
    return GoverningHeadingVerdict(kind="unstated")


def test_a_held_judgement_is_rendered_as_one_labelled_line_per_finding_in_order() -> None:
    module = importlib.import_module(_NODE_MODULE)
    held = DodJudgement(outcome=JUDGEMENT_HELD, findings=(_CHECK_FOUR, _CHECK_FIVE))

    lines = module.node_rubric_lines(judgement=held)

    assert lines == [
        f"definition-of-done finding (node rubric): {_CHECK_FOUR}",
        f"definition-of-done finding (node rubric): {_CHECK_FIVE}",
    ]


def test_an_admitted_judgement_is_rendered_as_an_explicit_pass_line() -> None:
    module = importlib.import_module(_NODE_MODULE)

    lines = module.node_rubric_lines(judgement=DodJudgement(outcome=JUDGEMENT_ADMITTED))

    assert lines == ["node-rubric judgement: passed"]


def test_a_judgement_that_could_not_be_taken_names_its_cause_and_is_not_a_pass() -> None:
    module = importlib.import_module(_NODE_MODULE)
    unavailable = DodJudgement(outcome=JUDGEMENT_UNAVAILABLE, cause="no-eligible-model")

    lines = module.node_rubric_lines(judgement=unavailable)

    assert lines == ["node-rubric judgement not taken: no-eligible-model"]


def test_the_display_appends_the_node_rubric_lines_after_the_wall_findings(
    tmp_path: Path,
) -> None:
    display = importlib.import_module(_DISPLAY_MODULE)
    seen: list[str] = []

    def taker(
        *, item: WorkItem, cwd: Path, governing: GoverningHeadingVerdict | None
    ) -> DodJudgement:
        del cwd, governing
        seen.append(item.id)
        return DodJudgement(outcome=JUDGEMENT_HELD, findings=(_CHECK_FOUR, _CHECK_FIVE))

    lines = display.filing_display(
        item=_item(),
        cwd=_repo(tmp_path=tmp_path),
        governing=_clean_governing,
        node_judgement=taker,
    ).splitlines()

    assert seen == ["bd-ib-node"]
    assert lines[-3:] == [
        "definition-of-done findings: none",
        f"definition-of-done finding (node rubric): {_CHECK_FOUR}",
        f"definition-of-done finding (node rubric): {_CHECK_FIVE}",
    ]


def test_a_caller_that_names_no_node_judgement_spends_none(tmp_path: Path) -> None:
    display = importlib.import_module(_DISPLAY_MODULE)

    lines = display.filing_display(
        item=_item(), cwd=_repo(tmp_path=tmp_path), governing=_clean_governing
    ).splitlines()

    assert lines[-1] == "definition-of-done findings: none"
    assert not any("node-rubric" in line or "node rubric" in line for line in lines)
