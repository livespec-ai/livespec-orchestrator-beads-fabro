"""A repository whose ledger connection cannot be resolved holds nothing at the tier.

`standing_hold_the_drain_drops` fails toward the behaviour the launcher had
without the tier screen, exactly as the drain filter beside it does
(bd-ib-kix22a).
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._spec_change_tier_wall import (
    standing_hold_the_drain_drops,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


def test_an_unresolvable_connection_holds_nothing(tmp_path: Path) -> None:
    item = WorkItem(
        id="bd-ib-any",
        type="bug",
        status="ready",
        title="t",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )

    assert standing_hold_the_drain_drops(repo=tmp_path, item=item) is None
