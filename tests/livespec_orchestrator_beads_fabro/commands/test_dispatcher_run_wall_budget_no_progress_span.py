"""The no-progress floor measures the trailing empty-diff sequence, not the slot's age."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_run_wall_budget_watch


def _watch_with_scripted_diffs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    diffs: list[dict[str, str]],
) -> tuple[_dispatcher_run_wall_budget_watch.RunWallBudgetWatch, list[float]]:
    cuts: list[float] = []
    readings = iter(diffs)
    monkeypatch.setattr(
        _dispatcher_run_wall_budget_watch,
        "stage_diffs_from_run_record",
        lambda **_: next(readings),
    )

    def cut(**kwargs: object) -> object:
        cuts.append(float(str(kwargs["elapsed_seconds"])))
        return _dispatcher_run_wall_budget_watch.RunWallVerdict.CANCELLED

    monkeypatch.setattr(_dispatcher_run_wall_budget_watch, "cancel_run_for_no_progress", cut)
    monkeypatch.setattr(
        _dispatcher_run_wall_budget_watch,
        "cancel_run_past_budget",
        lambda **_: _dispatcher_run_wall_budget_watch.RunWallVerdict.WITHIN,
    )
    return _dispatcher_run_wall_budget_watch.RunWallBudgetWatch(ledger=None), cuts


def _poll(
    watch: _dispatcher_run_wall_budget_watch.RunWallBudgetWatch, *, now_epoch: float
) -> object:
    return watch.verdict(
        dispatch_id="dispatch-01",
        plan=SimpleNamespace(),
        port=object(),
        runner=object(),
        journal=object(),
        run_id="01RUN",
        recorded_epoch=0.0,
        now_epoch=now_epoch,
    )


def test_a_progressing_run_is_not_cut_when_marker_diffs_first_appear_late(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The floor measures the trailing no-progress sequence, not the slot's age."""
    real = "diff --git a/x b/x\n" + "+line\n" * 40
    empties = {"green@1": real, "commit_green@1": "", "fix@1": "", "green@2": ""}
    watch, cuts = _watch_with_scripted_diffs(
        monkeypatch,
        diffs=[{"green@1": real}, empties, empties, empties],
    )

    first = _poll(watch, now_epoch=7200.0)
    second = _poll(watch, now_epoch=7210.0)
    third = _poll(watch, now_epoch=7210.0 + 1800.0)
    fourth = _poll(watch, now_epoch=7210.0 + 3600.0)

    within = _dispatcher_run_wall_budget_watch.RunWallVerdict.WITHIN
    cancelled = _dispatcher_run_wall_budget_watch.RunWallVerdict.CANCELLED
    assert [first, second, third] == [within, within, within]
    assert fourth is cancelled
    assert cuts == [7210.0 + 3600.0]


def test_a_changing_diff_restarts_the_no_progress_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = "diff --git a/x b/x\n" + "+line\n" * 40
    empties = {"green@1": "", "commit_green@1": "", "fix@1": ""}
    watch, cuts = _watch_with_scripted_diffs(
        monkeypatch,
        diffs=[empties, {**empties, "fix@2": real}, empties, empties],
    )

    _ = _poll(watch, now_epoch=4000.0)
    _ = _poll(watch, now_epoch=7000.0)
    _ = _poll(watch, now_epoch=7700.0)
    verdict = _poll(watch, now_epoch=7700.0 + 3599.0)

    assert verdict is _dispatcher_run_wall_budget_watch.RunWallVerdict.WITHIN
    assert cuts == []
