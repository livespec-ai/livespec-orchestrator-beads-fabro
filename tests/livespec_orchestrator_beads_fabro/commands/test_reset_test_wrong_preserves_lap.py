"""test_wrong_reset preserves a committed Green lap before returning to base (bd-ib-nckst7.2).

Drives the shipped reset program against a throwaway clone whose origin is a
local bare repository, with a committed Green lap on the run branch.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_implement_auxiliary_programs import (
    reset_test_wrong_program_source,
)

_RUN_ID = "01RUNIDLAP"


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


def _clone_with_lap(tmp_path: Path, *, commit_lap: bool) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    work = tmp_path / "work"
    _git(tmp_path, "clone", "-q", str(origin), str(work))
    (work / "base.txt").write_text("base\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "base")
    _git(work, "push", "-q", "origin", "HEAD:master")
    _git(work, "config", "livespec.factoryRunId", _RUN_ID)
    if commit_lap:
        (work / "lap.txt").write_text("green lap\n" * 5)
        _git(work, "add", "-A")
        _git(work, "commit", "-q", "-m", "green lap")
    return origin, work


def _run_reset(work: Path) -> subprocess.CompletedProcess[str]:
    script = work.parent / "reset.sh"
    script.write_text(reset_test_wrong_program_source())
    return subprocess.run(
        ["bash", str(script), "master"],
        cwd=work,
        capture_output=True,
        text=True,
        input="",
        check=False,
    )


def test_committed_green_lap_is_pushed_to_a_lap_ref_before_the_reset(tmp_path: Path) -> None:
    origin, work = _clone_with_lap(tmp_path, commit_lap=True)
    lap_tip = _git(work, "rev-parse", "HEAD")
    done = _run_reset(work)
    assert done.returncode == 0, done.stderr
    refs = _git(
        origin, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads/needs-human/"
    )
    lines = [line.split() for line in refs.splitlines()]
    assert [ref for ref, tip in lines if tip == lap_tip and "lap" in ref], refs
    lap_ref = next(ref for ref, tip in lines if tip == lap_tip)
    assert _git(origin, "diff", "--shortstat", f"master...{lap_ref}")
    assert lap_ref in done.stderr
    assert _git(work, "rev-parse", "HEAD") == _git(work, "rev-parse", "origin/master")


def test_a_lap_identical_to_the_base_is_not_pushed(tmp_path: Path) -> None:
    origin, work = _clone_with_lap(tmp_path, commit_lap=False)
    done = _run_reset(work)
    assert done.returncode == 0, done.stderr
    assert _git(origin, "for-each-ref", "refs/heads/needs-human/") == ""


def test_a_failed_push_still_resets_and_says_the_lap_was_not_preserved(tmp_path: Path) -> None:
    origin, work = _clone_with_lap(tmp_path, commit_lap=True)
    _git(work, "remote", "set-url", "--push", "origin", str(tmp_path / "missing.git"))
    done = _run_reset(work)
    assert done.returncode == 0, done.stderr
    assert "not preserved" in done.stderr
    assert _git(work, "rev-parse", "HEAD") == _git(work, "rev-parse", "origin/master")
    assert _git(origin, "for-each-ref", "refs/heads/needs-human/") == ""
