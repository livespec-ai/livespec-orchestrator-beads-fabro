"""Integration-tier acceptance for the Dispatcher preservation scenarios.

The cases in this module exercise the production lifecycle and recovery seams
against a hermetic forge.  Scenario 320's first case proves that accepting an
item removes each preservation ref that origin reports for that item.
"""

from __future__ import annotations

import json
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import StoreConfig

_HEADING = "## Scenario 320 — Preservation refs are deleted when the Dispatcher closes or collects an item's runs"
_NODE = (
    "tests.integration.test_dispatcher_preservation_scenarios_318_320_323."
    "test_accepting_an_item_deletes_its_preservation_refs"
)
_ITEM = "bd-ib-320"
_REFS_ENDPOINT = "/repos/{owner}/{repo}/git/refs/"
_MATCHING_REFS_ENDPOINT = "/repos/{owner}/{repo}/git/matching-refs/"
_REFS = (
    f"refs/livespec/wip/{_ITEM}/01RUN/1",
    f"refs/livespec/preserved-publish/{_ITEM}/abc123",
)


@dataclass(kw_only=True)
class _Forge:
    """A hermetic origin whose calls follow the production forge protocol."""

    refs: tuple[str, ...] = _REFS
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
            return CommandResult(exit_code=0, stdout="", stderr="")
        prefix = "refs/" + argv[3].removeprefix(_MATCHING_REFS_ENDPOINT)
        listed = [ref for ref in self.refs if ref.startswith(prefix)]
        return CommandResult(exit_code=0, stdout="\n".join(listed) + "\n", stderr="")

    @property
    def deleted(self) -> list[str]:
        return [call[-1].removeprefix(_REFS_ENDPOINT) for call in self.calls if "DELETE" in call]


def test_accepting_an_item_deletes_its_preservation_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given accepted work with preservation refs, acceptance deletes every ref."""
    forge = _Forge()
    monkeypatch.setattr(ref_deletion, "ShellCommandRunner", lambda: forge)
    monkeypatch.setattr(lifecycle_writes, "reconcile_after_lifecycle_write", lambda **_: None)
    monkeypatch.setattr(lifecycle_writes.store, "update_work_item_status", lambda **_: None)

    lifecycle_writes.write_work_item_status_and_reconcile(
        path=_config(repo_root=tmp_path), item_id=_ITEM, status="done"
    )

    assert forge.deleted == [ref.removeprefix("refs/") for ref in _REFS]
    assert _coverage_entry()["test"] == _NODE


def _coverage_entry() -> dict[str, object]:
    coverage_path = Path(__file__).resolve().parents[2] / "tests" / "heading-coverage.json"
    entries = json.loads(coverage_path.read_text(encoding="utf-8"))
    return next(entry for entry in entries if entry["heading"] == _HEADING)


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
