"""Contract: no shell script pipes into an early-exit reader under pipefail.

A script that runs `writer | head`, `writer | curl --header @-`, `writer | grep -q` or
`writer | sed -n '..q'` under `set -o pipefail` takes SIGPIPE (exit 141) whenever the
reader exits before the writer has finished writing, which a loaded shard makes
intermittent (bd-ib-k3xswd). The rule: feed a reader from a here-string or a file, and
bound output with a reader that consumes all of its input (`sed -n '1,8p'`) or with bash
substring expansion.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PIPEFAIL = re.compile(r"\bpipefail\b")
_EARLY_EXIT_READER = re.compile(
    r"\|[ \t]*(?:head\b|curl\b|read\b|grep[ \t]+-[A-Za-z]*q|sed[ \t]+-n[^|]*[^A-Za-z]q\b|awk\b[^|]*\bexit\b)"
)


def _tracked_shell_scripts() -> list[Path]:
    listing = subprocess.run(
        ["git", "ls-files", "*.sh"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    return [_REPO_ROOT / name for name in listing if not name.startswith("tmp/")]


def test_there_are_shell_scripts_to_scan() -> None:
    names = {path.name for path in _tracked_shell_scripts()}
    assert "provision-honeycomb-run-turn-trigger.sh" in names
    assert "build-and-verify.sh" in names


def test_no_pipefail_script_pipes_into_an_early_exit_reader() -> None:
    offenders: list[str] = []
    for script in _tracked_shell_scripts():
        text = script.read_text(encoding="utf-8")
        if not _PIPEFAIL.search(text):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            if _EARLY_EXIT_READER.search(line):
                offenders.append(f"{script.relative_to(_REPO_ROOT)}:{lineno}: {line.strip()}")
    assert offenders == [], "pipe into an early-exit reader under pipefail:\n" + "\n".join(
        offenders
    )
