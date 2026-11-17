"""A pytest session under an inherited repo-locating GIT_* never touches the outer repo.

A hook-spawned pytest inherits GIT_DIR and friends. The session scrub in
`tests/conftest.py` must drop every one before any test runs, so a test that
shells out to git acts on its own temp repo and never on the surrounding one.

Measured leak effects this binds: stray commits on the primary, `core.bare`
flipped, `core.hooksPath` repointed, `remote.origin.url` rewritten, and `user.*`
or `livespec.*` keys written into the real `.git/config`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.conftest import _scrub_repo_locating_git_env

_VARS = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_PREFIX",
)


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return done.stdout


def test_the_scrub_drops_every_repo_locating_variable_and_nothing_else() -> None:
    environ = {name: "/somewhere" for name in _VARS} | {"HOME": "/home/x", "GIT_AUTHOR_NAME": "a"}
    _scrub_repo_locating_git_env(environ=environ)
    assert environ == {"HOME": "/home/x", "GIT_AUTHOR_NAME": "a"}


def test_git_writes_under_an_inherited_repo_never_reach_the_outer_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outer = tmp_path / "outer"
    probe_work = tmp_path / "probe-work"
    outer.mkdir()
    probe_work.mkdir()
    _git(outer, "init", "-q", "-b", "master", ".")
    _git(outer, "remote", "add", "origin", "https://github.com/outer/outer.git")
    _git(outer, "config", "user.name", "outer")
    _git(outer, "config", "livespec.primaryPath", str(outer))
    config_before = _git(outer, "config", "--local", "--list")
    for name in _VARS:
        monkeypatch.setenv(name, str(outer / ".git"))
    _scrub_repo_locating_git_env(environ=os.environ)
    assert not [name for name in _VARS if name in os.environ]
    # The git writes a fixture performs, now under the scrubbed environment.
    _git(probe_work, "init", "-q", "-b", "master", ".")
    _git(probe_work, "remote", "add", "origin", "git@github.com:probe/probe.git")
    _git(probe_work, "config", "user.name", "probe")
    _git(probe_work, "config", "livespec.probe", "1")
    _git(
        probe_work, "-c", "user.email=p@example.invalid", "commit", "--allow-empty", "-q", "-m", "p"
    )
    _git(probe_work, "config", "core.hooksPath", "/tmp/probe-hooks")
    _git(probe_work, "config", "core.bare", "true")
    assert _git(outer, "config", "--local", "--list") == config_before
    assert _git(outer, "config", "--get", "remote.origin.url").strip() == (
        "https://github.com/outer/outer.git"
    )
    assert _git(outer, "config", "--get", "core.bare").strip() == "false"
    hooks = subprocess.run(
        ["git", "config", "--get", "core.hookspath"], cwd=outer, capture_output=True, check=False
    )
    assert hooks.returncode == 1
    assert _git(outer, "rev-list", "--all", "--count").strip() == "0"
    assert (probe_work / ".git").is_dir()
