"""Focused tests for failed AI-acceptance rework cap edge cases."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands import _dispatcher_completion
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-acceptance-rework-edge",
        type="task",
        status="ready",
        title="Acceptance rework edge",
        description="Exercise invalid per-item cap labels.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-07-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _green_outcome(*, item_id: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=item_id,
        status="green",
        stage="done",
        pr_number=11,
        merge_sha="feed01",
        detail="merged",
    )


@dataclass(frozen=True, kw_only=True)
class _FailingAcceptancePass:
    # The proof leg the real pass carries. `None` is what a legacy-source item
    # resolves to, and it is the right stand-in here: these cases are about the
    # DISPOSITION the verdict routes to, and the pointer write skips an item
    # with no record rather than changing which branch runs.
    proof: None = None
    verdict: str = "FAIL"
    absent_evidence: tuple[str, ...] = ()

    def journal_record(self, *, work_item_id: str, policy: str) -> dict[str, object]:
        return {
            "stage": "acceptance-ai-pass",
            "work_item_id": work_item_id,
            "verdict": self.verdict,
            "acceptance_policy": policy,
        }


def test_invalid_acceptance_rework_cap_label_falls_back_to_dispatcher_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    make_beads_client(config=_config()).update_issue(
        issue_id=item.id,
        add_labels=["acceptance-rework-cap:0"],
    )
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _FailingAcceptancePass(),
    )
    journal = JournalFile(path=repo / "journal.jsonl")

    _dispatcher_completion.complete_and_accept(
        repo=repo,
        item=item,
        outcome=_green_outcome(item_id=item.id),
        journal=journal,
    )

    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    rework = next(record for record in records if record["stage"] == "acceptance-auto-rework")
    assert rework["acceptance_rework_cap"] == 2
    assert rework["cap_source"] == "dispatcher.acceptance_rework_cap"


@pytest.mark.parametrize("policy", [("ai-only",), ("ai-then-human",), ("human-only",)])
def test_a_proof_only_not_reproduced_factory_assertion_parks_without_rework(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, policy: str
) -> None:
    """Scenario 257 keeps every policy in acceptance after a negative proof-only arm."""
    repo = _repo(tmp_path=tmp_path)
    item = replace(_item(), acceptance_policy=policy)
    append_work_item(path=_config(), item=item)
    proof = SimpleNamespace(
        record=SimpleNamespace(verdict="not_reproduced"),
        assertions=(
            SimpleNamespace(proof_mode="factory_captured", check=SimpleNamespace(passed=False)),
        ),
    )
    acceptance_pass = _FailingAcceptancePass(proof=proof)  # type: ignore[arg-type]
    parked: list[dict[str, object]] = []
    monkeypatch.setattr(_dispatcher_completion, "run_acceptance_pass", lambda **_: acceptance_pass)
    monkeypatch.setattr(
        _dispatcher_completion,
        "incident_decision",
        lambda **_: SimpleNamespace(policy=policy, to_done=True),
    )
    monkeypatch.setattr(
        _dispatcher_completion, "park_in_acceptance", lambda **kwargs: parked.append(kwargs)
    )
    journal = JournalFile(path=repo / "journal.jsonl")

    disposition = _dispatcher_completion.complete_and_accept(
        repo=repo,
        item=item,
        outcome=_green_outcome(item_id=item.id),
        journal=journal,
        park_unreproduced_factory_captured=True,
    )

    assert disposition.closed is False
    assert [call["policy"] for call in parked] == [policy]
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    assert "acceptance-auto-rework" not in [record["stage"] for record in records]
    stored = make_beads_client(config=_config()).show_issue(issue_id=item.id)
    assert stored["status"] == "acceptance"
    assert "rework:pending" not in stored["labels"]
