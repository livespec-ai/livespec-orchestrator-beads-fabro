"""A failed ending is preserved unless a needs-human ref already holds its work (bd-ib-nckst7.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_ref_work import (
    needs_human_ref_holds_work,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_base import SOURCE_STAGE
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    PRESERVED_TREE_STAGE,
)

from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_preserved_tree_escalation import (
    _BASE,  # pyright: ignore[reportPrivateUsage]
    _ITEM,  # pyright: ignore[reportPrivateUsage]
    _RUN,  # pyright: ignore[reportPrivateUsage]
    _preserved,  # pyright: ignore[reportPrivateUsage]
    _Runner,  # pyright: ignore[reportPrivateUsage]
)

_DISPATCH = "01DISPATCHID"
_REF = f"refs/heads/needs-human/{_DISPATCH}"
_COMMIT_FAILED = "commit_green failed: the Red lap could not be committed"


@dataclass(kw_only=True)
class _GitRunner:
    """A scripted git: the ref listing, the fetch, and the tree each revision names."""

    listing: CommandResult = field(
        default_factory=lambda: CommandResult(exit_code=0, stdout="", stderr="")
    )
    fetch_exit: int = 0
    trees: dict[str, str] = field(default_factory=dict[str, str])
    argvs: list[list[str]] = field(default_factory=list[list[str]])

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.argvs.append(argv)
        if argv[:2] == ["git", "ls-remote"]:
            return self.listing
        if argv[:2] == ["git", "fetch"]:
            return CommandResult(exit_code=self.fetch_exit, stdout="", stderr="")
        revision = argv[-1].removesuffix("^{tree}")
        tree = self.trees.get(revision)
        if tree is None:
            return CommandResult(exit_code=128, stdout="", stderr="unknown revision")
        return CommandResult(exit_code=0, stdout=f"{tree}\n", stderr="")


def _listing(*refs: str) -> CommandResult:
    return CommandResult(
        exit_code=0, stdout="".join(f"{'a' * 40}\t{ref}\n" for ref in refs), stderr=""
    )


def _holds(runner: _GitRunner, *, dispatch_id: str | None = _DISPATCH, base: str | None = _BASE):
    return needs_human_ref_holds_work(
        runner=runner, repo=Path(), dispatch_id=dispatch_id, base_commit=base
    )


def test_a_run_with_no_dispatch_id_cannot_say_whether_a_ref_holds_its_work() -> None:
    assert _holds(_GitRunner(), dispatch_id=None) is None


def test_a_ref_listing_that_cannot_be_taken_is_unknown_never_absent() -> None:
    runner = _GitRunner(listing=CommandResult(exit_code=128, stdout="", stderr="no route"))
    assert _holds(runner) is None


def test_an_origin_with_no_needs_human_ref_for_the_dispatch_holds_no_work() -> None:
    runner = _GitRunner()
    assert _holds(runner) is False
    listed = runner.argvs[0]
    assert f"refs/heads/needs-human/{_DISPATCH}" in listed
    assert f"refs/heads/needs-human/{_DISPATCH}-*" in listed


def test_a_ref_that_cannot_be_compared_with_an_unknown_base_is_unknown() -> None:
    assert _holds(_GitRunner(listing=_listing(_REF)), base=None) is None


def test_a_base_whose_tree_cannot_be_read_is_unknown() -> None:
    assert _holds(_GitRunner(listing=_listing(_REF))) is None


def test_a_ref_that_cannot_be_fetched_is_unknown() -> None:
    runner = _GitRunner(listing=_listing(_REF), fetch_exit=1, trees={_BASE: "t-base"})
    assert _holds(runner) is None


def test_a_fetched_tip_whose_tree_cannot_be_read_is_unknown() -> None:
    assert _holds(_GitRunner(listing=_listing(_REF), trees={_BASE: "t-base"})) is None


def test_a_ref_whose_tree_differs_from_the_base_holds_the_run_s_work() -> None:
    runner = _GitRunner(listing=_listing(_REF), trees={_BASE: "t-base", "FETCH_HEAD": "t-work"})
    assert _holds(runner) is True


def test_a_ref_whose_tree_equals_the_base_carries_no_work() -> None:
    runner = _GitRunner(
        listing=_listing(_REF, f"{_REF}-lap1"), trees={_BASE: "t-base", "FETCH_HEAD": "t-base"}
    )
    assert _holds(runner) is False


@dataclass(kw_only=True)
class _FailedRunRunner(_Runner):
    """The escalation runner, answering the git reads a failed ending now makes."""

    git: _GitRunner = field(default_factory=_GitRunner)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        if argv[0] == "git":
            return self.git.run(
                argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env, stdin=stdin
            )
        return super().run(
            argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env, stdin=stdin
        )


def _failed_outcome() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM,
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=_COMMIT_FAILED,
        fabro_run_id=_RUN,
        fabro_failure_cause=_COMMIT_FAILED,
    )


_STAMP: dict[str, object] = {
    "stage": "dispatch-run-stamp",
    "run_id": _RUN,
    "dispatch_id": _DISPATCH,
}
_SOURCE: dict[str, object] = {
    "stage": SOURCE_STAGE,
    "work_item_id": _ITEM,
    "staged_at": _BASE,
}


def test_a_run_failed_at_commit_green_with_no_needs_human_ref_is_published(
    tmp_path: Path,
) -> None:
    # The measured shape of run 01M7KR00K1FP: failed outside an engine checkpoint,
    # committed work, no needs-human ref on origin.
    journal, _, transport, bodies = _preserved(
        tmp_path=tmp_path,
        runner=_FailedRunRunner(),
        outcome=_failed_outcome(),
        journal_records=(_SOURCE, _STAMP),
    )
    assert transport.urls, "the failed ending's tree was never read"
    assert journal.row(stage=PRESERVED_TREE_STAGE) is not None
    assert len(bodies) == 1


def test_a_run_failed_with_a_needs_human_ref_holding_its_work_is_not_published_again(
    tmp_path: Path,
) -> None:
    git = _GitRunner(listing=_listing(_REF), trees={_BASE: "t-base", "FETCH_HEAD": "t-work"})
    journal, _, transport, bodies = _preserved(
        tmp_path=tmp_path,
        runner=_FailedRunRunner(git=git),
        outcome=_failed_outcome(),
        journal_records=(_SOURCE, _STAMP),
    )
    assert transport.urls == []
    assert journal.row(stage=PRESERVED_TREE_STAGE) is None
    assert bodies == []


def test_a_run_whose_stamp_names_no_dispatch_id_is_still_published(tmp_path: Path) -> None:
    # No dispatch id means no ref can be named for the run, so a ref holding its
    # work is unprovable and the publication is attempted rather than suppressed.
    stamp_without_id: dict[str, object] = {"stage": "dispatch-run-stamp", "run_id": _RUN}
    other_run: dict[str, object] = {
        "stage": "dispatch-run-stamp",
        "run_id": "another-run",
        "dispatch_id": "NOT-THIS-RUN",
    }
    git = _GitRunner(listing=_listing(_REF), trees={_BASE: "t-base", "FETCH_HEAD": "t-work"})
    journal, _, transport, _ = _preserved(
        tmp_path=tmp_path,
        runner=_FailedRunRunner(git=git),
        outcome=_failed_outcome(),
        journal_records=(_SOURCE, other_run, stamp_without_id),
    )
    assert transport.urls, "the publication was suppressed without a dispatch id"
    assert journal.row(stage=PRESERVED_TREE_STAGE) is not None
