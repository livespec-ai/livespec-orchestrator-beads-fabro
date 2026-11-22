"""Argument rules for the incident-authority process boundary."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._incident_authority_lifecycle import (
    LIFECYCLE_PAYLOADS,
)

__all__: list[str] = ["item_only_history", "parse"]

_RECORD_GATES = "record-local-gates"
_FILING = "file-incident"
_ADVANCE = "advance-repayment"
_ITEM_IDENTITY = ("item", "attempt", "phase", "generation")
_FENCED_IDENTITY = (*_ITEM_IDENTITY, "operation", "owner")
_IDENTITY_RULE = (
    "--item, --attempt, --phase, --generation, --operation and --owner: required "
    "unless file-incident or item-only read-history"
)

# Each writing action and the payload arguments it alone requires.
_ACTION_ARGUMENTS: dict[str, tuple[str, ...]] = {
    "commit-transition": ("successor_json",),
    _RECORD_GATES: ("receipt_json",),
    "read-local-gates": ("receipt_id",),
    "publish-genesis": ("genesis_json",),
    _FILING: ("filing_json",),
    **LIFECYCLE_PAYLOADS,
}
_PAYLOAD_OWNERS = {
    field: tuple(action for action, owned in _ACTION_ARGUMENTS.items() if field in owned)
    for field in dict.fromkeys(field for owned in _ACTION_ARGUMENTS.values() for field in owned)
}


def item_only_history(*, args: argparse.Namespace) -> bool:
    """Whether this history read names the item but no fenced generation identity."""
    return args.action == "read-history" and all(
        getattr(args, name) is None for name in _FENCED_IDENTITY[1:]
    )


def _check_receipt_source(*, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """A receipt has exactly one source, and only the action that records it takes one."""
    if args.action == _RECORD_GATES and (args.receipt_json is not None) == args.receipt_stdin:
        parser.error(f"{_RECORD_GATES} requires exactly one of --receipt-json or --receipt-stdin")
    if args.receipt_stdin and args.action != _RECORD_GATES:
        parser.error(f"--receipt-stdin is only valid for {_RECORD_GATES}")


def _check_identity(*, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Fenced reads stay exact; only item-only history omits the full fence."""
    if args.action == _FILING:
        if any(getattr(args, name) is not None for name in _ITEM_IDENTITY) or any(
            getattr(args, name) is None for name in ("operation", "owner")
        ):
            parser.error(_IDENTITY_RULE)
    elif args.item is None or (
        not item_only_history(args=args)
        and any(getattr(args, name) is None for name in _FENCED_IDENTITY)
    ):
        parser.error(_IDENTITY_RULE)


def parse(*, argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse action payloads and the identity form each action is allowed to use."""
    parser = argparse.ArgumentParser(prog="incident-authority")
    _ = parser.add_argument("action", choices=(*_ACTION_ARGUMENTS, "read-current", "read-history"))
    for field in _PAYLOAD_OWNERS:
        _ = parser.add_argument("--" + field.replace("_", "-"))
    _ = parser.add_argument("--admission-complete", action="store_true")
    _ = parser.add_argument("--receipt-stdin", action="store_true")
    _ = parser.add_argument("--repo", required=True, type=Path)
    _ = parser.add_argument("--repository", required=True)
    for name in ("operation", "owner", "item", "attempt", "phase"):
        _ = parser.add_argument(f"--{name}")
    _ = parser.add_argument("--generation", type=int)
    args = parser.parse_args(argv)
    for field, owners in _PAYLOAD_OWNERS.items():
        if (field != "receipt_json" or args.action != _RECORD_GATES) and (
            (args.action in owners) != (getattr(args, field) is not None)
        ):
            flag = field.replace("_", "-")
            parser.error(f"--{flag} is required by, and only valid for, {', '.join(owners)}")
    _check_receipt_source(parser=parser, args=args)
    if args.admission_complete and args.action != _ADVANCE:
        parser.error(f"--admission-complete is only valid for {_ADVANCE}")
    _check_identity(parser=parser, args=args)
    return args
