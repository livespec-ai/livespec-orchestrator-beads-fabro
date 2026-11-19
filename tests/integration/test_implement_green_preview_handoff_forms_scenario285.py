"""Scenario 285 — the handoff comparison reads every stated form of the preview result."""

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


def _run_gate(*, tmp_path: Path, status: int, targets: list[str], section: str) -> tuple[str, str]:
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    repo = tmp_path / "clone"
    repo.mkdir()
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    git_dir = repo / ".git"
    record = {"failed_targets": targets, "preview_ran": True, "status": status}
    _ = (git_dir / _PREVIEW_RECORD).write_text(json.dumps(record) + "\n", encoding="utf-8")
    _ = (git_dir / _HANDOFF).write_text(section, encoding="utf-8")
    completed = subprocess.run(
        ["sh", "-c", graph.nodes[_GATE]["script"]],
        cwd=repo,
        check=False,
        capture_output=True,
        input=_COMPLETION,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)["preferred_next_label"], completed.stderr


@pytest.mark.parametrize(
    ("section", "stated"),
    [
        ("## green\nPreview exited 1.\n", "preview exit status 1"),
        ("## green\n- Gate preview: exit code 2\n", "preview exit status 2"),
        ("## green\nThe gate preview\n  exited with status 3\n", "preview exit status 3"),
    ],
)
def test_a_preview_exit_stated_in_any_form_is_compared(
    tmp_path: Path, section: str, stated: str
) -> None:
    """A stated exit that differs from the recorded success refuses the handoff."""
    label, stderr = _run_gate(tmp_path=tmp_path, status=0, targets=[], section=section)

    assert label == "incomplete"
    assert stated in stderr


@pytest.mark.parametrize(
    ("section", "stated"),
    [
        ("## green\nFailed targets:\n- check-lint\n- check-format\n", "check-format check-lint"),
        ("## green\nPreview failed targets (1): `check-lint`.\n", "check-lint"),
        ("## green\nFailed targets: check-lint and check-format\n", "check-format check-lint"),
    ],
)
def test_failed_targets_stated_in_any_form_are_compared(
    tmp_path: Path, section: str, stated: str
) -> None:
    """A stated target list that differs from the record refuses the handoff."""
    label, stderr = _run_gate(tmp_path=tmp_path, status=0, targets=["check-x"], section=section)

    assert label == "incomplete"
    assert f"the handoff states failed targets {stated} but" in stderr


@pytest.mark.parametrize(
    ("section", "status", "targets"),
    [
        ("## green\nPreview exited 0.\nFailed targets: none\n\n- Changed one file\n", 0, []),
        ("## green\nFailed targets:\n- none\n", 0, []),
        (
            "## green\nFailed targets (2):\n\n- `check-b` (coverage)\n- check-a\n\nDone.\n",
            0,
            ["check-a", "check-b"],
        ),
        ("## green\nFailed targets: none. Everything else passed.\n", 0, []),
    ],
)
def test_a_handoff_that_matches_the_record_is_not_refused(
    tmp_path: Path, section: str, status: int, targets: list[str]
) -> None:
    """Every form agreeing with the recorded result passes the gate."""
    label, _ = _run_gate(tmp_path=tmp_path, status=status, targets=targets, section=section)

    assert label == "complete"
