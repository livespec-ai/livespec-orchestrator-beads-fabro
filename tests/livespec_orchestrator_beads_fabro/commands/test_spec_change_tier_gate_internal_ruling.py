"""The filing classifier records the first References heading that resolves to an H2."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _spec_change_tier_gate as gate
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    NO_TIER,
    SpecChangeTierDecision,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_current import (
    current_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import STAGE_FILING
from livespec_orchestrator_beads_fabro.types import WorkItem
from livespec_runtime.spec_stated import SpecStatedVerdict


def test_a_filing_internal_ruling_skips_an_unresolvable_reference() -> None:
    resolved = "## A resolvable topic"

    decision = gate._filing_internal_ruling(  # noqa: SLF001
        decision=SpecChangeTierDecision(
            tier=NO_TIER,
            classification="bug",
            verdict=SpecStatedVerdict(
                kind="stated",
                stated_by=(resolved,),
                generalization_target=None,
                rationale="The change is internal.",
            ),
            linked_proposal_topic=None,
        ),
        description=(
            "## Definition of Done\n\n"
            "- The classifier records a usable target.\n\n"
            f"References: ## Missing topic, {resolved}\n"
        ),
        spec_tree={"contracts.md": f"# Contracts\n\n{resolved}\n\nA clause.\n"},
        stage=STAGE_FILING,
    )

    assert decision.verdict is not None
    assert decision.verdict.generalization_target == resolved


def test_an_unreadable_spec_tree_has_no_current_internal_ruling(tmp_path: Path) -> None:
    item = WorkItem(
        id="bd-ib-current-tier",
        type="bug",
        status="ready",
        title="An internal ruling remains current",
        description="## Definition of Done\n\n- The subject reads its tier record.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-21T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )

    assert current_spec_change_tier(item=item, repo=tmp_path, comments=()) is None
