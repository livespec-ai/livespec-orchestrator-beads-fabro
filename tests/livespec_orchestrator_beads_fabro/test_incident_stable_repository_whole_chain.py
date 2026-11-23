"""A pre-swap chain is read by stable repository id at every link, not only its genesis."""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-vpuvdy
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro.effects import _incident_repository_identity as identity
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
    read_incident_authority,
)

ITEM = "test-incident"
CALLER = "livespec-ai/livespec-orchestrator-beads-fabro"
RECORDED = "thewoolleyman/livespec-orchestrator-beads-fabro"


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attempt(*, repository: str, generation: int) -> dict[str, Any]:
    return {
        "repository": repository,
        "item_id": ITEM,
        "attempt_id": f"attempt-{generation}",
        "phase": "repair",
        "operation_id": f"operation-{generation}",
        "generation": generation,
        "owner": "operator:alice",
        "base": "a" * 40,
        "head": "b" * 40,
        "pr_number": 7,
        "landed_commits": ["b" * 40],
        "landed_trees": ["c" * 40],
        "original_paths": ["app.py"],
        "deferred_work": ["normal-factory-proof"],
        "repayment_required": True,
    }


def _append(*, client: FakeBeadsClient, token: str, repository: str, generation: int) -> str:
    successor = client.create_no_history_issue(title=TOKEN_TITLE, description="Retained token.")
    payload = {
        "schema": 1,
        "repository": repository,
        "item_id": ITEM,
        "prior_token_id": token,
        "next_token_id": successor,
        "attempt": _attempt(repository=repository, generation=generation),
    }
    client.close_issue_without_verdict(issue_id=token, reason=TRANSITION_MARKER + _json(payload))
    return successor


def _pre_swap_chain(*, genesis_repository: str) -> FakeBeadsClient:
    """Genesis, then a first attempt and a second, every link naming the pre-swap owner."""
    client = FakeBeadsClient()
    client.create_issue(
        draft=IssueDraft(
            issue_id=ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-04T00:00:00Z",
        )
    )
    root = client.create_no_history_issue(title=TOKEN_TITLE, description="Retained token.")
    body = {
        "schema": 1,
        "repository": genesis_repository,
        "item_id": ITEM,
        "root_token_id": root,
    }
    client.add_comment(issue_id=ITEM, body=GENESIS_MARKER + _json(body))
    second = _append(client=client, token=root, repository=RECORDED, generation=1)
    _append(client=client, token=second, repository=RECORDED, generation=2)
    return client


def _ids(mapping: dict[str, str | None]) -> Callable[..., str | None]:
    return lambda *, repository: mapping.get(repository)


def _read(client: FakeBeadsClient) -> IncidentReading | AuthorityRefusal:
    query: dict[str, object] = {
        "attempt_id": "attempt-2",
        "phase": "repair",
        "operation_id": "operation-2",
        "generation": 2,
        "owner": "operator:alice",
    }
    return read_incident_authority(
        client=client, repository=CALLER, item_id=ITEM, query=query, historical=False
    )


def test_a_whole_pre_swap_chain_reads_current_when_every_link_resolves_to_one_stable_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _pre_swap_chain(genesis_repository=RECORDED)
    monkeypatch.setattr(identity, "resolve_repository_id", _ids({RECORDED: "42", CALLER: "42"}))
    reading = _read(client)
    assert isinstance(reading, IncidentReading)
    assert reading.attempt.generation == 2
    assert reading.is_current


@pytest.mark.parametrize("mapping", [{RECORDED: "42", CALLER: "43"}, {RECORDED: "42"}, {}])
def test_a_later_link_naming_another_stable_id_or_an_unreadable_one_still_refuses(
    monkeypatch: pytest.MonkeyPatch, mapping: dict[str, str | None]
) -> None:
    client = _pre_swap_chain(genesis_repository=CALLER)
    monkeypatch.setattr(identity, "resolve_repository_id", _ids(mapping))
    result = _read(client)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-invalid-transition"
