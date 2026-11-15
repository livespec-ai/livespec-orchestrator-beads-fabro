"""The worker projects the slot admission chose, not the unnumbered credential.

Proof for plan epic overseer-iyfjbo, DoD 6 ("factory runs choose among the
managed accounts' setup tokens at dispatch, so one account at its limit does not
stop that factory while another has headroom"), taken against the released
dispatcher code (build c1f8445f, release 0.328.0) and kept on master as a
regression guard. It binds Scenario 278's projection half end to end: the
session-headroom admission pass assesses the injected numbered slots, skips the
exhausted one, chooses the one with headroom, and `materialize_overlay` then
writes THAT slot's token into the worker's run-config overlay.

The three credential values are distinct synthetic strings, and the assertion is
on the sha256-12 fingerprint of the projected value, so a projection of the
exhausted slot or of the unnumbered `CLAUDE_CODE_OAUTH_TOKEN` cannot pass.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_credentials,
    _dispatcher_sibling_clones,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_routing import CodexRouting
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor

_NOW = "2026-11-15T08:00:00Z"
_BARE = "CLAUDE_CODE_OAUTH_TOKEN"
_SLOT_A = "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4"
_SLOT_B = "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_2"
_BARE_VALUE = "synthetic-bare-unnumbered-value"
_A_VALUE = "synthetic-slot-a-exhausted-value"
_B_VALUE = "synthetic-slot-b-headroom-value"
_UTILIZATION = {_A_VALUE: 100.0, _B_VALUE: 10.0, _BARE_VALUE: 0.0}
_GIT_AUTHOR = GitAuthor(name="Factory Test", email="factory-test@example.invalid")
_NOT_CODEX = CodexRouting(routes_codex=False, detail="no node routes to codex-acp")
_COMMITTED_WORKFLOW_TOML = '_version = 1\n\n[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "livespec-ci"\n'
_MINIMAL_GRAPH = (
    "digraph ImplementWorkItem {\n"
    '    graph [\n        stall_timeout="7200s"\n    ]\n\n'
    '    implement [\n        timeout="1800s"\n    ]\n'
    "}\n"
)
_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "livespec", "class": "core"}]}'
)
_PROJECTED = re.compile(r'^\s*CLAUDE_CODE_OAUTH_TOKEN\s*=\s*"([^"]*)"', re.MULTILINE)


def _fingerprint(*, value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
    return headroom.session_headroom_reading(
        credential_identity=f"id-{_fingerprint(value=token or '')}",
        observed_at=observed_at,
        utilization=_UTILIZATION[token or ""],
    )


def test_the_worker_projects_the_slot_with_headroom_not_the_exhausted_or_bare_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(_BARE, _BARE_VALUE)
    monkeypatch.setenv(_SLOT_A, _A_VALUE)
    monkeypatch.setenv(_SLOT_B, _B_VALUE)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    monkeypatch.setattr(
        _dispatcher_credentials, "codex_routing_for_dispatch", lambda **_kwargs: _NOT_CODEX
    )
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (tmp_path / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    overlay = tmp_path / "overlay.toml"

    policy = headroom_gate.session_headroom_policy(
        repo=tmp_path, now_iso=_NOW, journal_path=None, read=_read
    )
    chosen = policy.read()
    error = materialize_overlay(
        committed=committed,
        overlay=overlay,
        repo=tmp_path / "repo",
        work_item_id="bd-ib-dod6-proof",
        dispatch_id="dispatch-dod6",
        token=lambda: "synthetic-github-token",
        git_author=_GIT_AUTHOR,
        review_fix_visit_cap=4,
    )

    assert error is None
    assert chosen.slot is not None
    assert chosen.slot.slot == _SLOT_B
    pooled = policy.pool_read() if policy.pool_read is not None else ()
    skipped = {reading.slot.slot: reading.slot.skip_kind for reading in pooled if reading.slot}
    assert skipped == {_SLOT_A: "floor", _SLOT_B: None}
    [projected] = _PROJECTED.findall(overlay.read_text(encoding="utf-8"))
    assert _fingerprint(value=projected) == _fingerprint(value=_B_VALUE)
    assert _fingerprint(value=projected) != _fingerprint(value=_BARE_VALUE)
    assert _fingerprint(value=projected) != _fingerprint(value=_A_VALUE)
