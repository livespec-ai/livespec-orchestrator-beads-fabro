"""A Green-exempt completion belongs to ONE commit, never to every twin of its message.

The hook-exempt non-Python amend is recognised from a commit's changed files,
so the completion it earns is a fact about that commit. Two commits can carry
byte-identical message bodies (the hook writes the same trailer shape and a
run's `Factory-Run-Id` is shared), so a completion keyed by message text would
close a genuine open Red that merely reads the same.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_probe"
_DISPATCH_ID = "5fe8e3dfbfd54faa979e85364d8e9863"
_REPO = "livespec-ai/test-repo"
_EXEMPT_OID = "aaa111"
_OPEN_RED_OID = "bbb222"

_FILES_BY_OID = {
    _EXEMPT_OID: [{"filename": "ansible/tasks/main.yml"}, {"filename": "tests/test_role.py"}],
    _OPEN_RED_OID: [{"filename": "tests/test_other.py"}],
}


def _module() -> ModuleType:
    return importlib.import_module(_MODULE_NAME)


def _identical_red_commit(*, oid: str) -> dict[str, str]:
    return {
        "oid": oid,
        "messageHeadline": "fix: the same words twice",
        "messageBody": (
            "TDD-Red-Captured-At: 2026-11-22T18:00:00Z\n" f"Factory-Run-Id: {_DISPATCH_ID}\n"
        ),
    }


class _Runner:
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        assert cwd == Path("/repo")
        assert timeout_seconds > 0
        assert env is None
        if argv[:3] == ["gh", "pr", "view"]:
            commits = [
                _identical_red_commit(oid=_EXEMPT_OID),
                _identical_red_commit(oid=_OPEN_RED_OID),
            ]
            return CommandResult(exit_code=0, stdout=json.dumps({"commits": commits}), stderr="")
        if argv[:3] == ["gh", "repo", "view"]:
            return CommandResult(
                exit_code=0, stdout=json.dumps({"nameWithOwner": _REPO}), stderr=""
            )
        if argv[:2] == ["gh", "api"]:
            oid = argv[-1].rsplit("/", 1)[-1]
            return CommandResult(
                exit_code=0, stdout=json.dumps({"files": _FILES_BY_OID[oid]}), stderr=""
            )
        raise AssertionError(f"unexpected command: {argv}")


def test_identical_message_bodies_do_not_let_an_exempt_amend_close_an_open_red() -> None:
    signals = _module().commit_signals_for_dispatch(
        repo=Path("/repo"),
        outcome=DispatchOutcome(
            work_item_id="bd-ib-dug24j",
            status="green",
            stage="done",
            pr_number=4242,
            merge_sha="abc123",
            detail="merged",
        ),
        dispatch_id=_DISPATCH_ID,
        runner=_Runner(),
    )

    assert signals is not None
    assert signals.red_commit_count == 2
    # Only the commit whose own files show the exempt amend completed a cycle;
    # its twin by message is still an open Red.
    assert signals.green_commit_count == 1
