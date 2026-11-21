"""The credential-owning broker for an agent stage's narrow forge writes.

The broker is Dispatcher-materialized tooling, launched by the workflow beside an
agent node rather than by that node.  Consequently an agent never receives the
credential and cannot select the authority under which a request runs.  A client
can describe content to publish, but its claimed stage, pull-request number and
proof-asset store are checked against the ``WorkflowLaunch`` that the workflow
gave the broker.  The service uses that launch record, not request values, when
it finally constructs a forge command.

This module intentionally does not wire an agent-facing client.  The following
broker-routing item supplies that transport.  Keeping the policy here pure and
small means routing cannot accidentally turn an untrusted request field into a
publication capability.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import (
    CommandResult,
    CommandRunner,
)

__all__: list[str] = [
    "BrokerRequest",
    "BrokerResult",
    "PublicationBroker",
    "WorkflowLaunch",
    "refusal_for",
]

BrokerOperation = Literal["comment", "proof_asset"]

# These are the only agent nodes whose contracts currently require a forge
# write.  Command stages publish through their own scripted steps, never here.
_SERVED_STAGES = frozenset(("proof_capture", "proof_verify", "review"))
_SUPPORTED_OPERATIONS = frozenset(("comment", "proof_asset"))
_BROKER_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True, kw_only=True)
class BrokerRequest:
    """Untrusted request content received from an agent-stage client.

    The request deliberately contains no credential.  ``claimed_stage``,
    ``pull_request_number`` and ``proof_asset_store`` are retained only so the
    broker can reject a forged or cross-run request; none is used as authority.
    """

    operation: str
    claimed_stage: str
    pull_request_number: int
    comment_body: Path | None = None
    proof_asset: Path | None = None
    proof_asset_name: str | None = None
    proof_asset_store: str | None = None


@dataclass(frozen=True, kw_only=True)
class WorkflowLaunch:
    """The immutable publication authority supplied by the workflow launcher.

    ``request_directory`` is broker-owned staging, not the run checkout.  It
    prevents a request from using a path traversal to make the credential-owning
    process post or upload an arbitrary host file.
    """

    stage: str
    pull_request_number: int
    proof_asset_store: str | None = None
    request_directory: Path | None = None


@dataclass(frozen=True, kw_only=True)
class BrokerResult:
    """One broker response, with a refusal before every denied forge call."""

    command: CommandResult | None = None
    refusal: str | None = None


def refusal_for(*, request: BrokerRequest, launch: WorkflowLaunch) -> str | None:
    """Return a policy refusal, or ``None`` only for a launch-authorized write."""
    if request.operation not in _SUPPORTED_OPERATIONS:
        return (
            "publication broker refused operation "
            f"{request.operation!r}: only a new comment or a proof-asset upload is allowed"
        )
    if launch.stage not in _SERVED_STAGES:
        return (
            "publication broker refused workflow stage "
            f"{launch.stage!r}: that workflow stage has no broker publication authority"
        )
    if request.claimed_stage != launch.stage:
        return (
            "publication broker refused claimed stage "
            f"{request.claimed_stage!r}: the workflow launched {launch.stage!r}"
        )
    if request.pull_request_number != launch.pull_request_number:
        return (
            "publication broker refused pull request "
            f"#{request.pull_request_number}: the workflow launched pull request "
            f"#{launch.pull_request_number}"
        )
    if request.operation == "comment":
        return _comment_refusal(request=request, launch=launch)
    return _asset_refusal(request=request, launch=launch)


def _comment_refusal(*, request: BrokerRequest, launch: WorkflowLaunch) -> str | None:
    if request.comment_body is None:
        return "publication broker refused comment: no staged comment body was supplied"
    return _staged_path_refusal(
        path=request.comment_body,
        launch=launch,
        kind="comment body",
    )


def _asset_refusal(*, request: BrokerRequest, launch: WorkflowLaunch) -> str | None:
    if launch.proof_asset_store is None:
        return (
            "publication broker refused proof-asset upload: workflow supplied no "
            "proof asset store"
        )
    if request.proof_asset_store != launch.proof_asset_store:
        return (
            "publication broker refused proof asset store "
            f"{request.proof_asset_store!r}: the workflow launched "
            f"{launch.proof_asset_store!r}"
        )
    if request.proof_asset is None or not request.proof_asset_name:
        return "publication broker refused proof-asset upload: asset path and name are required"
    return _staged_path_refusal(
        path=request.proof_asset,
        launch=launch,
        kind="proof asset",
    )


def _staged_path_refusal(*, path: Path, launch: WorkflowLaunch, kind: str) -> str | None:
    if launch.request_directory is None:
        # The standalone policy function remains useful before routing exists;
        # execution below requires this boundary and fails closed without it.
        return None
    try:
        _ = path.resolve().relative_to(launch.request_directory.resolve())
    except ValueError:
        return (
            f"publication broker refused {kind} {str(path)!r}: it is outside the "
            "workflow-owned request directory"
        )
    return None


@dataclass(frozen=True, kw_only=True)
class PublicationBroker:
    """Execute only an already-authorized request in the broker's own process.

    ``credential`` belongs to the service and is consulted only after policy
    validation.  It is passed directly to the one child forge command as an
    environment delta; it is never placed in an agent request, a working-tree
    file, or this process's ambient environment.
    """

    runner: CommandRunner
    credential: Callable[[], str]
    cwd: Path

    def handle(self, *, request: BrokerRequest, launch: WorkflowLaunch) -> BrokerResult:
        """Validate and execute one narrow write, refusing before credential use."""
        refusal = refusal_for(request=request, launch=launch)
        if refusal is not None:
            return BrokerResult(refusal=refusal)
        if launch.request_directory is None:
            return BrokerResult(
                refusal=(
                    "publication broker refused request: workflow supplied no "
                    "broker-owned request directory"
                )
            )
        return BrokerResult(
            command=self.runner.run(
                argv=_argv_for(request=request, launch=launch),
                cwd=self.cwd,
                timeout_seconds=_BROKER_TIMEOUT_SECONDS,
                env={"GH_TOKEN": self.credential(), "GITHUB_TOKEN": None},
            )
        )


def _argv_for(*, request: BrokerRequest, launch: WorkflowLaunch) -> list[str]:
    """Build the only two forge writes from workflow-owned target values."""
    if request.operation == "comment":
        if request.comment_body is None:
            raise ValueError
        return [
            "gh",
            "pr",
            "comment",
            str(launch.pull_request_number),
            "--body-file",
            str(request.comment_body),
        ]
    if request.proof_asset is None or request.proof_asset_name is None:
        raise ValueError
    if launch.proof_asset_store is None:
        raise ValueError
    return [
        "gh",
        "release",
        "upload",
        launch.proof_asset_store,
        f"{request.proof_asset}#{request.proof_asset_name}",
        "--clobber",
    ]
