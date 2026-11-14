"""Admission keeps an incident repayment's chain in step with the factory claim.

bd-ib-wz6bsa, Definition-of-Done bullets 1, 2 and 4. The Dispatcher's admission
of a `ready` item is the one path every repayment takes to a factory run, the
explicit `approve` valve and an automatic approval alike, so the phase writes
sit around that admission: `repayment-ready` is recorded before the claim is
taken, and `repayment-active` once the item rests `active` under the claim.
A path that cannot record the phase refuses the dispatch by name. Each case
drives `admit_with_repayment_phase` over an in-memory tenant whose chain the
canonical genesis and transition writers recorded; the claim itself is a fake
`admit` that writes what ordinary admission writes.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import decode_attempt
from livespec_orchestrator_beads_fabro._incident_genesis import decode_genesis_request
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    ClaimStamp,
    claim_stamp_metadata,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_incident_repayment_admit as admission,
)
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
    commit_incident_transition,
    publish_incident_genesis,
    read_incident_authority,
)
from livespec_orchestrator_beads_fabro.incident_completion import read_incident_standing

REPOSITORY = "owner/repository"
ITEM = "test-incident"
PRINCIPAL = "operator:alice"
REPAIR_REF = "refs/heads/incident/test-incident-attempt-1"
REPAYMENT_REF = "refs/heads/feat/test-incident"
REPAIR_HEAD = "d" * 40
_IDENTITY = ("attempt_id", "phase", "operation_id", "generation", "owner")
# The tenant client is injected, so no store configuration is ever read.
_NO_CONFIG: Any = None


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


class _Claim:
    """What ordinary admission writes: `active`, assigned `fabro`, under a factory stamp."""

    def __init__(self, client: FakeBeadsClient, refusal: str | None = None) -> None:
        self.client = client
        self.refusal = refusal
        self.calls = 0
        self.chain_at_claim: list[str] = []

    def __call__(self, **_: object) -> str | None:
        self.calls += 1
        self.chain_at_claim = _phases(self.client)
        if self.refusal is not None:
            return self.refusal
        stamp = ClaimStamp(
            dispatch_id="01DISPATCH",
            dispatching_host="vps",
            run_id="01RUN",
            factory_name="petri",
            factory_server="http://petri",
        )
        self.client.update_issue(
            issue_id=ITEM,
            status="active",
            assignee="fabro",
            metadata=claim_stamp_metadata(stamp=stamp),
        )
        return None


def _admit(client: FakeBeadsClient, claim: _Claim) -> str | None:
    return admission.admit_with_repayment_phase(
        client=client, item_id=ITEM, admit=claim, config=_NO_CONFIG
    )


def test_admission_records_repayment_ready_before_the_claim_and_repayment_active_after_it(
    client: FakeBeadsClient,
) -> None:
    _repayment_admission(client)
    claim = _Claim(client)
    assert _admit(client, claim) is None
    assert claim.calls == 1
    # Bullet 1: the approval's phase is in the chain before any factory claim is taken.
    assert claim.chain_at_claim[-1] == "repayment-ready"
    # Bullet 2: the claim's phase is in the chain before the run starts.
    assert _phases(client)[-3:] == ["repayment-admission", "repayment-ready", "repayment-active"]
    # Admission's own lifecycle write is untouched.
    assert client.show_issue(issue_id=ITEM)["status"] == "active"


def test_an_item_with_no_incident_authority_is_admitted_exactly_as_before(
    client: FakeBeadsClient,
) -> None:
    client.update_issue(issue_id=ITEM, status="ready")
    claim = _Claim(client)
    assert _admit(client, claim) is None
    assert claim.calls == 1
    assert not any(
        str(comment.get("text", "")).startswith("livespec-incident")
        for comment in client.list_comments(issue_id=ITEM)
    )


def test_a_claim_refusal_is_returned_unchanged(client: FakeBeadsClient) -> None:
    _repayment_admission(client)
    claim = _Claim(client, refusal="claim-lost")
    assert _admit(client, claim) == "claim-lost"
    assert _phases(client)[-1] == "repayment-ready"


@pytest.mark.parametrize("when", ["before", "after"])
def test_a_phase_the_chain_cannot_record_refuses_the_dispatch_by_name(
    client: FakeBeadsClient, monkeypatch: pytest.MonkeyPatch, when: str
) -> None:
    _repayment_admission(client)
    real_sync = admission.sync_repayment_phase
    seen: list[str] = []

    def sync(**kwargs: Any) -> object:
        seen.append(str(client.show_issue(issue_id=ITEM)["status"]))
        refused = (when == "before") == (len(seen) == 1)
        if refused:
            return AuthorityRefusal(code="incident-authority-unavailable", detail="tenant down")
        return real_sync(**kwargs)

    monkeypatch.setattr(admission, "sync_repayment_phase", sync)
    claim = _Claim(client)
    refusal = _admit(client, claim)
    assert refusal is not None
    assert refusal.startswith("incident-repayment-phase-unrecorded")
    assert "incident-authority-unavailable" in refusal
    assert ITEM in refusal
    # A refusal before the claim takes no claim at all.
    assert claim.calls == (0 if when == "before" else 1)
