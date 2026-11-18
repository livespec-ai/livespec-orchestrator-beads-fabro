"""Regression coverage for CI coverage-verdict provenance."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_COVERAGE_RECIPE = _ROOT / "dev-tooling" / "just-check-coverage.sh"


@pytest.mark.parametrize(
    ("provenance", "mismatch"),
    [
        ("commit=other-commit\nuid={uid}\n", "commit"),
        ("commit={commit}\nuid=99999\n", "uid"),
    ],
)
def test_ci_coverage_gate_refuses_a_verdict_from_another_commit_or_uid(
    tmp_path: Path,
    provenance: str,
    mismatch: str,
) -> None:
    """The CI consumer rejects foreign artifacts without starting pytest."""
    repo = tmp_path / "repo"
    tooling = repo / "dev-tooling"
    tooling.mkdir(parents=True)
    _ = shutil.copy2(_COVERAGE_RECIPE, tooling / _COVERAGE_RECIPE.name)
    _run(["git", "init", "--quiet"], repo)
    _run(["git", "config", "user.email", "coverage@example.test"], repo)
    _run(["git", "config", "user.name", "Coverage"], repo)
    (repo / "tracked").touch()
    _run(["git", "add", "tracked"], repo)
    _run(["git", "commit", "--quiet", "-m", "fixture"], repo)
    commit = _run(["git", "rev-parse", "HEAD"], repo).stdout.strip()

    gates = repo / ".coverage-gates"
    gates.mkdir()
    (gates / "per-file.status").write_text("0\n", encoding="utf-8")
    (gates / "per-file.log").write_text("coverage passed\n", encoding="utf-8")
    (gates / "per-file.provenance").write_text(
        provenance.format(commit=commit, uid=os.getuid()), encoding="utf-8"
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    pytest_started = tmp_path / "pytest-started"
    fake_uv = fake_bin / "uv"
    _ = fake_uv.write_text(
        f"#!/usr/bin/env bash\ntouch {pytest_started}\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)

    consumer = subprocess.run(
        ["bash", str(tooling / _COVERAGE_RECIPE.name)],
        cwd=repo,
        env={
            **os.environ,
            "GITHUB_ACTIONS": "true",
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert consumer.returncode != 0
    assert "canonical per-file verdict provenance mismatch" in consumer.stderr
    assert mismatch in consumer.stderr
    assert not pytest_started.exists()


@pytest.mark.parametrize(("verdict", "expected_status"), [("0\n", 0), ("1\n", 1)])
def test_ci_coverage_gate_replays_a_matching_verdict(
    tmp_path: Path, verdict: str, expected_status: int
) -> None:
    """A matching CI artifact retains the per-file gate's pass or failure."""
    repo = tmp_path / "repo"
    tooling = repo / "dev-tooling"
    tooling.mkdir(parents=True)
    _ = shutil.copy2(_COVERAGE_RECIPE, tooling / _COVERAGE_RECIPE.name)
    _run(["git", "init", "--quiet"], repo)
    _run(["git", "config", "user.email", "coverage@example.test"], repo)
    _run(["git", "config", "user.name", "Coverage"], repo)
    (repo / "tracked").touch()
    _run(["git", "add", "tracked"], repo)
    _run(["git", "commit", "--quiet", "-m", "fixture"], repo)
    commit = _run(["git", "rev-parse", "HEAD"], repo).stdout.strip()

    gates = repo / ".coverage-gates"
    gates.mkdir()
    (gates / "per-file.status").write_text(verdict, encoding="utf-8")
    (gates / "per-file.log").write_text("coverage verdict\n", encoding="utf-8")
    (gates / "per-file.provenance").write_text(
        f"commit={commit}\nuid={os.getuid()}\n", encoding="utf-8"
    )

    consumer = subprocess.run(
        ["bash", str(tooling / _COVERAGE_RECIPE.name)],
        cwd=repo,
        env={**os.environ, "GITHUB_ACTIONS": "true"},
        check=False,
        capture_output=True,
        text=True,
    )

    assert consumer.returncode == expected_status
    assert "reading the canonical per-file verdict" in consumer.stdout
    assert "coverage verdict" in consumer.stderr


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)
