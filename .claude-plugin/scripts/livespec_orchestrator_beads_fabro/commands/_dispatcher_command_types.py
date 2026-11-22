"""The subprocess seam's two types, kept free of every other Dispatcher module.

`CommandResult` and `CommandRunner` live here, rather than in
`_dispatcher_engine_types`, so a program that needs only the seam (the
publication broker the helper bundle ships into a sandbox) imports this one
module instead of the engine's whole transitive closure. `_dispatcher_engine_types`
re-exports both names, so every existing importer is unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__: list[str] = ["CommandResult", "CommandRunner"]


@dataclass(frozen=True, kw_only=True)
class CommandResult:
    """Outcome of one subprocess invocation across the runner seam."""

    exit_code: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    """The single subprocess seam the engine executes argvs through."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        """Run argv in cwd, returning the completed result (never raising
        for non-zero exits; timeouts surface as non-zero results).

        `env` is the child's environment DELTA against this process, not the
        whole environment: a string value SETS the variable and a `None` value
        REMOVES it. The removal arm exists because a caller cannot express
        "without this variable" through a mapping that is merged over
        `os.environ` -- the post-merge janitor needs exactly that, and doing it
        by mutating `os.environ` around the call would reach every concurrent
        dispatch thread in the same process.
        """
        ...
