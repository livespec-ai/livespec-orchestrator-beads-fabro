"""Receipt-only workflow authorization preserves its distinct refusal paths."""

from __future__ import annotations

from dataclasses import replace

import pytest
from livespec_orchestrator_beads_fabro._incident_authority_types import AuthorityRefusal
from livespec_orchestrator_beads_fabro.effects import _incident_authority_transition as transition
from livespec_orchestrator_beads_fabro.incident_authority import (
    HumanAttestedWorkflowReceipt,
    IncidentReading,
    attest_workflow_paths,
    commit_incident_transition,
)

from tests.livespec_orchestrator_beads_fabro.test_incident_authority_cases import (
    ITEM,
    _chain,
    _read,
)


def _receipt(*, operation_id: str = "human-attestation-1") -> HumanAttestedWorkflowReceipt:
    return HumanAttestedWorkflowReceipt(
        operation_id=operation_id,
        workflow_paths=(".github/workflows/incident.yml",),
    )


def test_attestation_rejects_an_empty_workflow_scope() -> None:
    client, _, _ = _chain()
    observed = _read(client)
    assert isinstance(observed, IncidentReading)

    result = attest_workflow_paths(
        client=client,
        observed=observed,
        receipt=HumanAttestedWorkflowReceipt(
            operation_id="human-attestation-empty", workflow_paths=()
        ),
    )

    assert result == AuthorityRefusal(code="incident-workflow-attestation-invalid", detail=ITEM)


def test_attestation_replays_or_refuses_the_same_operation_id() -> None:
    client, _, _ = _chain()
    observed = _read(client)
    assert isinstance(observed, IncidentReading)
    receipt = _receipt()

    recorded = attest_workflow_paths(client=client, observed=observed, receipt=receipt)
    replayed = attest_workflow_paths(client=client, observed=observed, receipt=receipt)

    assert isinstance(recorded, IncidentReading)
    assert replayed == recorded
    conflict = attest_workflow_paths(
        client=client,
        observed=observed,
        receipt=HumanAttestedWorkflowReceipt(
            operation_id=receipt.operation_id,
            workflow_paths=(".github/workflows/other.yml",),
        ),
    )
    assert conflict == AuthorityRefusal(
        code="incident-workflow-attestation-operation-conflict",
        detail=receipt.operation_id,
    )


def test_attestation_refuses_stale_or_reused_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _ = _chain()
    observed = _read(client)
    assert isinstance(observed, IncidentReading)
    advanced = commit_incident_transition(
        client=client,
        observed=observed,
        successor=replace(
            observed.attempt,
            generation=2,
            operation_id="agent-transition-2",
            workflow_paths=(),
        ),
    )
    assert isinstance(advanced, IncidentReading)

    stale = attest_workflow_paths(client=client, observed=observed, receipt=_receipt())

    assert stale == AuthorityRefusal(code="incident-generation-stale", detail=ITEM)
    reused = attest_workflow_paths(
        client=client,
        observed=advanced,
        receipt=_receipt(operation_id="agent-transition-2"),
    )
    assert reused == AuthorityRefusal(
        code="incident-workflow-attestation-operation-reused",
        detail="agent-transition-2",
    )

    monkeypatch.setattr(
        transition,
        "read_history",
        lambda **_: AuthorityRefusal(code="history-unavailable", detail=ITEM),
    )
    unavailable = attest_workflow_paths(
        client=client,
        observed=advanced,
        receipt=_receipt(operation_id="human-attestation-2"),
    )
    assert unavailable == AuthorityRefusal(code="history-unavailable", detail=ITEM)
