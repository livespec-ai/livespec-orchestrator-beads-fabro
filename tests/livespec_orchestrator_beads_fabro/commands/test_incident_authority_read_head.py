"""The item-only incident-authority command boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import incident_authority as command
from livespec_orchestrator_beads_fabro.incident_authority import AuthorityRefusal

_REPOSITORY = "owner/repo"
_ITEM = "item-1"


def _head_argv(*, root: Path) -> list[str]:
    return ["read-head", "--repo", str(root), "--repository", _REPOSITORY, "--item", _ITEM]


def _current_argv(*, root: Path, generation: int, operation: str, owner: str) -> list[str]:
    return [
        "read-current",
        "--repo",
        str(root),
        "--repository",
        _REPOSITORY,
        "--item",
        _ITEM,
        "--attempt",
        "attempt-1",
        "--phase",
        "repair",
        "--generation",
        str(generation),
        "--operation",
        operation,
        "--owner",
        owner,
    ]


def _install_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def store_config(**_kwargs: Any) -> None:
        return None

    def make_client(**_kwargs: Any) -> str:
        return "client"

    monkeypatch.setattr(command, "store_config", store_config)
    monkeypatch.setattr(command, "make_beads_client", make_client)


@pytest.mark.parametrize(
    "code",
    [
        "incident-authority-ambiguous",
        "incident-authority-invalid-genesis",
        "incident-authority-cycle",
        "incident-authority-identity-mismatch",
        "incident-authority-item-mismatch",
        "incident-authority-unavailable",
    ],
)
def test_read_head_preserves_canonical_refusals_without_a_phase(
    code: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _install_client(monkeypatch)

    def refuse_head(**_kwargs: Any) -> AuthorityRefusal:
        return AuthorityRefusal(code=code, detail="canonical reader")

    monkeypatch.setattr(
        command,
        "read_incident_head",
        refuse_head,
    )

    assert command.main(argv=_head_argv(root=tmp_path)) == 78

    response = json.loads(capsys.readouterr().out)
    assert response["status"] == "refused"
    assert response["result"]["code"] == code
    assert "phase" not in response["result"]
    assert "generation" not in response["result"]
    assert response["authorizes_current_effects"] is False


def test_read_head_distinguishes_a_missing_genesis_from_a_refusal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _install_client(monkeypatch)

    def missing_head(**_kwargs: Any) -> AuthorityRefusal:
        return AuthorityRefusal(code="incident-authority-missing", detail=_ITEM)

    monkeypatch.setattr(
        command,
        "read_incident_head",
        missing_head,
    )

    assert command.main(argv=_head_argv(root=tmp_path)) == 0

    response = json.loads(capsys.readouterr().out)
    assert response == {
        "authorizes_current_effects": False,
        "normal_factory_proof": False,
        "result": {"item_id": _ITEM, "repository": _REPOSITORY},
        "schema": 1,
        "status": "absent",
    }


def test_read_head_requires_an_item_id(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="2"):
        _ = command.main(argv=["read-head", "--repo", str(tmp_path), "--repository", _REPOSITORY])


@pytest.mark.parametrize(
    ("generation", "operation", "owner"),
    [
        (2, "operation-1", "operator:alice"),
        (1, "operation-2", "operator:alice"),
        (1, "operation-1", "operator:bob"),
    ],
)
def test_read_current_never_authorizes_an_identity_mismatch(
    generation: int,
    operation: str,
    owner: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _install_client(monkeypatch)
    captured: dict[str, Any] = {}

    def refuse(**kwargs: Any) -> AuthorityRefusal:
        captured.update(kwargs)
        return AuthorityRefusal(code="incident-authority-identity-mismatch", detail=_ITEM)

    monkeypatch.setattr(command, "read_incident_authority", refuse)

    assert (
        command.main(
            argv=_current_argv(
                root=tmp_path, generation=generation, operation=operation, owner=owner
            )
        )
        == 78
    )

    response = json.loads(capsys.readouterr().out)
    assert response["result"]["code"] == "incident-authority-identity-mismatch"
    assert response["authorizes_current_effects"] is False
    assert captured["query"] == {
        "attempt_id": "attempt-1",
        "generation": generation,
        "operation_id": operation,
        "owner": owner,
        "phase": "repair",
    }
