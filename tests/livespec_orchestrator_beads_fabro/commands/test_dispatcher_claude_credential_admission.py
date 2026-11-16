"""Admission refuses before claim under an absent, invalid or unserved Claude credential policy.

Binds the admission half of `SPECIFICATION/contracts.md` v382, "The dispatcher
declares its Claude credential policy", and Scenario 376:

- An absent or invalid `dispatcher.claude_credential_policy` refuses a dispatch
  with a covered candidate before any claim, as a configuration refusal naming
  the key, and a hand-picked dispatch reports exit code 3.
- Under `numbered-slots` with no declared slot injected, every covered candidate
  is ineligible WITHOUT a reading. A covered primary with an uncovered fallback
  continues to the fallback; when no candidate is left on an admission-required
  node the dispatch is refused `no-declared-slot-injected`, exit code 3.
- A repository declaring no fallback chain is refused too: the no-fallback path
  fails open on graph shapes, never on this refusal.
- A chain offering only uncovered (Codex) candidates is unaffected.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_claude_credential_policy as policy_module,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    acp_preflight_refusal,
    resolve_acp_preflight,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential_policy import (
    resolve_claude_credential_policy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    dispatch_exit_code,
)

_NOW = "2026-11-16T09:00:00Z"
_KEY = "dispatcher.claude_credential_policy"
_LEGACY = "CLAUDE_CODE_OAUTH_TOKEN"
_SLOT_A = "CLAUDE_CODE_OAUTH_TOKEN__A"
_PLUGIN = "livespec-orchestrator-beads-fabro"
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


@pytest.fixture(autouse=True)
def _real_policy_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undo the suite's undeclared-means-legacy test seam for this module."""
    monkeypatch.setattr(
        policy_module, "resolve_claude_credential_policy", resolve_claude_credential_policy
    )
    monkeypatch.setenv(_LEGACY, "tok-legacy")


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


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


def _refusal(*, cause: str) -> policy_module.ClaudeCredentialRefusal:
    return policy_module.ClaudeCredentialRefusal(cause=cause, detail=f"{cause}: the detail")


def _verdict(*, chain: ResolvedAcpChain, refusal: Any) -> Any:
    policy = headroom.SessionHeadroomPolicy(
        floor_percent=20,
        horizon_minutes=180,
        read=lambda: pytest.fail("a refusing policy takes no reading"),
        credential_refusal=refusal,
    )
    return build_acp_preflight_verdict(
        chains={"implement": chain},
        graph_text=_GRAPH,
        ledger=AcpHoldLedger(holds=(), unobservable=(), observation_ids=frozenset()),
        inputs=PreflightInputs(headroom=policy),
    )


_CLAUDE = _candidate(agent_id=CLAUDE_AGENT_ID)
_CODEX = _candidate(agent_id=CODEX_AGENT_ID)


def test_a_covered_primary_continues_to_an_uncovered_fallback_without_a_slot() -> None:
    verdict = _verdict(
        chain=_chain(_CLAUDE, _CODEX), refusal=_refusal(cause="no-declared-slot-injected")
    )

    (node,) = verdict.nodes
    assert verdict.viable
    assert verdict.credential_refused is False
    assert node.candidates == (_CODEX,)
    assert [skip.reason for skip in node.skipped] == ["claude-credential-policy-refusal"]
    assert [skip.condition for skip in node.skipped] == ["no-declared-slot-injected"]
    assert verdict.headroom_assessments == ()


def test_no_declared_slot_emptying_a_required_node_refuses_before_claim() -> None:
    verdict = _verdict(chain=_chain(_CLAUDE), refusal=_refusal(cause="no-declared-slot-injected"))
    journal = _Journal()

    outcome = acp_preflight_refusal(work_item_id="bd-ib-tvcbmc", verdict=verdict, journal=journal)

    assert not verdict.viable
    assert verdict.credential_refused is True
    assert verdict.exhausted == ("implement",)
    assert verdict.detail == "no-declared-slot-injected: the detail"
    assert outcome is not None
    assert outcome.stage == "claude-credential-refusal"
    assert journal.records[0]["stage"] == "claude-credential-refusal"
    assert dispatch_exit_code(outcomes=[outcome]) == 3


def test_a_configuration_refusal_refuses_even_with_an_uncovered_fallback() -> None:
    verdict = _verdict(
        chain=_chain(_CLAUDE, _CODEX),
        refusal=_refusal(cause=policy_module.CLAUDE_CREDENTIAL_POLICY_ABSENT),
    )

    assert not verdict.viable
    assert verdict.credential_refused is True
    assert verdict.exhausted == ()


def test_a_codex_only_chain_is_unaffected_by_the_policy() -> None:
    verdict = _verdict(chain=_chain(_CODEX), refusal=_refusal(cause="no-declared-slot-injected"))

    assert verdict.viable
    assert verdict.credential_refused is False


def _no_fallback_repo(*, tmp_path: Path, policy: object | None) -> Path:
    repo = tmp_path / "governed"
    repo.mkdir()
    config: dict[str, object] = (
        {} if policy is None else {_PLUGIN: {"dispatcher": {"claude_credential_policy": policy}}}
    )
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    return repo


@pytest.mark.parametrize(
    ("policy", "cause", "named"),
    [
        (None, policy_module.CLAUDE_CREDENTIAL_POLICY_ABSENT, _KEY),
        ({"mode": "fleet"}, policy_module.CLAUDE_CREDENTIAL_POLICY_INVALID, _KEY),
        (
            {"mode": "numbered-slots", "slots": [_SLOT_A]},
            "no-declared-slot-injected",
            f"{_SLOT_A} (absent)",
        ),
    ],
)
def test_a_repository_without_fallback_chains_is_refused_not_failed_open(
    tmp_path: Path, policy: object | None, cause: str, named: str
) -> None:
    """Scenario 376 on the no-fallback path every undeclared repository takes."""
    repo = _no_fallback_repo(tmp_path=tmp_path, policy=policy)
    reads: list[str | None] = []

    built = headroom_gate.session_headroom_policy(
        repo=repo,
        now_iso=_NOW,
        journal_path=None,
        read=lambda **kwargs: reads.append(kwargs["token"]),
    )
    verdict = resolve_acp_preflight(repo=repo, journal_path=None, now_iso=_NOW, headroom=built)
    outcome = acp_preflight_refusal(
        work_item_id="bd-ib-tvcbmc", verdict=verdict, journal=_Journal()
    )

    assert built.credential_refusal is not None
    assert built.credential_refusal.cause == cause
    assert reads == []
    assert verdict.fallback_enabled is False
    assert verdict.credential_refused is True
    assert named in verdict.detail
    assert "tok-legacy" not in verdict.detail
    assert outcome is not None
    assert dispatch_exit_code(outcomes=[outcome]) == 3


def test_an_injected_declared_slot_admits_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _no_fallback_repo(
        tmp_path=tmp_path, policy={"mode": "numbered-slots", "slots": [_SLOT_A]}
    )
    monkeypatch.setenv(_SLOT_A, "tok-a")
    reads: list[str | None] = []

    def _read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        reads.append(token)
        return headroom.session_headroom_reading(
            credential_identity="slot-a", observed_at=observed_at, utilization=0
        )

    built = headroom_gate.session_headroom_policy(
        repo=repo, now_iso=_NOW, journal_path=None, read=_read
    )
    verdict = resolve_acp_preflight(repo=repo, journal_path=None, now_iso=_NOW, headroom=built)

    assert built.credential_refusal is None
    assert verdict.viable
    assert reads == ["tok-a"]
