"""Collection of an ended run's sandbox once its item rests at ready or backlog (bd-ib-jshkjz).

An ended run whose work-item went back to `ready` or `backlog` held its sandbox
forever, because the collector deleted only runs of CLOSED items. The collector now
also collects such a run when origin holds the run's committed tree, and then it
leaves the run's preservation refs alone, since a re-dispatch seeds from them.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_ended_run_collection import (
    JOURNAL_STAGE_COLLECTION_REFUSED,
    collect_closed_ended_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    FactoryRunInventory,
    journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary

_TIP = "a" * 40
_OTHER = "b" * 40
_UNPUBLISHED = "retained-for-unpublished-work"
_NOT_CLOSED = "item-not-closed"


@dataclass(kw_only=True)
class _Factory:
    """The factory CLI: `inspect` reports the run's committed tip, `dump` and `rm` succeed."""

    tip: str | None = _TIP
    inspect_stdout: str | None = None
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
        if argv[1] == "dump":
            Path(argv[argv.index("-o") + 1]).mkdir(parents=True, exist_ok=True)
        if argv[1] == "inspect":
            checkpoints = [] if self.tip is None else [{"checkpoint": {"git_commit_sha": self.tip}}]
            stdout = self.inspect_stdout
            if stdout is None:
                stdout = json.dumps([{"id": "run", "checkpoints": checkpoints}])
            return CommandResult(exit_code=0, stdout=stdout, stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")

    @property
    def verbs(self) -> list[str]:
        return [call[1] for call in self.calls]


@dataclass(kw_only=True)
class _Origin:
    """Origin through git and the forge: `ls-remote` lists refs, `rev-parse` reads trees."""

    refs: Mapping[str, str] = field(default_factory=dict)
    trees: Mapping[str, str] = field(default_factory=dict)
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
        if argv[:2] == ["git", "ls-remote"]:
            wanted = argv[3:]
            lines = [
                f"{sha}\t{ref}"
                for ref, sha in self.refs.items()
                if any(
                    ref == pattern or (pattern.endswith("*") and ref.startswith(pattern[:-1]))
                    for pattern in wanted
                )
            ]
            return CommandResult(exit_code=0, stdout="\n".join(lines) + "\n", stderr="")
        if argv[:2] == ["git", "rev-parse"]:
            commit = argv[-1].removesuffix("^{tree}")
            tree = self.trees.get(commit)
            return CommandResult(
                exit_code=0 if tree else 1, stdout=f"{tree}\n" if tree else "", stderr=""
            )
        return CommandResult(exit_code=0, stdout="", stderr="")

    @property
    def mutations(self) -> list[list[str]]:
        return [call for call in self.calls if "DELETE" in call or call[:2] == ["git", "push"]]


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)

    def stages(self) -> list[object]:
        return [record["stage"] for record in self.records]


def _inventory(*, status: str, refused_before: frozenset[tuple[str, str | None]] = frozenset()):
    return FactoryRunInventory(
        runs=(
            FabroRunSummary(run_id="01RUN", status_kind="failed", goal=None, total_usd_micros=None),
        ),
        item_statuses={"bd-ib-item": status},
        journaled=journaled_runs(
            text='{"stage":"dispatch-run-stamp","run_id":"01RUN","work_item_id":"bd-ib-item"}'
        ),
        id_prefix="bd-ib",
        factory_name="factory",
        factory_server_url="https://factory.test",
        only_work_item_id=None,
        refused_before=refused_before,
    )


def _collect(
    *,
    tmp_path: Path,
    status: str,
    factory: _Factory,
    origin: _Origin,
    journal: _Journal,
    dry_run: bool = False,
    refused_before: frozenset[tuple[str, str | None]] = frozenset(),
) -> None:
    collect_closed_ended_runs(
        inventory=_inventory(status=status, refused_before=refused_before),
        port=FabroPort(
            fabro_bin="fabro",
            target=FabroTarget(server_url="https://factory.test"),
            runner=factory,
            cwd=tmp_path,
        ),
        runner=origin,
        repo=tmp_path,
        journal=journal,
        dry_run=dry_run,
    )


@pytest.mark.parametrize("status", ["ready", "backlog"])
def test_a_run_whose_committed_tip_origin_holds_is_collected_and_keeps_its_refs(
    tmp_path: Path, status: str
) -> None:
    factory = _Factory()
    origin = _Origin(refs={"refs/heads/needs-human/01RUN": _TIP})
    journal = _Journal()

    _collect(tmp_path=tmp_path, status=status, factory=factory, origin=origin, journal=journal)

    assert "rm" in factory.verbs
    assert origin.mutations == []
    collected = [r for r in journal.records if r["stage"] == "ended-run-collected"]
    assert [(r["run_id"], r["work_item_status"]) for r in collected] == [("01RUN", status)]


def test_a_run_whose_tip_tree_a_preservation_ref_holds_under_another_commit_is_collected(
    tmp_path: Path,
) -> None:
    factory = _Factory()
    origin = _Origin(
        refs={"refs/livespec/wip/bd-ib-item/01RUN/2": _OTHER},
        trees={_TIP: "tree-1", _OTHER: "tree-1"},
    )

    _collect(tmp_path=tmp_path, status="ready", factory=factory, origin=origin, journal=_Journal())

    assert "rm" in factory.verbs
    assert origin.mutations == []


def test_a_run_with_work_origin_does_not_hold_keeps_its_sandbox_and_is_journaled(
    tmp_path: Path,
) -> None:
    factory = _Factory()
    origin = _Origin(
        refs={"refs/heads/needs-human/01RUN": _OTHER},
        trees={_TIP: "tree-new", _OTHER: "tree-old"},
    )
    journal = _Journal()

    _collect(tmp_path=tmp_path, status="ready", factory=factory, origin=origin, journal=journal)

    assert "rm" not in factory.verbs
    assert "dump" not in factory.verbs
    refusals = [r for r in journal.records if r["stage"] == JOURNAL_STAGE_COLLECTION_REFUSED]
    assert [(r["run_id"], r["work_item_status"], r["reason"]) for r in refusals] == [
        ("01RUN", "ready", _UNPUBLISHED)
    ]


def test_a_run_with_no_ref_on_origin_keeps_its_sandbox(tmp_path: Path) -> None:
    factory = _Factory()
    journal = _Journal()

    _collect(
        tmp_path=tmp_path, status="backlog", factory=factory, origin=_Origin(), journal=journal
    )

    assert "rm" not in factory.verbs
    assert [r["reason"] for r in journal.records] == [_UNPUBLISHED]


@pytest.mark.parametrize("tip", [None])
def test_a_run_whose_record_names_no_committed_tip_is_not_collected(
    tmp_path: Path, tip: str | None
) -> None:
    factory = _Factory(tip=tip)
    origin = _Origin(refs={"refs/heads/needs-human/01RUN": _TIP})

    _collect(tmp_path=tmp_path, status="ready", factory=factory, origin=origin, journal=_Journal())

    assert "rm" not in factory.verbs


def test_a_run_whose_record_cannot_be_read_is_not_collected(tmp_path: Path) -> None:
    factory = _Factory(inspect_stdout="not json")
    origin = _Origin(refs={"refs/heads/needs-human/01RUN": _TIP})
    journal = _Journal()

    _collect(tmp_path=tmp_path, status="ready", factory=factory, origin=origin, journal=journal)

    assert "rm" not in factory.verbs
    assert [r["reason"] for r in journal.records] == [_UNPUBLISHED]


@pytest.mark.parametrize("status", ["blocked", "needs-human", "active", "pending-approval"])
def test_a_run_whose_item_awaits_a_human_or_is_in_flight_keeps_its_sandbox_unread(
    tmp_path: Path, status: str
) -> None:
    factory = _Factory()
    origin = _Origin(refs={"refs/heads/needs-human/01RUN": _TIP})
    journal = _Journal()

    _collect(tmp_path=tmp_path, status=status, factory=factory, origin=origin, journal=journal)

    assert factory.verbs == []
    assert origin.calls == []
    assert [r["reason"] for r in journal.records] == [_NOT_CLOSED]


def test_a_standing_unpublished_refusal_is_not_journaled_again(tmp_path: Path) -> None:
    factory = _Factory()
    journal = _Journal()

    _collect(
        tmp_path=tmp_path,
        status="ready",
        factory=factory,
        origin=_Origin(),
        journal=journal,
        refused_before=frozenset({("01RUN", "ready")}),
    )

    assert "rm" not in factory.verbs
    assert journal.records == []


def test_a_dry_run_collects_nothing_and_reads_nothing(tmp_path: Path) -> None:
    factory = _Factory()
    origin = _Origin(refs={"refs/heads/needs-human/01RUN": _TIP})
    journal = _Journal()

    _collect(
        tmp_path=tmp_path,
        status="ready",
        factory=factory,
        origin=origin,
        journal=journal,
        dry_run=True,
    )

    assert factory.verbs == []
    assert origin.calls == []
    assert journal.records == []
