"""Scenario 285 — a Green turn that changed the Red test file has it restored mechanically.

`SPECIFICATION/scenarios.md` Scenario 285, "Green finds the Red test wrong": the
Red test file is unchanged by the green turn. The green prompt already says
"Never change the Red test file" and a run still rewrote it (bd-ib-a4gjc5), so
the end of the green node enforces it: `implement_completion`, the command node
that closes the green turn before `commit_green`, restores the Red test from the
Red commit, says so in the handoff file and in a marker the Dispatcher turns
into a `red-test-restored` journal row, and lets the run continue. Each claim is
observed by running the committed node script in a real git repository.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_ROOT = Path(__file__).parents[2]
_GRAPH = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_GATE = "implement_completion"
_COMPLETION = '{"definition_of_done_complete": true}'
_HANDOFF = "livespec-implement-handoff.md"
_TEST_PATH = "tests/test_the_red_behaviour.py"
_RED_TEST = "def test_the_behaviour() -> None:\n    assert behaviour() == 'wanted'\n"
_REWRITTEN_TEST = "def test_something_easier() -> None:\n    assert True\n"
_MARKER = "LIVESPEC_RED_TEST_RESTORED:"


def _gate_script() -> str:
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return graph.nodes[_GATE]["script"].replace("{{ inputs.default_branch }}", "master")


def _git(*, repo: Path, argv: list[str]) -> str:
    completed = subprocess.run(["git", *argv], cwd=repo, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def _repo_after_the_red_commit(*, tmp_path: Path) -> tuple[Path, str]:
    """A clone at the Red commit, one commit above the dispatch base."""
    repo = tmp_path / "clone"
    repo.mkdir()
    _git(repo=repo, argv=["init", "--quiet", "--initial-branch=master"])
    _git(repo=repo, argv=["config", "user.name", "Fixture"])
    _git(repo=repo, argv=["config", "user.email", "fixture@example.invalid"])
    _ = (repo / "product.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "product.py"])
    _git(repo=repo, argv=["commit", "--quiet", "-m", "dispatch base"])
    _git(repo=repo, argv=["update-ref", "refs/remotes/origin/master", "HEAD"])
    (repo / "tests").mkdir()
    _ = (repo / _TEST_PATH).write_text(_RED_TEST, encoding="utf-8")
    _git(repo=repo, argv=["add", _TEST_PATH])
    message = (
        "feat: red\n\n"
        "Factory-Run-Id: fixture\n"
        f"TDD-Red-Test: {_TEST_PATH}\n"
        "TDD-Red-Test-File-Checksum: sha256:fixture\n"
    )
    _git(repo=repo, argv=["commit", "--quiet", "-m", message])
    return repo, _git(repo=repo, argv=["rev-parse", "HEAD"])


def _run_the_gate(*, repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", _gate_script()],
        cwd=repo,
        check=False,
        capture_output=True,
        input=_COMPLETION,
        text=True,
    )


def _handoff(*, repo: Path) -> Path:
    return repo / _git(repo=repo, argv=["rev-parse", "--git-path", _HANDOFF])


def test_a_green_turn_that_edited_the_red_test_has_it_restored_and_continues(
    tmp_path: Path,
) -> None:
    """The edit is undone byte for byte, the run goes on, and the handoff and stderr say so."""
    repo, red_commit = _repo_after_the_red_commit(tmp_path=tmp_path)
    _ = (repo / _TEST_PATH).write_text(_REWRITTEN_TEST, encoding="utf-8")
    _ = (repo / "product.py").write_text("VALUE = 2\n", encoding="utf-8")
    red_blob = _git(repo=repo, argv=["rev-parse", f"{red_commit}:{_TEST_PATH}"])
    handoff = _handoff(repo=repo)
    _ = handoff.write_text("## green\nmade the test easier\n", encoding="utf-8")

    completed = _run_the_gate(repo=repo)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"preferred_next_label": "complete"}
    assert (repo / _TEST_PATH).read_text(encoding="utf-8") == _RED_TEST
    assert (repo / "product.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert (
        f"{_MARKER} path={_TEST_PATH} red_commit={red_commit} restored_blob={red_blob}"
        in completed.stderr
    )
    section = handoff.read_text(encoding="utf-8")
    assert "## red-test-restored" in section
    assert _TEST_PATH in section
    assert red_commit in section


def test_a_green_turn_that_deleted_the_red_test_has_it_restored(tmp_path: Path) -> None:
    """A deleted Red test file is a changed Red test file, and comes back the same way."""
    repo, red_commit = _repo_after_the_red_commit(tmp_path=tmp_path)
    (repo / _TEST_PATH).unlink()

    completed = _run_the_gate(repo=repo)

    assert completed.returncode == 0, completed.stderr
    assert (repo / _TEST_PATH).read_text(encoding="utf-8") == _RED_TEST
    assert f"red_commit={red_commit}" in completed.stderr


def test_an_edit_an_engine_checkpoint_already_committed_is_restored(tmp_path: Path) -> None:
    """The comparison reads the tree, so a checkpoint commit above the Red commit changes nothing."""
    repo, red_commit = _repo_after_the_red_commit(tmp_path=tmp_path)
    _ = (repo / _TEST_PATH).write_text(_REWRITTEN_TEST, encoding="utf-8")
    _git(repo=repo, argv=["commit", "--quiet", "-am", "checkpoint"])

    completed = _run_the_gate(repo=repo)

    assert completed.returncode == 0, completed.stderr
    assert (repo / _TEST_PATH).read_text(encoding="utf-8") == _RED_TEST
    assert f"red_commit={red_commit}" in completed.stderr


def test_a_green_turn_that_left_the_red_test_alone_is_not_refused(tmp_path: Path) -> None:
    """A byte-identical Red test file writes no marker and no handoff section."""
    repo, _red_commit = _repo_after_the_red_commit(tmp_path=tmp_path)
    _ = (repo / "product.py").write_text("VALUE = 2\n", encoding="utf-8")
    handoff = _handoff(repo=repo)
    _ = handoff.write_text("## green\nimplementation only\n", encoding="utf-8")

    completed = _run_the_gate(repo=repo)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"preferred_next_label": "complete"}
    assert _MARKER not in completed.stderr
    assert "## red-test-restored" not in handoff.read_text(encoding="utf-8")
    assert (repo / _TEST_PATH).read_text(encoding="utf-8") == _RED_TEST
