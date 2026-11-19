"""Scenario 285 — a failed Green preview cannot authorize a handoff."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_ROOT = Path(__file__).parents[2]
_GRAPH = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_GATE = "implement_completion"
_COMPLETION = '{"definition_of_done_complete": true}'
_PREVIEW_RECORD = "livespec-implement-gate-preview-green-result.json"
_HANDOFF = "livespec-implement-handoff.md"


def _gate_script() -> str:
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return graph.nodes[_GATE]["script"]


def test_a_failed_recorded_preview_refuses_the_green_handoff(tmp_path: Path) -> None:
    """The completion gate re-enters Green from the tool record, not its prose."""
    repo = tmp_path / "clone"
    repo.mkdir()
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    git_dir = repo / ".git"
    _ = (git_dir / _PREVIEW_RECORD).write_text(
        json.dumps(
            {
                "failed_targets": ["check-per-file-coverage"],
                "preview_ran": True,
                "status": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    handoff_path = git_dir / _HANDOFF
    _ = handoff_path.write_text(
        "## green\npreview exit status: 1; failed targets: check-per-file-coverage\n",
        encoding="utf-8",
    )

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
    assert "check-per-file-coverage" in completed.stderr
    assert "## green-preview-refused" in handoff_path.read_text(encoding="utf-8")
