"""Scenario 285 — an unstructured Green hook refusal retains its diagnostics."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_ROOT = Path(__file__).parents[2]
_GRAPH = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_PREVIEW_RECORD = "livespec-implement-gate-preview-green-result.json"
_HANDOFF = "livespec-implement-handoff.md"
_COMPLETION = '{"definition_of_done_complete": true}'


def test_an_unstructured_failed_preview_refusal_includes_its_recorded_output_tail(
    tmp_path: Path,
) -> None:
    """The refusal names the hook's diagnostic instead of claiming no failure detail."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    repo = tmp_path / "clone"
    repo.mkdir()
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    git_dir = repo / ".git"
    _ = (git_dir / _PREVIEW_RECORD).write_text(
        json.dumps(
            {
                "failed_targets": [],
                "output_tail": "running staged-file pre-check\\n"
                "type pre-check rejected created.py\\n",
                "preview_ran": True,
                "status": 23,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    handoff = git_dir / _HANDOFF
    _ = handoff.write_text(
        "## green\npreview exit status: 23; failed targets: none\n", encoding="utf-8"
    )

    completed = subprocess.run(
        ["sh", "-c", graph.nodes["implement_completion"]["script"]],
        cwd=repo,
        check=False,
        capture_output=True,
        input=_COMPLETION,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"preferred_next_label": "incomplete"}
    assert "recorded failed targets: none" in completed.stderr
    assert "recorded output tail:" in completed.stderr
    assert "type pre-check rejected created.py" in completed.stderr
    assert "type pre-check rejected created.py" in handoff.read_text(encoding="utf-8")


def test_a_structured_failed_preview_refusal_does_not_render_an_unneeded_output_tail(
    tmp_path: Path,
) -> None:
    """A parsed target list remains the refusal's precise failure account."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    repo = tmp_path / "clone"
    repo.mkdir()
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    git_dir = repo / ".git"
    _ = (git_dir / _PREVIEW_RECORD).write_text(
        json.dumps(
            {
                "failed_targets": ["check-types"],
                "output_tail": "unstructured-looking later output\\n",
                "preview_ran": True,
                "status": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _ = (git_dir / _HANDOFF).write_text(
        "## green\npreview exit status: 1; failed targets: check-types\n", encoding="utf-8"
    )

    completed = subprocess.run(
        ["sh", "-c", graph.nodes["implement_completion"]["script"]],
        cwd=repo,
        check=False,
        capture_output=True,
        input=_COMPLETION,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "recorded failed targets: check-types" in completed.stderr
    assert "recorded output tail:" not in completed.stderr


def test_a_silent_failed_preview_refusal_says_the_hook_produced_no_output(
    tmp_path: Path,
) -> None:
    """An empty recorded tail is reported as silence, not as 'failed targets: none' alone."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    repo = tmp_path / "clone"
    repo.mkdir()
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    git_dir = repo / ".git"
    _ = (git_dir / _PREVIEW_RECORD).write_text(
        json.dumps({"failed_targets": [], "output_tail": "", "preview_ran": True, "status": 23})
        + "\n",
        encoding="utf-8",
    )
    _ = (git_dir / _HANDOFF).write_text(
        "## green\npreview exit status: 23; failed targets: none\n", encoding="utf-8"
    )

    completed = subprocess.run(
        ["sh", "-c", graph.nodes["implement_completion"]["script"]],
        cwd=repo,
        check=False,
        capture_output=True,
        input=_COMPLETION,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "recorded output tail:" in completed.stderr
    assert "the hook produced no output" in completed.stderr
