"""Verified Red-Green pair enumeration for one already-selected dispatch."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles import (
    observed_pair_count,
    unobserved_pair_count,
    verified_pair_ids,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_order_sink import TddOrderSink
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_probe import gather_tdd_signals
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_signals import tdd_signal_fields
from livespec_orchestrator_beads_fabro.types import WorkItem

_DISPATCH_ID = "5fe8e3dfbfd54faa979e85364d8e9863"


@dataclass(kw_only=True)
class _Runner:
    """Script the one commits probe the integration boundary reads."""

    stdout: str = ""
    exit_code: int = 0

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        assert argv == ["gh", "pr", "view", "4242", "--json", "commits"]
        assert cwd == Path("/repo")
        assert timeout_seconds > 0
        assert env is None
        return CommandResult(exit_code=self.exit_code, stdout=self.stdout, stderr="")


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-defs3b",
        type="task",
        status="active",
        title="Count verified pairs",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-02T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_criteria="- One assertion.",
    )


def _outcome() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-defs3b",
        status="green",
        stage="done",
        pr_number=4242,
        merge_sha="abc123",
        detail="merged",
    )


def _commits_payload(*, message: str) -> str:
    return json.dumps({"commits": [{"messageHeadline": "feat: Red", "messageBody": message}]})


def _message(
    *,
    checksum: str | None = None,
    red: str | None = None,
    green: str | None = None,
    suite_green: str | None = None,
) -> str:
    trailers = ["Body prose."]
    if checksum is not None:
        trailers.append(f"TDD-Red-Test-File-Checksum: {checksum}")
    if red is not None:
        trailers.append(f"TDD-Red-Captured-At: {red}")
    if green is not None:
        trailers.append(f"TDD-Green-Verified-At: {green}")
    if suite_green is not None:
        trailers.append(f"TDD-Suite-Green-Captured-At: {suite_green}")
    return "\n".join(trailers)


def test_a_green_amend_and_a_duplicate_observation_count_one_pair() -> None:
    first = _message(
        checksum="sha256:first",
        red="2026-10-01T20:00:00Z",
        green="2026-10-01T20:04:00Z",
    )
    duplicate = _message(
        checksum="sha256:first",
        red="2026-10-01T20:00:00Z",
        green="2026-10-01T20:09:00Z",
    )

    assert verified_pair_ids(messages=(first, duplicate)) == ("sha256:first@2026-10-01T20:00:00Z",)


def test_open_red_suite_green_and_unrelated_history_are_not_pairs() -> None:
    assert (
        verified_pair_ids(
            messages=(
                _message(checksum="sha256:open", red="2026-10-01T20:00:00Z"),
                _message(suite_green="2026-10-01T20:04:00Z"),
                _message(),
            )
        )
        == ()
    )


def test_a_pair_without_checksum_uses_its_message_as_its_identity() -> None:
    pair = _message(red="2026-10-01T20:00:00Z", green="2026-10-01T20:04:00Z")

    assert verified_pair_ids(messages=(pair, pair)) == (f"message:{pair}",)


def test_observed_zero_and_unreadable_series_remain_distinct() -> None:
    observed = observed_pair_count(messages=(_message(),))
    unreadable = unobserved_pair_count(reason="commits-unreadable")

    assert (observed.count, observed.unobserved_reason) == (0, None)
    assert (unreadable.count, unreadable.unobserved_reason) == (None, "commits-unreadable")


def test_calibration_distinguishes_an_observed_zero_from_an_unreadable_series(
    tmp_path: Path,
) -> None:
    """Scenario 165 preserves the distinction through the Dispatcher boundary."""
    records = (
        {"stage": "dispatch-id", "work_item_id": "bd-ib-defs3b", "dispatch_id": _DISPATCH_ID},
    )
    readable = gather_tdd_signals(
        repo=Path("/repo"),
        item=_item(),
        outcome=_outcome(),
        records=records,
        sink=TddOrderSink(path=tmp_path / "readable-order.json"),
        runner=_Runner(
            stdout=_commits_payload(
                message=(
                    "TDD-Red-Captured-At: 2026-10-01T20:00:00Z\n" f"Factory-Run-Id: {_DISPATCH_ID}"
                )
            )
        ),
    )
    unreadable = gather_tdd_signals(
        repo=Path("/repo"),
        item=_item(),
        outcome=_outcome(),
        records=records,
        sink=TddOrderSink(path=tmp_path / "unreadable-order.json"),
        runner=_Runner(exit_code=1),
    )

    assert (
        tdd_signal_fields(signals=readable)["tdd.verified_pair_count"],
        tdd_signal_fields(signals=readable)["tdd.verified_pair_unobserved_reason"],
    ) == (0, None)
    assert (
        tdd_signal_fields(signals=unreadable)["tdd.verified_pair_count"],
        tdd_signal_fields(signals=unreadable)["tdd.verified_pair_unobserved_reason"],
    ) == (None, "commits-unreadable")
