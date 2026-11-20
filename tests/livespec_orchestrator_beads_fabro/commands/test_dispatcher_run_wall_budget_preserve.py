"""The wall-budget preservation adapter keeps a cut explanation with its pointer."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_run_wall_budget_preserve as module,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_export import (
    ExportOutcome,
)


def test_preserved_pointer_appends_the_no_progress_explanation_before_read_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def export_run_reference(**kwargs: object) -> ExportOutcome:
        captured.update(kwargs)
        return ExportOutcome(
            exported=True,
            comment_id="comment-9173",
            journal_body=None,
            detail="preserve-by-reference comment written and read back for 01RUN",
        )

    monkeypatch.setattr(module, "export_run_reference", export_run_reference)

    preserved = module.preserved_pointer(
        plan=SimpleNamespace(
            fabro_factory_server="https://factory.example.test",
            work_item_id="bd-ib-jrzbgj",
            repo="/repo",
            fabro_bin="fabro",
        ),
        runner=object(),
        run_id="01RUN",
        ledger=object(),
        pointer_suffix="\n\nno-progress cut\n\nK: 3",
    )

    assert preserved.pointer == "comment-9173"
    assert captured["pointer_suffix"] == "\n\nno-progress cut\n\nK: 3"


def test_preserved_pointer_holds_when_the_factory_server_is_unresolved() -> None:
    preserved = module.preserved_pointer(
        plan=SimpleNamespace(
            fabro_factory_server=None,
            work_item_id="bd-ib-jrzbgj",
            repo="/repo",
            fabro_bin="fabro",
        ),
        runner=object(),
        run_id="01RUN",
        ledger=object(),
    )

    assert preserved.pointer is None
    assert "no server url" in preserved.failed_measurement
