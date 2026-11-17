"""Green coverage for the fleet-launch hang diagnostic's remaining behaviour."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DIAGNOSTIC = _REPO_ROOT / "dev-tooling" / "diagnose-fleet-launch-hang.sh"


def _repository_with_harness(body: str) -> TemporaryDirectory[str]:
    temporary_directory = TemporaryDirectory[str]()
    tooling = Path(temporary_directory.name) / "dev-tooling"
    tooling.mkdir()
    shutil.copy2(_DIAGNOSTIC, tooling / _DIAGNOSTIC.name)
    (tooling / "just-check-fleet-launch.sh").write_text(
        "#!/usr/bin/env bash\nset -eu\n" + body,
        encoding="utf-8",
    )
    return temporary_directory


def test_timeout_names_scenario_and_prints_tree_and_wchan_for_stuck_iteration() -> None:
    """A diagnostic timeout captures the still-running scenario process tree."""
    with _repository_with_harness("sleep 10\n") as temporary_directory:
        result = subprocess.run(
            ["bash", "dev-tooling/diagnose-fleet-launch-hang.sh", "1"],
            cwd=temporary_directory,
            capture_output=True,
            check=False,
            env={"FLEET_LAUNCH_DIAGNOSTIC_TIMEOUT_S": "1"},
            text=True,
            timeout=20,
        )

    assert result.returncode != 0, result.stdout + result.stderr
    assert "timeout scenario=scenario312 iteration=1" in result.stdout
    assert "process tree scenario=scenario312 iteration=1" in result.stdout
    assert "wchan scenario=scenario312 iteration=1" in result.stdout
    assert "pid=" in result.stdout and "wchan=" in result.stdout


def test_runs_full_harness_and_reports_its_wall_time_after_requested_iterations() -> None:
    """The one full harness measurement follows all scenario312 measurements."""
    with _repository_with_harness(
        'printf "%s\\n" "harness slice=${1:-all}"\n'
    ) as temporary_directory:
        result = subprocess.run(
            ["bash", "dev-tooling/diagnose-fleet-launch-hang.sh", "2"],
            cwd=temporary_directory,
            capture_output=True,
            check=False,
            text=True,
            timeout=20,
        )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("harness slice=scenario312") == 2
    assert result.stdout.count("harness slice=all") == 1
    assert "scenario=full-harness exit=0 wall_seconds=" in result.stdout
