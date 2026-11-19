"""Scenario 285 — Green's preview evidence outranks its handoff prose."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_ROOT = Path(__file__).parents[2]
_GRAPH = (
    _ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.fabro"
)
_GATE = "implement_completion"
_COMPLETION = '{"definition_of_done_complete": true}'
_PREVIEW_RECORD = "livespec-implement-gate-preview-green-result.json"
_HANDOFF = "livespec-implement-handoff.md"


def _gate_script() -> str:
    """Read the command-node bytes that a Green handoff actually reaches."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return graph.nodes[_GATE]["script"]


@pytest.mark.parametrize(
    ("handoff", "needle"),
    [
        ("preview exit status: 1; failed targets: check-per-file-coverage\n", "exit status 1"),
        ("preview exit status: 0; failed targets: none\n", "failed targets none"),
    ],
    ids=("claimed-status-differs", "claimed-targets-differ"),
)
def test_a_clean_recorded_preview_refuses_green_prose_that_misstates_it(
    tmp_path: Path, handoff: str, needle: str
) -> None:
    """Only the persisted tool result can authorize the complete route.

    Both controls use a successful recorded preview.  They therefore establish
    that this is not merely the failed-preview refusal: a made-up status or
    failed-target list in the latest ``## green`` section also re-enters Green.
    """
    repo = tmp_path / "clone"
    repo.mkdir()
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    git_dir = repo / ".git"
    _ = (git_dir / _PREVIEW_RECORD).write_text(
        json.dumps(
            {
                "failed_targets": ["check-per-file-coverage"],
                "preview_ran": True,
                "status": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    handoff_path = git_dir / _HANDOFF
    _ = handoff_path.write_text(f"## green\n{handoff}", encoding="utf-8")

    completed = subprocess.run(
        ["sh", "-c", _gate_script()],
        cwd=repo,
        check=False,
        capture_output=True,
        input=_COMPLETION,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"preferred_next_label": "incomplete"}
    assert needle in completed.stderr
    assert "check-per-file-coverage" in completed.stderr
    assert "## green-preview-refused" in handoff_path.read_text(encoding="utf-8")
