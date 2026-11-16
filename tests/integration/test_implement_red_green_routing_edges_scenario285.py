"""Scenario 285 — every changed Red/Green branch is driven from the shipped graph.

The Red/Green split changed conditional routing rather than the command-node
scripts alone.  Each case below gives the helper one ``source->destination``
edge name and the outcome that selects it.  The helper reads the committed
``workflow.fabro`` and resolves that visit exactly as the graph does: matching
conditional edges win, otherwise its unconditional fallthrough does.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotGraph,
    parse_dot_graph,
)

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"


@dataclass(frozen=True, kw_only=True)
class _NodeOutcome:
    """The outcome fields the engine uses to select one outgoing edge."""

    outcome: str
    preferred_label: str | None = None


# Every branch edge changed by the v0.332.0 Red/Green split, keyed by its
# committed graph spelling.  Adding a later changed edge is one new named case.
_BRANCH_OUTCOMES = {
    "red->already_satisfied_route": _NodeOutcome(
        outcome="succeeded", preferred_label="already-satisfied"
    ),
    "already_satisfied_route->red_admission": _NodeOutcome(
        outcome="succeeded", preferred_label="carried"
    ),
    "already_satisfied_route->already_satisfied": _NodeOutcome(
        outcome="succeeded", preferred_label="unchanged"
    ),
    "red->implement_amendment_route": _NodeOutcome(outcome="failed"),
    "implement_amendment_route->needs_human": _NodeOutcome(outcome="failed"),
    "implement_amendment_route->red_admission": _NodeOutcome(outcome="succeeded"),
    "red_admission->needs_human": _NodeOutcome(outcome="failed"),
    "green_admission->needs_human": _NodeOutcome(outcome="failed"),
    "commit_red->red_admission": _NodeOutcome(outcome="failed"),
    "commit_green->green_admission": _NodeOutcome(outcome="failed"),
    "green->test_wrong_reset": _NodeOutcome(outcome="succeeded", preferred_label="test-wrong"),
    "test_wrong_reset->needs_human": _NodeOutcome(outcome="failed"),
    "test_wrong_reset->red_admission": _NodeOutcome(outcome="succeeded"),
    "green->green_amendment_route": _NodeOutcome(outcome="failed"),
    "green_amendment_route->needs_human": _NodeOutcome(outcome="failed"),
    "green_amendment_route->implement_completion": _NodeOutcome(outcome="succeeded"),
    "implement_completion->green_incomplete_route": _NodeOutcome(
        outcome="succeeded", preferred_label="incomplete"
    ),
    "green_incomplete_route->needs_human": _NodeOutcome(outcome="failed"),
    "green_incomplete_route->green": _NodeOutcome(outcome="succeeded"),
}


def _committed_graph() -> DotGraph:
    """The exact workflow payload the factory dispatches."""
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return graph


def _matches(*, condition: str, node_output: _NodeOutcome) -> bool:
    """Whether one changed-edge condition accepts this visit's node output."""
    if condition == f"outcome={node_output.outcome}":
        return True
    return condition == f"preferred_label={node_output.preferred_label}"


def _drive_branch_edge(*, named_edge: str) -> str:
    """Drive one named committed branch edge and return the node it reaches.

    The named form deliberately makes a later edge a one-line test case: add
    its graph spelling and the outcome that chooses it to ``_BRANCH_OUTCOMES``.
    """
    source, expected_destination = named_edge.split("->", maxsplit=1)
    node_output = _BRANCH_OUTCOMES[named_edge]
    outgoing = [edge for edge in _committed_graph().edges if edge.source == source]
    matching = [
        edge.destination
        for edge in outgoing
        if _matches(condition=edge.attributes.get("condition", ""), node_output=node_output)
    ]
    fallthrough = [edge.destination for edge in outgoing if "condition" not in edge.attributes]

    assert expected_destination in (matching or fallthrough), named_edge
    assert len(matching) <= 1, (named_edge, matching)
    assert len(fallthrough) == 1, (named_edge, fallthrough)
    return matching[0] if matching else fallthrough[0]


@pytest.mark.parametrize("named_edge", _BRANCH_OUTCOMES, ids=str)
def test_scenario285_drives_each_changed_red_green_branch_edge(*, named_edge: str) -> None:
    """Every changed edge reaches the target named by its committed graph spelling."""
    _source, expected_destination = named_edge.split("->", maxsplit=1)

    assert _drive_branch_edge(named_edge=named_edge) == expected_destination
