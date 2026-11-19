"""commit_green lands a seeded run's staged repairs instead of refusing them (bd-ib-hxifbi).

v0.343.2 seeded canary A (bd-ib-gmukke, run 01M7RMQ69SHQ): the carried seed is one
trailer-less reseed commit whose tests pass, so the Red turn declares
`seeded-red-passes`; the Green turn then repairs the seed's gate failures and
leaves them staged; `commit_green` ended with "Green left staged changes despite
the already-complete seed". A seed with passing tests and partial Green is not
already complete: the no-op is right only when the carried work is already on the
base. The repairs land as the run's commit and the repository hook grades them
(its suite-green leg for implementation staged with no Red-awaiting-Green HEAD),
so the Red gate is not weakened and no per-test Red is claimed.

The tests build the engine's shape in a real repository and EXECUTE the scripts.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).parents[2]
_PLUGIN_PROGRAM = (
    _ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_commit_green_program.sh"
)
_GREEN_SCRIPTS = (_PLUGIN_PROGRAM, _ROOT / "dev-tooling" / "commit-green.sh")
_TITLE = "A seeded run's carried work lands with its repairs"


@pytest.fixture(autouse=True)
def _current_fabro_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FABRO_RUN_ID", "run")
    monkeypatch.delenv("LIVESPEC_PR_TITLE", raising=False)
    monkeypatch.delenv("LIVESPEC_PR_BODY_FILE", raising=False)


def _git(*, repo: Path, argv: list[str]) -> str:
    return subprocess.run(
        ["git", *argv], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _write(*, repo: Path, path: str, text: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(text, encoding="utf-8")


def _commit(*, repo: Path, subject: str, trailers: tuple[str, ...] = ()) -> str:
    argv = ["commit", "--allow-empty", "--quiet", "-m", subject]
    if trailers:
        argv.extend(["-m", "\n".join(trailers)])
    _git(repo=repo, argv=["add", "--all"])
    _git(repo=repo, argv=argv)
    return _git(repo=repo, argv=["rev-parse", "HEAD"])


def _seeded_run(*, tmp_path: Path, carried: bool) -> tuple[Path, str]:
    """Master base; the engine's run branch snapshots the seeded tree over it."""
    repo = tmp_path / "repository"
    repo.mkdir()
    _git(repo=repo, argv=["init", "--quiet", "--initial-branch=master"])
    _git(repo=repo, argv=["config", "user.name", "Test Author"])
    _git(repo=repo, argv=["config", "user.email", "author@example.invalid"])
    _git(repo=repo, argv=["config", "livespec.factoryRunId", "current-run"])
    _write(repo=repo, path="implementation.py", text="VALUE = 1\n")
    base = _commit(repo=repo, subject="chore: baseline")
    _git(repo=repo, argv=["checkout", "--quiet", "-b", "fabro/run/run"])
    if carried:
        # The seed's tests pass; Green's repairs sit in the engine's checkpoint.
        _write(
            repo=repo,
            path="tests/test_feature.py",
            text="def test_feature() -> None:\n    assert True\n",
        )
        _write(repo=repo, path="implementation.py", text="VALUE = 2\n__all__ = ['VALUE']\n")
    _ = _commit(
        repo=repo,
        subject="fabro(run): green (success)",
        trailers=("Fabro-Run: run",),
    )
    handoff = repo / _git(
        repo=repo, argv=["rev-parse", "--git-path", "livespec-implement-handoff.md"]
    )
    _ = handoff.write_text("## seeded-red-passes\nThe Red test already passes.\n", encoding="utf-8")
    hook = repo / ".git" / "hooks" / "commit-msg"
    _ = hook.write_text(
        "#!/bin/sh\ngit interpret-trailers --in-place --trailer "
        "'TDD-Suite-Green-Scope: full-suite' \"$1\"\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    return repo, base


def _commit_green(*, repo: Path, script: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["LIVESPEC_PR_TITLE"] = _TITLE
    return subprocess.run(
        ["bash", str(script)], cwd=repo, env=env, check=False, capture_output=True, text=True
    )


@pytest.mark.parametrize("script", _GREEN_SCRIPTS, ids=lambda path: path.name)
def test_staged_repairs_of_a_seed_that_passes_its_tests_land_as_the_runs_commit(
    tmp_path: Path, script: Path
) -> None:
    repo, base = _seeded_run(tmp_path=tmp_path, carried=True)

    completed = _commit_green(repo=repo, script=script)

    assert "Green left staged changes" not in completed.stderr, completed.stderr
    assert completed.returncode == 0, completed.stderr
    assert _git(repo=repo, argv=["rev-parse", "HEAD^"]) == base
    assert _git(repo=repo, argv=["show", "--format=", "--name-only", "HEAD"]) == (
        "implementation.py\ntests/test_feature.py"
    )
    message = _git(repo=repo, argv=["log", "-1", "--format=%B"])
    assert message.splitlines()[0] == _TITLE
    assert "TDD-Suite-Green-Scope: full-suite" in message


@pytest.mark.parametrize("script", _GREEN_SCRIPTS, ids=lambda path: path.name)
def test_a_seed_whose_work_is_already_on_the_base_still_makes_no_commit(
    tmp_path: Path, script: Path
) -> None:
    repo, base = _seeded_run(tmp_path=tmp_path, carried=False)

    completed = _commit_green(repo=repo, script=script)

    assert completed.returncode == 0, completed.stderr
    assert "LIVESPEC_COMMIT_GREEN_SEEDED_RED_PASSES" in completed.stdout
    assert _git(repo=repo, argv=["rev-parse", "HEAD"]) == base
