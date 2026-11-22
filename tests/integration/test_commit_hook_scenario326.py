"""Integration coverage for Scenario 326's commit-hook and publication boundary."""

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
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_push import PUSH_ORIGIN_SOURCE

_ROOT = Path(__file__).resolve().parents[2]
_COVERAGE = _ROOT / "tests" / "heading-coverage.json"
_HEADING = (
    "## Scenario 326 — A resumed or seeded tree older than a harness guard passes its own "
    "commit hook, and an agent stage's own publication stays refused"
)
_NODE_ID = "tests.integration.test_commit_hook_scenario326.test_scenario326_commit_hooks_and_publication_boundary"


def test_scenario326_commit_hooks_and_publication_boundary(tmp_path: Path) -> None:
    """A real commit runner clears only the hook suite's guard, never the stage boundary."""
    runner = _install_runner(tmp_path=tmp_path)
    seeded = _fixture_repository(root=tmp_path / "seeded")
    unchanged = _fixture_repository(root=tmp_path / "unchanged")

    _run_hooked_commit(repo=seeded, runner=runner, allow_empty=False)
    _run_hooked_commit(repo=unchanged, runner=runner, allow_empty=True)

    # A test may set the stage itself, but a projected publication remains refused.
    self_set = _refused_push(tmp_path=tmp_path / "self-set", set_stage=True)
    assert self_set.returncode != 0
    assert (
        "LIVESPEC_AGENT_PUBLICATION_DENIED: stage=implement action=push_origin" in self_set.stderr
    )

    # The implement turn itself is equally refused without an inline environment assignment.
    own_attempt = _refused_push(tmp_path=tmp_path / "own-attempt", set_stage=False)
    assert own_attempt.returncode != 0
    assert (
        "LIVESPEC_AGENT_PUBLICATION_DENIED: stage=implement action=push_origin"
        in own_attempt.stderr
    )

    coverage = json.loads(_COVERAGE.read_text(encoding="utf-8"))
    [entry] = [entry for entry in coverage if entry["heading"] == _HEADING]
    assert entry["test"] == _NODE_ID


def _install_runner(*, tmp_path: Path) -> Path:
    runner = tmp_path / COMMIT_RUNNER_PROGRAM_FILENAME
    runner.write_text(commit_runner_program_source(), encoding="utf-8")
    return runner


def _fixture_repository(*, root: Path) -> Path:
    root.mkdir()
    _git(root, "init", "--quiet")
    _git(root, "config", "user.name", "Scenario Fixture")
    _git(root, "config", "user.email", "scenario@example.invalid")
    (root / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "--quiet", "-m", "chore: baseline")

    projected = root / ".projected" / "bin"
    projected.mkdir(parents=True)
    push_origin = projected / "push_origin"
    push_origin.write_text(PUSH_ORIGIN_SOURCE, encoding="utf-8")
    push_origin.chmod(0o755)
    fake_git = projected / "git"
    fake_git.write_text(
        "#!/bin/sh\n"
        'if test "$1 $2 $3" = "remote get-url --push"; then\n'
        "  printf '%s\\n' 'git@example.invalid:fixture.git'\n"
        "  exit 0\n"
        "fi\n"
        'printf "%s\\n" "$*" >> "$PWD/helper-ran"\n',
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    suite = root / "suite.sh"
    suite.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        'test -z "${LIVESPEC_AGENT_STAGE:-}"\n'
        'PATH="$PWD/.projected/bin:$PATH"\n'
        "export PATH\n"
        'exec "$PWD/.projected/bin/push_origin" git push origin HEAD:refs/heads/suite\n',
        encoding="utf-8",
    )
    suite.chmod(0o755)
    hook = root / ".git" / "hooks" / "pre-commit"
    hook.write_text('#!/bin/sh\nexec "$PWD/suite.sh"\n', encoding="utf-8")
    hook.chmod(0o755)
    return root


def _run_hooked_commit(*, repo: Path, runner: Path, allow_empty: bool) -> None:
    if not allow_empty:
        (repo / "tracked.txt").write_text("seeded tree\n", encoding="utf-8")
        _git(repo, "add", "tracked.txt")
    expected_tree = _git(repo, "write-tree")
    command = ["git", "commit", "--quiet", "-m", "test: hook suite"]
    if allow_empty:
        command.append("--allow-empty")
    environment = {**_clean_environment(), "LIVESPEC_AGENT_STAGE": "implement"}
    started = _runner(
        repo=repo, runner=runner, environment=environment, argv=["start", "--", *command]
    )
    assert started.returncode == 0, started.stderr
    report = _runner(
        repo=repo,
        runner=runner,
        environment=_clean_environment(),
        argv=["wait", started.stdout.strip(), "--timeout-seconds", "30"],
    )
    assert report.returncode == 0, report.stderr
    outcome = json.loads(report.stdout)
    assert outcome["state"] == "passed", outcome
    assert "LIVESPEC_AGENT_PUBLICATION_DENIED" not in outcome["output_tail"]
    assert _git(repo, "rev-parse", "HEAD^{tree}") == expected_tree
    assert (repo / "helper-ran").read_text(
        encoding="utf-8"
    ) == "push origin HEAD:refs/heads/suite\n"


def _refused_push(*, tmp_path: Path, set_stage: bool) -> subprocess.CompletedProcess[str]:
    bundle = tmp_path / "bundle"
    bin_dir = bundle / "bin"
    bin_dir.mkdir(parents=True)
    helper = bin_dir / "push_origin"
    helper.write_text(PUSH_ORIGIN_SOURCE, encoding="utf-8")
    helper.chmod(0o755)
    (bundle / "agent-stage").write_text(f"{os.getpid()} implement\n", encoding="utf-8")
    environment = _clean_environment()
    if set_stage:
        environment["LIVESPEC_AGENT_STAGE"] = "review_fix"
    return subprocess.run(
        [str(helper), "git", "push", "origin", "HEAD:refs/heads/forbidden"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _runner(
    *, repo: Path, runner: Path, environment: dict[str, str], argv: list[str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(runner), *argv],
        cwd=repo,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _git(repo: Path, *argv: str) -> str:
    result = subprocess.run(
        ["git", *argv],
        cwd=repo,
        env=_clean_environment(),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _clean_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "COVERAGE", "COV_CORE", "LIVESPEC_AGENT_STAGE"))
    }
    return {**environment, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_EDITOR": "true"}
