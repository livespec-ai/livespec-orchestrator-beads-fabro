"""The repository's commit-green entry point has one program source (bd-ib-xcif5x)."""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).parents[2]
_COMMANDS_DIRECTORY = (
    _ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)


@pytest.mark.parametrize(
    ("dev_tooling_name", "dispatcher_name"),
    (
        ("commit-green.sh", "_dispatcher_commit_green_program.sh"),
        ("commit-red.sh", "_dispatcher_commit_red_program.sh"),
        ("green-token-scope.sh", "_dispatcher_green_token_scope_program.sh"),
        (
            "reset-test-wrong-to-dispatch-base.sh",
            "_dispatcher_reset_test_wrong_program.sh",
        ),
    ),
)
def test_dev_tooling_dispatcher_entry_point_execs_the_production_program(
    dev_tooling_name: str, dispatcher_name: str
) -> None:
    """No dispatcher program logic lives beside its production program."""
    dev_tooling_program = _ROOT / "dev-tooling" / dev_tooling_name
    dispatcher_program = _COMMANDS_DIRECTORY / dispatcher_name
    expected = f"""#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${{BASH_SOURCE[0]}}")" && pwd)"
exec bash "$script_dir/../{dispatcher_program.relative_to(_ROOT)}" "$@"
"""

    assert dev_tooling_program.read_text(encoding="utf-8") == expected
