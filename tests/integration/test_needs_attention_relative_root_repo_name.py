"""A relative `--project-root .` must still name its repository in needs-attention.

`needs_attention.main` derived the repository name as `project_root.name`. For the
relative root `.` that is the EMPTY string, so every hygiene candidate keyed on the repository
(`hygiene:idle-factory:<repo>`, `hygiene:ready-aging:<repo>` and the staleness lanes) built a stable
id ending in a bare colon, which the runtime validator refuses: the operator saw four
`attention-invalid` rows instead of the facts (bd-ib-sliucq, observed on hetzner-xubuntu-info).
Every needs-attention handoff string itself passes `--project-root .`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import needs_attention


class _CapturedError(Exception):
    def __init__(self, repo_name: str) -> None:
        super().__init__(repo_name)
        self.repo_name = repo_name


def _capture_repo_name(monkeypatch: pytest.MonkeyPatch) -> None:
    def _build_attention(**kwargs: object) -> object:
        raise _CapturedError(str(kwargs["repo_name"]))

    monkeypatch.setattr(needs_attention, "build_attention", _build_attention)


def test_relative_dot_root_names_the_repository_by_its_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "hetzner-xubuntu-info"
    repo.mkdir()
    monkeypatch.chdir(repo)
    _capture_repo_name(monkeypatch)
    with pytest.raises(_CapturedError) as captured:
        _ = needs_attention.main(argv=["--project-root", "."])
    assert captured.value.repo_name == "hetzner-xubuntu-info"
