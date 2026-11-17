#!/usr/bin/env bash
# Forward launcher stop signals without making Bash parse a trap action.  This
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
        forwarded = False

        def forward(signum: int, _frame: object) -> None:
            nonlocal forwarded
            if forwarded:
                return
            forwarded = True
            name = signal.Signals(signum).name.removeprefix("SIG")
            write_cause(cause_path, name)
            with suppress(ProcessLookupError):
                worker.send_signal(signum)

        for watched in (signal.SIGINT, signal.SIGHUP, signal.SIGTERM):
            signal.signal(watched, forward)

        return_code = worker.wait()
    return return_code if return_code >= 0 else 128 - return_code


raise SystemExit(main(sys.argv))
PY
