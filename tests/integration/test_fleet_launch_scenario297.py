"""Integration coverage for Scenario 297's queued launcher preflight."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK_DRIVER = _REPO_ROOT / "dev-tooling" / "just-check-fleet-launch.sh"
_TARGET_EXTRACTOR = _REPO_ROOT / "dev-tooling" / "aggregate-targets.sh"

# A liveness guard against a hung harness, never a duration budget for its verdict.
_HARNESS_HANG_GUARD_SECONDS = 600

# The startup delay injected into each OLDER dispatch-dual.sh launcher
# (bd-ib-older, bd-ib-stale-older, bd-ib-failing-older). daa36563c removed the
# fixed 10 s preflight budget those three waits had (`wait_for_preflight <item>
# 1 10`), so the delay must exceed 10 s, or the test would still pass with that
# budget back. The younger launchers' old budget was 60 s, which no affordable
# delay exceeds, so they run undelayed; delaying all six by 30 s made this one
# test take about three minutes.
_INJECTED_OLDER_LAUNCHER_DELAY_SECONDS = 11


def _run(
    *, argv: list[str], environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=_HARNESS_HANG_GUARD_SECONDS,
    )


def _last_output(error: subprocess.TimeoutExpired) -> str:
    """Return all output captured before a subprocess stopped making progress."""
    output = (error.stdout, error.stderr)
    return (
        "\n".join(
            chunk.decode(errors="replace") if isinstance(chunk, bytes) else (chunk or "")
            for chunk in output
        ).strip()
        or "<no output captured>"
    )


def test_scenario297_queued_preflight_harness_runs_from_the_check_aggregate() -> None:
    """The shipped check tolerates delayed preflights while proving FIFO behavior."""
    temporary_directory = TemporaryDirectory()
    delayed_launcher_startup = Path(temporary_directory.name) / "delayed-launcher-startup.sh"
    older_launcher_delay = (
        f'case "${{0##*/}}:${{1:-}}" in dispatch-dual.sh:*-older) '
        f"sleep {_INJECTED_OLDER_LAUNCHER_DELAY_SECONDS} ;; esac\n"
    )
    _ = delayed_launcher_startup.write_text(older_launcher_delay, encoding="utf-8")
    environment = {**os.environ, "BASH_ENV": str(delayed_launcher_startup)}

    targets = _run(argv=["bash", str(_TARGET_EXTRACTOR)], environment=environment)
    assert targets.returncode == 0, targets.stderr
    assert "check-fleet-launch" in targets.stdout.split()

    try:
        checked = _run(argv=["bash", str(_CHECK_DRIVER), "scenario297"], environment=environment)
    except subprocess.TimeoutExpired as error:
        pytest.fail(
            "".join(
                (
                    "Scenario 297 harness HUNG (it did not finish) after ",
                    f"_HARNESS_HANG_GUARD_SECONDS={_HARNESS_HANG_GUARD_SECONDS}; ",
                    f"harness last output:\n{_last_output(error)}",
                )
            )
        )
    combined = checked.stdout + checked.stderr
    assert checked.returncode == 0, combined
    assert "shellcheck" not in combined.lower(), combined
    for assertion in (
        "the younger queued launcher starts its preflight before the older binds",
        "queued launchers bind in FIFO ticket order after their preflights",
        "a fresh queued preflight pass is reused when the younger launcher reaches the head",
        "a stale queued pass is re-run at the FIFO head before binding",
        "a failed queued preflight exits 4, drops its ticket, and never takes the mutex",
        "the mutex is released before either drive --action impl starts",
    ):
        assert assertion in combined, combined
    assert "--- 1. reads a stub factory board" not in combined, combined
    assert "0 failed" in combined, combined


def _run_stale_pass_ordering(
    *, preflights: list[tuple[int, str]], mutex_holds: list[tuple[int, str]]
) -> int:
    """Run the harness's real stale-pass ordering helpers against scripted stub logs."""
    harness = _REPO_ROOT / "fleet-launch" / "test" / "run-tests.sh"
    preflight_lines = "".join(f"{stamp} {item}\n" for stamp, item in preflights)
    mutex_lines = "".join(f"{stamp} {item}\n" for stamp, item in mutex_holds)
    script = f"""
set -u
eval "$(sed -n '/^preflight_between() {{/,/^}}/p' '{harness}')"
eval "$(sed -n '/^first_mutex_ns() {{/,/^}}/p' '{harness}')"
PREFLIGHT_LOG=$(mktemp)
MUTEX_OBSERVATION_LOG=$(mktemp)
printf '%s' '{preflight_lines}' > "$PREFLIGHT_LOG"
printf '%s' '{mutex_lines}' > "$MUTEX_OBSERVATION_LOG"
release_ns=1000
mutex_ns=$(first_mutex_ns the-younger)
[ -n "$mutex_ns" ] && preflight_between the-younger "$release_ns" "$mutex_ns"
"""
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, check=False, text=True, timeout=60
    ).returncode


def test_scenario297_stale_queued_preflight_is_ordered_on_events_not_counted() -> None:
    """A preflight between the older release and the younger mutex hold is what the case needs."""
    # The older launcher held the mutex first, then released it; the younger took it at 3000.
    holds = [(1900, "the-older"), (3000, "the-younger"), (3100, "the-younger")]
    queued = (500, "the-younger")

    # One re-run, and several head polls, both satisfy the ordering.
    assert (
        _run_stale_pass_ordering(preflights=[queued, (1500, "the-younger")], mutex_holds=holds) == 0
    )
    extra_polls = [queued, (1100, "the-younger"), (1200, "the-younger"), (1300, "the-younger")]
    assert _run_stale_pass_ordering(preflights=extra_polls, mutex_holds=holds) == 0

    # Only the queued pass (before the release): the head took the mutex without re-running.
    assert _run_stale_pass_ordering(preflights=[queued], mutex_holds=holds) != 0
    # A preflight of another item is not the younger launcher's head re-run.
    other_item = [queued, (1500, "the-older")]
    assert _run_stale_pass_ordering(preflights=other_item, mutex_holds=holds) != 0
    # A preflight stamped once the younger launcher already held the mutex came too late, as did
    # one stamped at the very instant the stub saw the mutex held (a preflight run under it).
    late = [queued, (3050, "the-younger")]
    assert _run_stale_pass_ordering(preflights=late, mutex_holds=holds) != 0
    under_mutex = [queued, (3000, "the-younger")]
    assert _run_stale_pass_ordering(preflights=under_mutex, mutex_holds=holds) != 0
    # A younger launcher that was never seen holding the mutex has nothing to order against.
    assert (
        _run_stale_pass_ordering(
            preflights=[queued, (1500, "the-younger")], mutex_holds=[(1900, "the-older")]
        )
        != 0
    )


def test_scenario297_stale_case_checks_the_ordering_not_an_exact_count() -> None:
    """The stale-pass case decides on the mutex ordering helper, with no preflight-count verdict."""
    harness = (_REPO_ROOT / "fleet-launch" / "test" / "run-tests.sh").read_text(encoding="utf-8")
    stale_case = harness.split(
        'scenario "7. re-runs a stale queued preflight at the FIFO head"', maxsplit=1
    )[1].split('scenario "8. drops a ticket when its queued preflight fails"', maxsplit=1)[0]

    assert 'preflight_between bd-ib-stale-younger "$release_ns" "$younger_mutex_ns"' in stale_case
    assert "first_drive_ns" not in stale_case
    assert 'preflight_count bd-ib-stale-younger)" =' not in stale_case
    assert 'preflight_count bd-ib-stale-younger)" -ge' not in stale_case


def _run_wait_for_preflight(
    *, launcher_exits_during_first_read: bool
) -> subprocess.CompletedProcess[str]:
    """Run the harness's real wait_for_preflight against a scripted preflight record."""
    harness = _REPO_ROOT / "fleet-launch" / "test" / "run-tests.sh"
    launcher = (
        "sleep 30 & pid=$!" if launcher_exits_during_first_read else "true & pid=$!; sleep 0.3"
    )
    script = f"""
set -u
eval "$(sed -n '/^wait_for_preflight() {{/,/^}}/p' '{harness}')"
HARNESS_POLL_S=0.01
HARNESS_PREFLIGHT_HANG_GUARD_S=30
marker=$(mktemp -u)
preflight_count() {{
    if [ "{int(launcher_exits_during_first_read)}" = 1 ] && [ -e "$marker" ]; then echo 1; return; fi
    if [ "{int(launcher_exits_during_first_read)}" = 1 ]; then
        : > "$marker"
        kill "$pid"
        sleep 0.3
    fi
    echo 0
}}
log=$(mktemp)
echo 'launcher log line' > "$log"
{launcher}
wait_for_preflight the-case younger "$pid" "$log" the-item 1
rc=$?
if [ "$rc" -ne 0 ]; then echo "$PREFLIGHT_FAILURE_DETAIL"; fi
kill "$pid" 2>/dev/null
exit "$rc"
"""
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, check=False, text=True, timeout=60
    )


def test_scenario297_preflight_wait_accepts_a_launcher_that_preflighted_then_exited() -> None:
    """A launcher that records its preflight and exits mid-poll did reach its preflight."""
    reached_then_exited = _run_wait_for_preflight(launcher_exits_during_first_read=True)
    assert reached_then_exited.returncode == 0, reached_then_exited.stdout

    exited_without_preflight = _run_wait_for_preflight(launcher_exits_during_first_read=False)
    assert exited_without_preflight.returncode != 0
    for needle in (
        "case=the-case",
        "launcher=younger",
        "did not reach preflight",
        "launcher log line",
    ):
        assert needle in exited_without_preflight.stdout, exited_without_preflight.stdout


def test_scenario297_timeout_reports_a_hung_harness_with_its_last_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard reports a hang and diagnostics; it is never a speed verdict."""
    results: list[subprocess.CompletedProcess[str] | subprocess.TimeoutExpired] = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="check-fleet-launch\n", stderr=""
        ),
        subprocess.TimeoutExpired(
            cmd="scenario297",
            timeout=_HARNESS_HANG_GUARD_SECONDS,
            output="queued preflight still running",
            stderr=b"last harness stderr",
        ),
    ]

    def timed_run(
        *, argv: list[str], environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        del argv, environment
        result = results.pop(0)
        if isinstance(result, subprocess.TimeoutExpired):
            raise result
        return result

    monkeypatch.setattr(sys.modules[__name__], "_run", timed_run)

    with pytest.raises(pytest.fail.Exception) as failure:
        test_scenario297_queued_preflight_harness_runs_from_the_check_aggregate()

    message = str(failure.value)
    assert "Scenario 297 harness HUNG (it did not finish)" in message
    assert f"_HARNESS_HANG_GUARD_SECONDS={_HARNESS_HANG_GUARD_SECONDS}" in message
    assert "harness last output:\nqueued preflight still running\nlast harness stderr" in message
