"""Retire an abandoned or drill incident chain whose expedited change never reached master.

An expedited attempt whose carrier pull request closed unmerged, a drill whose
scratch chain stopped before its recovery receipt, and an incident that was
entered but never attempted all leave a chain no completion can close: closure
needs a merged normal repayment, and nothing was ever merged that could be
repaid. The `retire` action of the incident authority writer ends such a chain.
It records who retired it and why, moves it under the normal generation fence
to the terminal phase `retired` (lifecycle state `done`, no repayment owed) and
closes the item.

It refuses, writing nothing, whenever the chain could still owe a real
repayment: any recorded landed or revert commit already reachable from master,
or any bound carrier pull request the forge reports merged into a base outside
`incident-scratch/**`, is `incident-retire-landed-on-master`; a bound carrier
pull request still open is `incident-retire-carrier-open`; a forge read that
fails or is incomplete is `incident-retire-evidence-unavailable`. A retired
item is never a completed incident: the completion rules name it
`incident-retired`.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_drill_evidence import master_reachable_evidence
from livespec_orchestrator_beads_fabro._incident_phases import (
    lifecycle_state_for,
    stored_status_for,
)
from livespec_orchestrator_beads_fabro._store_claim_tokens import (
    TRANSITION_WAIT_SECONDS,
    ClaimChangeResult,
    change_claim,
)
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import read_history
from livespec_orchestrator_beads_fabro.effects._incident_authority_transition import (
    commit_transition,
)
from livespec_orchestrator_beads_fabro.effects._incident_entry_writer import (
    require_current_generation,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

__all__: list[str] = [
    "RETIREMENT_MARKER",
    "IncidentRetired",
    "Retirement",
    "retire_incident",
]

RETIREMENT_MARKER = "livespec-incident-retirement-v1\n"
_ALLOWED = frozenset(
    ("repair", "master-observation", "reverting", "rollback-conflict", "collecting-failures")
)
_PHASE = "retired"
_SCRATCH = "incident-scratch/"
_LANDED = "incident-retire-landed-on-master"
_OPEN = "incident-retire-carrier-open"
_UNAVAILABLE = "incident-retire-evidence-unavailable"
_FINISHED = frozenset(("done", "closed"))


@dataclass(frozen=True, kw_only=True)
class Retirement:
    """Who retired the chain, and why; both are recorded on the item."""

    retired_by: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class IncidentRetired:
    reading: IncidentReading
    lifecycle_state: str
    repayment_outstanding: bool
    retired_by: str
    reason: str


def _refusal(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def _successor(*, reading: IncidentReading) -> IncidentAttempt:
    return replace(
        reading.attempt,
        phase=_PHASE,
        operation_id=f"{reading.attempt.attempt_id}#retire",
        generation=reading.attempt.generation + 1,
        repayment_required=False,
    )


def _bound_prs(*, history: tuple[IncidentAttempt, ...]) -> tuple[int, ...]:
    return tuple(sorted({attempt.pr_number for attempt in history if attempt.pr_number > 0}))


def _pr_refusal(
    *, pr_number: int, runner: CommandRunner, repo: Path, repository: str
) -> AuthorityRefusal | None:
    """Read one bound carrier pull request; open or merged outside scratch refuses."""
    result = runner.run(
        argv=[
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--repo",
            repository,
            "--json",
            "number,state,baseRefName",
        ],
        cwd=repo,
        timeout_seconds=60.0,
    )
    value = parse_json(text=result.stdout) if result.exit_code == 0 else None
    pull = cast("dict[str, object]", value) if isinstance(value, dict) else {}
    state, base = pull.get("state"), pull.get("baseRefName")
    if pull.get("number") != pr_number or not isinstance(state, str) or not isinstance(base, str):
        return _refusal(code=_UNAVAILABLE, detail=f"PR #{pr_number}: forge read failed")
    if state == "OPEN":
        return _refusal(code=_OPEN, detail=f"PR #{pr_number}")
    if state == "MERGED" and not base.startswith(_SCRATCH):
        return _refusal(code=_LANDED, detail=f"PR #{pr_number} merged into {base}")
    return None


def _evidence(
    *,
    client: BeadsClient,
    item_id: str,
    history: tuple[IncidentAttempt, ...],
    runner: CommandRunner,
    repo: Path,
    repository: str,
) -> AuthorityRefusal | None:
    for pr_number in _bound_prs(history=history):
        refused = _pr_refusal(pr_number=pr_number, runner=runner, repo=repo, repository=repository)
        if refused is not None:
            return refused
    return master_reachable_evidence(
        client=client,
        item_id=item_id,
        history=history,
        runner=runner,
        repo=repo,
        repository=repository,
        landed_code=_LANDED,
        unavailable_code=_UNAVAILABLE,
    )


def _commit(
    *,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
    repo: Path,
    repository: str,
) -> IncidentReading | AuthorityRefusal:
    """Recover a fixed retire operation, or prove the current chain before writing it."""
    successor = _successor(reading=reading)
    current = require_current_generation(client=client, observed=reading)
    if isinstance(current, AuthorityRefusal):
        recovered = commit_transition(
            client=client, observed=reading, successor=successor, allow_retire=True
        )
        return current if isinstance(recovered, AuthorityRefusal) else recovered
    history = read_history(client=client, repository=repository, item_id=reading.attempt.item_id)
    if isinstance(history, AuthorityRefusal):
        return history
    refused = _evidence(
        client=client,
        item_id=reading.attempt.item_id,
        history=history,
        runner=runner,
        repo=repo,
        repository=repository,
    )
    if refused is not None:
        return refused
    return commit_transition(
        client=client, observed=reading, successor=successor, allow_retire=True
    )


def _record(*, client: BeadsClient, committed: IncidentReading, retirement: Retirement) -> None:
    """Record who retired the chain and why, once per retire operation."""
    attempt = committed.attempt
    for row in client.list_comments(issue_id=attempt.item_id):
        text = row.get("text")
        if isinstance(text, str) and text.startswith(RETIREMENT_MARKER):
            prior = parse_json(text=text[len(RETIREMENT_MARKER) :])
            record = cast("dict[str, object]", prior) if isinstance(prior, dict) else {}
            if record.get("operation_id") == attempt.operation_id:
                return
    record = {
        "schema": 1,
        "item_id": attempt.item_id,
        "attempt_id": attempt.attempt_id,
        "operation_id": attempt.operation_id,
        "generation": attempt.generation,
        "retired_by": retirement.retired_by,
        "reason": retirement.reason,
    }
    client.add_comment(
        issue_id=attempt.item_id,
        body=RETIREMENT_MARKER + json.dumps(record, sort_keys=True, separators=(",", ":")),
    )


_POLL_SECONDS = 5.0
# Injectable time, so a test can advance the claim-transition wait without sleeping.
_clock = time.monotonic
_sleep = time.sleep


def _change_waiting_out_transition(*, client: BeadsClient, item_id: str) -> ClaimChangeResult:
    """Write the closed lifecycle status, waiting out a stranded claim transition."""
    observations: dict[tuple[str, str, str], float] = {}
    deadline = _clock() + TRANSITION_WAIT_SECONDS + _POLL_SECONDS
    while True:
        result = change_claim(
            client=client,
            work_item_id=item_id,
            writer="incident-retire",
            intent="retire",
            claim_tokens=True,
            status=stored_status_for(phase=_PHASE) or "",
            clear_assignee=True,
            still_as_decided=lambda row: row.get("status") not in _FINISHED,
            clock=_clock,
            transition_observations=observations,
        )
        if result.outcome != "claim-transition-pending" or _clock() >= deadline:
            return result
        _sleep(_POLL_SECONDS)


def _publish_lifecycle(
    *, client: BeadsClient, committed: IncidentReading, retirement: Retirement
) -> IncidentRetired | AuthorityRefusal:
    current = require_current_generation(client=client, observed=committed)
    if isinstance(current, AuthorityRefusal):
        return current
    _record(client=client, committed=committed, retirement=retirement)
    existing = client.show_issue(issue_id=committed.attempt.item_id)
    if existing.get("status") not in _FINISHED or existing.get("assignee") is not None:
        result = _change_waiting_out_transition(client=client, item_id=committed.attempt.item_id)
        if result.outcome != "applied":
            return _refusal(code="incident-retire-lifecycle-refused", detail=result.outcome)
    return IncidentRetired(
        reading=committed,
        lifecycle_state=lifecycle_state_for(phase=_PHASE) or "",
        repayment_outstanding=False,
        retired_by=retirement.retired_by,
        reason=retirement.reason,
    )


def retire_incident(
    *,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
    repo: Path,
    repository: str,
    retirement: Retirement,
) -> IncidentRetired | AuthorityRefusal:
    """Retire a chain nothing of which reached master, under the normal generation fence."""
    if not retirement.retired_by.strip() or not retirement.reason.strip():
        return _refusal(code="incident-retire-unattributed", detail=reading.attempt.item_id)
    if reading.attempt.phase not in _ALLOWED:
        return _refusal(code="incident-retire-ineligible-phase", detail=reading.attempt.phase)
    committed = _commit(
        client=client, reading=reading, runner=runner, repo=repo, repository=repository
    )
    if isinstance(committed, AuthorityRefusal):
        return committed
    return _publish_lifecycle(client=client, committed=committed, retirement=retirement)
