"""Boundary coverage for the split incident-authority command helpers."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-l4dowx
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _incident_authority_arguments as arguments
from livespec_orchestrator_beads_fabro.commands import _incident_authority_reply as replies
from livespec_orchestrator_beads_fabro.commands import incident_authority as command
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro.incident_normal_repayment import RepaymentEntry


def _identity(*, action: str, root: Path) -> list[str]:
    return [
        action,
        "--repo",
        str(root),
        "--repository",
        "owner/repo",
        "--item",
        "item-1",
        "--attempt",
        "attempt-1",
        "--phase",
        "repair",
        "--operation",
        "operation-1",
        "--generation",
        "1",
        "--owner",
        "operator:alice",
    ]


def _attempt(*, phase: str = "repair") -> IncidentAttempt:
    return IncidentAttempt(
        repository="owner/repo",
        item_id="item-1",
        attempt_id="attempt-1",
        phase=phase,
        operation_id="operation-1",
        generation=1,
        owner="operator:alice",
        base="a" * 40,
        head="b" * 40,
        pr_number=7,
        landed_commits=("b" * 40,),
        landed_trees=("c" * 40,),
        original_paths=("app.py",),
        deferred_work=(),
        repayment_required=True,
    )


def test_argument_parser_preserves_the_fenced_and_item_only_forms(tmp_path: Path) -> None:
    """Only history may omit the attempt fence, while filings retain their distinct form."""
    item_only = arguments.parse(
        argv=[
            "read-history",
            "--repo",
            str(tmp_path),
            "--repository",
            "owner/repo",
            "--item",
            "item-1",
        ]
    )
    assert arguments.item_only_history(args=item_only)
    assert not arguments.item_only_history(
        args=arguments.parse(argv=_identity(action="read-history", root=tmp_path))
    )

    filing = arguments.parse(
        argv=[
            "file-incident",
            "--repo",
            str(tmp_path),
            "--repository",
            "owner/repo",
            "--operation",
            "operation-1",
            "--owner",
            "operator:alice",
            "--filing-json",
            "{}",
        ]
    )
    assert filing.action == "file-incident"
    assert arguments.parse(
        argv=[*_identity(action="record-local-gates", root=tmp_path), "--receipt-stdin"]
    ).receipt_stdin


def test_argument_parser_refuses_malformed_identity_and_action_forms(tmp_path: Path) -> None:
    """Argument validation rejects every form that could blur an authority fence."""
    forms = [
        [*_identity(action="record-local-gates", root=tmp_path)],
        [*_identity(action="read-current", root=tmp_path), "--receipt-stdin"],
        [
            "file-incident",
            "--repo",
            str(tmp_path),
            "--repository",
            "owner/repo",
            "--operation",
            "operation-1",
            "--filing-json",
            "{}",
        ],
        [
            "file-incident",
            "--repo",
            str(tmp_path),
            "--repository",
            "owner/repo",
            "--item",
            "item-1",
            "--operation",
            "operation-1",
            "--owner",
            "operator:alice",
            "--filing-json",
            "{}",
        ],
        [
            value
            for index, value in enumerate(_identity(action="read-current", root=tmp_path))
            if index not in (5, 6)
        ],
        [
            value
            for index, value in enumerate(_identity(action="read-current", root=tmp_path))
            if index not in (15, 16)
        ],
        [*_identity(action="read-current", root=tmp_path), "--admission-complete"],
        [*_identity(action="read-current", root=tmp_path), "--successor-json", "{}"],
    ]
    for argv in forms:
        with pytest.raises(SystemExit, match="2"):
            _ = arguments.parse(argv=argv)


def test_item_only_history_refuses_a_missing_authority_by_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """An item with no authority keeps its named refusal through the item-only reply."""

    def store_config(**_kwargs: Any) -> None:
        return None

    def make_client(**_kwargs: Any) -> str:
        return "client"

    def missing_history(**_kwargs: Any) -> AuthorityRefusal:
        return AuthorityRefusal(code="incident-authority-missing", detail="item-1")

    monkeypatch.setattr(command, "store_config", store_config)
    monkeypatch.setattr(command, "make_beads_client", make_client)
    monkeypatch.setattr(
        command,
        "read_incident_history",
        missing_history,
    )
    assert (
        command.main(
            argv=[
                "read-history",
                "--repo",
                str(tmp_path),
                "--repository",
                "owner/repo",
                "--item",
                "item-1",
            ]
        )
        == 78
    )
    assert json.loads(capsys.readouterr().out)["result"]["code"] == "incident-authority-missing"


def test_history_reply_keeps_open_generations_without_closure_obligations(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Only the final closed generation receives a read-time outstanding list."""
    assert replies.history_reply(history=(_attempt(),)) == 0
    generation = json.loads(capsys.readouterr().out)["result"]["generations"][0]
    assert "outstanding" not in generation


def test_lifecycle_reply_keeps_the_attempt_in_its_reading(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A split reply helper preserves the lifecycle reply's retained attempt."""
    attempt = _attempt()
    token = "token-1"
    assert (
        replies.reply(
            result=RepaymentEntry(
                reading=IncidentReading(
                    attempt=attempt,
                    committed_token_id=token,
                    current_token_id=token,
                    is_current=True,
                ),
                operation_id="operation-2",
                lifecycle_state="backlog",
                recovered=False,
            ),
            authorizes=False,
        )
        == 0
    )
    assert (
        json.loads(capsys.readouterr().out)["result"]["reading"]["attempt"]["item_id"] == "item-1"
    )
