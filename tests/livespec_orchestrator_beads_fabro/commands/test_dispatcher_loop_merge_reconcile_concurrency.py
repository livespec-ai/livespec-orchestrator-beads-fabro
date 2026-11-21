"""A launch does not wait for another item's post-merge reconciliation.

The loop preamble surveys stranded claims.  A claim whose separately published
pull request merged routes through ``reconcile-merged``, which can wait for a
post-merge janitor gate.  That work must continue to its verdict without
serializing a later item's launch behind it.
"""

from __future__ import annotations

import argparse
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_loop_command as loop_command,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_run_checks as run_checks,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-later-launch",
        type="bug",
        status="ready",
        title="A later loop launch",
        description="Launch this item while another item is reconciled.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-21T22:28:33Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _stub_preamble(*, monkeypatch: pytest.MonkeyPatch, reconcile: object) -> None:
    monkeypatch.setattr(run_checks, "require_invoker_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(run_checks, "parse_janitor", lambda **_kwargs: (None, True))
    monkeypatch.setattr(
        run_checks,
        "_resolve_fabro_factory_for",
        lambda **_kwargs: FactoryTarget(name="test", server=None, dev_token=None),
    )
    for refusal in (
        "schema_validation_refusal",
        "sandbox_capabilities_refusal",
        "explicit_factory_selection_refusal",
        "factory_declaration_refusal",
        "overflow_factories_refusal",
        "record_file_generators_refusal",
        "_fabro_preflight_error",
        "step_discipline_refusal",
    ):
        monkeypatch.setattr(run_checks, refusal, lambda **_kwargs: None)
    monkeypatch.setattr(
        run_checks.factory_bin, "resolve_dispatch_fabro_bin", lambda **_kwargs: "fabro"
    )
    monkeypatch.setattr(run_checks, "reconcile_runs_pass", reconcile)


def _stub_loop(*, monkeypatch: pytest.MonkeyPatch, item: WorkItem, launch_wave: object) -> None:
    journal = SimpleNamespace()
    monkeypatch.setattr(loop_command, "handpicked_host_only_refusal_exit", lambda **_kwargs: None)
    monkeypatch.setattr(loop_command, "arm_otel_egress", lambda **_kwargs: None)
    monkeypatch.setattr(loop_command, "prepare", lambda **_kwargs: ([item], journal))
    for seam in (
        "configuration_or_ledger_exit",
        "factory_size_loop_exit",
        "pre_dispatch_wall_exit",
        "emit_outcomes",
    ):
        monkeypatch.setattr(loop_command, seam, lambda **_kwargs: None)
    monkeypatch.setattr(loop_command, "candidates", lambda **_kwargs: [item])
    monkeypatch.setattr(loop_command, "dispatch_loop_wave", launch_wave)


def test_a_loop_launch_starts_before_another_items_post_merge_reconcile_reaches_its_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launch and the unrelated janitor run concurrently, then both finish."""
    reconciliation_started = threading.Event()
    allow_reconciliation_verdict = threading.Event()
    launch_started = threading.Event()
    events: list[str] = []

    def reconcile(*, args: argparse.Namespace, repo: Path) -> object:
        _ = (args, repo)
        events.append("reconcile-start")
        reconciliation_started.set()
        assert allow_reconciliation_verdict.wait(timeout=1)
        events.append("reconcile-verdict")
        return SimpleNamespace()

    def launch_wave(**_kwargs: object) -> list[object]:
        events.append("launch")
        launch_started.set()
        return []

    item = _item()
    _stub_preamble(monkeypatch=monkeypatch, reconcile=reconcile)
    _stub_loop(monkeypatch=monkeypatch, item=item, launch_wave=launch_wave)

    args = argparse.Namespace(
        repo=str(tmp_path),
        budget=1,
        items=[item.id],
        dry_run=False,
        as_json=True,
        janitor=None,
        factory=None,
        fabro_bin=None,
    )
    loop = threading.Thread(target=loop_command.run_loop_command, kwargs={"args": args})
    loop.start()
    assert reconciliation_started.wait(timeout=1)
    try:
        assert launch_started.wait(timeout=0.2)
    finally:
        allow_reconciliation_verdict.set()
    loop.join(timeout=1)

    assert not loop.is_alive()
    assert events == ["reconcile-start", "launch", "reconcile-verdict"]
