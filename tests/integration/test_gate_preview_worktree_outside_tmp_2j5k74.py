"""The gate preview's disposable worktree is not under the system temp directory (bd-ib-2j5k74).

Measured on run 01M7RMY9VBYM (bd-ib-lhwlxr, python-agent-v1.188.1): the Green preview ran the
repository's commit hook in a worktree the preview program created with `tempfile.mkdtemp`, so
under /tmp, and `pyproject.toml` `[tool.coverage.run] omit` lists "/tmp/*" for the tests' own
scratch directories. Coverage then omitted every source file of the preview tree, collected
nothing and reported 0% for a change the direct `check-per-file-coverage` graded at 100%.

The preview program is executed exactly as a dispatch materializes it, against a real
repository whose hook reports the directory it runs in. Each case gives the program a system
temp directory and a home directory that are siblings, so "under the temp directory" is decided
by the program's own choice and never by where pytest keeps its own scratch space.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, cast

from tests.integration.test_implement_gate_preview_scenario285 import (
    _MODULE,
    _preview_repository,
    _run,
)

_ROOT_MARKER = "PREVIEW_ROOT="


def _reporting_hook(*, repo: Path) -> None:
    """A hook that passes and prints the directory it was run in."""
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text(
        f"#!/bin/sh\nprintf '{_ROOT_MARKER}%s\\n' \"$(pwd -P)\"\nexit 0\n", encoding="utf-8"
    )
    hook.chmod(0o755)


def _preview(*, tmp_path: Path, extra_env: dict[str, str] | None = None) -> tuple[Path, Path, Path]:
    """Run the preview; return the root the hook ran in, the temp dir and the home dir."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    _reporting_hook(repo=repo)
    system_temp = tmp_path / "system-temp"
    home = tmp_path / "preview-home"
    system_temp.mkdir()
    home.mkdir()
    env = {**env, "TMPDIR": str(system_temp), "HOME": str(home), **(extra_env or {})}
    completed = _run(repo=repo, env=env, argv=[sys.executable, str(runner), "green"], check=False)
    report = cast("dict[str, Any]", json.loads(completed.stdout.splitlines()[-1]))
    assert report["status"] == 0, completed.stderr + completed.stdout
    roots = [
        line[len(_ROOT_MARKER) :]
        for line in completed.stdout.splitlines()
        if line.startswith(_ROOT_MARKER)
    ]
    assert len(roots) == 1, completed.stdout
    return Path(roots[0]), system_temp.resolve(), home.resolve()


def test_the_preview_worktree_is_not_under_the_system_temp_directory(tmp_path: Path) -> None:
    root, system_temp, _home = _preview(tmp_path=tmp_path)

    assert not root.is_relative_to(system_temp), (root, system_temp)


def test_the_preview_worktree_is_below_the_home_directory_by_default(tmp_path: Path) -> None:
    root, _system_temp, home = _preview(tmp_path=tmp_path)

    assert root.is_relative_to(home), (root, home)


def test_a_named_preview_root_is_where_the_worktree_is_made(tmp_path: Path) -> None:
    chosen = tmp_path / "chosen-root"
    chosen.mkdir()

    root, _system_temp, _home = _preview(
        tmp_path=tmp_path, extra_env={"LIVESPEC_GATE_PREVIEW_ROOT": str(chosen)}
    )

    assert root.is_relative_to(chosen.resolve()), (root, chosen)


def test_the_preview_worktree_is_removed_after_the_preview(tmp_path: Path) -> None:
    root, _system_temp, _home = _preview(tmp_path=tmp_path)

    assert not root.exists(), root
