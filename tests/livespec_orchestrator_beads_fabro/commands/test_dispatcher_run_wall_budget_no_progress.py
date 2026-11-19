"""The no-progress cut preserves its own reason through the blocked-item comment."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_run_wall_budget_no_progress,
    _dispatcher_run_wall_budget_watch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import RunWallBudget
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_comment import (
    run_wall_budget_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    run_wall_budget_exceeded_record,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import REPOSITORY_LAYER


def test_no_progress_cut_is_named_in_the_blocked_item_comment() -> None:
    row = run_wall_budget_exceeded_record(
        work_item_id="bd-ib-jrzbgj",
        dispatch_id="dispatch-01",
        run_id="01RUN",
        factory="petri",
        executing_stage="fix@4",
        publication=None,
        elapsed_seconds=3600.0,
        budget=RunWallBudget(seconds=21600.0, layer=REPOSITORY_LAYER),
        start_source="recorded-running",
        preserved_pointer="comment-9173",
        no_progress_stages=("green@4", "fix@3", "fix@4"),
    )

    comment = run_wall_budget_comment(item_id="bd-ib-jrzbgj", row=row)

    assert "no-progress cut" in comment
    assert "K: 3" in comment
    assert "stages: green@4, fix@3, fix@4" in comment
    assert "before its whole-run wall budget" in comment


def test_changing_implementation_diffs_do_not_match_the_no_progress_cut() -> None:
    stage_diffs = {
        "green@1": "a" * 79,
        "commit_green@1": "b" * 80,
        "fix@1": "c" * 81,
    }

    cut = _dispatcher_run_wall_budget_no_progress.trailing_empty_implementation_stages(
        stage_diffs=stage_diffs,
        consecutive_stage_count=3,
    )

    assert cut is None


def test_an_incomplete_no_progress_measurement_is_not_rendered_as_a_cut() -> None:
    row = run_wall_budget_exceeded_record(
        work_item_id="bd-ib-jrzbgj",
        dispatch_id="dispatch-01",
        run_id="01RUN",
        factory="petri",
        executing_stage="fix@4",
        publication=None,
        elapsed_seconds=3600.0,
        budget=RunWallBudget(seconds=21600.0, layer=REPOSITORY_LAYER),
        start_source="recorded-running",
        preserved_pointer="comment-9173",
        no_progress_stages=("green@4", "fix@3", "fix@4"),
    )
    row["no_progress_stages"] = ["green@4", 3, "fix@4"]

    comment = run_wall_budget_comment(item_id="bd-ib-jrzbgj", row=row)

    assert "no-progress cut" not in comment


def test_no_progress_holds_when_the_preservation_pointer_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held: dict[str, object] = {}
    monkeypatch.setattr(
        _dispatcher_run_wall_budget_no_progress,
        "preserved_pointer",
        lambda **_: SimpleNamespace(pointer=None, failed_measurement="export unread"),
    )
    monkeypatch.setattr(
        _dispatcher_run_wall_budget_no_progress,
        "watchdog_run_reading",
        lambda **_: SimpleNamespace(),
    )
    monkeypatch.setattr(
        _dispatcher_run_wall_budget_no_progress,
        "hold_run",
        lambda **kwargs: held.update(kwargs),
    )

    verdict = _dispatcher_run_wall_budget_no_progress.cancel_run_for_no_progress(
        dispatch_id="dispatch-01",
        plan=SimpleNamespace(),
        port=object(),
        runner=object(),
        journal=object(),
        run_id="01RUN",
        ledger=None,
        stage_diffs={"green@1": "", "commit_green@1": "", "fix@1": ""},
    )

    assert verdict is _dispatcher_run_wall_budget_watch.RunWallVerdict.HELD
    assert held["failed_measurement"] == "export unread"


def test_cancel_for_no_progress_leaves_a_run_with_changing_diffs_within_budget() -> None:
    verdict = _dispatcher_run_wall_budget_no_progress.cancel_run_for_no_progress(
        dispatch_id="dispatch-01",
        plan=SimpleNamespace(),
        port=object(),
        runner=object(),
        journal=object(),
        run_id="01RUN",
        ledger=None,
        stage_diffs={"green@1": "a" * 200, "commit_green@1": "", "fix@1": ""},
    )

    assert verdict is _dispatcher_run_wall_budget_watch.RunWallVerdict.WITHIN


def test_nonpositive_k_never_matches_empty_stage_diffs() -> None:
    cut = _dispatcher_run_wall_budget_no_progress.trailing_empty_implementation_stages(
        stage_diffs={"green@1": ""},
        consecutive_stage_count=0,
    )

    assert cut is None


def test_watch_returns_the_no_progress_verdict_before_consulting_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _dispatcher_run_wall_budget_watch,
        "cancel_run_for_no_progress",
        lambda **_: _dispatcher_run_wall_budget_watch.RunWallVerdict.CANCELLED,
    )
    monkeypatch.setattr(
        _dispatcher_run_wall_budget_watch,
        "stage_diffs_from_run_record",
        lambda **_: {"green@1": "", "commit_green@1": "", "fix@1": ""},
    )
    monkeypatch.setattr(
        _dispatcher_run_wall_budget_watch,
        "cancel_run_past_budget",
        lambda **_: _dispatcher_run_wall_budget_watch.RunWallVerdict.WITHIN,
    )
    watch = _dispatcher_run_wall_budget_watch.RunWallBudgetWatch(ledger=None)

    verdict = None
    for now_epoch in (3600.0, 7200.0):
        verdict = watch.verdict(
            dispatch_id="dispatch-01",
            plan=SimpleNamespace(),
            port=object(),
            runner=object(),
            journal=object(),
            run_id="01RUN",
            recorded_epoch=0.0,
            now_epoch=now_epoch,
        )

    assert verdict is _dispatcher_run_wall_budget_watch.RunWallVerdict.CANCELLED
