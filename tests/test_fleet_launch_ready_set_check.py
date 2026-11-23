"""Regression coverage for the fleet launcher's installed-build ready-set probe."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = _REPO_ROOT / "fleet-launch" / "ready-set-check.py"
_MODULE_NAME = "fleet_launch_ready_set_check_under_test"


@dataclass(frozen=True)
class _Item:
    id: str
    status: str
    assignee: str = "unassigned"
    depends_on: tuple[object, ...] = ()


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def _install_store_seam(
    monkeypatch: pytest.MonkeyPatch,
    *,
    items: list[_Item],
    ready_items: list[_Item],
) -> None:
    bootstrap = ModuleType("_bootstrap")
    bootstrap.bootstrap = lambda: None  # type: ignore[attr-defined]
    config = ModuleType("livespec_orchestrator_beads_fabro.commands._config")
    config.resolve_store_config = lambda **_kwargs: "store-config"  # type: ignore[attr-defined]
    selection = ModuleType("livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection")
    selection.ready_items = lambda **_kwargs: ready_items  # type: ignore[attr-defined]
    store = ModuleType("livespec_orchestrator_beads_fabro.store")
    store.read_work_items = lambda **_kwargs: items  # type: ignore[attr-defined]

    for name, module in {
        "_bootstrap": bootstrap,
        "livespec_orchestrator_beads_fabro": ModuleType("livespec_orchestrator_beads_fabro"),
        "livespec_orchestrator_beads_fabro.commands": ModuleType(
            "livespec_orchestrator_beads_fabro.commands"
        ),
        config.__name__: config,
        selection.__name__: selection,
        store.__name__: store,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)


def test_ready_set_check_reports_usage_for_an_incomplete_argument_vector(
    capsys: pytest.CaptureFixture[str],
) -> None:
    check = _module()

    assert check.main(argv=["ready-set-check.py"]) == check.USAGE_ERROR
    assert "Usage: ready-set-check.py" in capsys.readouterr().out


def test_ready_set_check_reports_a_missing_item(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    check = _module()
    _install_store_seam(monkeypatch, items=[], ready_items=[])

    assert check.main(argv=["ready-set-check.py", "plugin", str(tmp_path), "bd-ib-missing"]) == 3
    assert capsys.readouterr().out == "READY-CHECK bd-ib-missing: not found\n"


def test_ready_set_check_admits_a_pending_approval_item_with_clear_dependencies(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    check = _module()
    item = _Item(id="bd-ib-pending", status="pending-approval")
    _install_store_seam(monkeypatch, items=[item], ready_items=[item])

    assert check.main(argv=["ready-set-check.py", "plugin", str(tmp_path), item.id]) == 0
    assert "pending-approval with clear dependencies" in capsys.readouterr().out


def test_ready_set_check_reports_an_item_in_the_regular_ready_set(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    check = _module()
    item = _Item(id="bd-ib-ready", status="ready")
    _install_store_seam(monkeypatch, items=[item], ready_items=[item])

    assert check.main(argv=["ready-set-check.py", "plugin", str(tmp_path), item.id]) == 0
    assert capsys.readouterr().out == "READY-CHECK bd-ib-ready: in the ready set\n"


def test_ready_set_check_names_visible_open_blockers(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    check = _module()
    item = _Item(
        id="bd-ib-blocked",
        status="pending-approval",
        assignee="seat-a",
        depends_on=(
            SimpleNamespace(work_item_id="bd-ib-active"),
            {"work_item_id": "bd-ib-done"},
            "bd-ib-closed",
            "bd-ib-not-visible",
        ),
    )
    _install_store_seam(
        monkeypatch,
        items=[
            item,
            _Item(id="bd-ib-active", status="active"),
            _Item(id="bd-ib-done", status="done"),
            _Item(id="bd-ib-closed", status="closed"),
        ],
        ready_items=[],
    )

    assert check.main(argv=["ready-set-check.py", "plugin", str(tmp_path), item.id]) == 3
    assert capsys.readouterr().out == (
        "READY-CHECK bd-ib-blocked: NOT in the ready set (status=pending-approval "
        "assignee=seat-a open blockers: ['bd-ib-active=active'])\n"
    )
