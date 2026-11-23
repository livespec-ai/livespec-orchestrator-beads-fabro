"""The product logical-line measurement for a completed cycle."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_measure"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_cycle_measure.py"
)


def _module() -> ModuleType:
    """Load the counter after a Red-safe existence assertion."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def test_a_replaced_product_statement_counts_added_plus_removed_lines() -> None:
    """Scenario 165 counts changed product code, rather than net file growth."""
    module = _module()

    changed = module.changed_product_logical_lines(
        before="value = 1\nother = 2\n",
        after="value = 3\nother = 2\n",
    )

    assert changed == 2
