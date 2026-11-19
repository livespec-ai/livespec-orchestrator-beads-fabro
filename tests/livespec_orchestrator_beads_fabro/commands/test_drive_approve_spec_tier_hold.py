"""The approve valve keeps a spec-change-tier hold out of ``ready``."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands import _drive_approve_valve as approve_valve
from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    SpecChangeTierDecision,
    behaviour_digest,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_FILING,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.spec_stated import SpecStatedVerdict

_ITEM_ID = "bd-ib-held-approval"


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    specification = repo / "SPECIFICATION"
    specification.mkdir(parents=True)
    _ = (specification / "contracts.md").write_text(
        "## Effective acceptance criteria\n",
        encoding="utf-8",
    )
    (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {
      "tenant": "livespec-impl-beads",
      "prefix": "bd-ib",
      "server_user": "livespec-impl-beads",
      "database": "livespec-impl-beads",
      "bd_path": "bd",
      "fake": true
    }
  }
}
""",
        encoding="utf-8",
    )
    return repo


def _held_item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="feature",
        status="pending-approval",
        title="Hold a spec-change-tier item before approval",
        description=(
            "Hold the item.\n\n## Definition of Done\n\n"
            "- The approval respects the standing hold.\n\n"
            "References: ## Effective acceptance criteria"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-18T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def test_approve_refuses_a_no_linked_topic_hold_without_a_definition_of_done_judgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _held_item()
    append_work_item(path=_config(), item=item)
    append_work_item_comment(
        path=_config(),
        work_item_id=item.id,
        body=spec_change_tier_comment(
            item_id=item.id,
            stage=STAGE_FILING,
            decision=SpecChangeTierDecision(
                tier="spec-change",
                classification="feature",
                verdict=SpecStatedVerdict(
                    kind="unstated",
                    stated_by=(),
                    generalization_target="## Governing clause",
                    rationale="not stated",
                ),
                linked_proposal_topic=None,
            ),
            spec_version="1",
            digest=behaviour_digest(item=item),
        ),
    )
    judgements: list[object] = []

    def _judgement(**_kwargs: object) -> SimpleNamespace:
        judgements.append(object())
        return SimpleNamespace(holds=False, findings=())

    monkeypatch.setattr(approve_valve, "judge_item_definition_of_done", _judgement)

    result = run_human_valve_action(repo=repo, action_id=f"approve:{item.id}")

    assert result["status"] == "failed"
    assert "(none linked)" in result["summary"]
    assert "no-linked-topic" in result["summary"]
    assert judgements == []
    assert _fake().show_issue(issue_id=item.id)["status"] == "pending-approval"
