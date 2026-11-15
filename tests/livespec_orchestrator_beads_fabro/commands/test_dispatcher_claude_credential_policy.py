"""A numbered-slot dispatcher draws its Claude credential only from its declared slots.

Binds the R01 rule proposed in orchestrator PR #5346 (R02/R10, plan epic
overseer-iyfjbo): under `dispatcher.claude_credential_policy` mode
`numbered-slots`, the factory pool is exactly the declared slots that are
injected non-empty. An undeclared numbered slot and the unnumbered
`CLAUDE_CODE_OAUTH_TOKEN` are never assessed or chosen, and the selector skips
any declared slot that is exhausted or below the headroom floor.

The fleet shape the coordinator ruled on 2026-11-15 is the allow-list
anthropic-2, -4, -5 and -6, with anthropic-0, -1 and -3 excluded.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential_policy import (
    LEGACY_INDEPENDENT,
    NUMBERED_SLOTS,
    ClaudeCredentialPolicy,
    parse_claude_credential_policy,
    resolve_claude_credential_policy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    SELECTED_ACCOUNT_RECORD_REL,
    injected_credential_slots,
    register_admission_slot_chooser,
    register_claude_credential_policy,
    select_factory_credential,
)
from returns.io import IOFailure, IOSuccess
from returns.result import Failure, Success

_NOW = "2026-11-15T08:00:00Z"
_PREFIX = "CLAUDE_CODE_OAUTH_TOKEN__"
_LEGACY = "CLAUDE_CODE_OAUTH_TOKEN"
_PLUGIN = "livespec-orchestrator-beads-fabro"


def _slot(n: int) -> str:
    return f"{_PREFIX}ANTHROPIC_{n}"


_ALLOW_LIST = (_slot(2), _slot(4), _slot(5), _slot(6))
_FLEET_POLICY = ClaudeCredentialPolicy(mode=NUMBERED_SLOTS, slots=_ALLOW_LIST)


@pytest.fixture(autouse=True)
def _clear_registrations() -> Iterator[None]:
    yield
    register_claude_credential_policy(policy=None)
    register_admission_slot_chooser(chooser=None)


def _write_config(*, repo: Path, policy: object) -> None:
    config = {_PLUGIN: {"dispatcher": {"claude_credential_policy": policy}}}
    (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")


def _reader(*, utilization_by_token: dict[str, float]) -> Any:
    def _read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        return headroom.session_headroom_reading(
            credential_identity=f"id-{token}",
            observed_at=observed_at,
            utilization=utilization_by_token[token or ""],
        )

    return _read


def _every_fleet_slot(*, monkeypatch: pytest.MonkeyPatch, home: Path) -> dict[str, str]:
    monkeypatch.setenv("HOME", str(home))
    environ = {_slot(n): f"tok-{n}" for n in range(7)}
    environ[_LEGACY] = "tok-legacy"
    for name, token in environ.items():
        monkeypatch.setenv(name, token)
    return environ


def test_four_exhausted_and_two_with_headroom_chooses_two_from_the_allow_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environ = _every_fleet_slot(monkeypatch=monkeypatch, home=tmp_path)
    _write_config(repo=tmp_path, policy={"mode": NUMBERED_SLOTS, "slots": list(_ALLOW_LIST)})
    seen: list[str | None] = []
    utilization = {f"tok-{n}": 0.0 for n in range(7)} | {"tok-legacy": 0.0}
    utilization |= {"tok-4": 100.0, "tok-5": 100.0, "tok-6": 100.0, "tok-2": 10.0}
    read = _reader(utilization_by_token=utilization)

    def _recording(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        seen.append(token)
        return read(token=token, observed_at=observed_at)

    policy = headroom_gate.session_headroom_policy(
        repo=tmp_path, now_iso=_NOW, journal_path=None, read=_recording
    )

    chosen = policy.read()
    pooled = policy.pool_read() if policy.pool_read is not None else ()
    choice = select_factory_credential(environ=environ, home=tmp_path, warn=print)

    assert chosen.slot is not None
    assert chosen.slot.slot == _slot(2)
    assert choice.env_name == _slot(2)
    assert sorted(token or "" for token in seen) == ["tok-2", "tok-4", "tok-5", "tok-6"]
    rows = {reading.slot.slot: reading.slot for reading in pooled if reading.slot is not None}
    assert set(rows) == set(_ALLOW_LIST)
    assert {name: rows[name].skip_kind for name in (_slot(4), _slot(5), _slot(6))} == {
        _slot(4): "floor",
        _slot(5): "floor",
        _slot(6): "floor",
    }


def test_the_pool_is_only_declared_injected_slots_and_never_the_unnumbered_token() -> None:
    register_claude_credential_policy(policy=_FLEET_POLICY)
    environ = {_slot(n): "x" for n in (0, 1, 3, 4)} | {_slot(6): "", _LEGACY: "t"}

    assert injected_credential_slots(environ=environ) == (_slot(4),)
    assert injected_credential_slots(environ={_slot(1): "x", _LEGACY: "t"}) == ()


def test_legacy_independent_and_no_policy_keep_the_unnumbered_fallback() -> None:
    register_claude_credential_policy(
        policy=ClaudeCredentialPolicy(mode=LEGACY_INDEPENDENT, slots=())
    )
    assert injected_credential_slots(environ={_LEGACY: "t"}) == (_LEGACY,)
    register_claude_credential_policy(policy=None)
    assert injected_credential_slots(environ={_LEGACY: "t", _slot(1): "x"}) == (_slot(1),)


def test_the_selector_never_falls_back_to_an_undeclared_or_unnumbered_credential(
    tmp_path: Path,
) -> None:
    register_claude_credential_policy(policy=_FLEET_POLICY)
    warnings: list[str] = []
    record = tmp_path / SELECTED_ACCOUNT_RECORD_REL
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"profile": "anthropic-1"}), encoding="utf-8")
    environ = {_slot(1): "x", _slot(3): "y", _LEGACY: "t"}

    choice = select_factory_credential(environ=environ, home=tmp_path, warn=warnings.append)

    assert choice.env_name in _ALLOW_LIST
    assert choice.env_name not in environ
    assert choice.fallback_reason is not None
    assert "no declared numbered slot" in choice.fallback_reason
    assert len(warnings) == 1


def test_the_selector_follows_a_declared_caam_profile_and_the_admitted_slot(
    tmp_path: Path,
) -> None:
    register_claude_credential_policy(policy=_FLEET_POLICY)
    record = tmp_path / SELECTED_ACCOUNT_RECORD_REL
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"profile": "anthropic-5"}), encoding="utf-8")
    environ = {_slot(4): "x", _slot(5): "y"}

    caam = select_factory_credential(environ=environ, home=tmp_path, warn=print)
    register_admission_slot_chooser(chooser=lambda: _slot(4))
    admitted = select_factory_credential(environ=environ, home=tmp_path, warn=print)
    register_admission_slot_chooser(chooser=lambda: None)
    record.write_text(json.dumps({"profile": "anthropic-9"}), encoding="utf-8")
    fallback = select_factory_credential(environ=environ, home=tmp_path, warn=print)

    assert caam.env_name == _slot(5)
    assert caam.fallback_reason is None
    assert admitted.env_name == _slot(4)
    assert fallback.env_name == _slot(4)
    assert fallback.fallback_reason is not None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (
            {"mode": "numbered-slots", "slots": [_slot(2), _slot(4)]},
            ClaudeCredentialPolicy(mode=NUMBERED_SLOTS, slots=(_slot(2), _slot(4))),
        ),
        (
            {"mode": "legacy-independent"},
            ClaudeCredentialPolicy(mode=LEGACY_INDEPENDENT, slots=()),
        ),
    ],
)
def test_a_well_formed_policy_parses(value: object, expected: object) -> None:
    assert parse_claude_credential_policy(value=value) == Success(expected)


@pytest.mark.parametrize(
    "value",
    [
        "numbered-slots",
        {"mode": "other"},
        {"mode": "numbered-slots"},
        {"mode": "numbered-slots", "slots": []},
        {"mode": "numbered-slots", "slots": "CLAUDE_CODE_OAUTH_TOKEN__A"},
        {"mode": "numbered-slots", "slots": [_LEGACY]},
        {"mode": "numbered-slots", "slots": [_slot(2), _slot(2)]},
        {"mode": "numbered-slots", "slots": ["claude_code_oauth_token__a"]},
        {"mode": "numbered-slots", "slots": [7]},
        {"mode": "legacy-independent", "slots": [_slot(2)]},
    ],
)
def test_a_malformed_policy_is_unreadable(value: object) -> None:
    result = parse_claude_credential_policy(value=value)

    assert isinstance(result, Failure)
    assert result.failure().setting == "claude_credential_policy"


def test_the_policy_resolves_from_committed_config(tmp_path: Path) -> None:
    absent = resolve_claude_credential_policy(cwd=tmp_path)
    _write_config(repo=tmp_path, policy={"mode": NUMBERED_SLOTS, "slots": [_slot(4)]})
    declared = resolve_claude_credential_policy(cwd=tmp_path)
    _write_config(repo=tmp_path, policy={"mode": "nope"})
    malformed = resolve_claude_credential_policy(cwd=tmp_path)

    assert absent == IOSuccess(None)
    assert declared == IOSuccess(ClaudeCredentialPolicy(mode=NUMBERED_SLOTS, slots=(_slot(4),)))
    assert isinstance(malformed, IOFailure)


def test_an_unreadable_policy_fails_closed_to_an_empty_pool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _every_fleet_slot(monkeypatch=monkeypatch, home=tmp_path)
    _write_config(repo=tmp_path, policy={"mode": "nope"})
    seen: list[str | None] = []

    def _read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        seen.append(token)
        return headroom.unobservable_session_headroom(
            credential_identity="absent", observed_at=observed_at, reason="absent-credential"
        )

    policy = headroom_gate.session_headroom_policy(
        repo=tmp_path, now_iso=_NOW, journal_path=None, read=_read
    )

    assert policy.read().slot is None
    assert seen == [None]
