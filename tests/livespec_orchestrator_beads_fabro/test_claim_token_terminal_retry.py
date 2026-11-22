"""Terminal claim writers must prove their successor landed before succeeding."""

from __future__ import annotations

from typing import Any

import pytest
from livespec_orchestrator_beads_fabro import _store_claim_tokens as claim_tokens
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    change_claim,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError

_ITEM_ID = "bd-ib-claim-token-terminal-retry"


def _client_with_current_token() -> tuple[FakeBeadsClient, str]:
    client = FakeBeadsClient()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM_ID,
            issue_type="task",
            title="A terminally written slice",
            description="Complete the slice.",
            assignee="fabro",
            created_at="2026-11-05T00:00:00Z",
        )
    )
    client.update_issue(issue_id=_ITEM_ID, status="active")
    token = create_claim_token(client=client)
    client.update_issue(
        issue_id=_ITEM_ID,
        metadata={CLAIM_TOKEN_METADATA_KEY: token},
        names_claim_token=True,
    )
    return client, token


def test_terminal_writer_refuses_a_transition_that_never_reads_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bounded terminal writer reports the exact stranded transition loudly."""
    client, token = _client_with_current_token()
    update = client.update_issue
    attempts = [0]

    def _drop_item_write(**fields: Any) -> None:
        if fields["issue_id"] == _ITEM_ID:
            attempts[0] += 1
            return
        update(**fields)

    def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(client, "update_issue", _drop_item_write)
    monkeypatch.setattr(claim_tokens.time, "sleep", _no_sleep)

    outcome = change_claim(
        client=client,
        work_item_id=_ITEM_ID,
        writer="dispatcher-terminal",
        intent="complete",
        claim_tokens=True,
        status="acceptance",
        clock=lambda: 0.0,
    )

    assert attempts == [3]
    assert outcome.outcome.startswith("claim-transition-unlanded:")
    assert f"item={_ITEM_ID}" in outcome.outcome
    assert f"closed-token={token}" in outcome.outcome
    assert outcome.successor_token_id is not None
    assert f"successor={outcome.successor_token_id}" in outcome.outcome
    assert client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY] == token


def test_terminal_writer_retries_when_its_read_back_is_temporarily_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unavailable read-back does not turn an ambiguous write into success."""
    client, _token = _client_with_current_token()
    show = client.show_issue
    reads = [0]

    def _unavailable_once(*, issue_id: str) -> dict[str, Any]:
        if issue_id == _ITEM_ID:
            reads[0] += 1
            if reads[0] == 3:
                raise BeadsConnectionError(detail="read-back unavailable")
        return show(issue_id=issue_id)

    def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(client, "show_issue", _unavailable_once)
    monkeypatch.setattr(claim_tokens.time, "sleep", _no_sleep)

    outcome = change_claim(
        client=client,
        work_item_id=_ITEM_ID,
        writer="dispatcher-terminal",
        intent="complete",
        claim_tokens=True,
        status="acceptance",
        clock=lambda: 0.0,
    )

    assert outcome.outcome == "applied"
    assert reads[0] >= 4


def test_terminal_writer_refuses_when_its_lease_ends_before_the_item_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The terminal writer does not issue a retry outside its claim lease."""
    client, token = _client_with_current_token()
    ticks = iter((0.0, 0.0, 120.0))

    def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(claim_tokens.time, "sleep", _no_sleep)

    outcome = change_claim(
        client=client,
        work_item_id=_ITEM_ID,
        writer="dispatcher-terminal",
        intent="complete",
        claim_tokens=True,
        status="acceptance",
        clock=lambda: next(ticks),
    )

    assert outcome.outcome.startswith("claim-transition-unlanded:")
    assert f"closed-token={token}" in outcome.outcome
    assert client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY] == token
