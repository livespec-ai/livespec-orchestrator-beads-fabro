"""Integration acceptance for Scenario 318's terminal preservation receipt."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import _dispatcher_wip_capture_receipt as receipt
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM = "bd-ib-318"
_RUN = "01SCENARIO318"
_HEAD = "a" * 40


@pytest.fixture(autouse=True)
def _tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass
class _Forge:
    wip: str = ""
    wip_exit: int = 0
    needs_human: str = ""
    needs_human_exit: int = 0
    merge_base: str = "base\n"
    merge_base_exit: int = 0
    diff: str = ""
    diff_exit: int = 0

    def run(
        self, *, argv: list[str], cwd: Path, timeout_seconds: float, **_: object
    ) -> CommandResult:
        _ = (cwd, timeout_seconds)
        if argv[:3] == ["git", "ls-remote", "origin"]:
            if "refs/livespec/wip" in argv[-1]:
                return CommandResult(exit_code=self.wip_exit, stdout=self.wip, stderr="refused")
            return CommandResult(
                exit_code=self.needs_human_exit, stdout=self.needs_human, stderr="refused"
            )
        if argv[:3] == ["git", "merge-base", "origin/master"]:
            return CommandResult(
                exit_code=self.merge_base_exit, stdout=self.merge_base, stderr="refused"
            )
        if argv[:3] == ["git", "diff", "--numstat"]:
            return CommandResult(exit_code=self.diff_exit, stdout=self.diff, stderr="refused")
        raise AssertionError(f"unexpected forge command: {argv}")


def test_scenario318_records_the_latest_wip_capture_or_an_honest_absence(
    tmp_path: Path,
) -> None:
    ref = f"refs/livespec/wip/{_ITEM}/{_RUN}/3"
    body = _record(
        tmp_path=tmp_path,
        forge=_Forge(wip=f"{'b' * 40}\t{ref.removesuffix('3')}2\n{_HEAD}\t{ref}\n"),
    )

    for expected in (ref, _HEAD, _RUN, "factory: petri"):
        assert expected in body

    reset_fake_singleton()
    assert "the run has no work-in-progress ref" in _record(
        tmp_path=tmp_path / "no-capture", forge=_Forge()
    )


def test_scenario318_never_reports_an_unreadable_forge_as_no_capture(tmp_path: Path) -> None:
    body = _record(tmp_path=tmp_path, forge=_Forge(wip_exit=1))

    assert "work-in-progress preservation could not be determined" in body
    assert "the run has no work-in-progress ref" not in body


@pytest.mark.parametrize(
    ("diff", "diff_exit", "expected"),
    [
        ("153\t12\tone.py\n0\t0\ttwo.py\n", 0, "2 files changed, 153 insertions, 12 deletions"),
        ("", 0, "0 files changed, 0 insertions, 0 deletions"),
        ("", 1, "needs-human diff could not be determined"),
    ],
)
def test_scenario318_names_needs_human_work_without_misreporting_its_diff(
    tmp_path: Path, diff: str, diff_exit: int, expected: str
) -> None:
    needs = f"{_HEAD}\trefs/heads/needs-human/{_RUN}\n"
    body = _record(
        tmp_path=tmp_path,
        forge=_Forge(needs_human=needs, diff=diff, diff_exit=diff_exit),
    )

    assert f"needs-human ref: refs/heads/needs-human/{_RUN}" in body
    assert f"commit id: {_HEAD}" in body
    assert expected in body
    assert body != "the run has no work-in-progress ref"


@pytest.mark.parametrize(
    ("forge", "expected"),
    [
        (_Forge(needs_human_exit=1), "the run has no work-in-progress ref"),
        (
            _Forge(
                needs_human=f"{_HEAD}\trefs/heads/needs-human/{_RUN}\n",
                merge_base_exit=1,
            ),
            "needs-human diff could not be determined",
        ),
        (
            _Forge(
                needs_human=f"{_HEAD}\trefs/heads/needs-human/{_RUN}\n",
                diff="not-a-numstat-row\n",
            ),
            "needs-human diff could not be determined",
        ),
    ],
)
def test_scenario318_keeps_unreadable_needs_human_data_distinct_from_an_empty_diff(
    tmp_path: Path, forge: _Forge, expected: str
) -> None:
    assert expected in _record(tmp_path=tmp_path, forge=forge)


def _record(*, tmp_path: Path, forge: _Forge) -> str:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro":{"connection":{"prefix":"bd-ib"}}}',
        encoding="utf-8",
    )
    config = StoreConfig(
        tenant="scenario318",
        prefix="bd-ib",
        server_user="scenario318",
        database="scenario318",
        bd_path="bd",
        fake=True,
    )
    append_work_item(
        path=config,
        item=WorkItem(
            id=_ITEM,
            type="task",
            status="blocked",
            title="terminal preservation receipt",
            description="",
            origin="freeform",
            gap_id=None,
            rank="a0",
            assignee=None,
            depends_on=(),
            captured_at="2026-11-22T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
        ),
    )
    receipt.record_wip_capture_receipt(
        repo=repo,
        work_item_id=_ITEM,
        run_id=_RUN,
        factory="petri",
        journal=_Journal(),
        runner=forge,
    )
    comments = read_work_item_comments(path=config, work_item_id=_ITEM)
    assert len(comments) == 1
    return comments[0].text
