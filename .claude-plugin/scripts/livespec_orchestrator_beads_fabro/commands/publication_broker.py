"""The executable entry point of the credential-owning publication broker.

``_dispatcher_publication_broker_serve.main`` takes its runner, request stream and
reply stream as arguments so a test can drive it.  This module is the one place those
three are bound to the real thing: the production command runner, this process's own
standard input and its own standard output.  Launching ``bin/publication_broker.py``, the
shebang wrapper that returns this ``main``'s exit code, therefore starts a broker as a
process of its own.

The workflow launches that process beside an agent node, under a user the agent does
not run as, and hands it the launch file and the credential file by argv.  The
credential is read from the file inside this process and reaches only the one forge
child a validated request produces, so the agent stage's environment, files and
processes never hold it.  Nothing here parses an argument or selects a stage; the
serve module owns both.
"""

from __future__ import annotations

import sys
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_broker_serve import (
    main as serve,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner

__all__: list[str] = ["main"]


def main(*, argv: list[str] | None = None) -> int:
    """Serve this process's standard input as broker requests until it closes."""
    return serve(
        argv=sys.argv[1:] if argv is None else argv,
        request_lines=sys.stdin,
        runner=ShellCommandRunner(),
        cwd=Path.cwd(),
        stdout=sys.stdout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
