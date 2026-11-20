"""Server conditional-close transitions on an existing incident authority.

This is a generation writer, not canonical entry or a factory-fence capability.
It never initializes authority, mutates lifecycle state or grants host takeover.
A close exit code is never a winner verdict; the committed reason is read back.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
from contextlib import suppress
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Literal

from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    HEAD_HINT_KEY,
    TOKEN_TITLE,
    TRANSITION_MARKER,
    attempt_record,
    decode_attempt,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_carrier import carrier_successor_allowed
from livespec_orchestrator_beads_fabro._incident_phases import (
    closure_successor_allowed,
    fresh_repayment_carrier,
    recovery_carrier,
)
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import (
    read_authority,
    read_history,
)
from livespec_orchestrator_beads_fabro.effects._incident_entry_writer import (
    require_current_generation,
)
from livespec_orchestrator_beads_fabro.effects._incident_workflow_attestation import (
    attestation_line,
    unverified_reason,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

__all__: list[str] = [
    "HumanAttestedWorkflowReceipt",
    "attest_workflow_paths",
    "commit_transition",
]

_LEDGER_ERRORS = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


@dataclass(frozen=True, kw_only=True)
class HumanAttestedWorkflowReceipt:
    """A request to record one exact workflow-path scope a maintainer attested.

    The receipt carries no authority of its own: it names the forge comment, by
    the maintainer `attester_login`, that the writer reads before recording.
    """

    operation_id: str
    workflow_paths: tuple[str, ...]
    attester_login: str
    comment_id: int
    operation: Literal["human_attested"] = "human_attested"


def _read(
    *, client: BeadsClient, attempt: IncidentAttempt, historical: bool
) -> IncidentReading | AuthorityRefusal:
    query = {
        key: value
        for key, value in asdict(attempt).items()
        if key in {"attempt_id", "phase", "operation_id", "generation", "owner"}
    }
    return read_authority(
        client=client,
        repository=attempt.repository,
        item_id=attempt.item_id,
        query=query,
        historical=historical,
    )


def _valid_successor(*, before: IncidentAttempt, after: IncidentAttempt) -> bool:
    return (
        before.repository == after.repository
        and before.item_id == after.item_id
        and after.generation == before.generation + 1
        and before.operation_id != after.operation_id
        and set(before.original_paths).issubset(after.original_paths)
        # Ordinary transitions are agent-written authority records.  A workflow
        # attestation expires with its recorded generation: only the separate
        # maintainer receipt operation may put it on a successor.
        and not after.workflow_scope()
        # No writer discharges the incident from anything but a merged repayment.
        and closure_successor_allowed(before=before, after=after)
        and (
            # The merged expedited carrier stays recorded under master-observation;
            # the one same-item repayment opens on its own fresh reserved branch.
            fresh_repayment_carrier(before=before, after=after)
            # A regression reopen binds the attributed merged carrier, and a
            # corrected repair opens its own branch after the revert receipt.
            or recovery_carrier(before=before, after=after)
            or carrier_successor_allowed(
                before=before.carrier,
                after=after.carrier,
                before_pr=before.pr_number,
                after_pr=after.pr_number,
            )
        )
    )


def _close(
    *, client: BeadsClient, observed: IncidentReading, successor: IncidentAttempt
) -> IncidentReading | AuthorityRefusal:
    candidate = client.create_no_history_issue(
        title=TOKEN_TITLE,
        description="Retained immutable incident authority transition. Not a work item.",
    )
    payload = {
        "schema": 1,
        "repository": successor.repository,
        "item_id": successor.item_id,
        "prior_token_id": observed.current_token_id,
        "next_token_id": candidate,
        "attempt": attempt_record(attempt=successor),
    }
    reason = TRANSITION_MARKER + json.dumps(payload, sort_keys=True, separators=(",", ":"))
    client.close_issue_without_verdict(issue_id=observed.current_token_id, reason=reason)
    standing = client.show_issue(issue_id=observed.current_token_id)
    if standing.get("status") != "closed" or not isinstance(standing.get("close_reason"), str):
        return AuthorityRefusal(code="incident-transition-outcome-unknown", detail=candidate)
    if standing["close_reason"] != reason:
        client.delete_issue(issue_id=candidate)
        return AuthorityRefusal(
            code="incident-transition-lost-race", detail=observed.current_token_id
        )
    # The hint is where a current read starts, never authority: a lost write only
    # lengthens the next forward walk, so it must not turn a committed close into an error.
    with suppress(*_LEDGER_ERRORS):
        client.update_issue(
            issue_id=successor.item_id, metadata={HEAD_HINT_KEY: observed.current_token_id}
        )
    return _read(client=client, attempt=successor, historical=False)


def _validated_successor(
    *, observed: IncidentReading, successor: IncidentAttempt, allow_drill_close: bool
) -> IncidentAttempt | AuthorityRefusal:
    """Decode the canonical successor and reserve `drill-closed` for its action."""
    decoded = decode_attempt(value=parse_json(text=json.dumps(attempt_record(attempt=successor))))
    if decoded is None or not _valid_successor(before=observed.attempt, after=decoded):
        return AuthorityRefusal(
            code="incident-transition-invalid-successor", detail=observed.attempt.item_id
        )
    if decoded.phase == "drill-closed" and not allow_drill_close:
        return AuthorityRefusal(
            code="incident-drill-close-requires-action", detail=observed.attempt.item_id
        )
    return decoded


def _commit(
    *,
    client: BeadsClient,
    observed: IncidentReading,
    successor: IncidentAttempt,
    allow_drill_close: bool,
) -> IncidentReading | AuthorityRefusal:
    decoded = _validated_successor(
        observed=observed, successor=successor, allow_drill_close=allow_drill_close
    )
    if isinstance(decoded, AuthorityRefusal):
        return decoded
    recovered = _read(client=client, attempt=decoded, historical=True)
    if isinstance(recovered, IncidentReading):
        return (
            recovered
            if recovered.attempt == decoded
            else AuthorityRefusal(
                code="incident-transition-operation-conflict", detail=decoded.operation_id
            )
        )
    # The stale-generation gate: an observation the head has moved past, or one
    # that is not the exact current reading, is refused by name before any close.
    current = require_current_generation(client=client, observed=observed)
    if isinstance(current, AuthorityRefusal):
        return current
    # A current read walks only the segment after the item's head hint, so reuse is
    # judged against the whole retained history.
    history = read_history(client=client, repository=decoded.repository, item_id=decoded.item_id)
    if isinstance(history, AuthorityRefusal):
        return history
    if decoded.operation_id in {prior.operation_id for prior in history}:
        return AuthorityRefusal(
            code="incident-transition-operation-reused", detail=decoded.operation_id
        )
    return _close(client=client, observed=observed, successor=decoded)


def commit_transition(
    *,
    client: BeadsClient,
    observed: IncidentReading,
    successor: IncidentAttempt,
    allow_drill_close: bool = False,
) -> IncidentReading | AuthorityRefusal:
    """Commit one next generation, or recover a retry without another effect."""
    try:
        return _commit(
            client=client,
            observed=observed,
            successor=successor,
            allow_drill_close=allow_drill_close,
        )
    except _LEDGER_ERRORS as exc:
        # Keep an unknown candidate: deleting it could sever our own successful
        # transition after a failed readback. A retry recovers the original.
        return AuthorityRefusal(code="incident-transition-unavailable", detail=str(exc))


def _attested_successor(
    *, observed: IncidentReading, receipt: HumanAttestedWorkflowReceipt
) -> IncidentAttempt | AuthorityRefusal:
    if receipt.operation != "human_attested" or not receipt.workflow_paths:
        return AuthorityRefusal(
            code="incident-workflow-attestation-invalid", detail=observed.attempt.item_id
        )
    successor = replace(
        observed.attempt,
        generation=observed.attempt.generation + 1,
        operation_id=receipt.operation_id,
        original_paths=tuple(
            dict.fromkeys((*observed.attempt.original_paths, *receipt.workflow_paths))
        ),
        workflow_paths=receipt.workflow_paths,
    )
    decoded = decode_attempt(value=parse_json(text=json.dumps(attempt_record(attempt=successor))))
    return (
        decoded
        if decoded is not None and decoded.workflow_scope()
        else AuthorityRefusal(
            code="incident-workflow-attestation-invalid", detail=observed.attempt.item_id
        )
    )


def _verified_successor(
    *,
    observed: IncidentReading,
    receipt: HumanAttestedWorkflowReceipt,
    runner: CommandRunner,
    repo: Path,
) -> IncidentAttempt | AuthorityRefusal:
    """The scoped successor, only once the forge shows a maintainer attested it."""
    decoded = _attested_successor(observed=observed, receipt=receipt)
    if isinstance(decoded, AuthorityRefusal):
        return decoded
    unverified = unverified_reason(
        runner=runner,
        repo=repo,
        repository=decoded.repository,
        comment_id=receipt.comment_id,
        attester_login=receipt.attester_login,
        expected_line=attestation_line(
            item_id=decoded.item_id,
            operation_id=receipt.operation_id,
            workflow_paths=receipt.workflow_paths,
        ),
    )
    if unverified is None:
        return decoded
    return AuthorityRefusal(code="incident-workflow-attestation-unverified", detail=unverified)


def attest_workflow_paths(
    *,
    client: BeadsClient,
    observed: IncidentReading,
    receipt: HumanAttestedWorkflowReceipt,
    runner: CommandRunner,
    repo: Path,
) -> IncidentReading | AuthorityRefusal:
    """Record one maintainer-attested workflow scope on the next generation.

    Ordinary transition callers cannot select a non-empty workflow scope.  This
    separate receipt operation first reads the named comment on the forge and
    refuses unless a human maintainer posted the exact attestation line, so a
    caller-built receipt alone never writes the scope.  It then constructs the
    only valid scoped successor and takes the same server-side generation fence
    and idempotent replay path.
    """
    decoded = _verified_successor(observed=observed, receipt=receipt, runner=runner, repo=repo)
    if isinstance(decoded, AuthorityRefusal):
        return decoded
    recovered = _read(client=client, attempt=decoded, historical=True)
    if isinstance(recovered, IncidentReading):
        return (
            recovered
            if attempt_record(attempt=recovered.attempt) == attempt_record(attempt=decoded)
            else AuthorityRefusal(
                code="incident-workflow-attestation-operation-conflict",
                detail=receipt.operation_id,
            )
        )
    current = require_current_generation(client=client, observed=observed)
    if isinstance(current, AuthorityRefusal):
        return current
    history = read_history(client=client, repository=decoded.repository, item_id=decoded.item_id)
    if isinstance(history, AuthorityRefusal):
        return history
    if receipt.operation_id in {prior.operation_id for prior in history}:
        return AuthorityRefusal(
            code="incident-workflow-attestation-operation-reused", detail=receipt.operation_id
        )
    return _close(client=client, observed=observed, successor=decoded)
