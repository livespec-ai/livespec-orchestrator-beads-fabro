"""A slow gate preview reports progress and leaves a pollable record (bd-ib-42erfz).

Reproduced on 2026-11-20 in the factory sandbox image the failing runs used
(python-agent-v1.188.1, via `just gate-repro --image ... -- <command>`): the preview ran the
commit hook with its output captured and printed nothing until the whole hook finished, so a
caller whose tool call ended first (90-180 s, against a 593-1043 s aggregate) saw no output,
and the preview left no record.

Every case runs the program exactly as a dispatch materializes it, against a real repository
whose hook is a shell script that names a lefthook step and then waits on a RELEASE FILE, so
"the hook is still running" holds on any host load instead of racing a sleep.
"""

from __future__ import annotations

import importlib
import itertools
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

from tests.integration.test_implement_gate_preview_scenario285 import (
    _FAILED_TARGET,
    _MODULE,
    _preview_repository,
)

_RECORD = "livespec-implement-gate-preview-green-result.json"
_STEP = "03-check-pre-commit"
_DEADLINE_SECONDS = 60.0
_FINAL_REPORT = {
    "failed_targets": [_FAILED_TARGET],
    "preview_ran": True,
    "status": 1,
    "unset_variables": ["LIVESPEC_CHECK_SKIP"],
}


def _waiting_hook(*, repo: Path, release: Path, runs: Path) -> None:
    """A hook that announces a lefthook step, then waits for the release file to appear."""
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text(
        "#!/bin/sh\n"
        f"printf 'run\\n' >> '{runs}'\n"
        f"printf '\\342\\224\\203  {_STEP} \\342\\235\\257 \\n'\n"
        "waited=0\n"
        f"while ! test -f '{release}' && test \"$waited\" -lt 600; do\n"
        "  sleep 0.1; waited=$((waited + 1))\n"
        "done\n"
        f"printf 'Failed targets (1):\\n  - {_FAILED_TARGET}\\n'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)


def _fixture(*, tmp_path: Path) -> tuple[Path, Path, dict[str, str], Path, Path]:
    """Build the repository, the waiting hook, and a one-second progress cadence."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    release = tmp_path / "release"
    runs = tmp_path / "hook-runs"
    _waiting_hook(repo=repo, release=release, runs=runs)
    # The shared fixture already drops GIT_ variables and COVERAGE_PROCESS_START;
    # an allowlisted spawn also drops COV_CORE_ ones.
    env = {name: value for name, value in env.items() if not name.startswith("COV_CORE_")}
    env = {**env, "LIVESPEC_GATE_PREVIEW_PROGRESS_SECONDS": "1"}
    return repo, runner, env, release, runs


def _start(*, repo: Path, runner: Path, env: dict[str, str]) -> subprocess.Popen[str]:
    """Start the preview the way a tool call does: its own process group, output piped."""
    return subprocess.Popen(
        [sys.executable, str(runner), "green"],
        cwd=repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )


def _progress_lines(*, process: subprocess.Popen[str], count: int) -> list[tuple[float, str]]:
    """Read stdout until `count` progress lines naming the step arrive; time each."""
    assert process.stdout is not None
    seen: list[tuple[float, str]] = []
    started = time.monotonic()
    while len(seen) < count:
        assert time.monotonic() - started < _DEADLINE_SECONDS, seen
        line = process.stdout.readline()
        assert line, f"preview output ended before {count} progress lines: {seen}"
        if "gate preview" in line and "running" in line and _STEP in line:
            seen.append((time.monotonic(), line))
    return seen


def _record(*, repo: Path) -> dict[str, Any] | None:
    path = repo / ".git" / _RECORD
    if not path.is_file():
        return None
    return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))


def _await_verdict(*, repo: Path) -> dict[str, Any]:
    started = time.monotonic()
    while time.monotonic() - started < _DEADLINE_SECONDS:
        record = _record(repo=repo)
        if record is not None and "status" in record:
            return record
        time.sleep(0.1)
    raise AssertionError(f"no verdict reached the record: {_record(repo=repo)}")


def test_a_running_preview_prints_a_progress_line_naming_the_hook_step(tmp_path: Path) -> None:
    """While the hook runs, progress lines naming its step arrive at the declared cadence."""
    repo, runner, env, release, _runs = _fixture(tmp_path=tmp_path)
    process = _start(repo=repo, runner=runner, env=env)
    try:
        lines = _progress_lines(process=process, count=3)
    finally:
        release.touch()
    stdout, _stderr = process.communicate(timeout=_DEADLINE_SECONDS)

    gaps = [later - earlier for (earlier, _), (later, _) in itertools.pairwise(lines)]
    assert max(gaps) < 5, gaps
    assert process.returncode == 1
    assert json.loads(stdout.splitlines()[-1]) == _FINAL_REPORT
    source = importlib.import_module(_MODULE).gate_preview_program_source()
    default = re.search(r"^DEFAULT_PROGRESS_SECONDS = (\d+)$", source, re.MULTILINE)
    assert default is not None
    assert 0 < int(default.group(1)) <= 60


def test_a_preview_whose_caller_is_killed_leaves_a_running_record_then_its_verdict(
    tmp_path: Path,
) -> None:
    """Killing the caller's process group leaves the hook running and the record readable."""
    repo, runner, env, release, runs = _fixture(tmp_path=tmp_path)
    process = _start(repo=repo, runner=runner, env=env)
    try:
        _ = _progress_lines(process=process, count=1)
        os.killpg(process.pid, signal.SIGKILL)
        _ = process.wait(timeout=_DEADLINE_SECONDS)

        running = _record(repo=repo)
        assert running is not None
        assert running["preview"] == "running"
        assert running["stage"] == "green"
        assert "status" not in running
        status = subprocess.run(
            [sys.executable, str(runner), "green", "--status"],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert status.returncode == 75, status.stdout + status.stderr
        assert json.loads(status.stdout.splitlines()[-1])["preview"] == "running"

        attached = _start(repo=repo, runner=runner, env=env)
        _ = _progress_lines(process=attached, count=1)
    finally:
        release.touch()
    stdout, _stderr = attached.communicate(timeout=_DEADLINE_SECONDS)

    assert _await_verdict(repo=repo) == _FINAL_REPORT
    assert attached.returncode == 1
    assert json.loads(stdout.splitlines()[-1]) == _FINAL_REPORT
    assert runs.read_text(encoding="utf-8").splitlines() == ["run"]
    finished = subprocess.run(
        [sys.executable, str(runner), "green", "--status"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert finished.returncode == 1
    assert json.loads(finished.stdout.splitlines()[-1]) == _FINAL_REPORT
