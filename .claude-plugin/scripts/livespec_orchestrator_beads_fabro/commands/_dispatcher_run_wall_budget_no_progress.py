"""The empty-diff no-progress cut shared by the run-wall budget watch."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_export import (
    LedgerComments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_hold import (
    RunWallHoldState,
    hold_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_preserve import (
    preserved_pointer,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_clock import (
    RunWallStart,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog_run_probe import (
    watchdog_run_reading,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_stage_diffs import (
    stage_diffs_from_run_state,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        JournalWriter,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
    from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
        RunWallVerdictValue,
    )

__all__: list[str] = [
    "EMPTY_DIFF_MARKER_MAX_BYTES",
    "NO_PROGRESS_CONSECUTIVE_STAGE_COUNT",
    "NO_PROGRESS_TIME_FLOOR_SECONDS",
    "NoProgressSpan",
    "cancel_run_for_no_progress",
    "no_progress_pointer_suffix",
    "stage_diffs_from_run_record",
    "trailing_empty_implementation_stages",
]

EMPTY_DIFF_MARKER_MAX_BYTES: Final = 78
NO_PROGRESS_CONSECUTIVE_STAGE_COUNT: Final = 3
NO_PROGRESS_TIME_FLOOR_SECONDS: Final = 3600.0
_NO_PROGRESS_STAGE_BASES: Final = frozenset(
    {"implement", "red", "green", "fix", "commit_red", "commit_green"}
)
_NUMBERED_STAGE_PREFIX = re.compile(r"^\d+-")
_NO_PROGRESS_START = RunWallStart(epoch=0.0, source="no-progress-cut")
_INSPECT_TIMEOUT_SECONDS = 60.0


@dataclass(kw_only=True)
class NoProgressSpan:
    """How long the run's trailing empty-diff sequence has been observed.

    The time floor guards against cutting a run on a transient reading, so it
    must measure the sequence itself rather than the slot's age: a run that made
    real progress for an hour and then emits K marker-sized diffs seconds apart
    has a span of seconds. The run-state projection carries no per-stage
    instant, so the span runs from the first poll that saw the sequence,
    which can only make it shorter than the true span and so cut later. Any
    reading without a trailing empty sequence ends it.
    """

    since_epoch: float | None = None

    def observe(self, *, stages: tuple[str, ...] | None, now_epoch: float) -> float | None:
        """This poll's span in seconds, or None when no empty sequence is trailing."""
        if stages is None:
            self.since_epoch = None
            return None
        if self.since_epoch is None:
            self.since_epoch = now_epoch
        return now_epoch - self.since_epoch


def cancel_run_for_no_progress(  # noqa: PLR0913 -- the shared preservation seams are independent.
    *,
    dispatch_id: str | None,
    plan: DispatchPlan,
    port: FabroPort,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str,
    ledger: LedgerComments | None,
    stage_diffs: Mapping[str, str],
    consecutive_stage_count: int = NO_PROGRESS_CONSECUTIVE_STAGE_COUNT,
    elapsed_seconds: float = 0.0,
    start: RunWallStart = _NO_PROGRESS_START,
    hold: RunWallHoldState | None = None,
) -> RunWallVerdictValue:
    """Preserve and cancel a run with K trailing empty implementation diffs."""
    # Imported lazily: the budget watch re-exports this entry point for its
    # stable call surface, while this cut reuses its one cancel record writer.
    from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
        RunWallVerdict,
        cancel_preserved_run,
    )

    stages = trailing_empty_implementation_stages(
        stage_diffs=stage_diffs, consecutive_stage_count=consecutive_stage_count
    )
    if stages is None:
        return RunWallVerdict.WITHIN
    preserved = preserved_pointer(
        plan=plan,
        runner=runner,
        run_id=run_id,
        ledger=ledger,
        pointer_suffix=no_progress_pointer_suffix(
            consecutive_stage_count=consecutive_stage_count, stages=stages
        ),
    )
    reading = watchdog_run_reading(port=port, run_id=run_id)
    if preserved.pointer is not None:
        cancel_preserved_run(
            dispatch_id=dispatch_id,
            plan=plan,
            port=port,
            journal=journal,
            run_id=run_id,
            elapsed_seconds=elapsed_seconds,
            start=start,
            reading=reading,
            pointer=preserved.pointer,
            verified_ref=None,
            export_failure=preserved.failed_measurement,
            no_progress_stages=stages,
        )
        return RunWallVerdict.CANCELLED
    hold_run(
        state=RunWallHoldState() if hold is None else hold,
        plan=plan,
        journal=journal,
        ledger=ledger,
        run_id=run_id,
        elapsed_seconds=elapsed_seconds,
        failed_measurement=preserved.failed_measurement,
    )
    return RunWallVerdict.HELD


def stage_diffs_from_run_record(*, port: FabroPort, run_id: str) -> dict[str, str]:
    """Read the current stage-diff projection without guessing from event text."""
    state = port.server_api().run_state(run_id=run_id, timeout_seconds=_INSPECT_TIMEOUT_SECONDS)
    if not state.succeeded:
        return {}
    return {
        _stage_name_from_artifact_path(path=stage_diff.path.as_posix()): stage_diff.payload
        for stage_diff in stage_diffs_from_run_state(run_state=state.payload)
    }


def trailing_empty_implementation_stages(
    *, stage_diffs: Mapping[str, str], consecutive_stage_count: int
) -> tuple[str, ...] | None:
    """Return the last K eligible stages only when each diff is empty."""
    if consecutive_stage_count <= 0:
        return None
    trailing = [
        (name, payload)
        for name, payload in stage_diffs.items()
        if _is_implementation_stage(name=name)
    ][-consecutive_stage_count:]
    if len(trailing) != consecutive_stage_count:
        return None
    if any(len(payload.encode("utf-8")) > EMPTY_DIFF_MARKER_MAX_BYTES for _, payload in trailing):
        return None
    return tuple(name for name, _ in trailing)


def no_progress_pointer_suffix(*, consecutive_stage_count: int, stages: tuple[str, ...]) -> str:
    """Name the predicate evidence in the exported preserve pointer."""
    return "\n\n".join(
        ("", "no-progress cut", f"K: {consecutive_stage_count}", f"stages: {', '.join(stages)}")
    )


def _stage_name_from_artifact_path(*, path: str) -> str:
    directory = path.split("/")[-2]
    return directory.split("-", 1)[-1]


def _is_implementation_stage(*, name: str) -> bool:
    base = _NUMBERED_STAGE_PREFIX.sub("", name).split("@", 1)[0]
    return base in _NO_PROGRESS_STAGE_BASES
