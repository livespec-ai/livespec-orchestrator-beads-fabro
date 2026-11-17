"""Regression coverage for the factory-sandbox fleet-launch diagnostic."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DIAGNOSTIC = _REPO_ROOT / "dev-tooling" / "diagnose-fleet-launch-hang.sh"


def test_diagnostic_repeats_the_scenario312_slice_and_reports_each_wall_time() -> None:
    """Every requested scenario312 iteration reports its status and elapsed time."""
    assert _DIAGNOSTIC.is_file(), "the fleet-launch hang diagnostic must be shipped"

    with TemporaryDirectory() as temporary_directory:
        repository = Path(temporary_directory)
        tooling = repository / "dev-tooling"
        tooling.mkdir()
        shutil.copy2(_DIAGNOSTIC, tooling / _DIAGNOSTIC.name)
        (tooling / "just-check-fleet-launch.sh").write_text(
            "#!/usr/bin/env bash\n" "set -eu\n" 'printf "harness slice=%s\\n" "${1:-all}"\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            ["bash", f"dev-tooling/{_DIAGNOSTIC.name}", "3"],
            cwd=repository,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )

    assert result.returncode == 0, result.stdout + result.stderr
    iteration_lines = [
        line for line in result.stdout.splitlines() if "scenario=scenario312" in line
    ]
    assert len(iteration_lines) == 3, result.stdout
    for index, line in enumerate(iteration_lines, start=1):
        assert f"iteration={index}" in line, line
        assert "exit=0" in line, line
        assert re.search(r"wall_seconds=[0-9]+(?:\.[0-9]+)?", line), line
