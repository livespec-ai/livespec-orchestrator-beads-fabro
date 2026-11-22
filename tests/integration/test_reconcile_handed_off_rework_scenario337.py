"""Integration journey for the rework-specific handed-off reconciliation lane."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimStamp, record_claim_stamp
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_stranded_claim_handoff_recovery as recovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_survey import (
    FactoryInventory,
    StrandedClaimInputs,
    survey_stranded_claims,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_HOST = "scenario337-host"
_FACTORY = "petri"
_SERVER = "https://petri.example:32276"
_RUN = "01SCENARIO337"


@pytest.fixture(autouse=True)
def _fake_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="scenario337",
        prefix="bd-ib",
        server_user="scenario337",
        database="scenario337",
        bd_path="bd",
        fake=True,
    )


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="active",
        title="A handed-off rework",
        description="Fix it.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-22T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        rework_pending=True,
    )


def _stored(*, item_id: str) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config()))[item_id]


@dataclass
class _Forge:
    state: str = "OPEN"
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self, *, argv: list[str], cwd: Path, timeout_seconds: float, env=None, stdin=None
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        if argv[:3] == ["gh", "api", "graphql"]:
            return CommandResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "commits": {
                                        "nodes": [
                                            {
                                                "commit": {
                                                    "statusCheckRollup": {
                                                        "contexts": {
                                                            "nodes": [
                                                                {
                                                                    "name": "check",
                                                                    "isRequired": True,
                                                                }
                                                            ]
                                                        }
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                }
                            }
                        }
                    }
                ),
                stderr="",
            )
        return CommandResult(
            exit_code=0,
            stdout=json.dumps(
                {
                    "number": 337,
                    "state": self.state,
                    "autoMergeRequest": None if self.state == "MERGED" else {"enabledAt": "now"},
                    "mergeQueueEntry": None,
                    "mergeStateStatus": "CLEAN",
                    "mergeCommit": {"oid": "cafe05"} if self.state == "MERGED" else None,
                    "headRefOid": "head337",
                    "baseRefOid": "base337",
                    "statusCheckRollup": [
                        {"name": "check", "status": "IN_PROGRESS", "conclusion": None}
                    ],
                }
            ),
            stderr="",
        )


def _handoff_journal(*, repo: Path, item_id: str) -> JournalFile:
    journal = JournalFile(path=repo / "tmp" / "journal.jsonl")
    journal.path.parent.mkdir(parents=True)
    for record in (
        {"stage": "ledger-rework-admit", "work_item_id": item_id},
        {"stage": "dispatch-id", "work_item_id": item_id},
        {
            "stage": "merge-wait-handed-off",
            "work_item_id": item_id,
            "run_id": _RUN,
            "pr_number": 337,
        },
    ):
        journal.append(record=record)
    return journal


def _survey(*, repo: Path, journal: JournalFile, items: tuple[WorkItem, ...], forge: _Forge):
    return survey_stranded_claims(
        inputs=StrandedClaimInputs(
            repo=repo,
            items=items,
            journal=journal,
            runner=forge,
            inventories=(
                FactoryInventory(
                    name=_FACTORY,
                    server_url=_SERVER,
                    fabro_bin="fabro",
                    surveyed=True,
                    status_kinds={_RUN: "succeeded"},
                ),
            ),
            this_host=_HOST,
            now_iso="2026-11-22T00:00:00Z",
        )
    )


def test_scenario337_reconciles_merged_handoffs_holds_open_ones_and_skips_parked_reworks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Merged handoffs complete, open handoffs name their hold, and parked rows are not surveyed."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    handed = _item(item_id="bd-ib-handed")
    parked_unstarted = _item(item_id="bd-ib-parked-unstarted")
    parked_failed = _item(item_id="bd-ib-parked-failed")
    for item in (handed, parked_unstarted, parked_failed):
        append_work_item(path=_config(), item=item)
        make_beads_client(config=_config()).update_issue(
            issue_id=item.id, add_labels=["rework:pending"]
        )
    record_claim_stamp(
        path=_config(),
        work_item_id=handed.id,
        stamp=ClaimStamp(
            dispatch_id="dispatch337",
            dispatching_host=_HOST,
            run_id=_RUN,
            factory_name=_FACTORY,
            factory_server=_SERVER,
        ),
    )
    journal = _handoff_journal(repo=repo, item_id=handed.id)
    forge = _Forge()

    # This is the handoff lane's valve boundary.  The survey, marker gate,
    # forge observation, fence and recovery routing are all production code;
    # the dedicated reconcile-merged acceptance journey owns its shell-heavy
    # janitor/acceptance valve.
    def _reconcile(*, args) -> int:
        assert args.handed_off_rework is True
        make_beads_client(config=_config()).update_issue(
            issue_id=args.item, status="acceptance", remove_labels=["rework:pending"]
        )
        return 0

    monkeypatch.setattr(recovery, "reconcile_merged_for_claim", _reconcile)
    open_pass = _survey(
        repo=repo, journal=journal, items=(handed, parked_unstarted, parked_failed), forge=forge
    )
    assert open_pass.recovered == ()
    assert [
        (held.work_item_id, held.hold_reason, "merge-wait-handed-off" in (held.detail or ""))
        for held in open_pass.held
    ] == [(handed.id, "run-succeeded", True)]
    assert all(
        _stored(item_id=item.id).rework_pending
        for item in (handed, parked_unstarted, parked_failed)
    )

    forge.state = "MERGED"
    merged_pass = _survey(
        repo=repo, journal=journal, items=(handed, parked_unstarted, parked_failed), forge=forge
    )
    assert [(entry.work_item_id, entry.route) for entry in merged_pass.recovered] == [
        (handed.id, "merge-wait-handoff-reconcile-merged")
    ]
    assert (_stored(item_id=handed.id).status, _stored(item_id=handed.id).rework_pending) == (
        "acceptance",
        False,
    )
    assert all(
        _stored(item_id=item.id).rework_pending for item in (parked_unstarted, parked_failed)
    )
    assert merged_pass.held == ()
