"""A green gate preview over a one-module change does not run the full pytest suite.

Definition-of-Done assertion 2 of bd-ib-pxecmp.  The three links of the chain have
their own tests (the preview program sets the implement-turn environment, the hook
routes that environment to `just check-changed`, the selector scopes under
`LIVESPEC_GATE_PREVIEW`); this case runs all three together.  It materializes the
real preview program, points a throwaway repository's pre-commit hook at the real
`just-check-pre-commit.sh`, runs the real selector behind a fake `just`, and
records every `uv run pytest` the gate makes.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from tests.prepare_step_support import env_of, steps_in

_ROOT = Path(__file__).parents[2]
_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_gate_preview_program"
_PKG = "pkg"
_PYPROJECT = (
    "[tool.livespec_dev_tooling]\n"
    f'source_tree_prefixes = ["{_PKG}/"]\n'
    "[[tool.livespec_dev_tooling.mirror_pairings]]\n"
    f'source_tree = "{_PKG}"\n'
    'test_tree = "tests/pkg"\n'
)
_FILES = {
    "pyproject.toml": _PYPROJECT,
    f"{_PKG}/__init__.py": "",
    f"{_PKG}/a.py": "VALUE = 1\n",
    f"{_PKG}/b.py": "from . import a\n",
    "tests/pkg/test_a.py": "def test_a() -> None: ...\n",
    "tests/pkg/test_b.py": "import pkg.b\n",
    "tests/pkg/test_other.py": "def test_other() -> None: ...\n",
}
_COPIED = (
    "dev-tooling/checks/_affected_tests_selection.py",
    "dev-tooling/checks/_affected_tests_scan.py",
    "dev-tooling/just-test-nprocs.sh",
)


def _run(*, repo: Path, env: dict[str, str], argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=repo, env=env, capture_output=True, text=True, check=False)


def _git(*, repo: Path, env: dict[str, str], argv: list[str]) -> None:
    done = _run(repo=repo, env=env, argv=["git", *argv])
    assert done.returncode == 0, done.stderr


def _tool(*, path: Path, body: str) -> None:
    _ = path.write_text(body, encoding="utf-8")
    _ = path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_repository(*, repo: Path, tools: Path, log: Path) -> None:
    """Write the repository's files and the fake `uv` and `just` the hook will find."""
    for relative, text in _FILES.items():
        (repo / relative).parent.mkdir(parents=True, exist_ok=True)
        _ = (repo / relative).write_text(text, encoding="utf-8")
    for relative in _COPIED:
        (repo / relative).parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copy(_ROOT / relative, repo / relative)
    _tool(
        path=tools / "uv",
        body=f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> '{log}'\nexit 0\n",
    )
    _tool(
        path=tools / "just",
        body=(
            "#!/usr/bin/env bash\n"
            'if [[ "$*" == check-changed ]]; then\n'
            f'  exec "{sys.executable}" dev-tooling/checks/_affected_tests_selection.py\n'
            "fi\n"
            "exit 0\n"
        ),
    )


def test_a_green_preview_over_one_changed_module_runs_only_its_tests(tmp_path: Path) -> None:
    """The recorded pytest calls name the mirror test alone and none is a whole-suite run."""
    preview = importlib.import_module(_MODULE)
    repo, home, tools, log = (
        tmp_path / "repo",
        tmp_path / "home",
        tmp_path / "bin",
        tmp_path / "uv.log",
    )
    for directory in (repo, home, tools):
        directory.mkdir()
    env = {
        **{
            name: value
            for name, value in os.environ.items()
            if not name.startswith(("GIT_", "LIVESPEC_", "COV_CORE_", "SKIP_"))
            and name != "COVERAGE_PROCESS_START"
        },
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Scenario Author",
        "GIT_AUTHOR_EMAIL": "author@example.invalid",
        "GIT_COMMITTER_NAME": "Scenario Author",
        "GIT_COMMITTER_EMAIL": "author@example.invalid",
        "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(tmp_path / "plugins"),
        "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
    }
    _write_repository(repo=repo, tools=tools, log=log)
    _git(repo=repo, env=env, argv=["init", "--quiet", "-b", "master"])
    _git(repo=repo, env=env, argv=["add", "."])
    _git(repo=repo, env=env, argv=["commit", "--quiet", "-m", "chore: baseline"])
    _git(repo=repo, env=env, argv=["update-ref", "refs/remotes/origin/master", "HEAD"])
    hook = repo / ".git" / "hooks" / "pre-commit"
    _tool(
        path=hook,
        body=f'#!/bin/sh\nexec bash "{_ROOT / "dev-tooling" / "just-check-pre-commit.sh"}"\n',
    )
    _ = (repo / _PKG / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
    steps = [
        step for step in steps_in(block=preview.gate_preview_prepare_steps_block()) if step.env
    ]
    materialized = _run(
        repo=repo, env=env_of(step=steps[0], base=env), argv=["sh", "-c", steps[0].script]
    )
    assert materialized.returncode == 0, materialized.stderr
    runner = tmp_path / "plugins" / preview.GATE_PREVIEW_PROGRAM_FILENAME

    completed = _run(repo=repo, env=env, argv=[sys.executable, str(runner), "green"])

    report = cast("dict[str, Any]", json.loads(completed.stdout.splitlines()[-1]))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert report["status"] == 0
    pytest_calls = [
        line for line in log.read_text(encoding="utf-8").splitlines() if " pytest " in f" {line} "
    ]
    assert len(pytest_calls) == 1, pytest_calls
    assert pytest_calls[0].endswith("--cov-fail-under=0 tests/pkg/test_a.py")
    assert "tests/pkg/test_b.py" not in pytest_calls[0]
    assert "tests/pkg/test_other.py" not in pytest_calls[0]
