"""The gate preview's progress line names the hook step that is RUNNING (bd-ib-42erfz).

Measured on this repository's own commit gate on 2026-11-20 (lefthook v1.13.6, output
not a terminal): lefthook prints a step's header line only when that step
FINISHES, together with its output. While `03-check-pre-commit` ran for minutes, the
newest header in the output was `02-commit-pairs-source-and-test`, which had finished
long before. A progress line built from the newest header therefore names a finished
step as the running one. The running step's own command is the outermost `just`
process under the preview, so the line must name that first.

The hook below prints a finished step's header and then runs a process whose argv[0]
is `just` (a symbolic link to `/bin/sh` named `just`, so the kernel reports argv[0] as
`just` exactly as it does for the real binary). That process waits on a release file.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import time
from pathlib import Path

from tests.integration.test_implement_gate_preview_scenario285 import (
    _MODULE,
    _preview_repository,
)

_FINISHED_STEP = "02-commit-pairs-source-and-test"
_DEADLINE_SECONDS = 60.0


def _fixture(*, tmp_path: Path) -> tuple[Path, Path, dict[str, str], Path]:
    """A hook that prints a finished step's header, then runs a waiting `just` process."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "just").symlink_to("/bin/sh")
    release = tmp_path / "release"
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text(
        "#!/bin/sh\n"
        f"printf '\\342\\224\\203  {_FINISHED_STEP} \\342\\235\\257 \\n'\n"
        "just -c 'n=0; while ! test -f \"$1\" && test $n -lt 600; do sleep 0.1; n=$((n+1)); done'"
        f" check-pre-commit '{release}'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    env = {name: value for name, value in env.items() if not name.startswith("COV_CORE_")}
    env = {
        **env,
        "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
        "LIVESPEC_GATE_PREVIEW_PROGRESS_SECONDS": "1",
    }
    return repo, runner, env, release


def test_progress_names_the_running_just_command_before_a_finished_steps_header(
    tmp_path: Path,
) -> None:
    """The running `just` command leads the line; the finished header is not called running."""
    repo, runner, env, release = _fixture(tmp_path=tmp_path)
    process = subprocess.Popen(
        [sys.executable, str(runner), "green"],
        cwd=repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    assert process.stdout is not None
    progress = ""
    started = time.monotonic()
    try:
        while not progress:
            assert time.monotonic() - started < _DEADLINE_SECONDS
            line = process.stdout.readline()
            assert line, "preview output ended before any progress line"
            if line.startswith("gate preview (green): still running"):
                progress = line
    finally:
        release.touch()
    _ = process.communicate(timeout=_DEADLINE_SECONDS)

    assert progress.startswith("gate preview (green): still running `just -c "), progress
    assert "check-pre-commit" in progress, progress
    assert f"hook step {_FINISHED_STEP}" not in progress, progress
    assert _FINISHED_STEP in progress, progress
    assert process.returncode == 0
