"""The session-headroom gate satisfies the parameter-count detector, not suppresses it."""

from __future__ import annotations

import ast
from pathlib import Path

_GATE = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
    / "_dispatcher_session_headroom_gate.py"
)


def test_gate_satisfies_parameter_count_without_a_noqa() -> None:
    """The gate keeps the detector enabled by giving `_assessed_pool` six inputs or fewer."""
    source = _GATE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assessed_pool = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_assessed_pool"
    )

    assert "noqa: PLR0913" not in source
    assert len(assessed_pool.args.kwonlyargs) <= 6
