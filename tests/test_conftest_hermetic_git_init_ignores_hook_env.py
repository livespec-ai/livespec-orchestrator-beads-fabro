"""The hermetic temp-root init never commits into a repo named by an inherited GIT_DIR."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.conftest import _git_init_origin_reachable


def test_an_inherited_git_dir_does_not_redirect_the_hermetic_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outer = tmp_path / "outer"
    inner = tmp_path / "inner"
    outer.mkdir()
    inner.mkdir()
    _ = subprocess.run(["git", "init", "-q", "-b", "master", "."], cwd=outer, check=True)
    monkeypatch.setenv("GIT_DIR", str(outer / ".git"))
    _git_init_origin_reachable(root=inner)
    monkeypatch.delenv("GIT_DIR")
    counted = subprocess.run(
        ["git", "rev-list", "--all", "--count"],
        cwd=outer,
        capture_output=True,
        text=True,
        check=True,
    )
    assert counted.stdout.strip() == "0"
    assert (inner / ".git").is_dir()
