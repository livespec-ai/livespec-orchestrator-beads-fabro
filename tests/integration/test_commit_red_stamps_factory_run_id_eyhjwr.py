"""commit_red records the factory run id itself, so commit_green can find its Red (bd-ib-eyhjwr).

The `Factory-Run-Id:` trailer was written only by the repository's commit-msg hook,
and that hook fails open: a sandbox where the hook's gate cannot run (an untrusted
mise config, an unsynced environment) commits the Red with no trailer. commit_green
then walks past every checkpoint, finds no Red carrying the run's id, and refuses
with "current run's own Red commit was not found beneath checkpoint commits".
The command that makes the Red commit knows the run id, so it stamps the trailer
itself and never depends on the hook.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).parents[2]
_RED = _ROOT / "dev-tooling" / "commit-red.sh"
_GREEN = _ROOT / "dev-tooling" / "commit-green.sh"
_RUN_ID = "factory-run-eyhjwr"


@pytest.fixture(autouse=True)
def _current_fabro_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name the engine run whose checkpoints the command scripts may fold."""
    monkeypatch.setenv("FABRO_RUN_ID", "run")


def _run(*, repo: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one command in the repository without raising on a non-zero exit."""
    return subprocess.run(argv, cwd=repo, check=False, capture_output=True, text=True)


def _git(*, repo: Path, argv: list[str]) -> str:
    """Run git successfully and return its stripped standard output."""
    completed = _run(repo=repo, argv=["git", *argv])
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _checkpoint(*, repo: Path, name: str) -> None:
    """Commit the current tree in the shape the engine leaves between nodes."""
    _git(
        repo=repo,
        argv=["commit", "--all", "--quiet", "-m", f"fabro(run): {name}", "-m", "Fabro-Run: run"],
    )


def test_a_red_made_with_no_provenance_hook_still_carries_the_factory_run_id(
    tmp_path: Path,
) -> None:
    """Red stamps its own run id, so Green amends it although no hook ever ran."""
    repo = tmp_path / "repository"
    repo.mkdir()
    _git(repo=repo, argv=["init", "--quiet"])
    _git(repo=repo, argv=["config", "user.name", "Test Author"])
    _git(repo=repo, argv=["config", "user.email", "author@example.invalid"])
    _ = (repo / "implementation.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "implementation.py"])
    _git(repo=repo, argv=["commit", "--quiet", "-m", "chore: baseline"])
    base = _git(repo=repo, argv=["rev-parse", "HEAD"])
    _git(repo=repo, argv=["config", "livespec.factoryRunId", _RUN_ID])
    test_file = repo / "tests" / "test_feature.py"
    test_file.parent.mkdir()
    _ = test_file.write_text("def test_feature() -> None:\n    assert True\n", encoding="utf-8")
    _ = (repo / "implementation.py").write_text("VALUE = 2\n", encoding="utf-8")
    _checkpoint(repo=repo, name="red")
    handoff_path = _git(
        repo=repo, argv=["rev-parse", "--git-path", "livespec-implement-handoff.md"]
    )
    _ = (repo / handoff_path).write_text(
        "## red\nRed test file: tests/test_feature.py\n", encoding="utf-8"
    )

    red = _run(repo=repo, argv=["bash", str(_RED)])

    assert red.returncode == 0, red.stderr
    message = _git(repo=repo, argv=["log", "-1", "--format=%B"]).splitlines()
    assert f"Factory-Run-Id: {_RUN_ID}" in message
    _checkpoint(repo=repo, name="green")

    green = _run(repo=repo, argv=["bash", str(_GREEN)])

    assert green.returncode == 0, green.stdout + green.stderr
    assert _git(repo=repo, argv=["rev-parse", "HEAD^"]) == base
