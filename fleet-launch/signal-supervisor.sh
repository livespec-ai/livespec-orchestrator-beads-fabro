#!/usr/bin/env bash
# Supervise launcher stop signals without making Bash parse a trap action. This
# stays a shell file so a launcher copied for an on-disk re-exec carries its
# supervisor with it.
export FLEET_LAUNCH_SIGNAL_SUPERVISOR=1
exec python3 - "$@" <<'PY'
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

MINIMUM_ARGUMENTS = 2


def write_cause(path: Path, name: str) -> None:
    """Publish a complete signal cause before the worker can begin cleanup."""
    descriptor = f"signal {name} (this exit was not a run ending)\n".encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, descriptor)
    finally:
        os.close(fd)


def main(argv: list[str]) -> int:
    if len(argv) < MINIMUM_ARGUMENTS:
        print("usage: signal-supervisor.sh <launcher> [args ...]", file=sys.stderr)
        return MINIMUM_ARGUMENTS

    launcher = Path(argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="fleet-launch-signal-") as temporary:
        cause_path = Path(temporary) / "cause"
        environment = os.environ.copy()
        environment["FLEET_LAUNCH_SIGNAL_SUPERVISOR_CHILD"] = "1"
        environment["FLEET_LAUNCH_SIGNAL_CAUSE_FILE"] = str(cause_path)
        worker = subprocess.Popen([launcher, *argv[2:]], env=environment)
        stop_signal: int | None = None

        def forward(signum: int, _frame: object) -> None:
            nonlocal stop_signal
            if stop_signal is not None:
                return
            stop_signal = signum
            name = signal.Signals(signum).name.removeprefix("SIG")
            write_cause(cause_path, name)
            with suppress(ProcessLookupError):
                # Bash can lose INT or HUP while it waits for its short-lived
                # hold-poll child.  The worker's default TERM exit is reliable;
                # its EXIT cleanup reads the original cause above, while this
                # supervisor preserves the caller-visible original status.
                worker.send_signal(signal.SIGTERM)

        for watched in (signal.SIGINT, signal.SIGHUP, signal.SIGTERM):
            signal.signal(watched, forward)

        return_code = worker.wait()
        if stop_signal is not None:
            return 128 + stop_signal
    return return_code if return_code >= 0 else 128 - return_code


raise SystemExit(main(sys.argv))
PY
