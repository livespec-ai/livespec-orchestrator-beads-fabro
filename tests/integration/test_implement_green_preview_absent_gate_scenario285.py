"""Scenario 285 — a Green handoff with no recorded preview result is refused."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_ROOT = Path(__file__).parents[2]
_GRAPH = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_GATE = "implement_completion"
_COMPLETION = '{"definition_of_done_complete": true}'
_PREVIEW_RECORD = "livespec-implement-gate-preview-green-result.json"
_HANDOFF = "livespec-implement-handoff.md"
_HANDOFF_TEXT = "## green\nfocused tests passed; the preview timed out after 180s without output\n"


def _gate_script() -> str:
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return graph.nodes[_GATE]["script"]


def _run_gate(
    *, tmp_path: Path, record: str | None
) -> tuple[subprocess.CompletedProcess[str], Path]:
    repo = tmp_path / "clone"
    repo.mkdir()
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    git_dir = repo / ".git"
    if record is not None:
        _ = (git_dir / _PREVIEW_RECORD).write_text(record, encoding="utf-8")
    handoff_path = git_dir / _HANDOFF
    _ = handoff_path.write_text(_HANDOFF_TEXT, encoding="utf-8")
    completed = subprocess.run(
        ["sh", "-c", _gate_script()],
        cwd=repo,
        check=False,
        capture_output=True,
        input=_COMPLETION,
        text=True,
    )
    return completed, handoff_path


@pytest.mark.parametrize(
    "record",
    [None, "", "{}\n", json.dumps({"failed_targets": [], "preview_ran": False}) + "\n"],
    ids=["absent", "empty", "no-status-object", "no-status-key"],
)
def test_an_absent_or_resultless_preview_record_refuses_the_green_handoff(
    tmp_path: Path, record: str | None
) -> None:
    """A stalled preview leaves no result, and no result cannot authorize a handoff."""
    completed, handoff_path = _run_gate(tmp_path=tmp_path, record=record)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"preferred_next_label": "incomplete"}
    assert "LIVESPEC_GREEN_PREVIEW_REFUSED" in completed.stderr
    assert "gate-preview" in completed.stderr
    assert "no result" in completed.stderr
    assert "## green-preview-refused" in handoff_path.read_text(encoding="utf-8")


def test_a_recorded_clean_preview_still_completes_the_green_handoff(tmp_path: Path) -> None:
    """The refusal is for a missing result only; a recorded exit zero proceeds."""
    record = json.dumps({"failed_targets": [], "preview_ran": True, "status": 0}) + "\n"
    completed, _ = _run_gate(tmp_path=tmp_path, record=record)

    assert json.loads(completed.stdout) == {"preferred_next_label": "complete"}
