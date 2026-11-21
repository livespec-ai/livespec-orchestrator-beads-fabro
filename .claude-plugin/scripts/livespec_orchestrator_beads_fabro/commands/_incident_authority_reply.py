"""Stable JSON replies for the incident-authority process boundary."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, cast

from livespec_orchestrator_beads_fabro._incident_authority_payload import attempt_record
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_completion_rules import (
    CLOSED_PHASE,
    IncidentCompletionEvidence,
    completion_obligations,
)
from livespec_orchestrator_beads_fabro.commands._incident_authority_lifecycle import lifecycle_body
from livespec_orchestrator_beads_fabro.commands.incident_local_gate_lookup import LocalGateLookup
from livespec_orchestrator_beads_fabro.commands.incident_local_gate_receipt import LocalGateReceipt
from livespec_orchestrator_beads_fabro.incident_authority import FilingReceipt, GenesisReceipt
from livespec_orchestrator_beads_fabro.incident_completion import IncidentCompletion
from livespec_orchestrator_beads_fabro.incident_drill_close import DrillClose
from livespec_orchestrator_beads_fabro.incident_normal_repayment import RepaymentEntry
from livespec_orchestrator_beads_fabro.incident_regression_recovery import RecoveryEntry
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = ["history_reply", "reply"]

_Reply = (
    IncidentReading
    | AuthorityRefusal
    | LocalGateLookup
    | LocalGateReceipt
    | GenesisReceipt
    | FilingReceipt
    | RepaymentEntry
    | RecoveryEntry
    | IncidentCompletion
    | DrillClose
)


def _without_walk_scope(*, value: object) -> object:
    """Omit read traversal details, which are not part of a retained identity."""
    if isinstance(value, dict):
        return {
            key: _without_walk_scope(value=item)
            for key, item in cast("dict[str, object]", value).items()
            if key != "operation_ids"
        }
    return value


def _result_body(*, result: _Reply) -> dict[str, object]:
    body = cast("dict[str, Any]", _without_walk_scope(value=asdict(result)))
    if isinstance(result, IncidentReading | GenesisReceipt):
        body["attempt"] = attempt_record(attempt=result.attempt)
    if isinstance(result, RepaymentEntry | RecoveryEntry | IncidentCompletion):
        lifecycle_body(result=result, body=body)
    return body


def _write(*, result: dict[str, object], refused: bool, authorizes: bool) -> int:
    response: dict[str, object] = {
        "schema": 1,
        "status": "refused" if refused else "verified",
        "result": result,
        "authorizes_current_effects": authorizes and not refused,
        "normal_factory_proof": False,
    }
    _ = write_stdout(text=json.dumps(response, sort_keys=True) + "\n")
    return 78 if refused else 0


def reply(*, result: _Reply, authorizes: bool) -> int:
    """Print one ordinary authority reply."""
    return _write(
        result=_result_body(result=result),
        refused=isinstance(result, AuthorityRefusal),
        authorizes=authorizes,
    )


def history_reply(*, history: tuple[IncidentAttempt, ...] | AuthorityRefusal) -> int:
    """Print every retained generation; recompute closure obligations at read time."""
    if isinstance(history, AuthorityRefusal):
        return reply(result=history, authorizes=False)
    generations = [attempt_record(attempt=attempt) for attempt in history]
    if history and history[-1].phase == CLOSED_PHASE:
        generations[-1]["outstanding"] = list(
            completion_obligations(history=history, evidence=IncidentCompletionEvidence())
        )
    return _write(result={"generations": generations}, refused=False, authorizes=False)
