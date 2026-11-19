"""The repository's commit-green entry point has one program source (bd-ib-xcif5x)."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).parents[2]
_DEV_TOOLING_PROGRAM = _ROOT / "dev-tooling" / "commit-green.sh"
_DISPATCHER_PROGRAM = (
    _ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_commit_green_program.sh"
)


def test_commit_green_dev_tooling_entry_point_execs_the_dispatcher_program() -> None:
    """No commit-green program logic lives beside the production dispatcher program."""
    expected = f"""#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${{BASH_SOURCE[0]}}")" && pwd)"
exec "$script_dir/../{_DISPATCHER_PROGRAM.relative_to(_ROOT)}" "$@"
"""

    assert _DEV_TOOLING_PROGRAM.read_text(encoding="utf-8") == expected
