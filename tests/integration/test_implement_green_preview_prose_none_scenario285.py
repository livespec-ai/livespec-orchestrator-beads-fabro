"""Scenario 285 — A green handoff's prose after "none" is not a failed-target list."""

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


def _run_gate(
    *,
    tmp_path: Path,
    recorded_targets: list[str],
    handoff_line: str,
) -> tuple[dict[str, str], str]:
    """Run the implement_completion script on a passing or failing preview record."""
    repo = tmp_path / "clone"
    repo.mkdir()
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    git_dir = repo / ".git"
    _ = (git_dir / _PREVIEW_RECORD).write_text(
        json.dumps(
            {
                "failed_targets": recorded_targets,
                "preview_ran": True,
                "status": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _ = (git_dir / _HANDOFF).write_text(
        f"## green\npreview exit status: 0\n{handoff_line}\n",
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
    return json.loads(completed.stdout), completed.stderr


def test_prose_in_parentheses_after_none_is_not_a_failed_target_list(tmp_path: Path) -> None:
    """The overseer-faf7w4 shape: "none (all 91 targets passed)" claims no targets."""
    verdict, stderr = _run_gate(
        tmp_path=tmp_path,
        recorded_targets=[],
        handoff_line="Failed targets: none (all 91 targets passed)",
    )

    assert verdict == {"preferred_next_label": "complete"}, stderr
    assert "LIVESPEC_GREEN_PREVIEW_REFUSED" not in stderr


def test_prose_after_none_and_a_comma_is_not_a_failed_target_list(tmp_path: Path) -> None:
    """The overseer-7cwey5 shape: "none, and all 91 aggregate targets passed" claims none."""
    verdict, stderr = _run_gate(
        tmp_path=tmp_path,
        recorded_targets=[],
        handoff_line="Failed targets: none, and all 91 aggregate targets passed",
    )

    assert verdict == {"preferred_next_label": "complete"}, stderr
    assert "LIVESPEC_GREEN_PREVIEW_REFUSED" not in stderr


def test_a_listed_target_the_record_does_not_name_is_still_refused(tmp_path: Path) -> None:
    """A real claimed target absent from the recorded tool result still refuses."""
    verdict, stderr = _run_gate(
        tmp_path=tmp_path,
        recorded_targets=[],
        handoff_line="Failed targets: check-per-file-coverage",
    )

    assert verdict == {"preferred_next_label": "incomplete"}
    assert "handoff states failed targets check-per-file-coverage" in stderr


def test_a_listed_target_the_record_names_is_not_refused(tmp_path: Path) -> None:
    """A claimed target the recorded tool result also names still matches."""
    _, stderr = _run_gate(
        tmp_path=tmp_path,
        recorded_targets=["check-per-file-coverage"],
        handoff_line="Failed targets: check-per-file-coverage",
    )

    assert "the handoff states failed targets" not in stderr
