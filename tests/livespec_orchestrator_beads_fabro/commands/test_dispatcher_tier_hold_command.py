"""The read-only `tier-hold` Dispatcher command a fleet launcher screens an item with.

A fleet launcher must learn whether the spec-change tier hold stands on an item
BEFORE it takes a launch ticket, from the SAME predicate the drain's admission
filter uses (`spec_change_unrefused_candidates`), so the launcher and the
Dispatcher never disagree and a held item never costs a ticket or a mutex turn
(bd-ib-kix22a). The command takes no judgement and reaches no model.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    decide_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_DISPATCH,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.spec_stated import SpecStatedVerdict

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_HELD_ITEM = "bd-ib-held"
_FREE_ITEM = "bd-ib-free"
_TOPIC = "hold-an-unstated-feature-for"
_TARGET = "## A governing clause"


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _repo(*, tmp_path: Path, ratified: bool) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    if ratified:
        changes = spec / "history" / "v001" / "proposed_changes"
        changes.mkdir(parents=True, exist_ok=True)
        _ = (changes / f"{_TOPIC}.md").write_text("the proposal\n", encoding="utf-8")
        _ = (changes / f"{_TOPIC}-revision.md").write_text(
            f"---\nproposal: {_TOPIC}.md\ndecision: accept\n---\n", encoding="utf-8"
        )
    return repo


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
        title="Hold an unstated feature for its proposal",
        description="New observable behaviour.",
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
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _record(*, repo: Path, item_id: str, spec_version: str = "1") -> None:
    item = _item(item_id=item_id)
    append_work_item(path=_config(repo=repo), item=item)
    decision = decide_spec_change_tier(
        item=item,
        classification="feature",
        verdict=SpecStatedVerdict(
            kind="unstated",
            stated_by=(),
            generalization_target=_TARGET,
            rationale="the ratified text does not state the whole of it",
        ),
    )
    append_work_item_comment(
        path=_config(repo=repo),
        work_item_id=item_id,
        body=spec_change_tier_comment(
            item_id=item_id,
            stage=STAGE_DISPATCH,
            decision=decision,
            spec_version=spec_version,
            digest="a-digest",
        ),
    )


def _run(*, repo: Path, item_id: str, capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    module = _module(name="_dispatcher_tier_hold_command")
    rc = module.run_tier_hold_command(
        args=argparse.Namespace(repo=str(repo), item=item_id, as_json=True)
    )
    assert rc == 0
    return json.loads(capsys.readouterr().out)


def test_a_tier_held_item_reports_its_hold_reason_and_linked_topic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path=tmp_path, ratified=False)
    _record(repo=repo, item_id=_HELD_ITEM)

    payload = _run(repo=repo, item_id=_HELD_ITEM, capsys=capsys)

    assert payload["spec_change_hold"] is True
    assert payload["reason"] == "unratified-topic"
    assert payload["topic"] == _TOPIC
    assert payload["work_item_id"] == _HELD_ITEM


def test_an_item_with_no_recorded_classification_reports_no_hold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path=tmp_path, ratified=False)
    append_work_item(path=_config(repo=repo), item=_item(item_id=_FREE_ITEM))

    payload = _run(repo=repo, item_id=_FREE_ITEM, capsys=capsys)

    assert payload == {"spec_change_hold": False, "work_item_id": _FREE_ITEM}


def test_a_ratified_hold_due_a_rejudgement_reports_no_hold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path=tmp_path, ratified=True)
    _record(repo=repo, item_id=_HELD_ITEM, spec_version="0")

    payload = _run(repo=repo, item_id=_HELD_ITEM, capsys=capsys)

    assert payload["spec_change_hold"] is False
