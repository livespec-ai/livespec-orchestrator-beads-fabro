"""Scenario 285 — a failed Green preview cannot authorize a handoff."""

from __future__ import annotations

import json
import os
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
    return graph.nodes[_GATE]["script"].replace("{{ inputs.default_branch }}", "master")


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
        ["sh", "-c", _gate_script()],
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
        ["sh", "-c", terminal_script],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "LIVESPEC_PUBLISH_BRANCH": "feat/bd-ib-bnxzbk"},
    )
    assert terminal.returncode == 0, terminal.stderr
    assert f"LIVESPEC_ALREADY_SATISFIED: base={base} " in terminal.stderr
    assert "work item bd-ib-bnxzbk" in terminal.stderr
    assert "red declared" not in terminal.stderr


def _seed_clean_green_records(*, repo: Path) -> None:
    git_dir = repo / ".git"
    _ = (git_dir / _PREVIEW_RECORD).write_text(
        json.dumps({"failed_targets": [], "preview_ran": True, "status": 2}) + "\n",
        encoding="utf-8",
    )
    _ = (git_dir / _HANDOFF).write_text(
        "## seeded-red-passes\nThe seeded Red test passes.\n\n"
        "## green\npreview exit status: 2; failed targets: none\n",
        encoding="utf-8",
    )


def _run_gate(*, repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", _gate_script()],
        cwd=repo,
        check=False,
        capture_output=True,
        input=_COMPLETION,
        text=True,
    )


def test_a_seeded_green_is_never_judged_clean_against_a_non_dispatch_remote_branch(
    tmp_path: Path,
) -> None:
    """With origin/HEAD absent, an unrelated remote branch is not the dispatch base.

    The unrelated branch stands at HEAD, so reading it as the base would judge the
    tree unchanged and take the already-satisfied terminal. Read against
    origin/master, the committed change is a carried seed, which proceeds to
    commit_green (bd-ib-orez2i).
    """
    repo, _base = _clean_seeded_repo(tmp_path=tmp_path)
    _ = (repo / "changed.txt").write_text("seeded green change\n", encoding="utf-8")
    _ = subprocess.run(["git", "add", "changed.txt"], cwd=repo, check=True)
    _ = subprocess.run(["git", "commit", "--quiet", "-m", "green change"], cwd=repo, check=True)
    _ = subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/aaa-feature", "HEAD"], cwd=repo, check=True
    )
    _seed_clean_green_records(repo=repo)

    completion = _run_gate(repo=repo)

    assert completion.returncode == 0, completion.stderr
    assert json.loads(completion.stdout) == {"preferred_next_label": "complete"}


def test_a_seeded_green_fails_closed_when_the_dispatch_base_ref_is_missing(
    tmp_path: Path,
) -> None:
    """A missing origin/<default branch> leaves the clean-tree guard unable to pass."""
    repo, _base = _clean_seeded_repo(tmp_path=tmp_path)
    _ = subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/aaa-feature", "HEAD"], cwd=repo, check=True
    )
    _ = subprocess.run(
        ["git", "update-ref", "-d", "refs/remotes/origin/master"], cwd=repo, check=True
    )
    _seed_clean_green_records(repo=repo)

    completion = _run_gate(repo=repo)

    assert completion.returncode == 0, completion.stderr
    assert json.loads(completion.stdout) == {"preferred_next_label": "incomplete"}


def _carried_seed_repo(*, tmp_path: Path) -> Path:
    """A seeded clone whose HEAD carries a complete change the dispatch base lacks."""
    repo, _base = _clean_seeded_repo(tmp_path=tmp_path)
    _ = (repo / "carried.py").write_text("ANSWER = 42\n", encoding="utf-8")
    _ = subprocess.run(["git", "add", "carried.py"], cwd=repo, check=True)
    _ = subprocess.run(
        ["git", "commit", "--quiet", "-m", "reseed: complete tree of an earlier run"],
        cwd=repo,
        check=True,
    )
    _seed_clean_green_records(repo=repo)
    return repo


def test_a_carried_complete_seed_with_preview_exit_two_proceeds_to_commit_green(
    tmp_path: Path,
) -> None:
    """A seeded-red-passes Green that stages nothing on a carried seed is complete.

    The carried seed already meets the Definition of Done and is not on the
    dispatch base, so its preview has nothing to stage and exits 2 with no failed
    targets. The run must reach commit_green and publish the carried change
    (Scenario 285, "A seed whose carried changes already meet the Definition of
    Done is published"), not end refused at the preview. Measured on run
    01M819P2G6AK (livespec-driver-codex-hmfbv4), where this exact record ended
    the run at needs_human (bd-ib-orez2i).
    """
    repo = _carried_seed_repo(tmp_path=tmp_path)

    completion = _run_gate(repo=repo)

    assert completion.returncode == 0, completion.stderr
    assert json.loads(completion.stdout) == {"preferred_next_label": "complete"}
    assert "LIVESPEC_GREEN_PREVIEW_REFUSED" not in completion.stderr
    assert "LIVESPEC_CARRIED_SEEDED_GREEN" in completion.stderr
    handoff = (repo / ".git" / _HANDOFF).read_text(encoding="utf-8")
    assert "## green-preview-refused" not in handoff
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    complete_route = next(
        edge.destination
        for edge in graph.edges
        if edge.source == _GATE and edge.attributes.get("condition") == "preferred_label=complete"
    )
    assert complete_route == "commit_green"


def test_a_carried_seed_with_an_uncommitted_change_is_still_refused(tmp_path: Path) -> None:
    """A Green that left a tracked change uncommitted has something the preview never graded."""
    repo = _carried_seed_repo(tmp_path=tmp_path)
    _ = (repo / "carried.py").write_text("ANSWER = 43\n", encoding="utf-8")

    completion = _run_gate(repo=repo)

    assert completion.returncode == 0, completion.stderr
    assert json.loads(completion.stdout) == {"preferred_next_label": "incomplete"}
    assert "LIVESPEC_GREEN_PREVIEW_REFUSED" in completion.stderr
