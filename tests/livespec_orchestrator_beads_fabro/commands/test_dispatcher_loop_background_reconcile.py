"""Pin that a loop launch never waits on the pass's reconciliation (bd-ib-4ifdud).

The reconciliation pass at the head of a `loop` tick can run a merged item's
post-merge `reconcile-merged` (a janitor gate Job on the shared gates queue, about
ten minutes) through the stranded-claim lane. Run inline, it held every launch
behind another item's acceptance work. The loop therefore starts the pass without
waiting for it, selects and launches meanwhile, and still waits for the pass to
finish before it returns, so the pass always reaches its recorded verdict.
"""

from __future__ import annotations

import argparse
import threading
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_command as loop_command
from livespec_orchestrator_beads_fabro.commands import _dispatcher_run_checks as run_checks
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.types import WorkItem

_WAIT_SECONDS = 2.0


def test_the_loop_selects_while_the_reconciliation_pass_is_still_running_and_then_awaits_it(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    fabro = tmp_path / "fabro"
    _ = fabro.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fabro.chmod(0o755)
    release = threading.Event()
    finished = threading.Event()
    pass_done_when_selecting: list[bool] = []

    def _reconcile(*, args: argparse.Namespace, repo: Path) -> object:
        _ = (args, repo)
        _ = release.wait(timeout=_WAIT_SECONDS)
        finished.set()
        return object()

    def _candidates(*, args: argparse.Namespace, items: list[WorkItem], repo: Path) -> list[Any]:
        _ = (args, items, repo)
        pass_done_when_selecting.append(finished.is_set())
        release.set()
        return []

    monkeypatch.setattr(run_checks, "reconcile_runs_pass", _reconcile)
    monkeypatch.setattr(loop_command, "candidates", _candidates)
    monkeypatch.setattr(loop_command, "arm_otel_egress", lambda **_: None)
    monkeypatch.setattr(
        loop_command,
        "prepare",
        lambda **_: ([], JournalFile(path=repo / "journal.jsonl")),
    )

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--fabro-bin",
            str(fabro),
            "--skip-ledger-check",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    # Selection (the launch's first step) did not wait for the pass...
    assert pass_done_when_selecting == [False]
    # ...and the loop did not return until the pass had run to its end.
    assert finished.is_set()
