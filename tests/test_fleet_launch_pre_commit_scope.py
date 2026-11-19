"""Coverage for the fleet-launch gate's pre-commit input scope."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HOOK = _REPO_ROOT / "dev-tooling" / "just-check-pre-commit.sh"
_FLEET_LAUNCH_INPUTS = (
    "fleet-launch/test/run-tests.sh",
    "check-targets.txt",
    "justfile",
    "dev-tooling/aggregate-targets.sh",
    "dev-tooling/just-check.sh",
    "dev-tooling/just-check-fleet-launch.sh",
)


def _run(*, argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, env=env, check=False, capture_output=True, text=True)


def _repository(*, tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    env = dict(os.environ)
    for command in (
        ["git", "init"],
        ["git", "config", "user.email", "test@example.com"],
        ["git", "config", "user.name", "Test User"],
    ):
        result = _run(argv=command, cwd=repo, env=env)
        assert result.returncode == 0, result.stderr
    (repo / "tests").mkdir()
    (repo / "tests" / "test_placeholder.py").write_text("", encoding="utf-8")
    (repo / ".claude-plugin" / "scripts").mkdir(parents=True)
    (repo / ".claude-plugin" / "scripts" / "widget.py").write_text("", encoding="utf-8")
    result = _run(argv=["git", "add", "."], cwd=repo, env=env)
    assert result.returncode == 0, result.stderr
    result = _run(argv=["git", "commit", "-m", "baseline"], cwd=repo, env=env)
    assert result.returncode == 0, result.stderr

    bin_dir = repo / "fake-bin"
    bin_dir.mkdir()
    fake_just = bin_dir / "just"
    fake_just.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> just.log\n",
        encoding="utf-8",
    )
    fake_just.chmod(fake_just.stat().st_mode | stat.S_IXUSR)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    return repo, env


def _stage(*, repo: Path, path: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("changed\n", encoding="utf-8")
    result = _run(argv=["git", "add", path], cwd=repo, env=dict(os.environ))
    assert result.returncode == 0, result.stderr


def _invoke(*, repo: Path, env: dict[str, str]) -> list[str]:
    result = _run(argv=["bash", str(_HOOK)], cwd=repo, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    return (repo / "just.log").read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("path", _FLEET_LAUNCH_INPUTS)
def test_declared_fleet_launch_inputs_run_the_gate_from_doc_only_mode(
    *, tmp_path: Path, path: str
) -> None:
    repo, env = _repository(tmp_path=tmp_path)
    _stage(repo=repo, path=path)

    assert _invoke(repo=repo, env=env) == [
        "check-pre-commit-doc-only",
        "check-fleet-launch",
    ]


def test_fleet_launch_path_is_a_declared_input_from_doc_only_mode(*, tmp_path: Path) -> None:
    repo, env = _repository(tmp_path=tmp_path)
    _stage(repo=repo, path="fleet-launch/config.sh")

    assert _invoke(repo=repo, env=env) == [
        "check-pre-commit-doc-only",
        "check-fleet-launch",
    ]


def test_unrelated_doc_only_commit_does_not_run_the_fleet_launch_gate(*, tmp_path: Path) -> None:
    repo, env = _repository(tmp_path=tmp_path)
    _stage(repo=repo, path="README.md")

    assert _invoke(repo=repo, env=env) == ["check-pre-commit-doc-only"]


def test_authoring_turn_runs_the_fleet_launch_gate_for_a_declared_input(*, tmp_path: Path) -> None:
    repo, env = _repository(tmp_path=tmp_path)
    _stage(repo=repo, path=".claude-plugin/scripts/widget.py")
    _stage(repo=repo, path="fleet-launch/dispatch-dual.sh")

    assert _invoke(repo=repo, env={**env, "LIVESPEC_AUTHORING_TURN": "implement"}) == [
        "check-staged-precheck",
        "check-fleet-launch",
        "check-changed",
    ]
