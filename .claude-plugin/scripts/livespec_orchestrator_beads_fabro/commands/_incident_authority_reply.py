"""Stable incident-authority process replies, including item-only absence."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, cast

from livespec_orchestrator_beads_fabro._incident_authority_payload import attempt_record
from livespec_orchestrator_beads_fabro.commands._incident_authority_lifecycle import lifecycle_body
from livespec_orchestrator_beads_fabro.commands.incident_local_gate_lookup import LocalGateLookup
from livespec_orchestrator_beads_fabro.commands.incident_local_gate_receipt import LocalGateReceipt
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    FilingReceipt,
    GenesisReceipt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro.incident_completion import IncidentCompletion
from livespec_orchestrator_beads_fabro.incident_drill_close import DrillClose
from livespec_orchestrator_beads_fabro.incident_normal_repayment import RepaymentEntry
from livespec_orchestrator_beads_fabro.incident_regression_recovery import RecoveryEntry
from livespec_orchestrator_beads_fabro.io import write_stdout

Reply = (
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
    """Leave out a reading's non-stable record of the chain it walked."""
    if isinstance(value, dict):
        return {
            key: _without_walk_scope(value=item)
            for key, item in cast("dict[str, object]", value).items()
            if key != "operation_ids"
        }
    return value


def _result_body(*, result: Reply) -> dict[str, object]:
    body = cast("dict[str, Any]", _without_walk_scope(value=asdict(result)))
    if isinstance(result, IncidentReading | GenesisReceipt):
        body["attempt"] = attempt_record(attempt=result.attempt)
    if isinstance(result, RepaymentEntry | RecoveryEntry | IncidentCompletion):
        lifecycle_body(result=result, body=body)
    return body


def reply(*, result: Reply, authorizes: bool) -> int:
    """Write a verified or refused reply without allowing a refused effect."""
    refused = isinstance(result, AuthorityRefusal)
    response: dict[str, object] = {
        "schema": 1,
        "status": "refused" if refused else "verified",
        "result": _result_body(result=result),
        "authorizes_current_effects": authorizes and not refused,
        "normal_factory_proof": False,
    }
    _ = write_stdout(text=json.dumps(response, sort_keys=True) + "\n")
    return 78 if refused else 0


def absent_reply(*, repository: str, item_id: str) -> int:
    """Write the non-refusal result for an item with no authority genesis."""
    response = {
        "schema": 1,
        "status": "absent",
        "result": {"repository": repository, "item_id": item_id},
        "authorizes_current_effects": False,
        "normal_factory_proof": False,
    }
    _ = write_stdout(text=json.dumps(response, sort_keys=True) + "\n")
    return 0
