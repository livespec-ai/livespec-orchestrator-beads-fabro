"""Clock injection for implicit central factory selections."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_central_factory_selection as central_selection,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_factory_account_selector as selector,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential_policy import (
    CENTRAL_FACTORY_SELECTION,
    NUMBERED_SLOTS,
)

_PLUGIN = "livespec-orchestrator-beads-fabro"
_SLOT = "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_5"
_NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def _configure(repo: Path) -> None:
    config = {
        _PLUGIN: {
            "dispatcher": {
                "claude_credential_policy": {
                    "mode": NUMBERED_SLOTS,
                    "slots": [_SLOT],
                    "selection": CENTRAL_FACTORY_SELECTION,
                }
            }
        }
    }
    (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")


def _write_record(*, home: Path, written_at: str) -> None:
    record = home / central_selection.FACTORY_SELECTION_RECORD_REL
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(
        json.dumps(
            {
                "account_uuid": "0d4f6c1e-9a52-4a7b-8c3e-5b1f2d7a9e60",
                "profile": "anthropic-5",
                "reason": None,
                "written_at": written_at,
            }
        ),
        encoding="utf-8",
    )


def test_implicit_central_selection_uses_the_callers_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _configure(tmp_path)
    _write_record(home=tmp_path, written_at="2026-11-21T11:55:00Z")

    assert selector.policy_pool_slots(repo=tmp_path, environ={_SLOT: "token"}, now=_NOW) == (_SLOT,)
    assert (
        selector.repo_credential_refusal(repo=tmp_path, environ={_SLOT: "token"}, now=_NOW) is None
    )


def test_implicit_central_selection_is_stale_at_the_callers_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _configure(tmp_path)
    _write_record(home=tmp_path, written_at="2026-11-21T10:30:00Z")

    assert selector.policy_pool_slots(repo=tmp_path, environ={_SLOT: "token"}, now=_NOW) == ()
