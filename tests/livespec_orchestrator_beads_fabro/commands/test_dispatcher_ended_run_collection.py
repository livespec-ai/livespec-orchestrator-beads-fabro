"""Tests for collection of ended sandboxes after their item closes."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_ended_run_collection import (
    collect_closed_ended_runs,
    journaled_refusals,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_preservation_ref_deletion import (
    JOURNAL_STAGE_DELETION_FAILED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    FactoryRunInventory,
    journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary

_EXPORTS = Path("tmp") / "ended-run-exports"
_DUMP_FILES = {"events.jsonl": '{"event":"run.completed"}\n', "stages/red.log": "red stage log\n"}


@dataclass(kw_only=True)
class _Runner:
    """The factory CLI's reference interface: `dump` writes the run's files, `rm` deletes it."""

    calls: list[list[str]] = field(default_factory=list)
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    dump_exit_code: int = 0
    dump_files: Mapping[str, str] = field(default_factory=lambda: dict(_DUMP_FILES))
    manifest_present_at_rm: list[bool] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (timeout_seconds, env, stdin)
        self.calls.append(argv)
        if argv[1] == "dump":
            if self.dump_exit_code == 0:
                out = Path(argv[argv.index("-o") + 1])
                for name, text in self.dump_files.items():
                    (out / name).parent.mkdir(parents=True, exist_ok=True)
                    _ = (out / name).write_text(text, encoding="utf-8")
            return CommandResult(exit_code=self.dump_exit_code, stdout="", stderr="")
        if argv[1] == "rm":
            self.manifest_present_at_rm.append(
                (cwd / _EXPORTS / argv[2] / "MANIFEST.json").exists()
            )
        return CommandResult(exit_code=self.exit_code, stdout=self.stdout, stderr=self.stderr)


@dataclass(kw_only=True)
class _Forge:
    """The forge's reference interface: lists refs by prefix, records deletions."""

    refs: tuple[str, ...] = ()
    refuse_delete: frozenset[str] = frozenset()
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
        if "DELETE" in argv:
            ref = "refs/" + argv[-1].removeprefix("/repos/{owner}/{repo}/git/refs/")
            if ref in self.refuse_delete:
                return CommandResult(exit_code=1, stdout="", stderr="HTTP 422")
            return CommandResult(exit_code=0, stdout="", stderr="")
        prefix = "refs/" + argv[3].removeprefix("/repos/{owner}/{repo}/git/matching-refs/")
        listed = [ref for ref in self.refs if ref.startswith(prefix)]
        return CommandResult(exit_code=0, stdout="\n".join(listed) + "\n", stderr="")

    @property
    def deleted(self) -> list[str]:
        return [
            "refs/" + call[-1].split("/git/refs/", 1)[1] for call in self.calls if "DELETE" in call
        ]


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_collects_only_ended_runs_of_closed_items_and_journals_the_provider_result(
    tmp_path: Path,
) -> None:
    runner = _Runner()
    forge = _Forge()
    journal = _Journal()

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(
                _run(run_id="01CLOSED", status_kind="succeeded"),
                _run(run_id="01BLOCKED", status_kind="succeeded"),
                _run(run_id="01CLEARANCE", status_kind="succeeded"),
                _run(run_id="01LIVE", status_kind="running"),
            ),
            statuses={"bd-ib-closed": "done", "bd-ib-blocked": "blocked"},
            stamps=(("01CLOSED", "bd-ib-closed"), ("01BLOCKED", "bd-ib-blocked")),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=forge,
        repo=tmp_path,
        journal=journal,
        dry_run=False,
    )

    assert [call[1] for call in runner.calls] == ["dump", "rm"]
    assert runner.calls[1] == ["fabro", "rm", "01CLOSED", "--server", "https://factory.test"]
    assert [record["stage"] for record in journal.records] == [
        "ended-run-exported",
        "ended-run-collected",
        "ended-run-collection-refused",
    ]
    assert journal.records[1:] == [
        {
            "stage": "ended-run-collected",
            "run_id": "01CLOSED",
            "factory_name": "factory",
            "factory_server_url": "https://factory.test",
            "dispatching_repository": tmp_path.name,
            "work_item_id": "bd-ib-closed",
            "work_item_status": "done",
            "rm_exit_code": 0,
            "rm_stdout": "",
            "rm_stderr": "",
        },
        {
            "stage": "ended-run-collection-refused",
            "run_id": "01BLOCKED",
            "factory_name": "factory",
            "factory_server_url": "https://factory.test",
            "dispatching_repository": tmp_path.name,
            "work_item_id": "bd-ib-blocked",
            "work_item_status": "blocked",
            "reason": "item-not-closed",
        },
    ]


def test_dry_run_leaves_an_ended_closed_run_and_its_journal_unchanged(tmp_path: Path) -> None:
    runner = _Runner()
    forge = _Forge()
    journal = _Journal()

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(_run(run_id="01CLOSED", status_kind="failed"),),
            statuses={"bd-ib-closed": "closed"},
            stamps=(("01CLOSED", "bd-ib-closed"),),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=forge,
        repo=tmp_path,
        journal=journal,
        dry_run=True,
    )

    assert (runner.calls, journal.records) == ([], [])


def _collected(journal: _Journal) -> list[dict[str, object]]:
    return [record for record in journal.records if record["stage"] == "ended-run-collected"]


def test_failed_provider_delete_is_journaled_for_the_next_collection_pass(tmp_path: Path) -> None:
    runner = _Runner(exit_code=1)
    forge = _Forge()
    journal = _Journal()

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(_run(run_id="01CLOSED", status_kind="dead"),),
            statuses={"bd-ib-closed": "done"},
            stamps=(("01CLOSED", "bd-ib-closed"),),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=forge,
        repo=tmp_path,
        journal=journal,
        dry_run=False,
    )

    assert _collected(journal)[0]["rm_exit_code"] == 1


def test_journal_carries_the_bounded_rm_response_for_diagnosis_and_retry(tmp_path: Path) -> None:
    runner = _Runner(
        exit_code=1,
        stdout="Preserved: sandbox_preserved\n" + "x" * 5000,
        stderr="lease lease-1: prune failed",
    )
    forge = _Forge()
    journal = _Journal()

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(_run(run_id="01CLOSED", status_kind="failed"),),
            statuses={"bd-ib-closed": "done"},
            stamps=(("01CLOSED", "bd-ib-closed"),),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=forge,
        repo=tmp_path,
        journal=journal,
        dry_run=False,
    )

    record = _collected(journal)[0]
    stdout = record["rm_stdout"]
    assert isinstance(stdout, str)
    assert stdout.startswith("Preserved: sandbox_preserved")
    assert 0 < len(stdout) < 5000
    assert record["rm_stderr"] == "lease lease-1: prune failed"


def test_targeted_pass_collects_only_its_own_items_closed_runs(tmp_path: Path) -> None:
    runner = _Runner()
    forge = _Forge()
    journal = _Journal()

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(
                _run(run_id="01MINE", status_kind="succeeded"),
                _run(run_id="01OTHER", status_kind="succeeded"),
            ),
            statuses={"bd-ib-mine": "done", "bd-ib-other": "done"},
            stamps=(("01MINE", "bd-ib-mine"), ("01OTHER", "bd-ib-other")),
            only_work_item_id="bd-ib-mine",
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=forge,
        repo=tmp_path,
        journal=journal,
        dry_run=False,
    )

    assert [call[1:3] for call in runner.calls] == [["dump", "01MINE"], ["rm", "01MINE"]]
    assert {record["run_id"] for record in journal.records} == {"01MINE"}


def _inventory(
    *,
    runs: tuple[FabroRunSummary, ...],
    statuses: dict[str, str],
    stamps: tuple[tuple[str, str], ...],
    only_work_item_id: str | None = None,
    refused_before: frozenset[tuple[str, str | None]] = frozenset(),
) -> FactoryRunInventory:
    return FactoryRunInventory(
        runs=runs,
        item_statuses=statuses,
        journaled=journaled_runs(
            text="\n".join(
                f'{{"stage":"dispatch-run-stamp","run_id":"{run_id}","work_item_id":"{item_id}"}}'
                for run_id, item_id in stamps
            )
        ),
        id_prefix="bd-ib",
        factory_name="factory",
        factory_server_url="https://factory.test",
        only_work_item_id=only_work_item_id,
        refused_before=refused_before,
    )


def _port(*, tmp_path: Path, runner: _Runner) -> FabroPort:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url="https://factory.test"),
        runner=runner,
        cwd=tmp_path,
    )


def _run(*, run_id: str, status_kind: str) -> FabroRunSummary:
    return FabroRunSummary(
        run_id=run_id,
        status_kind=status_kind,
        goal=None,
        total_usd_micros=None,
    )


def test_collecting_a_closed_items_run_deletes_its_refs_and_not_an_open_items(
    tmp_path: Path,
) -> None:
    runner = _Runner()
    forge = _Forge(
        refs=(
            "refs/livespec/wip/bd-ib-closed/01CLOSED/1",
            "refs/livespec/wip/bd-ib-closed/01OLDER/1",
            "refs/livespec/preserved-publish/bd-ib-closed/abc123",
            "refs/heads/needs-human/01CLOSED",
            "refs/livespec/wip/bd-ib-blocked/01BLOCKED/1",
            "refs/livespec/preserved-publish/bd-ib-blocked/def456",
            "refs/heads/needs-human/01BLOCKED",
        )
    )

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(
                _run(run_id="01CLOSED", status_kind="failed"),
                _run(run_id="01BLOCKED", status_kind="failed"),
            ),
            statuses={"bd-ib-closed": "done", "bd-ib-blocked": "blocked"},
            stamps=(("01CLOSED", "bd-ib-closed"), ("01BLOCKED", "bd-ib-blocked")),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=forge,
        repo=tmp_path,
        journal=_Journal(),
        dry_run=False,
    )

    assert forge.deleted == [
        "refs/livespec/wip/bd-ib-closed/01CLOSED/1",
        "refs/livespec/preserved-publish/bd-ib-closed/abc123",
        "refs/heads/needs-human/01CLOSED",
    ]
    assert [call[1:3] for call in runner.calls] == [["dump", "01CLOSED"], ["rm", "01CLOSED"]]


def test_one_collection_pass_lists_a_closed_items_shared_preserved_publish_namespace_once(
    tmp_path: Path,
) -> None:
    forge = _Forge()

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(
                _run(run_id="01FIRST", status_kind="succeeded"),
                _run(run_id="01SECOND", status_kind="succeeded"),
            ),
            statuses={"bd-ib-closed": "closed"},
            stamps=(
                ("01FIRST", "bd-ib-closed"),
                ("01SECOND", "bd-ib-closed"),
            ),
        ),
        port=_port(tmp_path=tmp_path, runner=_Runner()),
        runner=forge,
        repo=tmp_path,
        journal=_Journal(),
        dry_run=False,
    )

    shared_namespace = (
        "/repos/{owner}/{repo}/git/matching-refs/livespec/preserved-publish/bd-ib-closed/"
    )
    assert sum(call[3] == shared_namespace for call in forge.calls) == 1


def test_dry_run_deletes_no_preservation_ref(tmp_path: Path) -> None:
    forge = _Forge(refs=("refs/heads/needs-human/01CLOSED",))

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(_run(run_id="01CLOSED", status_kind="failed"),),
            statuses={"bd-ib-closed": "closed"},
            stamps=(("01CLOSED", "bd-ib-closed"),),
        ),
        port=_port(tmp_path=tmp_path, runner=_Runner()),
        runner=forge,
        repo=tmp_path,
        journal=_Journal(),
        dry_run=True,
    )

    assert forge.calls == []


def test_a_refused_ref_deletion_is_journaled_and_leaves_the_run_for_the_next_pass(
    tmp_path: Path,
) -> None:
    refused = "refs/heads/needs-human/01CLOSED"
    runner = _Runner()
    forge = _Forge(refs=(refused,), refuse_delete=frozenset({refused}))
    journal = _Journal()

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(_run(run_id="01CLOSED", status_kind="failed"),),
            statuses={"bd-ib-closed": "done"},
            stamps=(("01CLOSED", "bd-ib-closed"),),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=forge,
        repo=tmp_path,
        journal=journal,
        dry_run=False,
    )

    assert runner.calls == []
    assert [(record["stage"], record["ref"]) for record in journal.records] == [
        (JOURNAL_STAGE_DELETION_FAILED, refused)
    ]


def test_a_run_whose_item_status_could_not_be_read_is_refused_and_left_in_place(
    tmp_path: Path,
) -> None:
    runner = _Runner()
    journal = _Journal()

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(_run(run_id="01LOST", status_kind="failed"),),
            statuses={},
            stamps=(("01LOST", "bd-ib-lost"),),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=_Forge(),
        repo=tmp_path,
        journal=journal,
        dry_run=False,
    )

    assert runner.calls == []
    assert [
        (record["run_id"], record["work_item_id"], record["work_item_status"], record["reason"])
        for record in journal.records
    ] == [("01LOST", "bd-ib-lost", None, "item-status-unreadable")]


def test_a_refusal_already_journaled_at_the_same_status_is_not_journaled_again(
    tmp_path: Path,
) -> None:
    journal = _Journal()

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(
                _run(run_id="01SAME", status_kind="failed"),
                _run(run_id="01MOVED", status_kind="failed"),
            ),
            statuses={"bd-ib-same": "blocked", "bd-ib-moved": "open"},
            stamps=(("01SAME", "bd-ib-same"), ("01MOVED", "bd-ib-moved")),
            refused_before=frozenset({("01SAME", "blocked"), ("01MOVED", "blocked")}),
        ),
        port=_port(tmp_path=tmp_path, runner=_Runner()),
        runner=_Forge(),
        repo=tmp_path,
        journal=journal,
        dry_run=False,
    )

    assert [record["run_id"] for record in journal.records] == ["01MOVED"]


def test_a_live_run_of_an_open_item_is_neither_collected_nor_refused(tmp_path: Path) -> None:
    journal = _Journal()

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(_run(run_id="01LIVE", status_kind="running"),),
            statuses={"bd-ib-open": "active"},
            stamps=(("01LIVE", "bd-ib-open"),),
        ),
        port=_port(tmp_path=tmp_path, runner=_Runner()),
        runner=_Forge(),
        repo=tmp_path,
        journal=journal,
        dry_run=False,
    )

    assert journal.records == []


def test_journaled_refusals_reads_only_refusal_records_with_their_status(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    _ = path.write_text(
        "\n".join(
            (
                '{"stage":"ended-run-collection-refused","run_id":"01A","work_item_status":"blocked"}',
                '{"stage":"ended-run-collection-refused","run_id":"01B","work_item_status":null}',
                '{"stage":"ended-run-collection-refused","work_item_status":"blocked"}',
                '{"stage":"ended-run-collected","run_id":"01C","work_item_status":"done"}',
                "",
            )
        ),
        encoding="utf-8",
    )

    assert journaled_refusals(journal_path=path) == {("01A", "blocked"), ("01B", None)}
    assert journaled_refusals(journal_path=None) == frozenset()


def test_the_runs_record_is_exported_and_read_back_before_the_run_is_removed(
    tmp_path: Path,
) -> None:
    runner = _Runner()
    journal = _Journal()

    _collect_one(tmp_path=tmp_path, runner=runner, journal=journal)

    export = tmp_path / _EXPORTS / "01CLOSED"
    manifest = json.loads((export / "MANIFEST.json").read_text(encoding="utf-8"))
    assert {entry["path"] for entry in manifest["files"]} == set(_DUMP_FILES)
    for entry in manifest["files"]:
        body = (export / entry["path"]).read_bytes()
        assert (entry["bytes"], entry["sha256"]) == (len(body), hashlib.sha256(body).hexdigest())
    assert runner.manifest_present_at_rm == [True]
    exported = journal.records[0]
    assert exported["stage"] == "ended-run-exported"
    assert exported["run_id"] == "01CLOSED"
    assert exported["export_location"] == str(export)
    assert exported["export_bytes"] == sum(len(text.encode()) for text in _DUMP_FILES.values())
    digest = hashlib.sha256()
    for entry in sorted(manifest["files"], key=lambda item: item["path"]):
        digest.update(f"{entry['path']}\0{entry['sha256']}\n".encode())
    assert exported["export_sha256"] == digest.hexdigest()


def test_a_failed_dump_is_journaled_with_its_step_and_the_run_is_still_removed(
    tmp_path: Path,
) -> None:
    runner = _Runner(dump_exit_code=1)
    journal = _Journal()

    _collect_one(tmp_path=tmp_path, runner=runner, journal=journal)

    failed = journal.records[0]
    assert (failed["stage"], failed["run_id"], failed["export_failed_step"]) == (
        "ended-run-export-failed",
        "01CLOSED",
        "dump",
    )
    assert [call[1] for call in runner.calls] == ["dump", "rm"]
    assert len(_collected(journal)) == 1


def test_a_dump_that_wrote_nothing_is_a_failed_export_and_the_run_is_still_removed(
    tmp_path: Path,
) -> None:
    runner = _Runner(dump_files={})
    journal = _Journal()

    _collect_one(tmp_path=tmp_path, runner=runner, journal=journal)

    assert journal.records[0]["stage"] == "ended-run-export-failed"
    assert journal.records[0]["export_failed_step"] == "dump-empty"
    assert [call[1] for call in runner.calls] == ["dump", "rm"]


def test_an_export_older_than_the_retention_period_is_pruned_and_a_fresh_one_kept(
    tmp_path: Path,
) -> None:
    old = tmp_path / _EXPORTS / "01OLD"
    fresh = tmp_path / _EXPORTS / "01FRESH"
    for directory in (old, fresh):
        directory.mkdir(parents=True)
        _ = (directory / "events.jsonl").write_text("{}\n", encoding="utf-8")
    aged = time.time() - 400 * 24 * 3600
    os.utime(old / "events.jsonl", (aged, aged))
    os.utime(old, (aged, aged))

    _collect_one(tmp_path=tmp_path, runner=_Runner(), journal=_Journal())

    assert (old.exists(), fresh.exists()) == (False, True)


def _collect_one(*, tmp_path: Path, runner: _Runner, journal: _Journal) -> None:
    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(_run(run_id="01CLOSED", status_kind="succeeded"),),
            statuses={"bd-ib-closed": "done"},
            stamps=(("01CLOSED", "bd-ib-closed"),),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=_Forge(),
        repo=tmp_path,
        journal=journal,
        dry_run=False,
    )


class _Usage(NamedTuple):
    total: int
    used: int
    free: int


_TOTAL = 10**12


def _disk(monkeypatch: pytest.MonkeyPatch, *, free: int) -> None:
    """Make the filesystem the export would land on report `free` bytes free."""
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: _Usage(_TOTAL, _TOTAL - free, free))


@pytest.fixture(autouse=True)
def _ample_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test but the disk-pressure ones runs on a filesystem with room to export."""
    _disk(monkeypatch, free=_TOTAL)


def test_an_export_is_skipped_under_disk_pressure_and_the_run_is_still_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _disk(monkeypatch, free=0)
    runner = _Runner()
    journal = _Journal()

    _collect_one(tmp_path=tmp_path, runner=runner, journal=journal)

    skipped = journal.records[0]
    assert skipped["stage"] == "ended-run-export-skipped-disk-pressure"
    assert skipped["run_id"] == "01CLOSED"
    assert (skipped["free_bytes"], skipped["total_bytes"]) == (0, _TOTAL)
    assert {"min_free_fraction", "min_free_bytes"} <= set(skipped)
    assert [call[1] for call in runner.calls] == ["rm"]
    assert not (tmp_path / _EXPORTS / "01CLOSED").exists()
    assert len(_collected(journal)) == 1


def test_old_exports_are_still_pruned_when_the_disk_is_under_pressure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _disk(monkeypatch, free=0)
    old = tmp_path / _EXPORTS / "01OLD"
    old.mkdir(parents=True)
    _ = (old / "events.jsonl").write_text("{}\n", encoding="utf-8")
    aged = time.time() - 400 * 24 * 3600
    os.utime(old / "events.jsonl", (aged, aged))
    os.utime(old, (aged, aged))

    _collect_one(tmp_path=tmp_path, runner=_Runner(), journal=_Journal())

    assert not old.exists()
