"""Receipt-only workflow authorization preserves its distinct refusal paths."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient
from livespec_orchestrator_beads_fabro._incident_authority_types import AuthorityRefusal
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandResult
from livespec_orchestrator_beads_fabro.effects import _incident_authority_transition as transition
from livespec_orchestrator_beads_fabro.effects._incident_workflow_receipt import (
    attested_successor,
)
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

_WORKFLOW = ".github/workflows/incident.yml"
_COMMENT_ID = 4242


@dataclass(kw_only=True)
class _Forge:
    """The command seam answering the one attestation-comment read."""

    reply: object
    exit_code: int = 0
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        return CommandResult(exit_code=self.exit_code, stdout=json.dumps(self.reply), stderr="")


def _comment(
    *,
    operation_id: str = "human-attestation-1",
    paths: tuple[str, ...] = (_WORKFLOW,),
    login: str = "maintainer",
    kind: str = "User",
    association: str = "OWNER",
) -> dict[str, object]:
    line = (
        f"livespec-workflow-attestation: item={ITEM} operation={operation_id} "
        f"paths={','.join(paths)}"
    )
    return {
        "user": {"login": login, "type": kind},
        "author_association": association,
        "body": f"Attesting the workflow scope.\n{line}\n",
    }


def _receipt(
    *, operation_id: str = "human-attestation-1", paths: tuple[str, ...] = (_WORKFLOW,)
) -> HumanAttestedWorkflowReceipt:
    return HumanAttestedWorkflowReceipt(
        operation_id=operation_id,
        workflow_paths=paths,
        attester_login="maintainer",
        comment_id=_COMMENT_ID,
    )


def _attest(
    *,
    client: FakeBeadsClient,
    observed: IncidentReading,
    receipt: HumanAttestedWorkflowReceipt,
    forge: _Forge | None = None,
) -> IncidentReading | AuthorityRefusal:
    answering = forge or _Forge(
        reply=_comment(operation_id=receipt.operation_id, paths=receipt.workflow_paths)
    )
    return attest_workflow_paths(
        client=client,
        observed=observed,
        receipt=receipt,
        runner=answering,
        repo=Path(),
    )


def test_attested_successor_retains_the_cumulative_diff_scope() -> None:
    client, _, _ = _chain()
    observed = _read(client)
    assert isinstance(observed, IncidentReading)
    observed = replace(
        observed,
        attempt=replace(observed.attempt, original_paths=("app.py", _WORKFLOW)),
    )

    successor = attested_successor(observed=observed, receipt=_receipt())

    assert isinstance(successor, type(observed.attempt))
    assert successor.workflow_paths == (_WORKFLOW,)


def test_attestation_rejects_an_empty_workflow_scope() -> None:
    client, _, _ = _chain()
    observed = _read(client)
    assert isinstance(observed, IncidentReading)

    result = _attest(
        client=client,
        observed=observed,
        receipt=_receipt(operation_id="human-attestation-empty", paths=()),
    )

    assert result == AuthorityRefusal(code="incident-workflow-attestation-invalid", detail=ITEM)


def test_attestation_replays_or_refuses_the_same_operation_id() -> None:
    client, _, _ = _chain()
    observed = _read(client)
    assert isinstance(observed, IncidentReading)
    receipt = _receipt()

    recorded = _attest(client=client, observed=observed, receipt=receipt)
    replayed = _attest(client=client, observed=observed, receipt=receipt)

    assert isinstance(recorded, IncidentReading)
    assert replayed == recorded
    conflict = _attest(
        client=client,
        observed=observed,
        receipt=_receipt(operation_id=receipt.operation_id, paths=(".github/workflows/other.yml",)),
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

    stale = _attest(client=client, observed=observed, receipt=_receipt())

    assert stale == AuthorityRefusal(code="incident-generation-stale", detail=ITEM)
    reused = _attest(
        client=client, observed=advanced, receipt=_receipt(operation_id="agent-transition-2")
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
    unavailable = _attest(
        client=client, observed=advanced, receipt=_receipt(operation_id="human-attestation-2")
    )
    assert unavailable == AuthorityRefusal(code="history-unavailable", detail=ITEM)


def test_attestation_reads_the_named_forge_comment_before_recording() -> None:
    client, _, _ = _chain()
    observed = _read(client)
    assert isinstance(observed, IncidentReading)
    forge = _Forge(reply=_comment())

    recorded = _attest(client=client, observed=observed, receipt=_receipt(), forge=forge)

    assert isinstance(recorded, IncidentReading)
    assert recorded.attempt.workflow_paths == (_WORKFLOW,)
    assert forge.argvs == [["gh", "api", f"repos/owner/repository/issues/comments/{_COMMENT_ID}"]]


@pytest.mark.parametrize(
    ("forge", "reason"),
    [
        (_Forge(reply=_comment(kind="Bot", login="factory-bot[bot]")), "not a human"),
        (_Forge(reply=_comment(association="NONE")), "not a maintainer"),
        (_Forge(reply=_comment(login="someone-else")), "not by the named attester"),
        (_Forge(reply=_comment(operation_id="another-operation")), "does not state"),
        (_Forge(reply=_comment(paths=(".github/workflows/other.yml",))), "does not state"),
        (_Forge(reply={"user": "maintainer", "body": 7}), "no readable comment"),
        (_Forge(reply=["not", "a", "comment"]), "no readable comment"),
        (_Forge(reply=_comment(), exit_code=1), "no readable comment"),
    ],
)
def test_attestation_without_a_verified_maintainer_comment_records_nothing(
    forge: _Forge, reason: str
) -> None:
    client, _, _ = _chain()
    observed = _read(client)
    assert isinstance(observed, IncidentReading)

    refused = _attest(client=client, observed=observed, receipt=_receipt(), forge=forge)

    assert isinstance(refused, AuthorityRefusal)
    assert refused.code == "incident-workflow-attestation-unverified"
    assert reason in refused.detail
    current = _read(client)
    assert isinstance(current, IncidentReading)
    assert current.attempt.generation == observed.attempt.generation
    assert current.attempt.workflow_paths == ()
