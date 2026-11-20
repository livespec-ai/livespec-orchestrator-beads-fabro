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


def _clean_seeded_repo(*, tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "clone"
    repo.mkdir()
    _ = subprocess.run(["git", "init", "--quiet", "--initial-branch=master"], cwd=repo, check=True)
    _ = subprocess.run(["git", "config", "user.name", "Fixture"], cwd=repo, check=True)
    _ = subprocess.run(
        ["git", "config", "user.email", "fixture@example.invalid"], cwd=repo, check=True
    )
    _ = (repo / "unchanged.txt").write_text("dispatch base\n", encoding="utf-8")
    _ = subprocess.run(["git", "add", "unchanged.txt"], cwd=repo, check=True)
    _ = subprocess.run(["git", "commit", "--quiet", "-m", "dispatch base"], cwd=repo, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    _ = subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/master", "HEAD"], cwd=repo, check=True
    )
    return repo, base


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


def test_a_clean_seeded_green_with_preview_exit_two_ends_already_satisfied(
    tmp_path: Path,
) -> None:
    """A no-change seeded Green accepts its no-staged-change preview and takes the clean terminal."""
    repo, base = _clean_seeded_repo(tmp_path=tmp_path)

    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    git_dir = repo / ".git"
    _ = (git_dir / _PREVIEW_RECORD).write_text(
        json.dumps({"failed_targets": [], "preview_ran": True, "status": 2}) + "\n",
        encoding="utf-8",
    )
    handoff_path = git_dir / _HANDOFF
    _ = handoff_path.write_text(
        "## seeded-red-passes\nThe seeded Red test passes.\n\n"
        "## green\npreview exit status: 2; failed targets: none\n",
        encoding="utf-8",
    )

    completion = subprocess.run(
        ["sh", "-c", graph.nodes[_GATE]["script"]],
        cwd=repo,
        check=False,
        capture_output=True,
        input=_COMPLETION,
        text=True,
    )

    assert completion.returncode == 0, completion.stderr
    assert json.loads(completion.stdout) == {"preferred_next_label": "already-satisfied"}
    assert "## green-preview-refused" not in handoff_path.read_text(encoding="utf-8")

    clean_route = next(
        edge.destination
        for edge in graph.edges
        if edge.source == _GATE
        and edge.attributes.get("condition") == "preferred_label=already-satisfied"
    )
    assert clean_route == "already_satisfied_route"
    route_script = graph.nodes[clean_route]["script"].replace(
        "{{ inputs.default_branch }}", "master"
    )
    route = subprocess.run(
        ["sh", "-c", route_script], cwd=repo, check=False, capture_output=True, text=True
    )

    assert route.returncode == 0, route.stderr
    assert json.loads(route.stdout) == {"preferred_next_label": "unchanged"}
    terminal_script = graph.nodes["already_satisfied"]["script"].replace(
        "{{ inputs.default_branch }}", "master"
    )
    terminal = subprocess.run(
        ["sh", "-c", terminal_script], cwd=repo, check=False, capture_output=True, text=True
    )
    assert terminal.returncode == 0, terminal.stderr
    assert f"LIVESPEC_ALREADY_SATISFIED: base={base}" in terminal.stderr
