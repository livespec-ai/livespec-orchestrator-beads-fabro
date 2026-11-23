"""End-to-end fixture coverage for completed-cycle measurements."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_probe import (
    UNOBSERVED_COUNTING,
    UNOBSERVED_SOURCE_TREE,
    UNOBSERVED_TIMESTAMPS,
    CycleSource,
    ProvenanceCommit,
    gather_completed_cycle_series,
    parse_provenance_commits,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import WorkItem

_DISPATCH_ID = "5fe8e3dfbfd54faa979e85364d8e9863"
_SOURCE_TREE = "src/pkg"
_PYPROJECT = '[tool.livespec_dev_tooling]\nsource_trees = ["src/pkg"]\n'
_probe = import_module("livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_probe")
_PRIVATE = "_"
_blob = getattr(_probe, _PRIVATE + "blob")
_changed_paths = getattr(_probe, _PRIVATE + "changed_paths")
_dispatch_commits = getattr(_probe, _PRIVATE + "dispatch_commits")
_measure = getattr(_probe, _PRIVATE + "measure")
_verified_pairs = getattr(_probe, _PRIVATE + "verified_pairs")


@dataclass(kw_only=True)
class _ForgeRunner:
    """Answer the one forge request while git reads use the real fixture repo."""

    stdout: str

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        assert argv == ["gh", "pr", "view", "4242", "--json", "commits"]
        assert cwd.is_dir()
        assert timeout_seconds > 0
        assert env is None
        assert stdin is None
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-d3pdrv",
        type="task",
        status="active",
        title="Measure each completed cycle",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-23T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_criteria="- One assertion.\n- Another assertion.\n",
    )


def _git(*, repo: Path, argv: list[str]) -> str:
    return subprocess.run(
        ["git", *argv], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(*, tmp_path: Path, declaration: bytes | None = _PYPROJECT.encode()) -> Path:
    repo = tmp_path / "fixture"
    repo.mkdir(parents=True)
    _ = _git(repo=repo, argv=["init", "--initial-branch", "work"])
    _ = _git(repo=repo, argv=["config", "user.email", "fixture@example.com"])
    _ = _git(repo=repo, argv=["config", "user.name", "Fixture"])
    if declaration is not None:
        _ = (repo / "pyproject.toml").write_bytes(declaration)
    source = repo / _SOURCE_TREE
    source.mkdir(parents=True)
    _ = (source / "thing.py").write_text("value = 1\n", encoding="utf-8")
    _ = _git(repo=repo, argv=["add", "-A"])
    _ = _git(repo=repo, argv=["commit", "-m", "chore: seed"])
    return repo


def _commit_cycle(
    *, repo: Path, source: str, red_at: str, green_at: str, checksum: str, path: str = "thing.py"
) -> str:
    product = repo / _SOURCE_TREE / path
    product.parent.mkdir(parents=True, exist_ok=True)
    _ = product.write_text(source, encoding="utf-8")
    (repo / "tests").mkdir(exist_ok=True)
    _ = (repo / "tests" / f"test_{checksum}.py").write_text("assert True\n", encoding="utf-8")
    _ = _git(repo=repo, argv=["add", "-A"])
    message = "\n".join(
        (
            "feat(pkg): one assertion",
            "",
            f"TDD-Red-Test-File-Checksum: {checksum}",
            f"TDD-Red-Captured-At: {red_at}",
            f"Factory-Run-Id: {_DISPATCH_ID}",
            f"TDD-Green-Verified-At: {green_at}",
        )
    )
    _ = _git(repo=repo, argv=["commit", "-m", message])
    return _git(repo=repo, argv=["rev-parse", "HEAD"])


def _payload(*, repo: Path, shas: list[str]) -> str:
    return json.dumps(
        {
            "commits": [
                {
                    "oid": sha,
                    "messageHeadline": _git(repo=repo, argv=["log", "-1", "--format=%s", sha]),
                    "messageBody": _git(repo=repo, argv=["log", "-1", "--format=%b", sha]),
                }
                for sha in shas
            ]
        }
    )


def _series(*, repo: Path, shas: list[str]):
    return gather_completed_cycle_series(
        repo=repo,
        item=_item(),
        pr_number=4242,
        dispatch_id=_DISPATCH_ID,
        runner=_ForgeRunner(stdout=_payload(repo=repo, shas=shas)),
    )


def test_each_observable_cycle_retains_ordinal_identity_size_time_and_assertions(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    first = _commit_cycle(
        repo=repo,
        source="value = 2\n",
        red_at="2026-11-23T10:00:00Z",
        green_at="2026-11-23T10:04:10Z",
        checksum="first",
    )
    second = _commit_cycle(
        repo=repo,
        source="value = 2\nother = 3\n",
        red_at="2026-11-23T11:00:00Z",
        green_at="2026-11-23T11:01:00Z",
        checksum="second",
    )

    series = _series(repo=repo, shas=[second, first])

    assert series.completed_count == 2
    assert series.assertion_count == 2
    assert [(cycle.ordinal, cycle.pair_id, cycle.commit) for cycle in series.cycles] == [
        (1, "first@2026-11-23T10:00:00Z", first),
        (2, "second@2026-11-23T11:00:00Z", second),
    ]
    assert [cycle.product_lloc_changed for cycle in series.cycles] == [2, 1]
    assert [cycle.elapsed_seconds for cycle in series.cycles] == [250, 60]


def test_unreadable_blob_keeps_the_pair_but_marks_its_size_unobserved(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    sha = _commit_cycle(
        repo=repo,
        source="value = 2\n",
        red_at="2026-11-23T10:00:00Z",
        green_at="2026-11-23T10:01:00Z",
        checksum="missing-blob",
    )
    blob = _git(repo=repo, argv=["rev-parse", f"{sha}:{_SOURCE_TREE}/thing.py"])
    (repo / ".git" / "objects" / blob[:2] / blob[2:]).unlink()

    series = _series(repo=repo, shas=[sha])

    assert series.completed_count == 1
    assert series.cycles[0].product_lloc_changed is None
    assert series.cycles[0].product_lloc_unobserved_reason == UNOBSERVED_SOURCE_TREE


def test_missing_invalid_or_non_utf8_source_declarations_are_unobserved(tmp_path: Path) -> None:
    declarations = (None, b"[tool.livespec_dev_tooling\n", b"\xff\xfe")
    for index, declaration in enumerate(declarations):
        repo = _repo(tmp_path=tmp_path / str(index), declaration=declaration)
        sha = _commit_cycle(
            repo=repo,
            source="value = 2\n",
            red_at="2026-11-23T10:00:00Z",
            green_at="2026-11-23T10:01:00Z",
            checksum=f"declaration-{index}",
        )

        series = _series(repo=repo, shas=[sha])

        assert series.completed_count == 1
        assert series.cycles[0].product_lloc_changed is None
        assert series.cycles[0].product_lloc_unobserved_reason == UNOBSERVED_COUNTING


def test_invalid_or_reversed_provenance_times_are_unobserved_without_losing_pair(
    tmp_path: Path,
) -> None:
    time_pairs = (
        ("not-a-time", "2026-11-23T10:01:00Z"),
        ("2026-11-23T10:01:00Z", "2026-11-23T10:00:00Z"),
    )
    for index, times in enumerate(time_pairs):
        repo = _repo(tmp_path=tmp_path / str(index))
        sha = _commit_cycle(
            repo=repo,
            source="value = 2\n",
            red_at=times[0],
            green_at=times[1],
            checksum=f"time-{index}",
        )

        series = _series(repo=repo, shas=[sha])

        assert series.completed_count == 1
        assert series.cycles[0].elapsed_seconds is None
        assert series.cycles[0].elapsed_unobserved_reason == UNOBSERVED_TIMESTAMPS


@dataclass(kw_only=True)
class _Replies:
    replies: list[CommandResult]

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        assert argv
        assert cwd.is_dir()
        assert timeout_seconds > 0
        assert env is None
        assert stdin is None
        return self.replies.pop(0)


def test_unreadable_provenance_and_malformed_commit_entries_fail_soft(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    unreadable = gather_completed_cycle_series(
        repo=repo,
        item=_item(),
        pr_number=None,
        dispatch_id=_DISPATCH_ID,
        runner=_ForgeRunner(stdout="{}"),
    )
    assert unreadable.completed_count is None
    assert parse_provenance_commits(stdout="not json") is None
    assert parse_provenance_commits(stdout="[]") is None
    assert parse_provenance_commits(stdout='{"commits": {}}') is None
    assert parse_provenance_commits(stdout='{"commits": [1, {"oid": ""}, {"oid": "a"}]}') == ()


def test_git_read_failures_and_missing_tree_entries_are_not_numeric(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    source = CycleSource(
        commit="abc",
        pair_id="pair",
        red_captured_at="2026-11-23T10:00:00Z",
        green_verified_at="2026-11-23T10:01:00Z",
    )
    failed = _Replies(replies=[CommandResult(exit_code=1, stdout="", stderr="gone")])
    assert _changed_paths(repo=repo, commit="abc", runner=failed) is None
    absent = _Replies(replies=[CommandResult(exit_code=0, stdout="", stderr="")])
    assert _blob(repo=repo, rev="abc^", path="src/pkg/new.py", runner=absent) == ""
    measure_failed = _Replies(replies=[CommandResult(exit_code=1, stdout="", stderr="gone")])
    assert _measure(repo=repo, source=source, prefixes=("src/pkg",), runner=measure_failed) == (
        None,
        UNOBSERVED_SOURCE_TREE,
    )
    malformed = _Replies(
        replies=[
            CommandResult(exit_code=0, stdout="src/pkg/thing.py\n", stderr=""),
            CommandResult(exit_code=0, stdout="entry", stderr=""),
            CommandResult(exit_code=0, stdout="value = 1\n", stderr=""),
            CommandResult(exit_code=0, stdout="entry", stderr=""),
            CommandResult(exit_code=0, stdout="value = (\n", stderr=""),
        ]
    )
    assert _measure(repo=repo, source=source, prefixes=("src/pkg",), runner=malformed) == (
        None,
        UNOBSERVED_COUNTING,
    )


def test_dispatch_probe_discards_incomplete_pairs_and_failing_forge_reads(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    incomplete = ProvenanceCommit(sha="abc", message="subject")
    assert _verified_pairs(commits=(incomplete,)) == ()
    failed = _Replies(replies=[CommandResult(exit_code=1, stdout="", stderr="offline")])
    assert (
        _dispatch_commits(repo=repo, pr_number=1, dispatch_id=_DISPATCH_ID, runner=failed) is None
    )
    unparsable = _Replies(replies=[CommandResult(exit_code=0, stdout="not json", stderr="")])
    assert (
        _dispatch_commits(repo=repo, pr_number=1, dispatch_id=_DISPATCH_ID, runner=unparsable)
        is None
    )
