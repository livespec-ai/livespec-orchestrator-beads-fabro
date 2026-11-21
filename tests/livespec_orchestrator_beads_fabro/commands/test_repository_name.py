"""`repository_name` reads a repository's name from a root however the CLI spelled it."""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._repository_name import repository_name


def test_relative_dot_is_named_by_the_directory_it_resolves_to(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "some-repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    assert repository_name(root=Path()) == "some-repo"


def test_parent_relative_root_is_named_by_its_resolved_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "some-repo"
    (repo / "nested").mkdir(parents=True)
    monkeypatch.chdir(repo / "nested")
    assert repository_name(root=Path("..")) == "some-repo"


def test_absolute_root_keeps_its_own_name(tmp_path: Path) -> None:
    repo = tmp_path / "abs-repo"
    repo.mkdir()
    assert repository_name(root=repo) == "abs-repo"
