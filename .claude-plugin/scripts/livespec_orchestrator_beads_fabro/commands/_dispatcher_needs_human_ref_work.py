"""Whether a needs-human ref on origin holds a run's work (bd-ib-nckst7.1).

Answers one question for the failed-ending preservation: does origin already
carry the run's work on a needs-human ref named for the run's dispatch id, so
that publishing a second preservation ref would be redundant?

The answer is THREE-VALUED and only True suppresses. None is a listing or a
comparison that could not be taken, and the ratified clause makes it behave like
False: a duplicate preservation is recoverable, a missed one is not. A ref
carries NO WORK when its tip tree equals its base commit's tree, and such a ref
does not suppress.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_refs import refs_by_name

__all__: list[str] = ["needs_human_ref_holds_work"]

_REMOTE = "origin"
_GIT_TIMEOUT_SECONDS = 120.0
_NEEDS_HUMAN_PREFIX = "refs/heads/needs-human/"


def needs_human_ref_holds_work(
    *, runner: CommandRunner, repo: Path, dispatch_id: str | None, base_commit: str | None
) -> bool | None:
    """True when a needs-human ref of the dispatch carries work; None when unknowable."""
    if dispatch_id is None:
        return None
    refs = _listed_refs(runner=runner, repo=repo, dispatch_id=dispatch_id)
    if refs is None:
        return None
    if not refs:
        return False
    base_tree = (
        None if base_commit is None else _tree(runner=runner, repo=repo, revision=base_commit)
    )
    if base_tree is None:
        return None
    verdicts = [
        _carries_work(runner=runner, repo=repo, ref=ref, base_tree=base_tree) for ref in refs
    ]
    if any(verdict is True for verdict in verdicts):
        return True
    return None if any(verdict is None for verdict in verdicts) else False


def _listed_refs(*, runner: CommandRunner, repo: Path, dispatch_id: str) -> list[str] | None:
    """The dispatch's needs-human refs on origin, or None for a listing that failed."""
    listing = runner.run(
        argv=[
            "git",
            "ls-remote",
            _REMOTE,
            f"{_NEEDS_HUMAN_PREFIX}{dispatch_id}",
            f"{_NEEDS_HUMAN_PREFIX}{dispatch_id}-*",
        ],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if listing.exit_code != 0:
        return None
    return sorted(refs_by_name(stdout=listing.stdout))


def _carries_work(*, runner: CommandRunner, repo: Path, ref: str, base_tree: str) -> bool | None:
    """Whether the ref's tip tree differs from the base tree; None when unreadable."""
    fetched = runner.run(
        argv=["git", "fetch", "--quiet", _REMOTE, ref],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if fetched.exit_code != 0:
        return None
    tip_tree = _tree(runner=runner, repo=repo, revision="FETCH_HEAD")
    return None if tip_tree is None else tip_tree != base_tree


def _tree(*, runner: CommandRunner, repo: Path, revision: str) -> str | None:
    """The tree id of `revision`, or None when git cannot name one."""
    read = runner.run(
        argv=["git", "rev-parse", f"{revision}^{{tree}}"],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    tree = read.stdout.strip()
    return tree if read.exit_code == 0 and tree else None
