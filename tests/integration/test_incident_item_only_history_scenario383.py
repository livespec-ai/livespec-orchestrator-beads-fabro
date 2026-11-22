"""Scenario 383: an item-only read-history returns every generation of an incident.

The incident authority CLI's `main` is driven with operator arguments against a
retained incident chain seeded in the in-memory tenant exactly as the canonical
transition writer records it (a genesis comment naming the root token, then one
closed token per generation whose close reason carries the successor link and
the generation's attempt snapshot). Only the client factory is stood in, so the
real reader, chain walk and reply path run.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-l4dowx
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro.commands import incident_authority as command

_REPOSITORY = "owner/repository"
_ITEM = "incident-1"
# Two attempts that together recorded five generations; the head is closed.
_GENERATIONS = (
    ("attempt-1", "repair"),
    ("attempt-1", "master-observation"),
    ("attempt-1", "reverting"),
    ("attempt-2", "repayment-admission"),
    ("attempt-2", "closed"),
)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attempt(*, generation: int, attempt_id: str, phase: str) -> dict[str, Any]:
    return dict(
        repository=_REPOSITORY,
        item_id=_ITEM,
        attempt_id=attempt_id,
        phase=phase,
        operation_id=f"operation-{generation}",
        generation=generation,
        owner=f"operator:owner-{generation}",
        base="a" * 40,
        head="b" * 40,
        pr_number=73,
        landed_commits=["c" * 40],
        landed_trees=["d" * 40],
        original_paths=["app.py"],
        deferred_work=["normal-factory-proof"],
        repayment_required=True,
    )


def _item(client: FakeBeadsClient, *, item_id: str) -> None:
    client.create_issue(
        draft=IssueDraft(
            issue_id=item_id,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-04T00:00:00Z",
        )
    )


def _chain(*, generations: tuple[tuple[str, str], ...]) -> FakeBeadsClient:
    client = FakeBeadsClient()
    _item(client, item_id=_ITEM)
    _item(client, item_id="ordinary-1")
    token = client.create_no_history_issue(title=TOKEN_TITLE, description="token")
    client.add_comment(
        issue_id=_ITEM,
        body=GENESIS_MARKER
        + _canonical(dict(schema=1, repository=_REPOSITORY, item_id=_ITEM, root_token_id=token)),
    )
    for generation, (attempt_id, phase) in enumerate(generations, start=1):
        successor = client.create_no_history_issue(title=TOKEN_TITLE, description="token")
        payload = dict(
            schema=1,
            repository=_REPOSITORY,
            item_id=_ITEM,
            prior_token_id=token,
            next_token_id=successor,
            attempt=_attempt(generation=generation, attempt_id=attempt_id, phase=phase),
        )
        client.close_issue_without_verdict(
            issue_id=token, reason=TRANSITION_MARKER + _canonical(payload)
        )
        token = successor
    return client


def _run(
    *,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    client: FakeBeadsClient,
    argv: list[str],
) -> tuple[object, dict[str, Any]]:
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: None)
    monkeypatch.setattr(command, "make_beads_client", lambda **_kwargs: client)
    try:
        code: object = command.main(argv=argv)
    except SystemExit as error:
        code = error.code
    captured = capsys.readouterr()
    return code, json.loads(captured.out) if captured.out else {"stderr": captured.err}


def _item_only(*, root: Path, item_id: str = _ITEM) -> list[str]:
    return ["read-history", "--repo", str(root), "--repository", _REPOSITORY, "--item", item_id]


def _authority_text(client: FakeBeadsClient) -> str:
    """Every authority record the tenant holds: token close reasons and item comments."""
    records = [
        json.dumps(client.show_issue(issue_id=token)) for token in client.no_history_issue_ids()
    ]
    records += [json.dumps(row) for row in client.list_comments(issue_id=_ITEM)]
    return "\n".join(records)


def test_every_generation_of_every_attempt_is_returned_oldest_first(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    client = _chain(generations=_GENERATIONS)
    code, reply = _run(
        monkeypatch=monkeypatch, capsys=capsys, client=client, argv=_item_only(root=tmp_path)
    )
    assert code == 0, reply
    assert reply["status"] == "verified"
    assert reply["authorizes_current_effects"] is False
    assert reply["normal_factory_proof"] is False
    result = reply["result"]
    assert result["repository"] == _REPOSITORY
    assert result["item_id"] == _ITEM
    identities = [
        (
            entry["attempt_id"],
            entry["phase"],
            entry["generation"],
            entry["operation_id"],
            entry["owner"],
        )
        for entry in result["generations"]
    ]
    assert identities == [
        (attempt_id, phase, generation, f"operation-{generation}", f"operator:owner-{generation}")
        for generation, (attempt_id, phase) in enumerate(_GENERATIONS, start=1)
    ]
    assert result["generations"][0]["landed_commits"] == ["c" * 40]


def test_a_closed_head_alone_carries_a_read_time_outstanding_list(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    client = _chain(generations=_GENERATIONS)
    _code, reply = _run(
        monkeypatch=monkeypatch, capsys=capsys, client=client, argv=_item_only(root=tmp_path)
    )
    generations = reply["result"]["generations"]
    assert generations[-1]["outstanding"] == []
    assert all("outstanding" not in entry for entry in generations[:-1])
    assert "outstanding" not in _authority_text(client)

    open_client = _chain(generations=_GENERATIONS[:-1])
    _code, open_reply = _run(
        monkeypatch=monkeypatch, capsys=capsys, client=open_client, argv=_item_only(root=tmp_path)
    )
    assert all("outstanding" not in entry for entry in open_reply["result"]["generations"])


@pytest.mark.parametrize("item_id", ["ordinary-1", "unknown-1"])
def test_an_item_with_no_incident_authority_is_refused_by_name(
    item_id: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    client = _chain(generations=_GENERATIONS)
    code, reply = _run(
        monkeypatch=monkeypatch,
        capsys=capsys,
        client=client,
        argv=_item_only(root=tmp_path, item_id=item_id),
    )
    assert code == 78, reply
    assert reply["status"] == "refused"
    assert reply["result"]["code"] == "incident-authority-missing"
    assert reply["authorizes_current_effects"] is False


def test_a_partial_fence_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    client = _chain(generations=_GENERATIONS)
    code, _reply = _run(
        monkeypatch=monkeypatch,
        capsys=capsys,
        client=client,
        argv=[*_item_only(root=tmp_path), "--attempt", "attempt-1"],
    )
    assert code == 2


def test_the_full_fenced_identity_reads_the_same_historical_generation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    client = _chain(generations=_GENERATIONS)
    fenced = [
        *_item_only(root=tmp_path),
        "--attempt",
        "attempt-1",
        "--phase",
        "master-observation",
        "--operation",
        "operation-2",
        "--generation",
        "2",
        "--owner",
        "operator:owner-2",
    ]
    code, reply = _run(monkeypatch=monkeypatch, capsys=capsys, client=client, argv=fenced)
    assert code == 0, reply
    assert reply["status"] == "verified"
    assert reply["authorizes_current_effects"] is False
    assert sorted(reply["result"]) == [
        "attempt",
        "committed_token_id",
        "current_token_id",
        "is_current",
    ]
    assert reply["result"]["is_current"] is False
    assert reply["result"]["attempt"] == _attempt(
        generation=2, attempt_id="attempt-1", phase="master-observation"
    )
