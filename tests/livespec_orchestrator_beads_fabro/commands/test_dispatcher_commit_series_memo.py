"""The memoizing runner answers a commit-series request once and defers the rest."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_command_types import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_series_memo import (
    MemoizedSeriesRunner,
)

_SERIES = ["gh", "pr", "view", "7", "--json", "commits"]


@dataclass(kw_only=True)
class _Counting:
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout=f"answer-{len(self.calls)}", stderr="")


def _ask(*, runner: MemoizedSeriesRunner, argv: list[str]) -> CommandResult:
    return runner.run(argv=argv, cwd=Path(), timeout_seconds=1.0)


def test_a_repeated_commit_series_request_is_answered_from_memory() -> None:
    inner = _Counting()
    runner = MemoizedSeriesRunner(inner=inner)

    first = _ask(runner=runner, argv=_SERIES)
    second = _ask(runner=runner, argv=_SERIES)

    assert first == second
    assert inner.calls == [_SERIES]


def test_any_other_request_passes_through_unremembered() -> None:
    inner = _Counting()
    runner = MemoizedSeriesRunner(inner=inner)
    other = ["gh", "pr", "view", "7", "--json", "additions,deletions"]

    first = _ask(runner=runner, argv=other)
    second = _ask(runner=runner, argv=other)

    assert (first.stdout, second.stdout) == ("answer-1", "answer-2")
    assert inner.calls == [other, other]
