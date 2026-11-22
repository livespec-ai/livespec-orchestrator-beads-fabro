"""Integration acceptance for Scenario 320's preservation-ref lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_lifecycle_ref_deletion as ref_deletion,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_lifecycle_writes as lifecycle_writes,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_preservation_ref_deletion as preservation_deletion,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import StoreConfig

_ITEM = "bd-ib-320"
_REFS_ENDPOINT = "/repos/{owner}/{repo}/git/refs/"
_MATCHING_REFS_ENDPOINT = "/repos/{owner}/{repo}/git/matching-refs/"


@dataclass(kw_only=True)
class _Forge:
    refs: tuple[str, ...]
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
            ref = "refs/" + argv[-1].removeprefix(_REFS_ENDPOINT)
            if ref in self.refuse_delete:
                return CommandResult(exit_code=1, stdout="", stderr="refused")
            return CommandResult(exit_code=0, stdout="", stderr="")
        prefix = "refs/" + argv[3].removeprefix(_MATCHING_REFS_ENDPOINT)
        listed = [ref for ref in self.refs if ref.startswith(prefix)]
        return CommandResult(exit_code=0, stdout="\n".join(listed) + "\n", stderr="")

    @property
    def deleted(self) -> list[str]:
        return [call[-1].removeprefix(_REFS_ENDPOINT) for call in self.calls if "DELETE" in call]


@dataclass
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_scenario320_closing_collection_open_item_and_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise all four preservation-ref outcomes through their production seams."""
    closed_refs = (
        f"refs/livespec/wip/{_ITEM}/01RUN/1",
        f"refs/livespec/preserved-publish/{_ITEM}/abc123",
    )
    accepting = _Forge(refs=closed_refs)
    monkeypatch.setattr(ref_deletion, "ShellCommandRunner", lambda: accepting)
    monkeypatch.setattr(lifecycle_writes, "reconcile_after_lifecycle_write", lambda **_: None)
    monkeypatch.setattr(lifecycle_writes.store, "update_work_item_status", lambda **_: None)
    lifecycle_writes.write_work_item_status_and_reconcile(
        path=_config(repo_root=tmp_path), item_id=_ITEM, status="done"
    )
    assert accepting.deleted == [ref.removeprefix("refs/") for ref in closed_refs]

    run_id = "01ENDED"
    ended_refs = (
        f"refs/livespec/wip/{_ITEM}/{run_id}/1",
        f"refs/heads/needs-human/{run_id}",
        f"refs/livespec/preserved-publish/{_ITEM}/abc123",
    )
    collected = _Forge(refs=ended_refs)
    assert preservation_deletion.delete_ended_run_refs(
        runner=collected, repo=tmp_path, journal=_Journal(), work_item_id=_ITEM, run_id=run_id
    )
    assert collected.deleted == [
        ref.removeprefix("refs/") for ref in (ended_refs[0], ended_refs[2], ended_refs[1])
    ]

    open_item = _Forge(refs=closed_refs)
    monkeypatch.setattr(ref_deletion, "ShellCommandRunner", lambda: open_item)
    lifecycle_writes.write_work_item_status_and_reconcile(
        path=_config(repo_root=tmp_path), item_id=_ITEM, status="blocked"
    )
    assert open_item.calls == []

    retry_ref = f"refs/livespec/wip/{_ITEM}/01RETRY/1"
    journal = _Journal()
    refused = _Forge(refs=(retry_ref,), refuse_delete=frozenset({retry_ref}))
    assert not preservation_deletion.delete_ended_run_refs(
        runner=refused, repo=tmp_path, journal=journal, work_item_id=_ITEM, run_id="01RETRY"
    )
    assert journal.records[0]["stage"] == preservation_deletion.JOURNAL_STAGE_DELETION_FAILED
    retried = _Forge(refs=(retry_ref,))
    assert preservation_deletion.delete_ended_run_refs(
        runner=retried, repo=tmp_path, journal=journal, work_item_id=_ITEM, run_id="01RETRY"
    )
    assert retried.deleted == [retry_ref.removeprefix("refs/")]


def _config(*, repo_root: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-orchestrator-beads-fabro",
        prefix="bd-ib",
        server_user="livespec-orchestrator-beads-fabro",
        database="livespec-orchestrator-beads-fabro",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )
