"""The background-reconcile scope: inline outside it, awaited and raising inside it."""

from __future__ import annotations

import threading

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_background_reconcile import (
    reconcile_in_background,
    run_reconcile,
)


def test_outside_a_scope_the_pass_runs_inline() -> None:
    ran: list[str] = []

    run_reconcile(run=lambda: ran.append("pass"))

    assert ran == ["pass"]


def test_inside_a_scope_the_pass_runs_on_another_thread_and_is_awaited_on_exit() -> None:
    caller = threading.get_ident()
    seen: list[int] = []
    release = threading.Event()

    def _slow() -> None:
        _ = release.wait(timeout=2.0)
        seen.append(threading.get_ident())

    with reconcile_in_background():
        run_reconcile(run=_slow)
        assert seen == []
        release.set()

    assert len(seen) == 1
    assert seen[0] != caller


def test_a_failure_the_pass_did_not_absorb_is_raised_when_the_scope_closes() -> None:
    def _boom() -> None:
        raise RuntimeError("bug in the pass")

    with pytest.raises(RuntimeError, match="bug in the pass"), reconcile_in_background():
        run_reconcile(run=_boom)
