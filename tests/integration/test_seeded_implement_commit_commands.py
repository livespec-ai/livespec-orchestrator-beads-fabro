"""Seed-entry coverage for the Red and Green command commits."""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_ROOT = Path(__file__).parents[2]
_RED = _ROOT / "dev-tooling" / "commit-red.sh"
_GREEN = _ROOT / "dev-tooling" / "commit-green.sh"
_WORKFLOW = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_RED_PROMPT = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/prompts/red.md"
_GREEN_PROMPT = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/prompts/green.md"


def _run(*, repo: Path, argv: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run one command against the scratch repository."""
    return subprocess.run(argv, cwd=repo, check=check, capture_output=True, text=True)


def _git(*, repo: Path, argv: list[str]) -> str:
    """Run Git successfully and return its stripped standard output."""
    return _run(repo=repo, argv=["git", *argv]).stdout.strip()


def _repository(*, tmp_path: Path) -> Path:
    """Create a dispatch-base repository with one product file."""
    repo = tmp_path / "repository"
    repo.mkdir()
    _run(repo=repo, argv=["git", "init", "--quiet"])
    _run(repo=repo, argv=["git", "config", "user.name", "Test Author"])
    _run(repo=repo, argv=["git", "config", "user.email", "author@example.invalid"])
    _ = (repo / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = ["src/pkg"]\n', encoding="utf-8"
    )
    product = repo / "src" / "pkg" / "feature.py"
    product.parent.mkdir(parents=True)
    _ = product.write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "--all"])
    _git(repo=repo, argv=["commit", "--quiet", "-m", "chore: dispatch base"])
    return repo


def _checkpoint(*, repo: Path, name: str, run_id: str) -> None:
    """Commit the current tree in the shape the Fabro engine leaves."""
    _git(
        repo=repo,
        argv=[
            "commit",
            "--all",
            "--allow-empty",
            "--quiet",
            "-m",
            f"fabro({run_id}): {name}",
            "-m",
            f"Fabro-Run: {run_id}",
        ],
    )


def _handoff(*, repo: Path, text: str) -> Path:
    """Write the git-local handoff read by the command stages."""
    path = repo / _git(repo=repo, argv=["rev-parse", "--git-path", "livespec-implement-handoff.md"])
    _ = path.write_text(text, encoding="utf-8")
    return path


def test_seeded_commit_red_hides_carried_product_changes_from_its_hook(
    tmp_path: Path, monkeypatch
) -> None:
    """A Red commit is tested at the dispatch base, then restores the carried tree."""
    monkeypatch.setenv("FABRO_RUN_ID", "current-run")
    repo = _repository(tmp_path=tmp_path)
    base = _git(repo=repo, argv=["rev-parse", "HEAD"])
    product = repo / "src" / "pkg" / "feature.py"
    _ = product.write_text("VALUE = 2\n", encoding="utf-8")
    _checkpoint(repo=repo, name="preserved", run_id="earlier-run")
    test_file = repo / "tests" / "test_feature.py"
    test_file.parent.mkdir()
    _ = test_file.write_text("def test_feature() -> None:\n    assert False\n", encoding="utf-8")
    _checkpoint(repo=repo, name="red", run_id="current-run")
    _handoff(repo=repo, text="## red\nRed test file: tests/test_feature.py\n")
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text(
        "#!/bin/sh\n"
        "test \"$(cat src/pkg/feature.py)\" = 'VALUE = 1'\n"
        "test \"$(cat tests/test_feature.py)\" = 'def test_feature() -> None:\n    assert False'\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)

    completed = _run(repo=repo, argv=["bash", str(_RED)], check=False)

    assert completed.returncode == 0, completed.stderr
    assert _git(repo=repo, argv=["rev-parse", "HEAD^"]) == base
    assert _git(repo=repo, argv=["show", "--format=", "--name-only", "HEAD"]) == (
        "tests/test_feature.py"
    )
    assert product.read_text(encoding="utf-8") == "VALUE = 2\n"
    assert "src/pkg/feature.py" in _git(repo=repo, argv=["status", "--porcelain"])


def test_seeded_commit_red_accepts_the_legacy_test_file_field(tmp_path: Path, monkeypatch) -> None:
    """The two permitted handoff fields select the same Red test path."""
    monkeypatch.setenv("FABRO_RUN_ID", "current-run")
    repo = _repository(tmp_path=tmp_path)
    test_file = repo / "tests" / "test_feature.py"
    test_file.parent.mkdir()
    _ = test_file.write_text("def test_feature() -> None:\n    assert False\n", encoding="utf-8")
    _checkpoint(repo=repo, name="red", run_id="current-run")
    _handoff(repo=repo, text="## red\nTest file: tests/test_feature.py\n")

    completed = _run(repo=repo, argv=["bash", str(_RED)], check=False)

    assert completed.returncode == 0, completed.stderr
    assert _git(repo=repo, argv=["show", "--format=", "--name-only", "HEAD"]) == (
        "tests/test_feature.py"
    )


def test_seeded_open_red_reaches_green_without_a_second_red_commit(
    tmp_path: Path, monkeypatch
) -> None:
    """An inherited open Red is the commit Green amends after checkpoint folding."""
    monkeypatch.setenv("FABRO_RUN_ID", "current-run")
    repo = _repository(tmp_path=tmp_path)
    base = _git(repo=repo, argv=["rev-parse", "HEAD"])
    test_file = repo / "tests" / "test_feature.py"
    test_file.parent.mkdir()
    _ = test_file.write_text("def test_feature() -> None:\n    assert False\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "tests/test_feature.py"])
    _git(
        repo=repo,
        argv=[
            "commit",
            "--quiet",
            "-m",
            "feat: red",
            "-m",
            "TDD-Red-Test-File-Checksum: red",
        ],
    )
    _ = (repo / "src" / "pkg" / "feature.py").write_text("VALUE = 2\n", encoding="utf-8")
    _checkpoint(repo=repo, name="preserved", run_id="earlier-run")
    _checkpoint(repo=repo, name="green", run_id="current-run")
    _handoff(repo=repo, text="## seeded-open-red\n")
    hook = repo / ".git" / "hooks" / "commit-msg"
    _ = hook.write_text(
        "#!/bin/sh\n"
        "git interpret-trailers --in-place --trailer 'TDD-Green-Verified-At: green' \"$1\"\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)

    completed = _run(repo=repo, argv=["bash", str(_GREEN)], check=False)

    assert completed.returncode == 0, completed.stderr
    assert _git(repo=repo, argv=["rev-parse", "HEAD^"]) == base
    assert _git(repo=repo, argv=["show", "--format=", "--name-only", "HEAD"]) == (
        "src/pkg/feature.py\ntests/test_feature.py"
    )
    message = _git(repo=repo, argv=["log", "-1", "--format=%B"])
    assert "TDD-Red-Test-File-Checksum: red" in message
    assert "TDD-Green-Verified-At: green" in message


def test_seeded_implementation_reaches_green_through_a_dispatch_base_red(
    tmp_path: Path, monkeypatch
) -> None:
    """A seed that already holds the implementation publishes through Red then Green."""
    monkeypatch.setenv("FABRO_RUN_ID", "current-run")
    repo = _repository(tmp_path=tmp_path)
    base = _git(repo=repo, argv=["rev-parse", "HEAD"])
    product = repo / "src" / "pkg" / "feature.py"
    _ = product.write_text("VALUE = 2\n", encoding="utf-8")
    _checkpoint(repo=repo, name="preserved", run_id="earlier-run")
    test_file = repo / "tests" / "test_feature.py"
    test_file.parent.mkdir()
    _ = test_file.write_text("def test_feature() -> None:\n    assert False\n", encoding="utf-8")
    _checkpoint(repo=repo, name="red", run_id="current-run")
    _handoff(repo=repo, text="## red\nRed test file: tests/test_feature.py\n")
    hooks = repo / ".git" / "hooks"
    _ = (hooks / "pre-commit").write_text(
        "#!/bin/sh\ntest \"$(cat src/pkg/feature.py)\" = 'VALUE = 1'\n", encoding="utf-8"
    )
    (hooks / "pre-commit").chmod(0o755)

    red = _run(repo=repo, argv=["bash", str(_RED)], check=False)

    assert red.returncode == 0, red.stderr
    assert _git(repo=repo, argv=["rev-parse", "HEAD^"]) == base
    (hooks / "pre-commit").unlink()
    _git(
        repo=repo,
        argv=[
            "commit",
            "--amend",
            "--quiet",
            "-m",
            "feat: red",
            "-m",
            "Factory-Run-Id: current-run",
            "-m",
            "TDD-Red-Test-File-Checksum: red",
        ],
    )
    _git(repo=repo, argv=["config", "--local", "livespec.factoryRunId", "current-run"])
    _checkpoint(repo=repo, name="green", run_id="current-run")
    _ = (hooks / "commit-msg").write_text(
        "#!/bin/sh\n"
        "git interpret-trailers --in-place --trailer 'TDD-Green-Verified-At: green' \"$1\"\n",
        encoding="utf-8",
    )
    (hooks / "commit-msg").chmod(0o755)

    green = _run(repo=repo, argv=["bash", str(_GREEN)], check=False)

    assert green.returncode == 0, green.stderr
    assert _git(repo=repo, argv=["rev-parse", "HEAD^"]) == base
    assert _git(repo=repo, argv=["show", "--format=", "--name-only", "HEAD"]) == (
        "src/pkg/feature.py\ntests/test_feature.py"
    )
    assert "TDD-Green-Verified-At: green" in _git(repo=repo, argv=["log", "-1", "--format=%B"])


def test_seeded_routes_and_prompts_direct_the_open_red_path() -> None:
    """The graph and handoff prose send inherited Red evidence through Green."""
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    edges = {
        (edge.source, edge.destination, edge.attributes.get("condition")) for edge in graph.edges
    }
    assert ("red", "green_admission", "preferred_label=seeded-open-red") in edges
    red = _RED_PROMPT.read_text(encoding="utf-8")
    green = _GREEN_PROMPT.read_text(encoding="utf-8")
    assert "Red test file: <path>" in red
    assert "seeded-open-red" in red
    assert "seeded-open-red" in green
    assert "never declare `already-satisfied` for such a seed" in " ".join(red.lower().split())
    assert "dispatch base" in red
