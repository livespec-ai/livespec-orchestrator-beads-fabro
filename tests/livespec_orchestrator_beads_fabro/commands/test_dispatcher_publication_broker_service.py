"""Tests for the trusted broker's deliberately tiny forge-write surface."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_broker import (
    BrokerRequest,
    PublicationBroker,
    WorkflowLaunch,
    _argv_for,
    refusal_for,
)


@dataclass(kw_only=True)
class _Runner:
    calls: list[tuple[list[str], Path, float, Mapping[str, str | None] | None]] = field(
        default_factory=list
    )

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del stdin
        self.calls.append((argv, cwd, timeout_seconds, env))
        return CommandResult(exit_code=0, stdout="published", stderr="")


def _launch(*, directory: Path | None, stage: str = "proof_verify") -> WorkflowLaunch:
    return WorkflowLaunch(
        stage=stage,
        pull_request_number=73,
        proof_asset_store="proof-assets",
        request_directory=directory,
    )


def test_the_broker_posts_a_new_comment_only_to_the_workflow_pull_request(tmp_path: Path) -> None:
    body = tmp_path / "record.md"
    body.write_text("proof", encoding="utf-8")
    runner = _Runner()
    broker = PublicationBroker(runner=runner, credential=lambda: "broker-secret", cwd=tmp_path)

    result = broker.handle(
        request=BrokerRequest(
            operation="comment",
            claimed_stage="proof_verify",
            pull_request_number=73,
            comment_body=body,
        ),
        launch=_launch(directory=tmp_path),
    )

    assert result.refusal is None
    assert result.command is not None
    assert result.command.exit_code == 0
    assert runner.calls == [
        (
            ["gh", "pr", "comment", "73", "--body-file", str(body)],
            tmp_path,
            120.0,
            {"GH_TOKEN": "broker-secret", "GITHUB_TOKEN": None},
        )
    ]
    assert "credential" not in BrokerRequest.__dataclass_fields__


def test_the_broker_uploads_only_to_the_workflow_proof_asset_store(tmp_path: Path) -> None:
    asset = tmp_path / "proof.txt"
    asset.write_text("proof", encoding="utf-8")
    runner = _Runner()
    broker = PublicationBroker(runner=runner, credential=lambda: "broker-secret", cwd=tmp_path)

    result = broker.handle(
        request=BrokerRequest(
            operation="proof_asset",
            claimed_stage="proof_verify",
            pull_request_number=73,
            proof_asset=asset,
            proof_asset_name="run-proof.txt",
            proof_asset_store="proof-assets",
        ),
        launch=_launch(directory=tmp_path),
    )

    assert result.refusal is None
    assert runner.calls[0][0] == [
        "gh",
        "release",
        "upload",
        "proof-assets",
        f"{asset}#run-proof.txt",
        "--clobber",
    ]


@pytest.mark.parametrize("operation", ["merge", "ready", "edit"])
def test_publication_operations_other_than_comments_and_assets_are_refused(operation: str) -> None:
    refusal = refusal_for(
        request=BrokerRequest(
            operation=operation,
            claimed_stage="proof_verify",
            pull_request_number=73,
        ),
        launch=_launch(directory=None),
    )

    assert refusal is not None
    assert operation in refusal
    assert "only" in refusal


@pytest.mark.parametrize(
    ("broker_request", "launch", "expected"),
    [
        (
            BrokerRequest(operation="comment", claimed_stage="review", pull_request_number=73),
            _launch(directory=None),
            "claimed stage",
        ),
        (
            BrokerRequest(
                operation="comment", claimed_stage="proof_verify", pull_request_number=74
            ),
            _launch(directory=None),
            "pull request",
        ),
        (
            BrokerRequest(operation="comment", claimed_stage="pr", pull_request_number=73),
            _launch(directory=None),
            "workflow",
        ),
        (
            BrokerRequest(operation="comment", claimed_stage="pr", pull_request_number=73),
            _launch(directory=None, stage="pr"),
            "no broker publication authority",
        ),
    ],
)
def test_workflow_authority_refuses_forged_or_unsupported_targets(
    broker_request: BrokerRequest,
    launch: WorkflowLaunch,
    expected: str,
) -> None:
    refusal = refusal_for(request=broker_request, launch=launch)

    assert refusal is not None
    assert expected in refusal


def test_content_must_be_complete_and_staged_in_the_workflow_directory(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.md"
    launch = _launch(directory=tmp_path)
    requests = (
        BrokerRequest(operation="comment", claimed_stage="proof_verify", pull_request_number=73),
        BrokerRequest(
            operation="comment",
            claimed_stage="proof_verify",
            pull_request_number=73,
            comment_body=outside,
        ),
        BrokerRequest(
            operation="proof_asset",
            claimed_stage="proof_verify",
            pull_request_number=73,
            proof_asset_store="other-store",
        ),
        BrokerRequest(
            operation="proof_asset",
            claimed_stage="proof_verify",
            pull_request_number=73,
            proof_asset_store="proof-assets",
        ),
        BrokerRequest(
            operation="proof_asset",
            claimed_stage="proof_verify",
            pull_request_number=73,
            proof_asset=outside,
            proof_asset_name="proof.txt",
            proof_asset_store="proof-assets",
        ),
    )

    refusals = [refusal_for(request=request, launch=launch) for request in requests]

    assert all(refusal is not None for refusal in refusals)
    assert "no staged comment body" in str(refusals[0])
    assert "outside" in str(refusals[1])
    assert "other-store" in str(refusals[2])
    assert "asset path and name" in str(refusals[3])
    assert "outside" in str(refusals[4])


def test_asset_upload_requires_the_store_the_workflow_supplied(tmp_path: Path) -> None:
    asset = tmp_path / "proof.txt"
    request = BrokerRequest(
        operation="proof_asset",
        claimed_stage="proof_verify",
        pull_request_number=73,
        proof_asset=asset,
        proof_asset_name="proof.txt",
    )
    launch = WorkflowLaunch(
        stage="proof_verify",
        pull_request_number=73,
        request_directory=tmp_path,
    )

    refusal = refusal_for(request=request, launch=launch)

    assert refusal is not None
    assert "no proof asset store" in refusal


def test_execution_fails_closed_without_a_workflow_owned_directory(tmp_path: Path) -> None:
    used_credential = False

    def credential() -> str:
        nonlocal used_credential
        used_credential = True
        return "broker-secret"

    result = PublicationBroker(runner=_Runner(), credential=credential, cwd=tmp_path).handle(
        request=BrokerRequest(
            operation="comment",
            claimed_stage="proof_verify",
            pull_request_number=73,
            comment_body=tmp_path / "record.md",
        ),
        launch=_launch(directory=None),
    )

    assert result.command is None
    assert result.refusal is not None
    assert "workflow supplied no broker-owned request directory" in result.refusal
    assert not used_credential


def test_a_refusal_never_asks_the_broker_for_its_credential(tmp_path: Path) -> None:
    def credential() -> str:
        raise AssertionError("a refused request must not read the credential")

    result = PublicationBroker(runner=_Runner(), credential=credential, cwd=tmp_path).handle(
        request=BrokerRequest(
            operation="comment",
            claimed_stage="review",
            pull_request_number=73,
        ),
        launch=_launch(directory=tmp_path),
    )

    assert result.command is None
    assert result.refusal is not None
    assert "claimed stage" in result.refusal


def test_private_argv_builder_rejects_an_impossible_authorized_request(tmp_path: Path) -> None:
    launch = _launch(directory=tmp_path)
    with pytest.raises(ValueError, match=r"^$"):
        _ = _argv_for(
            request=BrokerRequest(
                operation="comment",
                claimed_stage="proof_verify",
                pull_request_number=73,
            ),
            launch=launch,
        )
    with pytest.raises(ValueError, match=r"^$"):
        _ = _argv_for(
            request=BrokerRequest(
                operation="proof_asset",
                claimed_stage="proof_verify",
                pull_request_number=73,
                proof_asset_name="proof.txt",
            ),
            launch=launch,
        )
    with pytest.raises(ValueError, match=r"^$"):
        _ = _argv_for(
            request=BrokerRequest(
                operation="proof_asset",
                claimed_stage="proof_verify",
                pull_request_number=73,
                proof_asset=tmp_path / "proof.txt",
                proof_asset_name="proof.txt",
            ),
            launch=WorkflowLaunch(
                stage="proof_verify",
                pull_request_number=73,
                request_directory=tmp_path,
            ),
        )
