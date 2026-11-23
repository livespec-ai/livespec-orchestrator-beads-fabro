"""A pre-swap genesis is read by stable repository id, and an unreadable one still refuses."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import AuthorityRefusal
from livespec_orchestrator_beads_fabro.effects import _incident_repository_identity as identity
from livespec_orchestrator_beads_fabro.effects._incident_authority_chain import read_genesis

ITEM = "test-incident"
CALLER = "livespec-ai/livespec-orchestrator-beads-fabro"
RECORDED = "thewoolleyman/livespec-orchestrator-beads-fabro"


def _client_with_genesis(*, repository: str) -> tuple[FakeBeadsClient, str]:
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
    body = {"schema": 1, "repository": repository, "item_id": ITEM, "root_token_id": root}
    client.add_comment(
        issue_id=ITEM, body=GENESIS_MARKER + json.dumps(body, sort_keys=True, separators=(",", ":"))
    )
    return client, root


def _ids(mapping: dict[str, str | None]) -> Callable[..., str | None]:
    return lambda *, repository: mapping.get(repository)


def test_a_pre_swap_genesis_is_read_when_both_names_resolve_to_one_stable_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, root = _client_with_genesis(repository=RECORDED)
    monkeypatch.setattr(identity, "resolve_repository_id", _ids({RECORDED: "42", CALLER: "42"}))
    result = read_genesis(client=client, repository=CALLER, item_id=ITEM)
    assert not isinstance(result, AuthorityRefusal)
    assert result[0] == root


@pytest.mark.parametrize(
    "mapping",
    [
        {RECORDED: "42", CALLER: "43"},
        {RECORDED: None, CALLER: "42"},
        {RECORDED: "42", CALLER: None},
        {},
    ],
)
def test_a_genesis_whose_stable_id_differs_or_is_unreadable_still_refuses(
    monkeypatch: pytest.MonkeyPatch, mapping: dict[str, str | None]
) -> None:
    client, _root = _client_with_genesis(repository=RECORDED)
    monkeypatch.setattr(identity, "resolve_repository_id", _ids(mapping))
    result = read_genesis(client=client, repository=CALLER, item_id=ITEM)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-invalid-genesis"


def test_a_genesis_naming_another_repository_name_is_refused_without_a_forge_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _root = _client_with_genesis(repository="thewoolleyman/another-repository")

    def boom(*, repository: str) -> str:
        raise AssertionError(repository)

    monkeypatch.setattr(identity, "resolve_repository_id", boom)
    result = read_genesis(client=client, repository=CALLER, item_id=ITEM)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-invalid-genesis"


def test_the_same_repository_check_is_exact_for_equal_names() -> None:
    assert identity.same_repository(recorded=CALLER, caller=CALLER)
