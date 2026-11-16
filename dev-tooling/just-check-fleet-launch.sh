#!/usr/bin/env bash
# Run shell lint and the hermetic fleet-launch harness.  The harness is the
# behavioural gate: a syntax check cannot detect a dropped launch condition.
set -euo pipefail

if [ "$#" -gt 1 ]; then
    echo "usage: just-check-fleet-launch.sh [scenario297]" >&2
    exit 2
fi

# The Scenario 297 slice runs the harness cases alone, so its verdict reflects
# harness behaviour rather than time spent linting. The aggregate target still
# lints every fleet-launch script before it runs the full harness.
if [ "$#" -eq 0 ]; then
    mapfile -t shell_scripts < <(git ls-files -z 'fleet-launch/*.sh' 'fleet-launch/**/*.sh' | tr '\0' '\n')

    if [ "${#shell_scripts[@]}" -eq 0 ]; then
        echo "check-fleet-launch: no tracked shell script found under fleet-launch/" >&2
        exit 1
    fi

    if command -v shellcheck >/dev/null 2>&1; then
        shellcheck --severity=warning "${shell_scripts[@]}"
        printf 'check-fleet-launch: shellcheck clean over %d shell scripts under fleet-launch/\n' \
            "${#shell_scripts[@]}"
    else
        echo "WARNING: shellcheck not found; skipping shell lint (the hermetic harness still runs)" >&2
    fi
fi

# The harness runs under a NON-REAPING subreaper: adopted orphans stay zombies, exactly as under a
# CI container's PID 1, so a launcher that leaves a killed drive to be reaped by init fails here
# too instead of only in CI (Scenario 330 cases 20a and 20e, 2026-11-15). Python keeps the role
# because `subprocess.run` waits on its one child and reaps nothing else; a bash subreaper would
# reap adopted children in its SIGCHLD handler and hide the leak.
python3 -I - "$@" <<'PY'
import ctypes
import subprocess
import sys

PR_SET_CHILD_SUBREAPER = 36
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
    print("check-fleet-launch: prctl(PR_SET_CHILD_SUBREAPER) failed; the harness needs Linux", file=sys.stderr)
    sys.exit(2)
sys.exit(subprocess.run(["bash", "fleet-launch/test/run-tests.sh", *sys.argv[1:]], check=False).returncode)
PY
