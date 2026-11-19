"""commit_green resolves a seeded Red the engine's checkpoint chain never carried (bd-ib-5ypy5v).

A seeded dispatch checks the seed out detached, but the engine's run branch was
created from the MASTER tip and its checkpoint commits snapshot the seeded tree
with master as their parent (livespec-dev-tooling-pojsfk run 01M7R8HYHKD6: events
`run.branch` base_sha = master tip; first checkpoint's parent = master). The
seed's own Red commit therefore is not in the run's history, and it carries the
EARLIER run's `Factory-Run-Id`, so `commit_green` ended with "current run's own
Red commit was not found beneath checkpoint commits".

These tests build that exact shape in a real repository and EXECUTE the command
script. The seeded Red is resolved from `LIVESPEC_RESUME_PUBLISHED_HEAD` through
the seed commit's own TDD-Red trailers; no trailer is trusted that cannot match.
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
# The production program and the repository-relative copy the orchestrator repos run.
_GREEN_SCRIPTS = (_PLUGIN_PROGRAM, _ROOT / "dev-tooling" / "commit-green.sh")
_RED_SUBJECT = "feat: red"


@pytest.fixture(autouse=True)
def _current_fabro_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FABRO_RUN_ID", "run")
    # These direct command fixtures deliberately do not model a dispatched
    # work item.  A factory-provided PR title would otherwise make the command
    # replace the fixture's Red subject during its Green amend.
    monkeypatch.delenv("LIVESPEC_PR_TITLE", raising=False)


def _git(*, repo: Path, argv: list[str]) -> str:
    return subprocess.run(
        ["git", *argv], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _write(*, repo: Path, path: str, text: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(text, encoding="utf-8")


def _commit(*, repo: Path, subject: str, trailers: tuple[str, ...] = ()) -> str:
    argv = ["commit", "--all", "--allow-empty", "--quiet", "-m", subject]
    if trailers:
        argv.extend(["-m", "\n".join(trailers)])
    _git(repo=repo, argv=["add", "--all"])
    _git(repo=repo, argv=argv)
    return _git(repo=repo, argv=["rev-parse", "HEAD"])


def _checkpoint(*, repo: Path, run: str, name: str) -> str:
    return _commit(repo=repo, subject=f"fabro({run}): {name}", trailers=(f"Fabro-Run: {run}",))


def _seeded_run(*, tmp_path: Path, seed_red_trailers: tuple[str, ...]) -> tuple[Path, str, str]:
    """A master base, a seed with its own Red, and the engine's checkpoints over master."""
    repo = tmp_path / "repository"
    repo.mkdir()
    _git(repo=repo, argv=["init", "--quiet", "--initial-branch=master"])
    _git(repo=repo, argv=["config", "user.name", "Test Author"])
    _git(repo=repo, argv=["config", "user.email", "author@example.invalid"])
    _git(repo=repo, argv=["config", "livespec.factoryRunId", "current-run"])
    _write(repo=repo, path="implementation.py", text="VALUE = 1\n")
    _ = _commit(repo=repo, subject="chore: seed base")
    _git(repo=repo, argv=["checkout", "--quiet", "-b", "seed"])
    _write(
        repo=repo,
        path="tests/test_feature.py",
        text="def test_feature() -> None:\n    assert True\n",
    )
    _ = _commit(repo=repo, subject=_RED_SUBJECT, trailers=seed_red_trailers)
    _write(repo=repo, path="implementation.py", text="VALUE = 2\n")
    seed_tip = _checkpoint(repo=repo, run="earlier", name="green")
    _git(repo=repo, argv=["checkout", "--quiet", "master"])
    _write(repo=repo, path="unrelated.txt", text="master moved on\n")
    base = _commit(repo=repo, subject="chore: master moved on")
    # The engine's run branch hangs off the master base and snapshots the seeded tree.
    _git(repo=repo, argv=["checkout", "--quiet", "-b", "fabro/run/run"])
    _git(repo=repo, argv=["checkout", seed_tip, "--", "implementation.py", "tests"])
    _ = _checkpoint(repo=repo, run="run", name="green")
    _ = _checkpoint(repo=repo, run="run", name="commit_green (failure)")
    handoff = repo / _git(
        repo=repo, argv=["rev-parse", "--git-path", "livespec-implement-handoff.md"]
    )
    _ = handoff.write_text("## seeded-open-red\nThe seed carries one open Red.\n", encoding="utf-8")
    hook = repo / ".git" / "hooks" / "commit-msg"
    _ = hook.write_text(
        "#!/bin/sh\ngit interpret-trailers --in-place --trailer "
        "'TDD-Green-Verified-At: green' \"$1\"\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    return repo, base, seed_tip


def _commit_green(
    *, repo: Path, script: Path, resume_head: str | None
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if resume_head is not None:
        env["LIVESPEC_RESUME_PUBLISHED_HEAD"] = resume_head
    return subprocess.run(
        ["bash", str(script)], cwd=repo, env=env, check=False, capture_output=True, text=True
    )


_OPEN_RED = (
    "Factory-Run-Id: earlier-run",
    "TDD-Red-Test-File-Checksum: red",
)


@pytest.mark.parametrize("script", _GREEN_SCRIPTS, ids=lambda path: path.name)
def test_a_seeded_red_the_checkpoint_chain_never_carried_is_rebuilt_from_the_seed(
    tmp_path: Path, script: Path
) -> None:
    repo, base, seed_tip = _seeded_run(tmp_path=tmp_path, seed_red_trailers=_OPEN_RED)

    completed = _commit_green(repo=repo, script=script, resume_head=seed_tip)

    assert "Red commit was not found" not in completed.stderr, completed.stderr
    assert completed.returncode == 0, completed.stderr
    assert _git(repo=repo, argv=["rev-parse", "HEAD^"]) == base
    assert _git(repo=repo, argv=["show", "--format=", "--name-only", "HEAD"]) == (
        "implementation.py\ntests/test_feature.py"
    )
    message = _git(repo=repo, argv=["log", "-1", "--format=%B"])
    assert "TDD-Red-Test-File-Checksum: red" in message
    assert "TDD-Green-Verified-At: green" in message
    assert message.splitlines()[0] == _RED_SUBJECT


@pytest.mark.parametrize("script", _GREEN_SCRIPTS, ids=lambda path: path.name)
def test_a_fresh_unseeded_run_still_finds_its_own_red(tmp_path: Path, script: Path) -> None:
    repo = tmp_path / "repository"
    repo.mkdir()
    _git(repo=repo, argv=["init", "--quiet", "--initial-branch=master"])
    _git(repo=repo, argv=["config", "user.name", "Test Author"])
    _git(repo=repo, argv=["config", "user.email", "author@example.invalid"])
    _git(repo=repo, argv=["config", "livespec.factoryRunId", "current-run"])
    _write(repo=repo, path="implementation.py", text="VALUE = 1\n")
    base = _commit(repo=repo, subject="chore: baseline")
    _write(
        repo=repo,
        path="tests/test_feature.py",
        text="def test_feature() -> None:\n    assert True\n",
    )
    _ = _commit(
        repo=repo,
        subject=_RED_SUBJECT,
        trailers=("Factory-Run-Id: current-run", "TDD-Red-Test-File-Checksum: red"),
    )
    _write(repo=repo, path="implementation.py", text="VALUE = 2\n")
    _ = _checkpoint(repo=repo, run="run", name="green")
    handoff = repo / _git(
        repo=repo, argv=["rev-parse", "--git-path", "livespec-implement-handoff.md"]
    )
    _ = handoff.write_text("## green\nImplementation changed.\n", encoding="utf-8")
    hook = repo / ".git" / "hooks" / "commit-msg"
    _ = hook.write_text(
        "#!/bin/sh\ngit interpret-trailers --in-place --trailer "
        "'TDD-Green-Verified-At: green' \"$1\"\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)

    completed = _commit_green(repo=repo, script=script, resume_head=None)

    assert completed.returncode == 0, completed.stderr
    assert _git(repo=repo, argv=["rev-parse", "HEAD^"]) == base
