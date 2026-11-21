"""A `central-factory-selection` dispatcher draws only the slot the central record names.

Binds `SPECIFICATION/contracts.md` "The dispatcher declares its Claude credential
policy" and "Under `central-factory-selection`, the central factory selection names
the slot", and Scenario 378 (livespec-overseer item overseer-nspnuw):

- The policy accepts `selection: central-factory-selection` only under
  `numbered-slots`, with `central_selection_max_age_minutes` an integer 1..1440
  (default 60).
- The record `factory-selected-account.json` names the ONE pool slot, assessed
  under the ordinary headroom paragraph; no other slot is assessed or projected.
- A missing, unreadable, unparseable, null-profile, stale, undeclared or
  uninjected record skips covered candidates with `no-central-factory-selection`
  carrying the record's reason or the condition, and an uncovered fallback
  continues.
- The named slot failing its own headroom skips; it never moves to another slot.
- The journal names the record's profile, written_at, the slot's opaque identity
  and the outcome, and never a credential value.

The fixtures are real-shaped records (the four fields the overseer writes); no
fixture holds a credential value, only placeholder tokens injected as env.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_central_factory_selection as central_module,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_claude_credential_policy as policy_module,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_factory_account_selector as selector,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import (
    CLAUDE_AGENT_ID,
    CODEX_AGENT_ID,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import PreflightInputs
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import AcpHoldLedger
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    build_acp_preflight_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential_policy import (
    CENTRAL_FACTORY_SELECTION,
    LEGACY_INDEPENDENT,
    NUMBERED_SLOTS,
    ClaudeCredentialPolicy,
    ClaudeCredentialRefusal,
    parse_claude_credential_policy,
    resolve_claude_credential_policy,
)
from returns.result import Failure, Success

_PLUGIN = "livespec-orchestrator-beads-fabro"
_PREFIX = "CLAUDE_CODE_OAUTH_TOKEN__"
_SLOT_4 = f"{_PREFIX}ANTHROPIC_4"
_SLOT_5 = f"{_PREFIX}ANTHROPIC_5"
_NOW_ISO = "2026-11-21T12:00:00Z"
_NOW = datetime(2026, 11, 21, 12, 0, 0, tzinfo=timezone.utc)
_FIVE_MINUTES_AGO = "2026-11-21T11:55:00Z"
_NINETY_MINUTES_AGO = "2026-11-21T10:30:00Z"
_TOKENS = {_SLOT_4: "placeholder-4", _SLOT_5: "placeholder-5"}
_GRAPH = """
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="a", timeout="60s"]
    gate [shape=parallelogram, timeout="60s"]
    start -> implement
    implement -> gate
    gate -> exit [label="green", condition="outcome=succeeded"]
"""


def _central_policy(*, age: int = 60) -> ClaudeCredentialPolicy:
    return ClaudeCredentialPolicy(
        mode=NUMBERED_SLOTS,
        slots=(_SLOT_4, _SLOT_5),
        selection=CENTRAL_FACTORY_SELECTION,
        central_selection_max_age_minutes=age,
    )


def _write_record(*, home: Path, payload: object) -> None:
    path = home / central_module.FACTORY_SELECTION_RECORD_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")


def _record(
    *, profile: str | None = "anthropic-5", written_at: str = _FIVE_MINUTES_AGO
) -> dict[str, object]:
    return {
        "account_uuid": None if profile is None else "0d4f6c1e-9a52-4a7b-8c3e-5b1f2d7a9e60",
        "profile": profile,
        "reason": None if profile is not None else "no account qualifies",
        "written_at": written_at,
    }


@pytest.fixture(autouse=True)
def _real_policy_resolver(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Undo the suite's undeclared-means-legacy seam and pin HOME to the fixture."""
    monkeypatch.setattr(
        policy_module, "resolve_claude_credential_policy", resolve_claude_credential_policy
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    for name in (_SLOT_4, _SLOT_5):
        monkeypatch.setenv(name, _TOKENS[name])


def _write_config(*, repo: Path, policy: object) -> None:
    config = {_PLUGIN: {"dispatcher": {"claude_credential_policy": policy}}}
    (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")


def _central_config(*, repo: Path) -> None:
    _write_config(
        repo=repo,
        policy={
            "mode": NUMBERED_SLOTS,
            "slots": [_SLOT_4, _SLOT_5],
            "selection": CENTRAL_FACTORY_SELECTION,
        },
    )


# --- the policy --------------------------------------------------------------


def test_the_central_policy_parses_with_the_default_and_an_explicit_age() -> None:
    base = {"mode": NUMBERED_SLOTS, "slots": [_SLOT_4], "selection": CENTRAL_FACTORY_SELECTION}

    default = parse_claude_credential_policy(value=base)
    explicit = parse_claude_credential_policy(
        value=base | {"central_selection_max_age_minutes": 1440}
    )
    local = parse_claude_credential_policy(value={"mode": NUMBERED_SLOTS, "slots": [_SLOT_4]})
    legacy_local = parse_claude_credential_policy(
        value={"mode": LEGACY_INDEPENDENT, "selection": "local-ranking"}
    )

    assert default == Success(
        ClaudeCredentialPolicy(
            mode=NUMBERED_SLOTS,
            slots=(_SLOT_4,),
            selection=CENTRAL_FACTORY_SELECTION,
            central_selection_max_age_minutes=60,
        )
    )
    assert explicit.unwrap().central_selection_max_age_minutes == 1440
    assert local.unwrap().selection == "local-ranking"
    assert legacy_local.unwrap().mode == LEGACY_INDEPENDENT


@pytest.mark.parametrize(
    ("extra", "defect"),
    [
        ({"selection": "fastest"}, "selection must be"),
        ({"selection": 3}, "selection must be"),
        ({"central_selection_max_age_minutes": 0}, "central_selection_max_age_minutes must be"),
        ({"central_selection_max_age_minutes": 1441}, "central_selection_max_age_minutes must be"),
        ({"central_selection_max_age_minutes": "60"}, "central_selection_max_age_minutes must be"),
        ({"central_selection_max_age_minutes": True}, "central_selection_max_age_minutes must be"),
    ],
)
def test_a_malformed_selection_or_age_is_a_configuration_refusal(
    extra: dict[str, object], defect: str
) -> None:
    parsed = parse_claude_credential_policy(
        value={"mode": NUMBERED_SLOTS, "slots": [_SLOT_4]} | extra
    )

    assert isinstance(parsed, Failure)
    assert "dispatcher.claude_credential_policy" in parsed.failure().detail
    assert defect in parsed.failure().detail


def test_central_selection_under_legacy_independent_is_refused() -> None:
    parsed = parse_claude_credential_policy(
        value={"mode": LEGACY_INDEPENDENT, "selection": CENTRAL_FACTORY_SELECTION}
    )

    assert isinstance(parsed, Failure)
    assert "requires mode numbered-slots" in parsed.failure().detail


def test_a_refusal_without_a_condition_skips_by_its_cause() -> None:
    bare = ClaudeCredentialRefusal(cause="no-declared-slot-injected", detail="d")

    assert bare.skip_condition == "no-declared-slot-injected"


# --- the record reader -------------------------------------------------------


def _read(*, home: Path, policy: ClaudeCredentialPolicy | None = None, **env: str):
    return central_module.read_central_factory_selection(
        home=home, policy=policy or _central_policy(), environ=env or dict(_TOKENS), now=_NOW
    )


def test_the_slot_is_the_upper_cased_profile_with_underscores() -> None:
    assert central_module.derived_slot_name(profile="anthropic-5") == _SLOT_5


def test_a_current_record_names_its_slot(tmp_path: Path) -> None:
    _write_record(home=tmp_path, payload=_record())

    selection = _read(home=tmp_path)

    assert selection.slot == _SLOT_5
    assert selection.profile == "anthropic-5"
    assert selection.written_at == _FIVE_MINUTES_AGO
    assert selection.refusal is None


def test_a_record_exactly_at_the_maximum_age_is_still_current(tmp_path: Path) -> None:
    _write_record(home=tmp_path, payload=_record(written_at="2026-11-21T11:00:00Z"))

    assert _read(home=tmp_path).slot == _SLOT_5


@pytest.mark.parametrize(
    ("payload", "condition"),
    [
        (None, "record absent"),
        ("{not json", "does not parse"),
        ("[]", "not an object"),
        (_record(profile=""), "unusable profile or written_at"),
        (_record(profile="x") | {"profile": 5}, "unusable profile or written_at"),
        (_record() | {"written_at": "yesterday"}, "unusable profile or written_at"),
        (_record() | {"written_at": 7}, "unusable profile or written_at"),
        (_record(profile=None), "record names no account: no account qualifies"),
        (_record(written_at=_NINETY_MINUTES_AGO), "stale record"),
        (_record(profile="anthropic-9"), f"{_PREFIX}ANTHROPIC_9 is not declared"),
    ],
)
def test_an_unusable_record_skips_with_the_named_condition(
    tmp_path: Path, payload: object, condition: str
) -> None:
    if payload is not None:
        _write_record(home=tmp_path, payload=payload)

    selection = _read(home=tmp_path)

    assert selection.slot is None
    assert selection.refusal is not None
    assert selection.refusal.cause == "no-central-factory-selection"
    assert condition in selection.refusal.skip_condition
    assert not selection.refusal.configuration


def test_a_null_profile_record_carries_its_own_reason_even_without_one(tmp_path: Path) -> None:
    _write_record(home=tmp_path, payload=_record(profile=None) | {"reason": None})

    selection = _read(home=tmp_path)

    assert selection.reason is None
    assert selection.refusal is not None
    assert selection.refusal.detail.endswith("record names no account")


def test_a_stale_record_names_the_record_and_keeps_its_fields(tmp_path: Path) -> None:
    _write_record(home=tmp_path, payload=_record(written_at=_NINETY_MINUTES_AGO))

    selection = _read(home=tmp_path)

    assert selection.profile == "anthropic-5"
    assert selection.written_at == _NINETY_MINUTES_AGO
    assert selection.refusal is not None
    assert _NINETY_MINUTES_AGO in selection.refusal.detail


def test_a_named_slot_that_is_not_injected_non_empty_skips(tmp_path: Path) -> None:
    _write_record(home=tmp_path, payload=_record())

    selection = _read(home=tmp_path, **{_SLOT_4: "placeholder-4", _SLOT_5: ""})

    assert selection.slot is None
    assert selection.refusal is not None
    assert "not injected non-empty" in selection.refusal.detail


def test_an_unreadable_record_skips(tmp_path: Path) -> None:
    record = tmp_path / central_module.FACTORY_SELECTION_RECORD_REL
    record.parent.mkdir(parents=True)
    record.mkdir()

    selection = _read(home=tmp_path)

    assert selection.refusal is not None
    assert "unreadable or does not parse" in selection.refusal.detail


def test_the_record_path_is_the_overseers_fixed_location() -> None:
    assert (
        Path(".local/state/caam-usage-rotate/factory-selected-account.json")
        == central_module.FACTORY_SELECTION_RECORD_REL
    )


# --- the selector ------------------------------------------------------------


def _select(*, repo: Path, **kwargs: Any) -> Any:
    return selector.select_factory_credential(
        repo=repo, environ=dict(_TOKENS), home=repo, warn=print, **kwargs
    )


def test_the_selector_names_the_record_slot_and_never_the_first_declared(tmp_path: Path) -> None:
    _central_config(repo=tmp_path)
    _write_record(home=tmp_path, payload=_record())

    choice = _select(repo=tmp_path, now=_NOW)

    assert choice.env_name == _SLOT_5


def test_the_selector_refuses_without_a_current_record_rather_than_fall_back(
    tmp_path: Path,
) -> None:
    _central_config(repo=tmp_path)

    absent = _select(repo=tmp_path)
    _write_record(home=tmp_path, payload=_record(written_at=_NINETY_MINUTES_AGO))
    stale = _select(repo=tmp_path, now=_NOW)

    assert isinstance(absent, ClaudeCredentialRefusal)
    assert absent.cause == "no-central-factory-selection"
    assert isinstance(stale, ClaudeCredentialRefusal)
    assert "stale record" in stale.detail
    assert all(token not in stale.detail for token in _TOKENS.values())


def test_the_interactive_selection_is_never_read(tmp_path: Path) -> None:
    _central_config(repo=tmp_path)
    _write_record(home=tmp_path, payload=_record())
    interactive = tmp_path / selector.SELECTED_ACCOUNT_RECORD_REL
    interactive.write_text(json.dumps({"profile": "anthropic-4"}), encoding="utf-8")
    interactive.chmod(0)

    try:
        choice = _select(repo=tmp_path, now=_NOW)
    finally:
        interactive.chmod(0o600)

    assert choice.env_name == _SLOT_5


def test_pool_and_admission_helpers_follow_the_central_selection(tmp_path: Path) -> None:
    _central_config(repo=tmp_path)
    _write_record(home=tmp_path, payload=_record())
    policy = _central_policy()
    named = central_module.read_central_factory_selection(
        home=tmp_path, policy=policy, environ=_TOKENS, now=_NOW
    )
    none_named = central_module.read_central_factory_selection(
        home=tmp_path / "elsewhere", policy=policy, environ=_TOKENS, now=_NOW
    )

    assert selector.injected_credential_slots(environ=_TOKENS, policy=policy, central=named) == (
        _SLOT_5,
    )
    assert (
        selector.injected_credential_slots(environ=_TOKENS, policy=policy, central=none_named) == ()
    )
    assert (
        selector.admission_credential_refusal(resolved=policy, environ=_TOKENS, central=named)
        is None
    )
    assert (
        selector.admission_credential_refusal(resolved=policy, environ=_TOKENS, central=none_named)
        is none_named.refusal
    )
    # No `central` supplied: the pool and the refusal each read the record themselves.
    assert selector.policy_pool_slots(repo=tmp_path, environ=_TOKENS) == (_SLOT_5,)
    assert selector.repo_credential_refusal(repo=tmp_path, environ=_TOKENS) is None
    assert selector.policy_pool_slots(repo=tmp_path, environ=_TOKENS, central=none_named) == ()


def test_central_selection_for_is_none_unless_the_policy_asks_for_it(tmp_path: Path) -> None:
    local = ClaudeCredentialPolicy(mode=NUMBERED_SLOTS, slots=(_SLOT_4,))
    refusal = ClaudeCredentialRefusal(cause="c", detail="d")

    assert selector.central_selection_for(policy=local, environ={}, home=tmp_path, now=_NOW) is None
    assert (
        selector.central_selection_for(policy=refusal, environ={}, home=tmp_path, now=_NOW) is None
    )


# --- admission ---------------------------------------------------------------


def _reader(*, utilization_by_token: dict[str, float], seen: list[str | None]) -> Any:
    def _read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        seen.append(token)
        return headroom.session_headroom_reading(
            credential_identity=f"id-{(token or '').rsplit('-', 1)[-1]}",
            observed_at=observed_at,
            utilization=utilization_by_token[token or ""],
        )

    return _read


def _gate(*, repo: Path, utilization: dict[str, float], seen: list[str | None]) -> Any:
    return headroom_gate.session_headroom_policy(
        repo=repo,
        now_iso=_NOW_ISO,
        journal_path=None,
        register_chooser=False,
        read=_reader(utilization_by_token=utilization, seen=seen),
    )


def test_only_the_named_slot_is_assessed_and_chosen_even_when_another_reads_more_headroom(
    tmp_path: Path,
) -> None:
    _central_config(repo=tmp_path)
    _write_record(home=tmp_path, payload=_record())
    seen: list[str | None] = []

    policy = _gate(
        repo=tmp_path,
        utilization={_TOKENS[_SLOT_5]: 40.0, _TOKENS[_SLOT_4]: 0.0},
        seen=seen,
    )
    chosen = policy.read()

    assert policy.credential_refusal is None
    assert chosen.slot is not None
    assert chosen.slot.slot == _SLOT_5
    assert seen == [_TOKENS[_SLOT_5]]
    assert policy.central_selection is not None
    assert policy.central_selection.slot == _SLOT_5


def test_the_named_slot_failing_its_floor_is_not_replaced_by_another(tmp_path: Path) -> None:
    _central_config(repo=tmp_path)
    _write_record(home=tmp_path, payload=_record())
    seen: list[str | None] = []

    policy = _gate(
        repo=tmp_path,
        utilization={_TOKENS[_SLOT_5]: 95.0, _TOKENS[_SLOT_4]: 0.0},
        seen=seen,
    )

    slot = policy.read().slot
    assert slot is not None
    assert (slot.slot, slot.chosen, slot.skip_kind) == (_SLOT_5, False, "floor")
    assert seen == [_TOKENS[_SLOT_5]]


@pytest.mark.parametrize(
    "payload",
    [None, _record(profile=None), _record(written_at=_NINETY_MINUTES_AGO)],
)
def test_no_usable_record_assesses_no_slot_at_all(tmp_path: Path, payload: object) -> None:
    _central_config(repo=tmp_path)
    if payload is not None:
        _write_record(home=tmp_path, payload=payload)
    seen: list[str | None] = []

    policy = _gate(repo=tmp_path, utilization={}, seen=seen)

    assert policy.credential_refusal is not None
    assert policy.credential_refusal.cause == "no-central-factory-selection"
    assert seen == []


def test_local_ranking_is_unchanged_when_selection_is_absent(tmp_path: Path) -> None:
    _write_config(repo=tmp_path, policy={"mode": NUMBERED_SLOTS, "slots": [_SLOT_4, _SLOT_5]})
    _write_record(home=tmp_path, payload=_record(profile="anthropic-4"))
    seen: list[str | None] = []

    policy = _gate(
        repo=tmp_path,
        utilization={_TOKENS[_SLOT_5]: 10.0, _TOKENS[_SLOT_4]: 50.0},
        seen=seen,
    )

    assert policy.read().slot is not None
    assert policy.read().slot.slot == _SLOT_5
    assert sorted(token or "" for token in seen) == sorted(_TOKENS.values())
    assert policy.central_selection is None


# --- the verdict and the journal ---------------------------------------------


def _candidate(*, agent_id: str) -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command=f"{agent_id}-adapter", env={}, args=()),
        identity=AcpCandidateIdentity(
            display_name=f"{agent_id}/model",
            candidate_key=f"{agent_id}-model",
            availability_key=f"{agent_id}-account",
        ),
        agent_id=agent_id,
    )


def _chain(*candidates: AcpCandidate) -> ResolvedAcpChain:
    return ResolvedAcpChain(
        node="implement",
        primary=candidates[0],
        fallbacks=candidates[1:],
        enabled=True,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _verdict(*, repo: Path, utilization: dict[str, float], chain: ResolvedAcpChain) -> Any:
    # Codex headroom is a separate clause; leave the fallback uncovered here.
    policy = replace(_gate(repo=repo, utilization=utilization, seen=[]), codex_read=None)
    return build_acp_preflight_verdict(
        chains={"implement": chain},
        graph_text=_GRAPH,
        ledger=AcpHoldLedger(holds=(), unobservable=(), observation_ids=frozenset()),
        inputs=PreflightInputs(headroom=policy),
    )


def _central_rows(journal: _Journal) -> list[dict[str, object]]:
    return [row for row in journal.records if row["stage"] == "central-factory-selection"]


def test_a_missing_record_skips_the_covered_primary_and_continues_to_the_codex_fallback(
    tmp_path: Path,
) -> None:
    _central_config(repo=tmp_path)
    claude = _candidate(agent_id=CLAUDE_AGENT_ID)
    codex = _candidate(agent_id=CODEX_AGENT_ID)

    verdict = _verdict(repo=tmp_path, utilization={}, chain=_chain(claude, codex))

    (node,) = verdict.nodes
    assert verdict.viable
    assert node.candidates == (codex,)
    (skip,) = node.skipped
    assert skip.reason == "claude-credential-policy-refusal"
    assert skip.condition is not None
    assert skip.condition.startswith("no-central-factory-selection: record absent")


def test_a_null_profile_with_no_fallback_leaves_the_node_empty_and_carries_the_reason(
    tmp_path: Path,
) -> None:
    _central_config(repo=tmp_path)
    _write_record(home=tmp_path, payload=_record(profile=None))

    verdict = _verdict(
        repo=tmp_path, utilization={}, chain=_chain(_candidate(agent_id=CLAUDE_AGENT_ID))
    )
    journal = _Journal()
    headroom_gate.journal_session_headroom(work_item_id="bd-x", verdict=verdict, journal=journal)

    assert not verdict.viable
    assert "no account qualifies" in verdict.detail
    (row,) = _central_rows(journal)
    assert row["profile"] is None
    assert row["slot_identity"] is None
    assert row["reason"] == "no account qualifies"
    assert "no account qualifies" in str(row["outcome"])


def test_the_dispatch_record_names_the_selection_it_followed(tmp_path: Path) -> None:
    _central_config(repo=tmp_path)
    _write_record(home=tmp_path, payload=_record())
    verdict = _verdict(
        repo=tmp_path,
        utilization={_TOKENS[_SLOT_5]: 10.0},
        chain=_chain(_candidate(agent_id=CLAUDE_AGENT_ID)),
    )
    journal = _Journal()

    headroom_gate.journal_session_headroom(work_item_id="bd-x", verdict=verdict, journal=journal)

    (row,) = _central_rows(journal)
    assert row["profile"] == "anthropic-5"
    assert row["written_at"] == _FIVE_MINUTES_AGO
    assert row["outcome"] == "named-slot-admitted"
    assert row["work_item_id"] == "bd-x"
    identity = row["slot_identity"]
    assert isinstance(identity, str)
    assert identity not in {*_TOKENS.values(), ""}
    assert all(token not in json.dumps(journal.records) for token in _TOKENS.values())


def test_a_named_slot_below_the_floor_is_journaled_as_a_headroom_skip(tmp_path: Path) -> None:
    _central_config(repo=tmp_path)
    _write_record(home=tmp_path, payload=_record())
    verdict = _verdict(
        repo=tmp_path,
        utilization={_TOKENS[_SLOT_5]: 95.0, _TOKENS[_SLOT_4]: 0.0},
        chain=_chain(_candidate(agent_id=CLAUDE_AGENT_ID)),
    )
    journal = _Journal()

    headroom_gate.journal_session_headroom(work_item_id="bd-x", verdict=verdict, journal=journal)

    (row,) = _central_rows(journal)
    assert row["outcome"] == "named-slot-headroom-skipped"
    chosen = {
        assessment.slot.slot for assessment in verdict.headroom_assessments if assessment.slot
    }
    assert chosen == {_SLOT_5}


def test_no_central_row_is_written_under_local_ranking(tmp_path: Path) -> None:
    _write_config(repo=tmp_path, policy={"mode": NUMBERED_SLOTS, "slots": [_SLOT_4, _SLOT_5]})
    verdict = _verdict(
        repo=tmp_path,
        utilization={_TOKENS[_SLOT_5]: 10.0, _TOKENS[_SLOT_4]: 10.0},
        chain=_chain(_candidate(agent_id=CLAUDE_AGENT_ID)),
    )
    journal = _Journal()

    headroom_gate.journal_session_headroom(work_item_id="bd-x", verdict=verdict, journal=journal)

    assert _central_rows(journal) == []
