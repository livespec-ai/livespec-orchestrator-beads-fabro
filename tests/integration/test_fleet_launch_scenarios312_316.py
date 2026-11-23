"""Integration coverage for fleet-launch's Scenario 312 and 316 harness slices."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_HARNESS = _ROOT / "fleet-launch" / "test" / "run-tests.sh"
# A liveness guard for the real shell harness, not a timing assertion.  The
# affected-tests gate may run both slices concurrently on a contended worker.
_HARNESS_HANG_GUARD_SECONDS = 600


def _slice(name: str, *, environment: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["bash", str(_HARNESS), name],
        cwd=_ROOT,
        capture_output=True,
        check=False,
        env={**os.environ, **(environment or {})},
        text=True,
        timeout=_HARNESS_HANG_GUARD_SECONDS,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output
    assert "0 failed" in output, output
    return output


def test_scenario312_terminal_exit_ticket_and_stall_paths() -> None:
    """Run the committed launcher harness through all four Scenario 312 Thens."""
    output = _slice(
        "scenario312",
        environment={
            "HARNESS_SIGNAL_SUBSTITUTION_ATTEMPTS": "1",
            "HARNESS_SIGNAL_HOLD_ATTEMPTS": "1",
            "HARNESS_RESUME_INT_HOLD_ATTEMPTS": "1",
        },
    )
    for assertion in (
        "impl launcher yielding on a repository hold: a TERM leaves one last terminal line",
        "impl launcher yielding on a repository hold: the dropped ticket is reported in one ledger comment",
        "a ready-set refusal that clears within the retry bound keeps the ticket, holds no mutex or marker, and launches",
        "a ready-set refusal that outlasts the retry bound ends after exactly the bound with a terminal line",
        "the persistent ready-set refusal is recorded in one ledger comment",
        "dead-pid ticket is reported as one stall line naming item, ticket number and pid before it is removed",
    ):
        assert assertion in output, output


def test_scenario316_repository_hold_scope_and_launch_point() -> None:
    """Run the committed launcher harness through all three Scenario 316 Thens."""
    output = _slice("scenario316")
    for assertion in (
        "a dispatch-scoped hold keeps the impl ticket, lets resume launch, and logs its scope",
        "a no-kinds repository hold fails closed for both launch kinds",
        "a hold created during the mutex wait releases the mutex and marker without driving",
    ):
        assert assertion in output, output


def test_scenario307_canary_hold_releases_a_differently_registered_build() -> None:
    """A build-scoped canary hold does not stop a target using another build."""
    output = _slice("scenario307")

    assert (
        "a canary hold naming another build lets a differently registered target launch" in output
    ), output
