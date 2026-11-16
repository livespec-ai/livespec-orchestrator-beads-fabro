"""A dispatcher draws its Claude credential only under its declared credential policy.

Binds `SPECIFICATION/contracts.md` v382, "The dispatcher declares its Claude
credential policy", and Scenario 376 (plan epic overseer-iyfjbo, R01), for the
policy loader and every downstream consumer:

- An ABSENT or INVALID `dispatcher.claude_credential_policy` is a configuration
  refusal naming the key and the defect; it is never read as
  `legacy-independent`, and a caam record cannot route around it.
- `select_factory_credential` reads the policy from the repository it is handed
  on EVERY call, so the credential-status probe, the re-probe wait, the
  availability probe, the projection and the judgement apply it with or without
  an admission pass having run first.
- Under `numbered-slots` the pool is exactly the declared slots injected
  non-empty. With none, the call refuses `no-declared-slot-injected`, naming each
  declared slot as absent or empty; the unnumbered `CLAUDE_CODE_OAUTH_TOKEN` and
  undeclared numbered variables are never substituted. A consumer whose admitted
  slot is gone refuses rather than choose another credential.
- The host judgement does not run its Claude model under a refusing policy, and
  its did-not-run line names the defect; an uncovered (Codex) candidate still runs.

This repository's committed declaration is `numbered-slots` with
CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4 and CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_5
(throughput-plans-coordinator ruling, 2026-11-16). The four-slot list in the
headroom case below is a fixture of this module, not the committed one.

The suite reads an UNDECLARED policy as `legacy-independent` (`conftest.py`);
this module restores the real resolver so the absent-policy refusal is exercised.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_claude_credential_policy as policy_module,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_factory_account_selector as selector,
)
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
    register_admission_slot_chooser,
    select_factory_credential,
)
from returns.io import IOFailure, IOSuccess
from returns.result import Failure, Success

_NOW = "2026-11-16T08:00:00Z"
_PREFIX = "CLAUDE_CODE_OAUTH_TOKEN__"
_LEGACY = "CLAUDE_CODE_OAUTH_TOKEN"
_PLUGIN = "livespec-orchestrator-beads-fabro"
_KEY = "dispatcher.claude_credential_policy"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SLOT_A = f"{_PREFIX}A"
_SLOT_B = f"{_PREFIX}B"
_SLOT_C = f"{_PREFIX}C"


def _slot(n: int) -> str:
    return f"{_PREFIX}ANTHROPIC_{n}"


_ALLOW_LIST = (_slot(2), _slot(4), _slot(5), _slot(6))


@pytest.fixture(autouse=True)
def _real_policy_resolver(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Undo the suite's undeclared-means-legacy test seam for this module."""
    monkeypatch.setattr(
        policy_module, "resolve_claude_credential_policy", resolve_claude_credential_policy
    )
    yield
    register_admission_slot_chooser(chooser=None)


def _write_config(*, repo: Path, policy: object) -> None:
    config = {_PLUGIN: {"dispatcher": {"claude_credential_policy": policy}}}
    (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")


def _numbered(*slots: str) -> dict[str, object]:
    return {"mode": NUMBERED_SLOTS, "slots": list(slots)}


def _publish_caam(*, home: Path, profile: str) -> None:
    record = home / SELECTED_ACCOUNT_RECORD_REL
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"profile": profile}), encoding="utf-8")


def _select(*, repo: Path, environ: dict[str, str], warn: Any = print) -> Any:
    return select_factory_credential(repo=repo, environ=environ, home=repo, warn=warn)


# --- the policy loader -------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            _numbered(_slot(4), _slot(5)),
            ClaudeCredentialPolicy(mode=NUMBERED_SLOTS, slots=(_slot(4), _slot(5))),
        ),
        (
            {"mode": "legacy-independent"},
            ClaudeCredentialPolicy(mode=LEGACY_INDEPENDENT, slots=()),
        ),
    ],
)
def test_a_well_formed_policy_parses(value: object, expected: object) -> None:
    assert parse_claude_credential_policy(value=value) == Success(expected)


def test_an_absent_policy_is_a_failure_naming_the_key(tmp_path: Path) -> None:
    """Absence is never read as legacy-independent."""
    parsed = parse_claude_credential_policy(value=None)
    resolved = resolve_claude_credential_policy(cwd=tmp_path)

    assert isinstance(parsed, Failure)
    assert _KEY in parsed.failure().detail
    assert "absent" in parsed.failure().detail
    assert isinstance(resolved, IOFailure)


@pytest.mark.parametrize(
    ("value", "defect"),
    [
        ("numbered-slots", "must be an object"),
        ({"mode": "fleet"}, "mode must be"),
        ({"mode": "numbered-slots"}, "non-empty array"),
        ({"mode": "numbered-slots", "slots": []}, "non-empty array"),
        ({"mode": "numbered-slots", "slots": "CLAUDE_CODE_OAUTH_TOKEN__A"}, "non-empty array"),
        ({"mode": "numbered-slots", "slots": [_LEGACY]}, "must match"),
        ({"mode": "numbered-slots", "slots": ["OTHER_TOKEN"]}, "must match"),
        ({"mode": "numbered-slots", "slots": [7]}, "must match"),
        ({"mode": "numbered-slots", "slots": [_slot(2), _slot(2)]}, "distinct"),
        ({"mode": "legacy-independent", "slots": [_slot(2)]}, "slots must be absent"),
    ],
)
def test_a_malformed_policy_refuses_naming_its_defect(
    value: object, defect: str, tmp_path: Path
) -> None:
    """Grade point 3: a malformed policy is carried into a refusal, never an empty pool."""
    parsed = parse_claude_credential_policy(value=value)
    _write_config(repo=tmp_path, policy=value)

    refusal = _select(repo=tmp_path, environ={_slot(4): "x", _LEGACY: "t"})

    assert isinstance(parsed, Failure)
    assert parsed.failure().setting == "claude_credential_policy"
    assert isinstance(refusal, policy_module.ClaudeCredentialRefusal)
    assert refusal.configuration
    assert refusal.cause == policy_module.CLAUDE_CREDENTIAL_POLICY_INVALID
    assert _KEY in refusal.detail
    assert defect in refusal.detail


def test_the_committed_declaration_is_the_factory_half_of_the_partition() -> None:
    assert resolve_claude_credential_policy(cwd=_REPO_ROOT) == IOSuccess(
        ClaudeCredentialPolicy(mode=NUMBERED_SLOTS, slots=(_slot(4), _slot(5)))
    )


# --- the selector ------------------------------------------------------------


def test_a_missing_policy_refuses_even_when_a_caam_record_names_anthropic_0(
    tmp_path: Path,
) -> None:
    """Grade point 1: no any-slot rule survives an absent policy."""
    _publish_caam(home=tmp_path, profile="anthropic-0")
    environ = {_slot(0): "tok-0", _slot(4): "tok-4", _LEGACY: "tok-legacy"}
    warnings: list[str] = []

    refusal = _select(repo=tmp_path, environ=environ, warn=warnings.append)

    assert isinstance(refusal, policy_module.ClaudeCredentialRefusal)
    assert refusal.configuration
    assert refusal.cause == policy_module.CLAUDE_CREDENTIAL_POLICY_ABSENT
    assert refusal.detail.startswith("configuration refusal: ")
    assert _KEY in refusal.detail
    assert all(token not in refusal.detail for token in environ.values())
    assert warnings == []


def test_the_selector_reads_the_policy_on_every_call(tmp_path: Path) -> None:
    """Grade point 2: no registration side effect; each call reads the repository."""
    environ = {_slot(4): "x", _slot(5): "y", _LEGACY: "t"}

    _write_config(repo=tmp_path, policy=_numbered(_slot(4), _slot(5)))
    first = _select(repo=tmp_path, environ=environ)
    _write_config(repo=tmp_path, policy=_numbered(_slot(5)))
    second = _select(repo=tmp_path, environ=environ)

    assert first.env_name == _slot(4)
    assert first.fallback_reason is None
    assert second.env_name == _slot(5)


def test_no_declared_slot_injected_names_each_declared_slot_absent_or_empty(
    tmp_path: Path,
) -> None:
    """Grade point 4: neither the unnumbered token nor an undeclared slot stands in."""
    _write_config(repo=tmp_path, policy=_numbered(_SLOT_A, _SLOT_B))
    _publish_caam(home=tmp_path, profile="c")
    environ = {_SLOT_B: "", _SLOT_C: "tok-c", _LEGACY: "tok-legacy"}

    refusal = _select(repo=tmp_path, environ=environ)

    assert isinstance(refusal, policy_module.ClaudeCredentialRefusal)
    assert not refusal.configuration
    assert refusal.cause == "no-declared-slot-injected"
    assert refusal.detail.startswith("no-declared-slot-injected: ")
    assert f"{_SLOT_A} (absent)" in refusal.detail
    assert f"{_SLOT_B} (empty)" in refusal.detail
    assert _SLOT_C not in refusal.detail
    assert "tok-" not in refusal.detail


def test_a_numbered_policy_never_reads_the_caam_selection(tmp_path: Path) -> None:
    _write_config(repo=tmp_path, policy=_numbered(_slot(4), _slot(5)))
    _publish_caam(home=tmp_path, profile="anthropic-5")

    choice = _select(repo=tmp_path, environ={_slot(4): "x", _slot(5): "y"})

    assert choice.env_name == _slot(4)


def test_a_consumer_refuses_when_the_admitted_slot_is_gone(tmp_path: Path) -> None:
    """Scenario 376: the projection never falls over to another slot or the legacy token."""
    _write_config(repo=tmp_path, policy=_numbered(_SLOT_A, _SLOT_B))
    environ = {_SLOT_B: "tok-b", _LEGACY: "tok-legacy"}

    register_admission_slot_chooser(chooser=lambda: _SLOT_A)
    gone = _select(repo=tmp_path, environ=environ)
    register_admission_slot_chooser(chooser=lambda: _SLOT_B)
    kept = _select(repo=tmp_path, environ=environ)

    assert isinstance(gone, policy_module.ClaudeCredentialRefusal)
    assert gone.cause == "admitted-slot-absent"
    assert not gone.configuration
    assert _SLOT_A in gone.detail
    assert kept.env_name == _SLOT_B


def test_the_legacy_independent_pool_rule() -> None:
    legacy = ClaudeCredentialPolicy(mode=LEGACY_INDEPENDENT, slots=())
    numbered = ClaudeCredentialPolicy(mode=NUMBERED_SLOTS, slots=(_slot(4),))

    assert selector.injected_credential_slots(environ={_LEGACY: "t"}, policy=legacy) == (_LEGACY,)
    assert selector.injected_credential_slots(
        environ={_LEGACY: "t", _slot(1): "x", _slot(3): ""}, policy=legacy
    ) == (_slot(1),)
    assert (
        selector.injected_credential_slots(environ={_slot(1): "x", _LEGACY: "t"}, policy=numbered)
        == ()
    )


def test_the_explicit_legacy_policy_keeps_the_unnumbered_token(tmp_path: Path) -> None:
    _write_config(repo=tmp_path, policy={"mode": "legacy-independent"})
    warnings: list[str] = []

    choice = _select(repo=tmp_path, environ={_LEGACY: "t"}, warn=warnings.append)

    assert choice.env_name == _LEGACY
    assert len(warnings) == 1


def test_the_admission_refusal_names_why_no_covered_candidate_may_run(tmp_path: Path) -> None:
    absent = selector.claude_credential_policy_for(repo=tmp_path)
    numbered = ClaudeCredentialPolicy(mode=NUMBERED_SLOTS, slots=(_SLOT_A,))
    legacy = ClaudeCredentialPolicy(mode=LEGACY_INDEPENDENT, slots=())
    refuse = selector.admission_credential_refusal

    assert refuse(resolved=absent, environ={_LEGACY: "t"}) == absent
    assert refuse(resolved=numbered, environ={_LEGACY: "t"}).cause == "no-declared-slot-injected"
    assert refuse(resolved=numbered, environ={_SLOT_A: "a"}) is None
    assert refuse(resolved=legacy, environ={}) is None


# --- the admission pool ------------------------------------------------------


def _reader(*, utilization_by_token: dict[str, float]) -> Any:
    def _read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        return headroom.session_headroom_reading(
            credential_identity=f"id-{token}",
            observed_at=observed_at,
            utilization=utilization_by_token[token or ""],
        )

    return _read


def test_three_exhausted_and_one_with_headroom_chooses_it_from_the_declared_slots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    environ = {_slot(n): f"tok-{n}" for n in range(7)} | {_LEGACY: "tok-legacy"}
    for name, token in environ.items():
        monkeypatch.setenv(name, token)
    _write_config(repo=tmp_path, policy=_numbered(*_ALLOW_LIST))
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
    choice = _select(repo=tmp_path, environ=environ)

    assert chosen.slot is not None
    assert chosen.slot.slot == _slot(2)
    assert choice.env_name == _slot(2)
    assert sorted(token or "" for token in seen) == ["tok-2", "tok-4", "tok-5", "tok-6"]


def test_a_refusing_policy_assesses_no_slot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(_LEGACY, "tok-legacy")
    monkeypatch.setenv(_slot(4), "tok-4")
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


# --- the downstream consumers ------------------------------------------------


def test_claude_cred_status_refuses_a_missing_policy_as_a_precondition(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from livespec_orchestrator_beads_fabro.commands import _dispatcher_claude_credential_command

    monkeypatch.setenv(_LEGACY, "tok-legacy")

    exit_code = _dispatcher_claude_credential_command.run_claude_cred_status(
        args=argparse.Namespace(as_json=True, repo=str(tmp_path))
    )

    captured = capsys.readouterr()
    assert exit_code == 3
    assert captured.out == ""
    assert "claude-cred-status refused" in captured.err
    assert _KEY in captured.err
    assert "tok-legacy" not in captured.err


def test_the_pre_launch_check_and_the_reprobe_refuse_without_probing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from livespec_orchestrator_beads_fabro.commands import (
        _dispatcher_credential_env,
        _dispatcher_credential_reprobe,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

    _write_config(repo=tmp_path, policy=_numbered(_SLOT_A))
    monkeypatch.setenv(_LEGACY, "tok-legacy")
    probed: list[str] = []
    _probe: Any = lambda *, token: probed.append(token)  # noqa: E731

    refusal = _dispatcher_credential_env.check_credential_env(repo=tmp_path, probe=_probe)
    status = _dispatcher_credential_env.assess_credential_status(repo=tmp_path, probe=_probe)
    _dispatcher_credential_reprobe.await_usable_credential(
        repo=tmp_path,
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        budget=3,
        probe=_probe,
        sleep=lambda _: None,
    )

    assert refusal is not None
    assert "no-declared-slot-injected" in refusal
    assert status.present is False
    assert probed == []


def test_the_pre_launch_check_names_the_slot_the_projection_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from livespec_orchestrator_beads_fabro.commands import _dispatcher_credential_env

    _write_config(repo=tmp_path, policy=_numbered(_SLOT_A))
    monkeypatch.setenv(_SLOT_A, "tok-a")
    from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
        ClaudeCredentialStatus,
    )

    def _probe(*, token: str) -> ClaudeCredentialStatus:
        assert token == "tok-a"
        return ClaudeCredentialStatus(
            condition="usable",
            present=True,
            usable=True,
            http_status=200,
            error_type=None,
            input_tokens=None,
            output_tokens=None,
            message="usable",
            remedy="none",
        )

    checked = _dispatcher_credential_env.checked_credential_env(repo=tmp_path, probe=_probe)

    assert checked == _dispatcher_credential_env.CheckedCredentialEnv(env_name=_SLOT_A)


def test_the_availability_probe_refuses_under_a_missing_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from livespec_orchestrator_beads_fabro.commands._acp_availability_probe_credential import (
        project_probe_credential,
    )
    from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
    from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter

    monkeypatch.setenv(_LEGACY, "tok-legacy")

    result = project_probe_credential(
        repo=tmp_path,
        factory_name="petri",
        server="https://factory.example",
        fabro_bin="fabro",
        environment="livespec-ci",
        candidate=AcpCandidate(
            adapter=AcpAdapter(command="claude-code-acp"), agent_id="claude-acp"
        ),
        builtin=False,
        runner=object(),  # pyright: ignore[reportArgumentType]
    )

    assert isinstance(result, str)
    assert _KEY in result
    assert "tok-legacy" not in result


def test_a_missing_policy_keeps_the_host_judgement_from_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 376: no judge starts, and the did-not-run line names the key."""
    from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
    from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
    from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_candidate_attempt import (
        unavailable_report,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_candidates import (
        run_candidate_chain,
    )

    monkeypatch.setenv(_LEGACY, "tok-legacy")
    started: list[object] = []
    runner = SimpleNamespace(run=lambda **kwargs: started.append(kwargs))

    claude = AcpCandidate(
        adapter=AcpAdapter(command="claude-code-acp", env={"ANTHROPIC_MODEL": "claude-opus-5"}),
        agent_id="claude-acp",
    )

    result = run_candidate_chain(
        prompt="judge",
        cwd=tmp_path,
        runner=runner,  # pyright: ignore[reportArgumentType]
        is_verdict=lambda _: True,
        candidate_resolver=lambda **_: (claude,),
    )

    assert started == []
    assert result.reply is None
    assert result.cause == "dispatcher.claude_credential_policy-absent"
    assert [attempt.outcome for attempt in result.attempts] == [result.cause]
    line = unavailable_report(cause=result.cause, attempts=result.attempts)
    assert "the judgement did not run" in line
    assert _KEY in line
    assert "\n" not in line


def test_an_uncovered_judge_still_runs_after_a_refused_claude_judge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
    from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
    from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_candidates import (
        run_candidate_chain,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

    _write_config(repo=tmp_path, policy=_numbered(_SLOT_A))
    monkeypatch.setenv(_LEGACY, "tok-legacy")
    monkeypatch.setenv("HOME", str(tmp_path))
    environments: list[object] = []

    class _Runner:
        def run(self, **kwargs: object) -> CommandResult:
            environments.append(kwargs)
            return CommandResult(exit_code=0, stdout="VERDICT", stderr="")

    claude = AcpCandidate(adapter=AcpAdapter(command="claude-code-acp"), agent_id="claude-acp")
    codex = AcpCandidate(
        adapter=AcpAdapter(command="codex-acp", env={"CODEX_CONFIG": '{"model": "gpt-5"}'}),
        agent_id="codex-acp",
    )

    result = run_candidate_chain(
        prompt="judge",
        cwd=tmp_path,
        runner=_Runner(),  # pyright: ignore[reportArgumentType]
        is_verdict=lambda reply: reply == "VERDICT",
        candidate_resolver=lambda **_: (claude, codex),
    )

    assert result.reply == "VERDICT"
    assert [attempt.outcome for attempt in result.attempts] == [
        "no-declared-slot-injected",
        "verdict",
    ]
    assert len(environments) == 1
