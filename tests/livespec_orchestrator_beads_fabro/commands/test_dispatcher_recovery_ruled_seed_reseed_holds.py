"""Every fact the stale-seed read cannot take holds and names itself (bd-ib-nlofrn).

A ruled seed is reseeded when it is behind the default branch. A branch that cannot be
resolved, a tip or an ancestry that cannot be read, and a reseed the forge refuses are
each a hold naming the measurement; none is read as "not stale", which would lay the
seed's whole tree over the tip again.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_recovery_ruled_seed as ruled
from livespec_orchestrator_beads_fabro.commands._dispatcher_diff_apply_reseed_publish import (
    ReseedRefusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    RecoveryHold,
    RecoverySeed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import SeedRuling

_ITEM = "bd-ib-nlofrn"
_SEED_REF = "refs/heads/needs-human/abc"
_SEED = "a1" * 20
_TIP = "f0" * 20


class _Origin:
    """Answers each read by argv prefix; `broken` names the one prefix that fails."""

    def __init__(self, *, broken: tuple[str, ...] = (), ancestor: bool = False) -> None:
        self.broken = broken
        self.ancestor = ancestor

    def run(self, **kwargs: object) -> CommandResult:
        argv = [str(one) for one in kwargs["argv"]]  # type: ignore[attr-defined]
        if self.broken and tuple(argv[: len(self.broken)]) == self.broken:
            return CommandResult(exit_code=128, stdout="", stderr="fatal: unreachable")
        if argv[:3] == ["git", "symbolic-ref", "--short"]:
            return CommandResult(exit_code=0, stdout="origin/master\n", stderr="")
        if argv[:3] == ["git", "ls-remote", "origin"]:
            ref = argv[3]
            commit = _TIP if ref == "refs/heads/master" else _SEED
            return CommandResult(exit_code=0, stdout=f"{commit}\t{ref}\n", stderr="")
        if argv[:3] == ["git", "merge-base", "--is-ancestor"]:
            return CommandResult(exit_code=0 if self.ancestor else 1, stdout="", stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")


def _ruled(*, origin: _Origin, tmp_path: Path) -> RecoverySeed | RecoveryHold:
    return ruled.ruled_seed(
        runner=origin,  # type: ignore[arg-type]
        repo=tmp_path,
        work_item_id=_ITEM,
        ruling=SeedRuling(
            work_item_id=_ITEM,
            preservation_ref=_SEED_REF,
            commit_sha=_SEED,
            invoker="coordinator",
            reason="the ruled tree carries the checked work",
            instant="2026-11-18T22:00:00Z",
        ),
        earlier_run_ids=("run-1",),
    )


def _only_measurement(*, held: RecoverySeed | RecoveryHold) -> tuple[str, str]:
    assert isinstance(held, RecoveryHold)
    (measurement,) = held.measurements
    return measurement.name, measurement.detail


def test_an_unresolvable_default_branch_holds_rather_than_reading_the_seed_as_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ruled, "resolve_default_branch", lambda **_: None)

    name, detail = _only_measurement(held=_ruled(origin=_Origin(), tmp_path=tmp_path))

    assert name == "seed-reseed"
    assert "default branch could not be resolved" in detail


def test_an_unreadable_default_branch_tip_holds(tmp_path: Path) -> None:
    origin = _Origin(broken=("git", "ls-remote", "origin", "refs/heads/master"))

    name, detail = _only_measurement(held=_ruled(origin=origin, tmp_path=tmp_path))

    assert name == "seed-reseed"
    assert "refs/heads/master could not be read" in detail


def test_a_failed_fetch_of_the_seed_and_tip_holds(tmp_path: Path) -> None:
    origin = _Origin(broken=("git", "fetch"))

    name, detail = _only_measurement(held=_ruled(origin=origin, tmp_path=tmp_path))

    assert name == "seed-reseed"
    assert "could not be established" in detail


def test_a_reseed_the_forge_refuses_without_a_conflict_holds_under_the_plain_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ruled,
        "diff_apply_reseed",
        lambda **_: ReseedRefusal(detail="the seed carries no work; nothing was published"),
    )

    name, detail = _only_measurement(held=_ruled(origin=_Origin(), tmp_path=tmp_path))

    assert name == "seed-reseed"
    assert "carries no work" in detail
    assert _SEED_REF in detail
    assert _SEED in detail
