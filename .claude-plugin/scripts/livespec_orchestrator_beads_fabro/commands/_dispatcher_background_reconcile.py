"""Run a loop tick's reconciliation pass beside the launch instead of ahead of it.

The reconciliation pass at the head of a `loop` tick surveys stranded claims, and
a claim whose pull request merged is completed by `reconcile-merged`, which runs
that item's post-merge janitor: a gate Job on the shared gates queue, about ten
minutes (measured 2026-11-21, bd-ib-4ifdud). Run inline, one item's acceptance
work held every other item's launch behind it, although a launch needs no result
the pass produces.

`reconcile_in_background` is the scope the loop command opens around one tick.
Inside it, `run_reconcile` starts the pass on a worker thread and returns, so the
tick selects and launches meanwhile; on leaving the scope the loop waits for the
pass, so it always runs to its recorded verdict before the process exits, and a
failure the pass did not absorb (a bug) is raised there, after the launch, rather
than lost on a thread. Outside the scope, which is every command but `loop`,
`run_reconcile` runs the pass inline exactly as before.

Safety does not rest on ordering: the standalone `reconcile-runs` sweep already
runs concurrently with any dispatch on the host, so the pass is written to
tolerate a launch happening beside it (its claim lane takes the per-item
recovery fence and holds an unattributed claim rather than recovering it).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

__all__: list[str] = [
    "reconcile_in_background",
    "run_reconcile",
]


@dataclass(kw_only=True)
class _Scope:
    pool: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(max_workers=1))
    futures: list[Future[object]] = field(default_factory=list)


_ACTIVE: ContextVar[_Scope | None] = ContextVar("background_reconcile_scope", default=None)


@contextmanager
def reconcile_in_background() -> Iterator[None]:
    """Open the scope; leaving it waits for every pass started inside and raises its failure."""
    scope = _Scope()
    token = _ACTIVE.set(scope)
    try:
        yield
    finally:
        _ACTIVE.reset(token)
        scope.pool.shutdown(wait=True)
        for future in scope.futures:
            _ = future.result()


def run_reconcile(*, run: Callable[[], object]) -> None:
    """Start `run` beside the caller inside a scope; run it inline outside one."""
    scope = _ACTIVE.get()
    if scope is None:
        _ = run()
        return
    scope.futures.append(scope.pool.submit(run))
