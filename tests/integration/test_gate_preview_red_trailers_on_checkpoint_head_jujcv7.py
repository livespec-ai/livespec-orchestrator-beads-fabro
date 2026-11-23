"""A Green preview grades gate 02 the way the real Red-to-Green amend is graded (bd-ib-jujcv7).

Measured on run 01M84G4RWM0Z (bd-ib-iwhugc): the preview keeps HEAD at the run's latest
`fabro(...)` checkpoint commit, and gate 02-commit-pairs-source-and-test skips an amend only
when HEAD's message carries the Red commit's `TDD-Red-Test-File-Checksum:` trailer. A checkpoint
commit carries none, so the gate saw the implementation staged without its paired test and
refused a commit that the real amend over the Red commit accepts. The record then named no
failed target, because lefthook's step summary has no `Failed targets (N):` header.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, cast

from tests.integration.test_implement_gate_preview_scenario285 import (
    _MODULE,
    _git,
    _preview_repository,
    _run,
)

_RED_TRAILER = "TDD-Red-Test-File-Checksum:"
_GREEN_TRAILER = "TDD-Green-Verified-At:"


def _checkpoint_over_red_commit(
    *, tmp_path: Path, red_message: str
) -> tuple[Path, Path, dict[str, str]]:
    """Build a Red commit, then a `fabro(...)` checkpoint over it, with a hook that grades HEAD."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    commit_env = env.copy()
    _ = commit_env.pop("LIVESPEC_CHECK_SKIP")
    _git(
        repo=repo,
        env=commit_env,
        argv=[
            "commit",
            "--quiet",
            "--allow-empty",
            "--no-verify",
            "-m",
            "fix: red",
            "-m",
            red_message,
        ],
    )
    _git(repo=repo, env=env, argv=["add", "tracked.py", "created.py"])
    _git(
        repo=repo,
        env=commit_env,
        argv=[
            "commit",
            "--quiet",
            "--no-verify",
            "-m",
            "fabro(run): green (success)",
            "-m",
            "Fabro-Run: run",
        ],
    )
    checkpoint_tree = _git(repo=repo, env=env, argv=["rev-parse", "HEAD^{tree}"])
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text(
        "#!/bin/sh\n"
        "if ! git diff --quiet; then\n"
        "  printf 'unstaged changes would be stashed away\\n'\n"
        "  exit 6\n"
        "fi\n"
        f'if test "$(git write-tree)" != "{checkpoint_tree}"; then\n'
        "  printf 'the index is not the latest checkpoint tree\\n'\n"
        "  exit 7\n"
        "fi\n"
        "for path in tracked.py created.py; do\n"
        '  git diff --cached --name-only | grep -qx "$path" || exit 8\n'
        "done\n"
        'message="$(git log -1 --format=%B HEAD)"\n'
        f'if ! (printf %s "$message" | grep -q "{_RED_TRAILER}") || '
        f'(printf %s "$message" | grep -q "{_GREEN_TRAILER}"); then\n'
        "  printf 'source change staged without paired test change\\n'\n"
        "  exit 1\n"
        "fi\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    return repo, runner, env


def _preview_report(*, repo: Path, runner: Path, env: dict[str, str]) -> dict[str, Any]:
    completed = _run(repo=repo, env=env, argv=[sys.executable, str(runner), "green"], check=False)
    return cast("dict[str, Any]", json.loads(completed.stdout.splitlines()[-1]))


def test_a_checkpoint_over_an_unpaired_red_commit_is_graded_as_the_red_amend(
    tmp_path: Path,
) -> None:
    repo, runner, env = _checkpoint_over_red_commit(
        tmp_path=tmp_path, red_message=f"{_RED_TRAILER} 0123abcd"
    )
    before_head = _git(repo=repo, env=env, argv=["rev-parse", "HEAD"])

    report = _preview_report(repo=repo, runner=runner, env=env)

    assert report["status"] == 0, report
    assert _git(repo=repo, env=env, argv=["rev-parse", "HEAD"]) == before_head


def test_a_checkpoint_over_a_paired_red_commit_keeps_its_own_message(tmp_path: Path) -> None:
    repo, runner, env = _checkpoint_over_red_commit(
        tmp_path=tmp_path, red_message=f"{_RED_TRAILER} 0123abcd\n\n{_GREEN_TRAILER} 2026-11-23"
    )

    report = _preview_report(repo=repo, runner=runner, env=env)

    assert report["status"] == 1, report


def test_the_record_names_the_failed_lefthook_steps_when_no_header_is_printed(
    tmp_path: Path,
) -> None:
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text(
        "#!/bin/sh\n"
        "printf ':: affected-tests gate refused the commit\\n'\n"
        "printf '\\342\\234\\227 02-commit-pairs-source-and-test (0.49 seconds)\\n'\n"
        "printf '\\342\\234\\227 03-check-pre-commit (23.69 seconds)\\n'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)

    report = _preview_report(repo=repo, runner=runner, env=env)

    assert report["failed_targets"] == [
        "02-commit-pairs-source-and-test",
        "03-check-pre-commit",
    ], report
