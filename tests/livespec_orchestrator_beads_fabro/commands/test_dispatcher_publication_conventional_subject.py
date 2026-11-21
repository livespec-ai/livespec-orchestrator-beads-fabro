"""Publication titles provide release-please-visible conventional subjects."""

from __future__ import annotations

from typing import Literal

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_metadata import (
    publication_metadata_for,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item(*, type_: Literal["feature", "task", "chore", "epic"], title: str) -> WorkItem:
    return WorkItem(
        id="bd-ib-d5avjp",
        type=type_,
        status="ready",
        title=title,
        description="",
        acceptance_criteria=None,
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


@pytest.mark.parametrize("type_", ["feature", "task", "chore", "epic"])
def test_non_bug_items_render_feat_subjects_that_keep_the_change_description(
    type_: Literal["feature", "task", "chore", "epic"],
) -> None:
    item = _item(type_=type_, title="Publish factory commits for release-please")

    metadata = publication_metadata_for(item=item)

    assert metadata.title == f"feat: {item.title} ({item.id})"
