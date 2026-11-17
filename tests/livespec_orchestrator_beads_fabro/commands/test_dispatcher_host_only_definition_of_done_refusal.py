"""The host-only refusal for an all-host Definition of Done."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import host_only_refusal
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_only import is_host_only_item
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem


def _host_captured_item() -> WorkItem:
    return WorkItem(
        id="bd-ib-ugel56",
        type="bug",
        status="ready",
        title="Route an all-host Definition of Done away from the factory",
        description=(
            "## Definition of Done\n"
            "\n"
            "### Host-captured\n"
            "\n"
            "Reason: the proof requires an attended host.\n"
            "\n"
            "- An attended host records the assertion.\n"
            "\n"
            "References: ## Dispatcher admission, WIP cap, and post-merge acceptance\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def test_host_only_refusal_explains_the_definition_of_done_host_route(tmp_path: Path) -> None:
    """An all-host item is refused before a caller can launch a factory run."""
    item = _host_captured_item()

    outcome = host_only_refusal(
        repo=tmp_path,
        item=item,
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
    )

    assert outcome is not None
    assert outcome.work_item_id == item.id
    assert outcome.status == "failed"
    assert outcome.stage == "host-only-refused"
    assert "no factory-captured Definition-of-Done assertion" in outcome.detail
    assert "every assertion is proved outside the factory" in outcome.detail
    assert "attended host session" in outcome.detail
    assert item.status == "ready"


def test_factory_captured_definition_of_done_is_not_host_only() -> None:
    item = _host_captured_item()
    item = replace(
        item,
        description=(
            "## Definition of Done\n\n"
            "### Factory-captured\n\n"
            "- A factory run captures this assertion.\n\n"
            "References: ## Dispatcher admission, WIP cap, and post-merge acceptance\n"
        ),
    )

    assert is_host_only_item(item=item) is False
