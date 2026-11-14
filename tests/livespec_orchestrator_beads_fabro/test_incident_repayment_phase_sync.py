"""`sync_repayment_phase` records the repayment phase an item's lifecycle state pairs with.

bd-ib-wz6bsa. Unit cases for the sync the Dispatcher's admission calls on each
side of the factory claim: what it reads, what it records, and the items it
leaves alone, over an in-memory tenant whose chain the canonical genesis and
transition writers recorded.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    decode_attempt,
)
from livespec_orchestrator_beads_fabro._incident_genesis import decode_genesis_request
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    ClaimStamp,
    claim_stamp_metadata,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
    commit_incident_transition,
    publish_incident_genesis,
    read_incident_authority,
)
from livespec_orchestrator_beads_fabro.incident_completion import read_incident_standing
from livespec_orchestrator_beads_fabro.incident_normal_repayment import RepaymentEntry
from livespec_orchestrator_beads_fabro.incident_repayment_phase_sync import (
    genesis_repository,
    repayment_in_play,
    sync_repayment_phase,
)

REPOSITORY = "owner/repository"
ITEM = "test-incident"
PRINCIPAL = "operator:alice"
REPAIR_REF = "refs/heads/incident/test-incident-attempt-1"
REPAYMENT_REF = "refs/heads/feat/test-incident"
REPAIR_HEAD = "d" * 40
_IDENTITY = ("attempt_id", "phase", "operation_id", "generation", "owner")


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _carrier(*, ref: str, state: str = "pr-bound") -> dict[str, str]:
    base = {"state": state, "target_ref": ref, "input_parent": "c" * 40, "staged_tree": "f" * 40}
    return base if state == "branch-reserved" else base | {"remote_head": "b" * 40}


def _attempt(**changes: Any) -> dict[str, Any]:
    return {
        "repository": REPOSITORY,
        "item_id": ITEM,
        "attempt_id": "attempt-1",
        "phase": "repair",
        "operation_id": "operation-1",
        "generation": 1,
        "owner": PRINCIPAL,
        "base": "a" * 40,
        "head": "b" * 40,
        "pr_number": 0,
        "landed_commits": [],
        "landed_trees": [],
        "original_paths": ["app.py"],
        "deferred_work": [],
        "repayment_required": True,
        "carrier": _carrier(ref=REPAIR_REF, state="branch-reserved"),
    } | changes


def _advance(client: FakeBeadsClient, observed: IncidentReading, **changes: Any) -> IncidentReading:
    successor = decode_attempt(
        value=_attempt(generation=observed.attempt.generation + 1, **changes)
    )
    assert successor is not None
    advanced = commit_incident_transition(client=client, observed=observed, successor=successor)
    assert isinstance(advanced, IncidentReading), advanced
    return advanced


@pytest.fixture
def client() -> FakeBeadsClient:
    tenant = FakeBeadsClient()
    _ = tenant.create_issue(
        draft=IssueDraft(
            issue_id=ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-07T00:00:00Z",
        )
    )
    return tenant


def _repayment_admission(client: FakeBeadsClient) -> None:
    """Genesis, the expedited merge, then `enter-repayment`'s admission generation."""
    token = create_claim_token(client=client)
    client.update_issue(
        issue_id=ITEM,
        status="ready",
        metadata={"rank": "a0", CLAIM_TOKEN_METADATA_KEY: token},
        names_claim_token=True,
    )
    request = decode_genesis_request(
        text=_json(dict(schema=1, principal=PRINCIPAL, expected_claim=token, attempt=_attempt())),
        repository=REPOSITORY,
        item_id=ITEM,
        operation_id="operation-1",
    )
    assert request is not None
    receipt = publish_incident_genesis(client=client, request=request, claim_tokens=True)
    assert not isinstance(receipt, AuthorityRefusal)
    reading = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={key: _attempt()[key] for key in _IDENTITY},
        historical=True,
    )
    assert isinstance(reading, IncidentReading)
    reading = _advance(
        client, reading, operation_id="bind-1", pr_number=7, carrier=_carrier(ref=REPAIR_REF)
    )
    reading = _advance(
        client,
        reading,
        operation_id="merge-1",
        phase="master-observation",
        pr_number=7,
        landed_commits=[REPAIR_HEAD],
        landed_trees=["e" * 40],
        carrier=_carrier(ref=REPAIR_REF),
    )
    _ = _advance(
        client,
        reading,
        operation_id="repayment-1#repayment-admission",
        phase="repayment-admission",
        attempt_id="repayment-1",
        owner="fabro",
        base=REPAIR_HEAD,
        head=REPAIR_HEAD,
        carrier=_carrier(ref=REPAYMENT_REF, state="branch-reserved"),
    )
    # Ordinary admission approved the unchanged Definition of Done: the item rests `ready`.
    client.update_issue(issue_id=ITEM, status="ready")


def _phases(client: FakeBeadsClient) -> list[str]:
    return [
        attempt.phase for attempt in read_incident_standing(client=client, item_id=ITEM).history
    ]


def _claimed(client: FakeBeadsClient) -> None:
    stamp = ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host="vps",
        run_id="01RUN",
        factory_name="petri",
        factory_server="http://petri",
    )
    client.update_issue(
        issue_id=ITEM, status="active", assignee="fabro", metadata=claim_stamp_metadata(stamp=stamp)
    )


def test_an_item_with_no_genesis_names_no_repository_and_owes_no_phase(
    client: FakeBeadsClient,
) -> None:
    assert genesis_repository(client=client, item_id=ITEM) is None
    assert sync_repayment_phase(client=client, item_id=ITEM) is None


def test_the_genesis_record_names_the_chain_repository(client: FakeBeadsClient) -> None:
    _repayment_admission(client)
    assert genesis_repository(client=client, item_id=ITEM) == REPOSITORY


def test_a_ready_item_at_repayment_admission_records_repayment_ready(
    client: FakeBeadsClient,
) -> None:
    _repayment_admission(client)
    entry = sync_repayment_phase(client=client, item_id=ITEM)
    assert isinstance(entry, RepaymentEntry)
    assert (entry.reading.attempt.phase, entry.lifecycle_state) == ("repayment-ready", "ready")
    # Nothing more is owed until the factory claims it.
    assert sync_repayment_phase(client=client, item_id=ITEM) is None
    assert _phases(client)[-1] == "repayment-ready"


@pytest.mark.parametrize("ready_first", [True, False])
def test_a_factory_claimed_item_records_every_phase_up_to_repayment_active(
    client: FakeBeadsClient, *, ready_first: bool
) -> None:
    _repayment_admission(client)
    if ready_first:
        _ = sync_repayment_phase(client=client, item_id=ITEM)
    _claimed(client)
    entry = sync_repayment_phase(client=client, item_id=ITEM)
    assert isinstance(entry, RepaymentEntry)
    assert entry.reading.attempt.phase == "repayment-active"
    assert _phases(client)[-3:] == ["repayment-admission", "repayment-ready", "repayment-active"]
    assert sync_repayment_phase(client=client, item_id=ITEM) is None


def test_an_item_still_awaiting_approval_owes_no_phase_yet(client: FakeBeadsClient) -> None:
    _repayment_admission(client)
    client.update_issue(issue_id=ITEM, status="pending-approval")
    assert sync_repayment_phase(client=client, item_id=ITEM) is None
    assert _phases(client)[-1] == "repayment-admission"


def test_a_claim_the_chain_cannot_take_is_refused_by_name(client: FakeBeadsClient) -> None:
    _repayment_admission(client)
    client.update_issue(issue_id=ITEM, status="active", assignee="someone")
    refusal = sync_repayment_phase(client=client, item_id=ITEM)
    assert isinstance(refusal, AuthorityRefusal)
    assert refusal.code == "incident-repayment-claim-missing"


def test_comments_that_are_not_a_genesis_record_name_no_repository(
    client: FakeBeadsClient,
) -> None:
    client.add_comment(issue_id=ITEM, body="an ordinary comment")
    client.add_comment(issue_id=ITEM, body=GENESIS_MARKER + "not a record")
    assert genesis_repository(client=client, item_id=ITEM) is None
    assert sync_repayment_phase(client=client, item_id=ITEM) is None


def test_a_genesis_record_whose_chain_cannot_be_read_is_refused_by_name(
    client: FakeBeadsClient,
) -> None:
    record = {"schema": 1, "repository": REPOSITORY, "item_id": ITEM, "root_token_id": "absent"}
    client.add_comment(issue_id=ITEM, body=GENESIS_MARKER + _json(record))
    refusal = sync_repayment_phase(client=client, item_id=ITEM)
    assert isinstance(refusal, AuthorityRefusal)
    # The admission wrapper turns any such refusal into a named dispatch refusal.
    assert refusal.code == "incident-authority-unavailable"


def test_an_item_whose_record_carries_no_head_hint_owes_admission_no_sync(
    client: FakeBeadsClient,
) -> None:
    client.update_issue(issue_id=ITEM, status="ready", metadata={"rank": "a0"})
    assert repayment_in_play(client=client, item_id=ITEM) is False


def test_an_item_the_chain_has_transitioned_carries_the_hint_and_owes_the_sync(
    client: FakeBeadsClient,
) -> None:
    _repayment_admission(client)
    assert repayment_in_play(client=client, item_id=ITEM) is True


def test_a_record_the_tenant_cannot_serve_owes_the_sync_rather_than_skipping_it(
    client: FakeBeadsClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _down(**_: object) -> dict[str, object]:
        raise BeadsConnectionError(detail="tenant down")

    monkeypatch.setattr(client, "show_issue", _down)
    assert repayment_in_play(client=client, item_id=ITEM) is True
