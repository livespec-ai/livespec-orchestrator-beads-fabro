"""Scenario 242: every provisional fleet-launch script carries its banner (bd-ib-mflywb).

The scenario says every shell and Python script under fleet-launch/ marks itself PROVISIONAL and
EXPERIMENTAL in its opening comment block and names the livespec console application and the
launch-loop tool bd-ib-jr6w7v as its first-class replacement, and that `check-fleet-launch` is
part of the check aggregate. It does not drive the launcher harness; the Scenario 297 test and the
commit and push gates do that.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FLEET_LAUNCH = _ROOT / "fleet-launch"
_OPENING_COMMENT_LINES = 25


def _scripts() -> list[Path]:
    tracked = subprocess.run(
        ["git", "ls-files", "fleet-launch"],
        cwd=_ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.split()
    return sorted(_ROOT / path for path in tracked if path.endswith((".sh", ".py")) and path != "")


def _banner_problems(*, script: Path) -> list[str]:
    lines = script.read_text(encoding="utf-8").splitlines()[:_OPENING_COMMENT_LINES]
    comment = "\n".join(line for line in lines if line.lstrip().startswith("#"))
    problems = []
    for needle, label in (
        ("PROVISIONAL", "PROVISIONAL"),
        ("EXPERIMENTAL", "EXPERIMENTAL"),
        ("console", "the livespec console application"),
        ("bd-ib-jr6w7v", "the launch-loop tool bd-ib-jr6w7v"),
    ):
        if needle not in comment:
            problems.append(label)
    return problems


def test_scenario242_every_fleet_launch_script_carries_the_provisional_banner() -> None:
    scripts = _scripts()
    assert scripts, "no tracked shell or Python script found under fleet-launch/"
    failures = {
        str(script.relative_to(_ROOT)): problems
        for script in scripts
        if (problems := _banner_problems(script=script))
    }
    assert not failures, f"scripts missing their banner, with what each lacks: {failures}"


def test_scenario242_the_check_aggregate_declares_check_fleet_launch() -> None:
    extractor = _ROOT / "dev-tooling" / "aggregate-targets.sh"
    completed = subprocess.run(
        ["bash", str(extractor)], cwd=_ROOT, capture_output=True, check=False, text=True
    )
    assert completed.returncode == 0, completed.stderr
    assert "check-fleet-launch" in completed.stdout.split()
