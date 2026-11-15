"""The implement graph invokes plugin-owned programs outside the orchestrator repo."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_PLUGINS_ROOT = "${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}"


def _graph() -> object:
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return graph


def test_commit_red_uses_the_program_materialized_in_the_plugin_root() -> None:
    """Red must not resolve the target repository's dev-tooling directory."""
    assert _graph().nodes["commit_red"]["script"] == (
        f'bash "{_PLUGINS_ROOT}/livespec-commit-red.sh"'
    )


def test_remaining_implement_commands_use_programs_materialized_in_the_plugin_root() -> None:
    """Green, reset, and janitor must not depend on target-repository tooling."""
    graph = _graph()

    assert graph.nodes["commit_green"]["script"] == (
        f'bash "{_PLUGINS_ROOT}/livespec-commit-green.sh"'
        " {{ inputs.implement_mechanical_reentries }} {{ inputs.implement_mechanical_targets }}"
    )
    assert (
        f'bash "{_PLUGINS_ROOT}/livespec-reset-test-wrong-to-dispatch-base.sh"'
        in graph.nodes["test_wrong_reset"]["script"]
    )
    assert (
        f'bash "{_PLUGINS_ROOT}/livespec-green-token-scope.sh"' in graph.nodes["janitor"]["script"]
    )
