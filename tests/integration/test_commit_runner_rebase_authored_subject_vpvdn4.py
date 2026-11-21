"""Scenario 377 (bd-ib-vpvdn4): a stopped rebase resumes with an authored subject."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = (
    _ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.fabro"
)
_TRAILER_HOOK = (
    "#!/bin/sh\n"
    'git interpret-trailers --in-place --trailer "Factory-Run-Id: 0123456789abcdef" "$1"\n'
)


def _environment() -> dict[str, str]:
    """Run each fixture outside the outer test's Git and coverage environment."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "COV_CORE", "COVERAGE"))
    }
    return {**environment, "GIT_EDITOR": "true", "GIT_CONFIG_GLOBAL": "/dev/null"}


def _git(repo: Path, *argv: str) -> str:
    result = subprocess.run(
        ["git", *argv], cwd=repo, check=True, capture_output=True, text=True, env=_environment()
    )
    return result.stdout.strip()


def _write(repo: Path, name: str, text: str) -> None:
    _ = (repo / name).write_text(text, encoding="utf-8")


def _commit(repo: Path, message: str) -> None:
    _ = _git(repo, "add", "-A")
    _ = _git(repo, "commit", "--quiet", "-m", message)


def _stopped_rebase_repo(tmp_path: Path) -> Path:
    """Return a stopped first pick with a second pick for settle to replay."""
    repo = tmp_path / "clone"
    repo.mkdir()
    _ = _git(repo, "init", "--quiet", "-b", "base")
    _ = _git(repo, "config", "user.name", "Fixture")
    _ = _git(repo, "config", "user.email", "fixture@example.invalid")
    _write(repo, "a.txt", "base\n")
    _commit(repo, "base")
    _ = _git(repo, "checkout", "--quiet", "-b", "side")
    _write(repo, "a.txt", "side\n")
    _commit(repo, "side")
    _ = _git(repo, "checkout", "--quiet", "-b", "work", "base")
    _write(repo, "a.txt", "work\n")
    _commit(repo, "fix: picked subject")
    _write(repo, "b.txt", "next pick\n")
    _commit(repo, "fix: next pick")
    rebase = subprocess.run(
        ["git", "rebase", "side"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=_environment(),
    )
    assert rebase.returncode != 0, rebase.stdout
    _write(repo, "a.txt", "resolved\n")
    _ = _git(repo, "add", "a.txt")
    hook = repo / ".git" / "hooks" / "commit-msg"
    _ = hook.write_text(_TRAILER_HOOK, encoding="utf-8")
    hook.chmod(0o755)
    return repo


def _runner(repo: Path, plugins: Path, *argv: str) -> str:
    result = subprocess.run(
        [sys.executable, str(plugins / COMMIT_RUNNER_PROGRAM_FILENAME), *argv],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=_environment(),
    )
    return result.stdout.strip()


def _delayed_commit_runner(tmp_path: Path, repo: Path) -> tuple[str, Path, Path, dict[str, str]]:
    """Install a runner whose final expected-HEAD update waits for the checkpoint."""
    real_git = shutil.which("git")
    assert real_git is not None
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/bin/sh\n" "printf '%s\\n' 'lefthook hook: pre-commit' 'All 1 targets passed.'\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").write_text(
        "#!/bin/sh\n"
        'if test "${LIVESPEC_TEST_DELAYED_COMMIT:-}" = 1 && test "${1:-}" = commit; then\n'
        '  git_dir="$($LIVESPEC_TEST_REAL_GIT rev-parse --git-dir)"\n'
        '  "$git_dir/hooks/pre-commit" || exit $?\n'
        '  start="$($LIVESPEC_TEST_REAL_GIT rev-parse HEAD)"\n'
        '  tree="$($LIVESPEC_TEST_REAL_GIT write-tree)"\n'
        '  commit="$($LIVESPEC_TEST_REAL_GIT commit-tree "$tree" -p "$start" -m \'runner change\')"\n'
        '  touch "$git_dir/runner-commit-created"\n'
        '  while test ! -f "$git_dir/release-runner-commit"; do sleep 0.01; done\n'
        '  exec "$LIVESPEC_TEST_REAL_GIT" update-ref HEAD "$commit" "$start"\n'
        "fi\n"
        'exec "$LIVESPEC_TEST_REAL_GIT" "$@"\n',
        encoding="utf-8",
    )
    (bin_dir / "git").chmod(0o755)
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    runner = plugins / COMMIT_RUNNER_PROGRAM_FILENAME
    runner.write_text(commit_runner_program_source(), encoding="utf-8")
    return (
        real_git,
        plugins,
        runner,
        {
            **_environment(),
            "LIVESPEC_TEST_DELAYED_COMMIT": "1",
            "LIVESPEC_TEST_REAL_GIT": real_git,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
        },
    )


def _checkpoint(repo: Path, real_git: str, subject: str = "fabro(run): fix (success)") -> None:
    """Move HEAD using the engine's checkpoint-shaped, hooks-disabled commit."""
    _ = subprocess.run(
        [real_git, "-c", "core.hooksPath=/dev/null", "add", "-A"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=_environment(),
    )
    checkpoint = subprocess.run(
        [
            real_git,
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            subject,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=_environment(),
    )
    assert checkpoint.returncode == 0


def test_a_rebase_resolution_reuses_the_picked_authored_subject_and_settles(tmp_path: Path) -> None:
    repo = _stopped_rebase_repo(tmp_path)
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    _ = (plugins / COMMIT_RUNNER_PROGRAM_FILENAME).write_text(
        commit_runner_program_source(), encoding="utf-8"
    )

    run_id = _runner(repo, plugins, "start", "--", "git", "commit", "-C", "REBASE_HEAD")
    report = json.loads(_runner(repo, plugins, "wait", run_id, "--timeout-seconds", "60"))

    assert report["state"] == "passed"
    assert _git(repo, "log", "-1", "--format=%s") == "fix: picked subject"
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    settled = subprocess.run(
        ["sh", "-c", parsed.nodes["fix_commit_settle"]["script"]],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env={**_environment(), "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins)},
    )

    assert settled.returncode == 0, settled.stderr
    assert _git(repo, "log", "-1", "--format=%s") == "fix: next pick"
    assert not (repo / ".git" / "rebase-merge").exists()


def test_a_runner_commit_refused_after_a_checkpoint_advance_is_overtaken_by_checkpoint(
    tmp_path: Path,
) -> None:
    """A passed hook plus Git's expected-HEAD refusal is not a hook refusal."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = _git(repo, "init", "--quiet")
    _ = _git(repo, "config", "user.name", "Fixture")
    _ = _git(repo, "config", "user.email", "fixture@example.invalid")
    _write(repo, "base.txt", "base\n")
    _commit(repo, "base")

    real_git, plugins, runner, environment = _delayed_commit_runner(tmp_path, repo)
    _write(repo, "runner.txt", "runner change\n")
    _ = _git(repo, "add", "runner.txt")
    started = subprocess.run(
        [sys.executable, str(runner), "start", "--", "git", "commit", "-m", "runner change"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    run_id = started.stdout.strip()
    created = repo / ".git" / "runner-commit-created"
    deadline = time.monotonic() + 10
    while not created.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert created.is_file()

    _checkpoint(repo, real_git)
    (repo / ".git" / "release-runner-commit").touch()
    report = json.loads(_runner(repo, plugins, "wait", run_id, "--timeout-seconds", "10"))

    assert report["state"] == "overtaken-by-checkpoint"
    assert str(report["git_refusal_line"]).startswith("fatal: cannot lock ref 'HEAD':")


def test_a_runner_commit_refused_after_a_non_checkpoint_advance_is_a_failure_not_overtaken(
    tmp_path: Path,
) -> None:
    """Only engine checkpoints count as overtaking: another HEAD move is a real refusal."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = _git(repo, "init", "--quiet")
    _ = _git(repo, "config", "user.name", "Fixture")
    _ = _git(repo, "config", "user.email", "fixture@example.invalid")
    _write(repo, "base.txt", "base\n")
    _commit(repo, "base")

    real_git, plugins, runner, environment = _delayed_commit_runner(tmp_path, repo)
    _write(repo, "runner.txt", "runner change\n")
    _ = _git(repo, "add", "runner.txt")
    started = subprocess.run(
        [sys.executable, str(runner), "start", "--", "git", "commit", "-m", "runner change"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    run_id = started.stdout.strip()
    created = repo / ".git" / "runner-commit-created"
    deadline = time.monotonic() + 10
    while not created.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert created.is_file()

    _checkpoint(repo, real_git, "fabro(run): fix (success)")
    _checkpoint(repo, real_git, "feat: a concurrent authored commit")
    (repo / ".git" / "release-runner-commit").touch()
    report = json.loads(_runner(repo, plugins, "wait", run_id, "--timeout-seconds", "10"))

    assert report["state"] == "failed"
    assert str(report["git_refusal_line"]).startswith("fatal: cannot lock ref 'HEAD':")
    assert _git(repo, "log", "-1", "--format=%s") == "feat: a concurrent authored commit"


def test_fix_commit_settle_retries_a_checkpoint_overtaken_runner_commit(tmp_path: Path) -> None:
    """An overtaken run retains the command its settle node needs to retry it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = _git(repo, "init", "--quiet")
    _ = _git(repo, "config", "user.name", "Fixture")
    _ = _git(repo, "config", "user.email", "fixture@example.invalid")
    _write(repo, "base.txt", "base\n")
    _commit(repo, "base")

    real_git, plugins, runner, environment = _delayed_commit_runner(tmp_path, repo)
    _write(repo, "runner.txt", "runner change\n")
    _ = _git(repo, "add", "runner.txt")
    started = subprocess.run(
        [sys.executable, str(runner), "start", "--", "git", "commit", "-m", "runner change"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    run_id = started.stdout.strip()
    created = repo / ".git" / "runner-commit-created"
    deadline = time.monotonic() + 10
    while not created.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert created.is_file()

    _checkpoint(repo, real_git)
    (repo / ".git" / "release-runner-commit").touch()
    report = json.loads(_runner(repo, plugins, "wait", run_id, "--timeout-seconds", "10"))
    assert report["state"] == "overtaken-by-checkpoint"

    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    settled = subprocess.run(
        ["sh", "-c", parsed.nodes["fix_commit_settle"]["script"]],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env={**_environment(), "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins)},
    )

    assert settled.returncode == 0, settled.stderr
    assert _git(repo, "log", "-1", "--format=%s") == "runner change"
    original = json.loads((repo / ".git" / "livespec-commit-runs" / f"{run_id}.json").read_text())
    assert isinstance(original["retried_by"], str)
