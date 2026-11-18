"""Read-only CLI projection of the spec-change tier hold a launcher screens with."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_wall import (
    standing_hold_the_drain_drops,
)
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = [
    "add_tier_hold_arguments",
    "add_tier_hold_subcommand",
    "run_tier_hold_command",
]


class _SubcommandParsers(Protocol):
    """The public parser factory surface the command registration needs."""

    def add_parser(self, *, name: str) -> argparse.ArgumentParser: ...


def add_tier_hold_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Add the read-only tier-hold command's arguments."""
    _ = parser.add_argument("--repo", dest="repo", required=True)
    _ = parser.add_argument("--item", dest="item", required=True)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")


def add_tier_hold_subcommand(
    *,
    subparsers: _SubcommandParsers,
    handlers: dict[str, Callable[..., int]],
) -> None:
    """Register the read-only tier-hold command with the Dispatcher router."""
    add_tier_hold_arguments(parser=subparsers.add_parser(name="tier-hold"))
    handlers["tier-hold"] = run_tier_hold_command


def run_tier_hold_command(*, args: argparse.Namespace) -> int:
    """Print whether the spec-change tier hold stands on one work item.

    Takes no judgement and reaches no model: the verdict is the drain's own
    admission predicate, so a fleet launcher and the Dispatcher agree.
    """
    repo = Path(args.repo)
    item = next(candidate for candidate in load_items(repo=repo) if candidate.id == args.item)
    hold = standing_hold_the_drain_drops(repo=repo, item=item)
    payload: dict[str, str | bool] = {"work_item_id": item.id, "spec_change_hold": hold is not None}
    if hold is not None:
        payload["reason"] = hold.reason
        payload["topic"] = hold.linked_proposal_topic or "(none linked)"
    _ = write_stdout(text=json.dumps(payload, sort_keys=True) + "\n")
    return 0
