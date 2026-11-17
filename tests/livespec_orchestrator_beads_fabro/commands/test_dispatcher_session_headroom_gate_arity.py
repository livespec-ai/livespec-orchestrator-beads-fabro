"""The session-headroom gate satisfies the parameter-count detector, not suppresses it."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_GATE = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
    / "_dispatcher_session_headroom_gate.py"
)


def test_gate_satisfies_parameter_count_without_a_noqa() -> None:
    """With every `noqa` ignored, the gate module still has no too-many-arguments finding."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--ignore-noqa",
            "--select",
            "PLR0913",
            "--no-fix",
            "--output-format",
            "concise",
            str(_GATE),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
