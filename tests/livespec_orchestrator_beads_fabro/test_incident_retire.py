"""An abandoned or drill incident chain retires through one sanctioned action (zhonwq).

The retire action records who retired the chain and why, moves it to the
terminal phase `retired` and closes the item with no repayment owed. It refuses
by name, writing nothing, whenever any expedited change of the chain reached
master, so it cannot bypass a real repayment obligation.
"""

from __future__ import annotations

import importlib
import json
from argparse import Namespace
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._store_claim_tokens import (
    ClaimChangeResult,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._incident_authority_lifecycle import (
    run_lifecycle_action,
)
from livespec_orchestrator_beads_fabro.commands._incident_provenance import receipts_from_history
from livespec_orchestrator_beads_fabro.effects._incident_completion_reader import (
    read_incident_standing,
)
from livespec_orchestrator_beads_fabro.incident_authority import (
    commit_incident_transition,
    read_incident_authority,
)

REPOSITORY = "owner/repository"
ITEM = "bd-ib-abandoned"
_MODULE = "livespec_orchestrator_beads_fabro.incident_retire"
_MARKER = "livespec-incident-retirement-v1\n"
_BY = "operator:alice"
_WHY = "PR #7 closed unmerged; the fix landed on the normal lane as PR #9"


def _encode(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attempt(**changes: Any) -> dict[str, Any]:
    return {
        "repository": REPOSITORY,
        "item_id": ITEM,
        "attempt_id": "abandoned-1",
        "phase": "repair",
        "operation_id": "abandoned-1#repair",
        "generation": 1,
        "owner": "operator:alice",
        "base": "a" * 40,
        "head": "b" * 40,
        "pr_number": 7,
        "landed_commits": [],
        "landed_trees": [],
        "original_paths": ["app.py"],
        "deferred_work": ["normal-factory-proof"],
        "repayment_required": True,
        "carrier": {
            "state": "pr-bound",
            "target_ref": "refs/heads/incident/bd-ib-abandoned",
            "input_parent": "a" * 40,
            "staged_tree": "c" * 40,
            "remote_head": "b" * 40,
        },
    } | changes


_PRE_PR = {
    "pr_number": 0,
    "carrier": {
        "state": "branch-reserved",
        "target_ref": "refs/heads/incident/bd-ib-abandoned",
        "input_parent": "a" * 40,
        "staged_tree": "c" * 40,
    },
}


def _seed(*, snapshot: dict[str, Any]) -> tuple[FakeBeadsClient, IncidentReading]:
    client = FakeBeadsClient()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=ITEM,
            issue_type="bug",
            title="abandoned incident",
            description="an expedited attempt whose PR closed unmerged",
            assignee="operator:alice",
            created_at="2026-11-22T00:00:00Z",
        )
    )
    root = client.create_no_history_issue(title=TOKEN_TITLE, description="authority root")
    token = client.create_no_history_issue(title=TOKEN_TITLE, description="authority token")
    client.add_comment(
        issue_id=ITEM,
        body=GENESIS_MARKER
        + _encode({"schema": 1, "repository": REPOSITORY, "item_id": ITEM, "root_token_id": root}),
    )
    client.close_issue_without_verdict(
        issue_id=root,
        reason=TRANSITION_MARKER
        + _encode(
            {
                "schema": 1,
                "repository": REPOSITORY,
                "item_id": ITEM,
                "prior_token_id": root,
                "next_token_id": token,
                "attempt": snapshot,
            }
        ),
    )
    client.update_issue(
        issue_id=ITEM,
        status="active",
        metadata={"dispatch_claim_token": create_claim_token(client=client)},
        names_claim_token=True,
    )
    reading = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={
            key: snapshot[key]
            for key in ("attempt_id", "phase", "operation_id", "generation", "owner")
        },
    )
    assert isinstance(reading, IncidentReading)
    return client, reading


class _Forge:
    """The forge: one pull request view and one master comparison answer."""

    def __init__(self, *, pr: dict[str, object] | None, behind_by: object = 1) -> None:
        self.pr = pr
        self.behind_by = behind_by
        self.reads: list[str] = []

    def run(self, *, argv: list[str], **_: object) -> CommandResult:
        self.reads.append(" ".join(argv[:3]))
        if argv[:3] == ["gh", "pr", "view"]:
            if self.pr is None:
                return CommandResult(exit_code=1, stdout="", stderr="forge down")
            return CommandResult(exit_code=0, stdout=_encode(self.pr), stderr="")
        return CommandResult(exit_code=0, stdout=_encode({"behind_by": self.behind_by}), stderr="")


def _closed_unmerged(*, base: str = "master") -> dict[str, object]:
    return {"number": 7, "state": "CLOSED", "baseRefName": base}


def _retire(
    *,
    client: FakeBeadsClient,
    reading: IncidentReading,
    forge: object,
    tmp_path: Path,
    retired_by: str = _BY,
    reason: str = _WHY,
) -> Any:
    module = importlib.import_module(_MODULE)
    return module.retire_incident(
        client=client,
        reading=reading,
        runner=forge,
        repo=tmp_path,
        repository=REPOSITORY,
        retirement=module.Retirement(retired_by=retired_by, reason=reason),
    )


def _records(*, client: FakeBeadsClient) -> list[dict[str, object]]:
    """Every retirement record on the item that decodes to one JSON object."""
    texts = [row.get("text") for row in client.list_comments(issue_id=ITEM)]
    decoded = [
        json.loads(text[len(_MARKER) :])
        for text in texts
        if isinstance(text, str) and text.startswith(_MARKER)
    ]
    return [record for record in decoded if isinstance(record, dict)]


def _unchanged(*, client: FakeBeadsClient) -> None:
    item = client.show_issue(issue_id=ITEM)
    assert (item["status"], item["assignee"]) == ("active", "operator:alice")
    assert _records(client=client) == []


def test_an_abandoned_chain_retires_with_who_and_why_and_its_item_closes(tmp_path: Path) -> None:
    module_path = (
        Path(__file__).parents[2]
        / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/incident_retire.py"
    )
    assert module_path.is_file()
    client, reading = _seed(snapshot=_attempt())

    retired = _retire(
        client=client, reading=reading, forge=_Forge(pr=_closed_unmerged()), tmp_path=tmp_path
    )

    attempt = retired.reading.attempt
    assert (attempt.phase, attempt.generation, attempt.repayment_required) == ("retired", 2, False)
    assert (retired.lifecycle_state, retired.repayment_outstanding) == ("done", False)
    assert client.show_issue(issue_id=ITEM)["status"] == "closed"
    assert _records(client=client) == [
        {
            "schema": 1,
            "item_id": ITEM,
            "attempt_id": "abandoned-1",
            "operation_id": "abandoned-1#retire",
            "generation": 2,
            "retired_by": _BY,
            "reason": _WHY,
        }
    ]
    standing = read_incident_standing(client=client, item_id=ITEM)
    assert standing.outstanding == ("incident-retired",)
    receipt_attempt = replace(standing.history[-1], landed_commits=("c" * 40,))
    receipts = receipts_from_history(history=(receipt_attempt,))
    assert [receipt.repayment_outstanding for receipt in receipts] == [False]


def test_a_never_bound_chain_and_a_scratch_drill_retire(tmp_path: Path) -> None:
    client, reading = _seed(snapshot=_attempt(**_PRE_PR))
    forge = _Forge(pr=None, behind_by=-1)
    retired = _retire(client=client, reading=reading, forge=forge, tmp_path=tmp_path)
    assert retired.reading.attempt.phase == "retired"
    assert forge.reads == []

    drill_client, drill_reading = _seed(snapshot=_attempt(phase="reverting"))
    drill = _retire(
        client=drill_client,
        reading=drill_reading,
        forge=_Forge(pr={"number": 7, "state": "MERGED", "baseRefName": "incident-scratch/x"}),
        tmp_path=tmp_path,
    )
    assert drill.reading.attempt.phase == "retired"


def test_a_landed_commit_on_master_is_refused_by_name_and_nothing_is_written(
    tmp_path: Path,
) -> None:
    client, reading = _seed(
        snapshot=_attempt(
            phase="master-observation", landed_commits=["d" * 40], landed_trees=["e" * 40]
        )
    )
    refused = _retire(
        client=client,
        reading=reading,
        forge=_Forge(pr=_closed_unmerged(), behind_by=0),
        tmp_path=tmp_path,
    )
    assert isinstance(refused, AuthorityRefusal)
    assert (refused.code, "d" * 40 in refused.detail) == ("incident-retire-landed-on-master", True)
    _unchanged(client=client)


def test_a_carrier_merged_into_master_or_still_open_is_refused(tmp_path: Path) -> None:
    cases: tuple[tuple[dict[str, object] | None, str], ...] = (
        (
            {"number": 7, "state": "MERGED", "baseRefName": "master"},
            "incident-retire-landed-on-master",
        ),
        ({"number": 7, "state": "OPEN", "baseRefName": "master"}, "incident-retire-carrier-open"),
        (
            {"number": 8, "state": "CLOSED", "baseRefName": "master"},
            "incident-retire-evidence-unavailable",
        ),
        (None, "incident-retire-evidence-unavailable"),
    )
    for pr, code in cases:
        client, reading = _seed(snapshot=_attempt())
        refused = _retire(client=client, reading=reading, forge=_Forge(pr=pr), tmp_path=tmp_path)
        assert isinstance(refused, AuthorityRefusal)
        assert refused.code == code
        _unchanged(client=client)


def test_an_unattributed_or_ineligible_retire_is_refused(tmp_path: Path) -> None:
    client, reading = _seed(snapshot=_attempt())
    forge = _Forge(pr=_closed_unmerged())
    for retired_by, reason in (("", _WHY), (_BY, "  ")):
        refused = _retire(
            client=client,
            reading=reading,
            forge=forge,
            tmp_path=tmp_path,
            retired_by=retired_by,
            reason=reason,
        )
        assert isinstance(refused, AuthorityRefusal)
        assert refused.code == "incident-retire-unattributed"
    repaying_client, repaying = _seed(snapshot=_attempt(phase="repayment-active"))
    refused = _retire(client=repaying_client, reading=repaying, forge=forge, tmp_path=tmp_path)
    assert isinstance(refused, AuthorityRefusal)
    assert (refused.code, refused.detail) == (
        "incident-retire-ineligible-phase",
        "repayment-active",
    )
    assert forge.reads == []


def test_the_generic_transition_cannot_write_retired() -> None:
    client, reading = _seed(snapshot=_attempt())
    successor = replace(
        reading.attempt,
        phase="retired",
        operation_id="abandoned-1#retire",
        generation=2,
        repayment_required=False,
    )
    refused = commit_incident_transition(client=client, observed=reading, successor=successor)
    assert isinstance(refused, AuthorityRefusal)
    assert refused.code == "incident-retire-requires-action"


def test_a_rerun_recovers_the_same_retirement_and_records_it_once(tmp_path: Path) -> None:
    client, reading = _seed(snapshot=_attempt())
    client.add_comment(issue_id=ITEM, body=_MARKER + _encode({"operation_id": "other#retire"}))
    client.add_comment(issue_id=ITEM, body=_MARKER + "[]")
    forge = _Forge(pr=_closed_unmerged())
    first = _retire(client=client, reading=reading, forge=forge, tmp_path=tmp_path)
    again = _retire(client=client, reading=reading, forge=forge, tmp_path=tmp_path)
    assert again == first
    assert [record.get("operation_id") for record in _records(client=client)] == [
        "other#retire",
        "abandoned-1#retire",
    ]


def test_the_retire_action_runs_through_the_lifecycle_cli_and_decodes_its_payload(
    tmp_path: Path,
) -> None:
    client, reading = _seed(snapshot=_attempt())
    payload = _encode({"reason": _WHY, "retired_by": _BY})
    retired = run_lifecycle_action(
        args=Namespace(action="retire", retire_json=payload, repo=tmp_path, repository=REPOSITORY),
        client=client,
        reading=reading,
        runner=_Forge(pr=_closed_unmerged()),
    )
    assert cast("Any", retired).reading.attempt.phase == "retired"
    invalid = run_lifecycle_action(
        args=Namespace(
            action="retire", retire_json='{"reason":"x"}', repo=tmp_path, repository=REPOSITORY
        ),
        client=client,
        reading=reading,
        runner=_Forge(pr=_closed_unmerged()),
    )
    assert isinstance(invalid, AuthorityRefusal)
    assert invalid.code == "incident-action-invalid-payload"


def test_retire_returns_fence_history_and_lifecycle_refusals(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = importlib.import_module(_MODULE)
    stale = AuthorityRefusal(code="incident-generation-stale", detail=ITEM)
    unavailable = AuthorityRefusal(code="incident-authority-unavailable", detail=ITEM)
    client, reading = _seed(snapshot=_attempt())
    forge = _Forge(pr=_closed_unmerged())

    def always_stale(**_: object) -> AuthorityRefusal:
        return stale

    def refused(**_: object) -> AuthorityRefusal:
        return unavailable

    monkeypatch.setattr(module, "require_current_generation", always_stale)
    monkeypatch.setattr(module, "commit_transition", refused)
    assert _retire(client=client, reading=reading, forge=forge, tmp_path=tmp_path) == stale
    monkeypatch.undo()

    monkeypatch.setattr(module, "read_history", refused)
    assert _retire(client=client, reading=reading, forge=forge, tmp_path=tmp_path) == unavailable
    monkeypatch.undo()

    calls = {"n": 0}

    def stale_after_commit(**_: object) -> IncidentReading | AuthorityRefusal:
        calls["n"] += 1
        return reading if calls["n"] == 1 else stale

    monkeypatch.setattr(module, "require_current_generation", stale_after_commit)
    assert _retire(client=client, reading=reading, forge=forge, tmp_path=tmp_path) == stale
    monkeypatch.undo()
    _unchanged(client=client)


def test_retire_waits_out_a_pending_claim_transition_and_names_a_changed_claim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = importlib.import_module(_MODULE)
    outcomes = ["claim-transition-pending", "claim-changed"]
    now = {"t": 0.0}

    def clock() -> float:
        return now["t"]

    def sleep(seconds: float) -> None:
        now["t"] += seconds

    def change_claim(**_: object) -> ClaimChangeResult:
        return ClaimChangeResult(outcome=outcomes.pop(0))

    monkeypatch.setattr(module, "_clock", clock)
    monkeypatch.setattr(module, "_sleep", sleep)
    monkeypatch.setattr(module, "change_claim", change_claim)
    client, reading = _seed(snapshot=_attempt())

    refused = _retire(
        client=client, reading=reading, forge=_Forge(pr=_closed_unmerged()), tmp_path=tmp_path
    )

    assert isinstance(refused, AuthorityRefusal)
    assert (refused.code, refused.detail) == ("incident-retire-lifecycle-refused", "claim-changed")
    assert now["t"] == 5.0
