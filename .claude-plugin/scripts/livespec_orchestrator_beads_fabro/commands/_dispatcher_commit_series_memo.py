"""One forge read of a dispatch's commit series, shared by its two derivations.

Calibration derives the TDD signals and the completed-cycle measurements from
the SAME pull-request commit series, and each derivation asks the forge for it
through its own request. Two requests could answer differently while a dispatch
is still publishing, leaving the two derivations describing different series,
and each one is a forge call spent at a post-verdict stage. This runner answers
the commit-series request once, failure included, and passes every other request
through unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_command_types import (
    CommandResult,
    CommandRunner,
)

__all__: list[str] = ["MemoizedSeriesRunner"]


@dataclass(kw_only=True)
class MemoizedSeriesRunner:
    """A `CommandRunner` that remembers its answer to each commit-series request."""

    inner: CommandRunner
    answers: dict[tuple[str, ...], CommandResult] = field(default_factory=dict)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        """Answer a repeated commit-series request from memory, else defer."""
        if argv[:3] != ["gh", "pr", "view"] or argv[-2:] != ["--json", "commits"]:
            return self.inner.run(
                argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env, stdin=stdin
            )
        key = tuple(argv)
        if key not in self.answers:
            self.answers[key] = self.inner.run(
                argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env, stdin=stdin
            )
        return self.answers[key]
