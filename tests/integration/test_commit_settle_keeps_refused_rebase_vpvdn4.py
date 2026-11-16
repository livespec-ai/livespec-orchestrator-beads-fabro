"""Scenario 377 (bd-ib-vpvdn4): a settle after a subjectless refusal keeps the rebase resumable."""

from __future__ import annotations

import json
import os
import subprocess
import sys
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
    """Return a clone stopped on a conflicting first pick, resolved and staged."""
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


def _commit_through_runner(repo: Path, plugins: Path, *argv: str) -> dict[str, object]:
    run_id = _runner(repo, plugins, "start", "--", "git", "commit", *argv)
    return json.loads(_runner(repo, plugins, "wait", run_id, "--timeout-seconds", "60"))


def _settle(repo: Path, plugins: Path) -> subprocess.CompletedProcess[str]:
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    return subprocess.run(
        ["sh", "-c", parsed.nodes["fix_commit_settle"]["script"]],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env={**_environment(), "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins)},
    )


def test_a_settle_after_a_subjectless_refusal_leaves_the_rebase_resumable(tmp_path: Path) -> None:
    repo = _stopped_rebase_repo(tmp_path)
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    _ = (plugins / COMMIT_RUNNER_PROGRAM_FILENAME).write_text(
        commit_runner_program_source(), encoding="utf-8"
    )
    start_head = _git(repo, "rev-parse", "HEAD")

    report = _commit_through_runner(repo, plugins, "--allow-empty-message", "-m", "")
    assert report["state"] == "failed"
    settled = _settle(repo, plugins)

    assert settled.returncode != 0, settled.stderr
    assert (repo / ".git" / "rebase-merge").is_dir()
    assert _git(repo, "rev-parse", "HEAD") == start_head
    assert _git(repo, "diff", "--cached", "--name-only") == "a.txt"
    assert (repo / "a.txt").read_text(encoding="utf-8") == "resolved\n"

    resumed = _commit_through_runner(repo, plugins, "-C", "REBASE_HEAD")
    assert resumed["state"] == "passed"
    assert _settle(repo, plugins).returncode == 0
    assert _git(repo, "log", "-1", "--format=%s") == "fix: picked subject"
    assert not (repo / ".git" / "rebase-merge").exists()
