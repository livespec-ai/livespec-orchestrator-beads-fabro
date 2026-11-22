"""The journal row a published-head relation lacked, named for the resume refusal."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_run_age import (
    published_head_attribution_gap,
)


@pytest.mark.parametrize(
    ("records", "publications", "expected"),
    [
        ((), (), "published-head"),
        ((), (("head", "newer"),), "published-head"),
        (({"run_id": "newer", "published_head": "head"},), (), "preserved-run"),
        (
            ({"run_id": "older"}, {"run_id": "newer", "published_head": "head"}),
            (),
            None,
        ),
        ((), (("head", "older"),), None),
    ],
)
def test_the_attribution_gap_names_which_journal_row_the_relation_lacked(
    *,
    records: tuple[dict[str, object], ...],
    publications: tuple[tuple[str, str], ...],
    expected: str | None,
) -> None:
    assert (
        published_head_attribution_gap(
            records=records,
            preserved_run_id="older",
            published_head="head",
            publications=publications,
        )
        == expected
    )
