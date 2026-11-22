"""Versioned process boundary for incident authority consumers in other projects."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    attempt_record,
    decode_attempt,
    unsupported_carrier,
)
from livespec_orchestrator_beads_fabro._incident_carrier import CARRIER_UNSUPPORTED
from livespec_orchestrator_beads_fabro._incident_genesis import (
    GENESIS_CAPABILITY_UNAVAILABLE,
    capability_unavailable,
    decode_genesis_request,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    resolve_claim_tokens,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._incident_authority_arguments import (
    item_only_history,
    parse,
)
from livespec_orchestrator_beads_fabro.commands._incident_authority_lifecycle import (
    LIFECYCLE_PAYLOADS,
    run_lifecycle_action,
)
from livespec_orchestrator_beads_fabro.commands._incident_authority_reply import (
    history_reply,
    missing_if_unknown,
)
from livespec_orchestrator_beads_fabro.commands._incident_authority_reply import (
    reply as _reply,
)
from livespec_orchestrator_beads_fabro.commands._intake_valve_claim_writes import TakeoverWait
from livespec_orchestrator_beads_fabro.commands.incident_local_gate_lookup import (
    read_local_gates,
)
from livespec_orchestrator_beads_fabro.commands.incident_local_gate_receipt import (
    read_receipt_stream,
    record_local_gates,
)
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    FilingReceipt,
    GenesisReceipt,
    IncidentReading,
    commit_incident_transition,
    decode_filing_request,
    file_incident,
    publish_incident_genesis,
    read_incident_authority,
    read_incident_history,
)

__all__: list[str] = ["main"]

_RECORD_GATES = "record-local-gates"
_ADVANCE = "advance-repayment"
_HISTORICAL = frozenset(("read-history", "commit-transition", *LIFECYCLE_PAYLOADS))
_FILING = "file-incident"
_TRANSITION_PENDING = "incident-genesis-claim-transition-pending"


def main(*, argv: Sequence[str] | None = None) -> int:
    """Print one schema-1 reply; an unverifiable identity exits 78, not normal mode."""
    args = parse(argv=argv)
    if args.action == "publish-genesis":
        return _reply(result=_genesis(args=args), authorizes=False)
    if args.action == _FILING:
        return _reply(result=_filing(args=args), authorizes=False)
    client = make_beads_client(config=store_config(repo=args.repo))
    if item_only_history(args=args):
        history = read_incident_history(
            client=client, repository=args.repository, item_id=args.item
        )
        return history_reply(
            repository=args.repository,
            item_id=args.item,
            history=missing_if_unknown(client=client, item_id=args.item, history=history),
        )
    result = read_incident_authority(
        client=client,
        repository=args.repository,
        item_id=args.item,
        query={
            "attempt_id": args.attempt,
            "phase": args.phase,
            "operation_id": args.operation,
            "generation": args.generation,
            "owner": args.owner,
        },
        historical=args.action in _HISTORICAL,
    )
    if args.action == "commit-transition" and isinstance(result, IncidentReading):
        raw = parse_json(text=args.successor_json)
        successor = decode_attempt(value=raw)
        result = (
            commit_incident_transition(client=client, observed=result, successor=successor)
            if successor is not None
            and args.successor_json
            == json.dumps(attempt_record(attempt=successor), sort_keys=True, separators=(",", ":"))
            else AuthorityRefusal(
                code=CARRIER_UNSUPPORTED
                if unsupported_carrier(value=raw)
                else "incident-transition-invalid-successor",
                detail=args.item,
            )
        )
    if args.action == _RECORD_GATES and isinstance(result, IncidentReading):
        text = (
            read_receipt_stream(stream=sys.stdin.buffer)
            if args.receipt_stdin
            else args.receipt_json
        )
        result = record_local_gates(client=client, observed=result, text=text)
    if args.action == "read-local-gates" and isinstance(result, IncidentReading):
        result = read_local_gates(client=client, observed=result, receipt_id=args.receipt_id)
    if args.action in LIFECYCLE_PAYLOADS and isinstance(result, IncidentReading):
        result = run_lifecycle_action(
            args=args, client=client, reading=result, runner=ShellCommandRunner()
        )
    return _reply(result=result, authorizes=args.action == "read-current")


def _claim_tokens(*, repo: Path, detail: str) -> bool | AuthorityRefusal:
    """The committed cutover; unreadable is a capability refusal, never `false`."""
    setting = resolve_claim_tokens(cwd=repo)
    if not is_successful(setting):
        return AuthorityRefusal(
            code=GENESIS_CAPABILITY_UNAVAILABLE,
            detail=f"{detail}: committed dispatcher.claim_tokens is unreadable",
        )
    return unsafe_perform_io(setting.unwrap())


def _wait_out_transition() -> None:
    """A one-shot entry waits the protocol's takeover wait before its one retry."""
    TakeoverWait().wait_out()


def _genesis(*, args: argparse.Namespace) -> GenesisReceipt | AuthorityRefusal:
    """Bind the request; without the committed claim-token cutover, refuse with no client."""
    request = decode_genesis_request(
        text=args.genesis_json,
        repository=args.repository,
        item_id=args.item,
        operation_id=args.operation,
    )
    if request is None or (
        request.attempt.attempt_id,
        request.attempt.owner,
        request.attempt.generation,
        request.attempt.phase,
    ) != (args.attempt, args.owner, args.generation, args.phase):
        return AuthorityRefusal(code="incident-genesis-invalid-request", detail=args.item)
    cutover = _claim_tokens(repo=args.repo, detail=args.item)
    if isinstance(cutover, AuthorityRefusal):
        return cutover
    if not cutover:
        return capability_unavailable(request=request)
    client = make_beads_client(config=store_config(repo=args.repo))
    result = publish_incident_genesis(client=client, request=request, claim_tokens=True)
    if isinstance(result, AuthorityRefusal) and result.code == _TRANSITION_PENDING:
        _wait_out_transition()
        result = publish_incident_genesis(client=client, request=request, claim_tokens=True)
    return result


def _filing(*, args: argparse.Namespace) -> FilingReceipt | AuthorityRefusal:
    """File one identified incident under the exact principal and operation named."""
    request = decode_filing_request(text=args.filing_json)
    if request is None or (request.repository, request.operation_id, request.principal) != (
        args.repository,
        args.operation,
        args.owner,
    ):
        return AuthorityRefusal(code="incident-filing-invalid-request", detail=args.operation)
    cutover = _claim_tokens(repo=args.repo, detail=args.operation)
    if isinstance(cutover, AuthorityRefusal):
        return cutover
    config = store_config(repo=args.repo)
    return file_incident(
        client=make_beads_client(config=config),
        prefix=config.prefix,
        request=request,
        claim_tokens=cutover,
    )
