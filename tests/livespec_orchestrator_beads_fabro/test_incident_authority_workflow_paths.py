"""An attempt's optional workflow_paths list is written only by an attested receipt."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
    attempt_record,
    decode_attempt,
)
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
    attest_incident_workflow_paths,
    commit_incident_transition,
    read_incident_authority,
)

REPOSITORY = "owner/repository"
ITEM = "test-incident"
WORKFLOW = ".github/workflows/ci.yml"
PATHS = (WORKFLOW,)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attempt(**changes: Any) -> dict[str, Any]:
    return (
        dict(
            repository=REPOSITORY,
            item_id=ITEM,
            attempt_id="attempt-1",
            phase="repair",
            operation_id="operation-1",
            generation=1,
            owner="operator:alice",
            base="a" * 40,
            head="b" * 40,
            pr_number=0,
            landed_commits=[],
            landed_trees=[],
            original_paths=["app.py", WORKFLOW],
            deferred_work=["normal-factory-proof"],
            repayment_required=True,
            carrier=dict(
                state="branch-reserved",
                target_ref="refs/heads/incident/test-incident-attempt-1",
                input_parent="a" * 40,
                staged_tree="c" * 40,
            ),
        )
        | changes
    )


def _query(attempt: dict[str, Any]) -> dict[str, object]:
    return {k: attempt[k] for k in ("attempt_id", "phase", "operation_id", "generation", "owner")}


def _chain(snapshot: dict[str, Any]) -> FakeBeadsClient:
    client = FakeBeadsClient()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-05T00:00:00Z",
        )
    )
    root = client.create_no_history_issue(title=TOKEN_TITLE, description="authority")
    current = client.create_no_history_issue(title=TOKEN_TITLE, description="authority")
    _ = client.add_comment(
        issue_id=ITEM,
        body=GENESIS_MARKER
        + _json(dict(schema=1, repository=REPOSITORY, item_id=ITEM, root_token_id=root)),
    )
    payload = dict(
        schema=1,
        repository=REPOSITORY,
        item_id=ITEM,
        prior_token_id=root,
        next_token_id=current,
        attempt=snapshot,
    )
    _ = client.close_issue_without_verdict(issue_id=root, reason=TRANSITION_MARKER + _json(payload))
    return client


def _observed() -> tuple[FakeBeadsClient, IncidentReading]:
    snapshot = _attempt()
    client = _chain(snapshot)
    observed = read_incident_authority(
        client=client, repository=REPOSITORY, item_id=ITEM, query=_query(snapshot)
    )
    assert isinstance(observed, IncidentReading)
    return client, observed


def _paths(attempt: object) -> object:
    return getattr(attempt, "workflow_paths", None)


def _successor(
    observed: IncidentReading, *, generation: int = 2, **changes: Any
) -> IncidentAttempt:
    return replace(
        observed.attempt, generation=generation, operation_id=f"operation-{generation}", **changes
    )


def test_a_workflow_paths_record_decodes_and_serializes_back_to_identical_bytes() -> None:
    snapshot = _attempt(workflow_paths=[WORKFLOW])
    decoded = decode_attempt(value=snapshot)
    facts = [
        _paths(decoded) == PATHS,
        decoded is not None and _json(attempt_record(attempt=decoded)) == _json(snapshot),
    ]
    assert all(facts)


def test_a_record_without_workflow_paths_decodes_empty_and_omits_the_key() -> None:
    snapshot = _attempt()
    decoded = decode_attempt(value=snapshot)
    facts = [
        _paths(decoded) == (),
        decoded is not None and "workflow_paths" not in attempt_record(attempt=decoded),
        decoded is not None and _json(attempt_record(attempt=decoded)) == _json(snapshot),
    ]
    assert all(facts)


@pytest.mark.parametrize(
    "paths",
    [
        [],
        ["app.py"],
        [".github/workflows/"],
        [".github/workflows/../x.yml"],
        [".github/workflows/other.yml"],
        [WORKFLOW, WORKFLOW],
        [7],
        "not-a-list",
    ],
)
def test_a_malformed_or_unscoped_workflow_paths_list_is_not_an_attempt(paths: object) -> None:
    assert decode_attempt(value=_attempt(workflow_paths=paths)) is None


def test_an_agent_written_transition_cannot_add_workflow_paths() -> None:
    client, observed = _observed()
    result = commit_incident_transition(
        client=client, observed=observed, successor=_successor(observed, workflow_paths=PATHS)
    )
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-transition-invalid-successor"


def test_an_attested_receipt_writes_workflow_paths_on_the_next_generation() -> None:
    client, observed = _observed()
    result = attest_incident_workflow_paths(
        client=client, observed=observed, successor=_successor(observed, workflow_paths=PATHS)
    )
    assert isinstance(result, IncidentReading)
    assert _paths(result.attempt) == PATHS
    assert result.is_current


def test_an_attestation_with_no_paths_is_refused() -> None:
    client, observed = _observed()
    result = attest_incident_workflow_paths(
        client=client, observed=observed, successor=_successor(observed)
    )
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-transition-invalid-successor"


def test_the_attestation_is_current_only_for_the_generation_that_recorded_it() -> None:
    client, observed = _observed()
    attested = attest_incident_workflow_paths(
        client=client, observed=observed, successor=_successor(observed, workflow_paths=PATHS)
    )
    assert isinstance(attested, IncidentReading)
    carried = commit_incident_transition(
        client=client,
        observed=attested,
        successor=_successor(attested, generation=3, workflow_paths=PATHS),
    )
    cleared = commit_incident_transition(
        client=client,
        observed=attested,
        successor=_successor(attested, generation=3, workflow_paths=()),
    )
    history = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=ITEM,
        query=_query(attempt_record(attempt=attested.attempt)),
        historical=True,
    )
    facts = [
        isinstance(carried, AuthorityRefusal),
        isinstance(cleared, IncidentReading),
        isinstance(cleared, IncidentReading) and _paths(cleared.attempt) == (),
        isinstance(history, IncidentReading) and not history.is_current,
        isinstance(history, IncidentReading) and _paths(history.attempt) == PATHS,
    ]
    assert all(facts)
