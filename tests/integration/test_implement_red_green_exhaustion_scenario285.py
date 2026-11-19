"""Scenario 285 exhausted command nodes retain their recorded verdicts."""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"


def _run(*, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True)


def _repo(*, tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo = tmp_path / "repo"
    _ = _run(cwd=tmp_path, args=["git", "init", "-q", str(repo)])
    return repo


def test_exhausted_red_and_green_bounds_name_the_last_commit_verdict(tmp_path: Path) -> None:
    """A retry cap reports the command that refused, not an unrelated turn."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph

    for node, counter, section, status, target in (
        ("red_admission", "livespec-red-admission-count", "commit_red", "8", "check-red"),
        ("green_admission", "livespec-green-admission-count", "commit_green", "10", "check-green"),
    ):
        repo = _repo(tmp_path=tmp_path / node)
        git_dir = repo / ".git"
        (git_dir / counter).write_text("3\n", encoding="utf-8")
        (git_dir / "livespec-implement-handoff.md").write_text(
            f"## {section}\nExit status: {status}; failed targets: {target}\n",
            encoding="utf-8",
        )

        result = _run(cwd=repo, args=["sh", "-c", str(graph.nodes[node]["script"])])

        cause = (git_dir / "livespec-stage-cause").read_text(encoding="utf-8")
        assert result.returncode != 0, result.stderr
        assert f"Exit status: {status}" in cause
        assert target in cause


def test_exhausted_commit_nodes_retain_targets_before_a_long_output_tail(tmp_path: Path) -> None:
    """Scenario 285: the needs-human cause retains every command-node target.

    The commit scripts put the hook's `Failed targets` block before their
    rendered output tail.  A long hook transcript therefore pushes that block
    outside the bounded tail that the later admission node used to copy into
    its failure cause.  Both Red and Green must still name the targets from the
    complete command-node record when their ordinary re-entry budget is spent.
    """
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    long_tail = "unrelated hook output\n" * 200

    for node, counter, section, status, targets in (
        (
            "red_admission",
            "livespec-red-admission-count",
            "commit_red",
            "8",
            ("check-red-format", "check-red-types"),
        ),
        (
            "green_admission",
            "livespec-green-admission-count",
            "commit_green",
            "10",
            ("check-green-format", "check-green-types"),
        ),
    ):
        repo = _repo(tmp_path=tmp_path / node)
        git_dir = repo / ".git"
        (git_dir / counter).write_text("3\n", encoding="utf-8")
        (git_dir / "livespec-implement-handoff.md").write_text(
            "\n".join(
                (
                    f"## {section}",
                    f"Exit status: {status}",
                    f"Failed targets ({len(targets)}):",
                    *(f"  - {target}" for target in targets),
                    "Hook output (last 80 lines):",
                    long_tail,
                )
            ),
            encoding="utf-8",
        )

        result = _run(cwd=repo, args=["sh", "-c", str(graph.nodes[node]["script"])])

        cause = (git_dir / "livespec-stage-cause").read_text(encoding="utf-8")
        assert result.returncode != 0, result.stderr
        for target in targets:
            assert target in cause
