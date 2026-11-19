"""A non-governing citation is a MECHANICAL filing finding, so it withholds `ready`.

Binds the filing half of work-item `bd-ib-77qyww`: the host-side wall's findings
(`filing_findings`) carry the governing-heading mismatch as a mechanical finding,
the same one `filing_display` shows, so the intake route's own `withholds_ready`
gate stops on it rather than relying on the pre-admission judgement alone.

THE JUDGE IS STOOD IN AT THE EXECUTABLE, as in
`test_governing_heading_pre_admission_hold`, and two controls carry the claim: a
citation the judgement returned adds no finding, and a judgement that could not
be taken adds none either, because a failure to measure is not evidence.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display import (
    MECHANICAL_FINDING_PREFIX,
)
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
    filing_findings,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.unsafe import unsafe_perform_io

_ITEM_ID = "bd-ib-m76p2n"
_GOVERNING = "## Scenario 206 — The spec-change tier is decided by the spec-stated judgement"
_NON_GOVERNING = "## Effective acceptance criteria"

_SPEC_STATED_REPLY = (
    '{\\"kind\\": \\"stated\\", \\"stated_by\\": [\\"' + _GOVERNING + '\\"],'
    ' \\"generalization_target\\": null, \\"rationale\\": \\"It states the behaviour.\\",'
    ' \\"evidence\\": [{\\"heading\\": \\"'
    + _GOVERNING
    + '\\", \\"quote\\": \\"The dispatched slice lands its change.\\"}]}'
)
_PASS_REPLY = '{\\"outcome\\": \\"passed\\"}'


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _repo(*, tmp_path: Path) -> Path:
    """A governed tree carrying BOTH headings, so each citation resolves."""
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {"prefix": "bd-ib"},
    "dispatcher": {
      "acp_nodes": {
        "dod_gate": {"agent": "claude-acp", "model": "claude-opus-5"}
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_NON_GOVERNING}\n\nThe criteria clause.\n", encoding="utf-8"
    )
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_GOVERNING}\n\nThe dispatched slice lands its change.\n",
        encoding="utf-8",
    )
    return repo


def _install_judge(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One executable answering both takings, told apart by their own argv.

    Both judgements use the configured candidate's same argv and receive their
    prompts on standard input. The spec-stated prompt alone names its
    `generalization_target` field, so the fixture classifies the bytes the
    production runner actually supplies rather than relying on argv shape.
    """
    script = tmp_path / "fake-judge"
    _ = script.write_text(
        "#!/bin/sh\n"
        'prompt="$(cat)"\n'
        'if printf "%s" "$prompt" | grep -q generalization_target; then\n'
        f'  printf "%s\\n" "{_SPEC_STATED_REPLY}"\n'
        "else\n"
        f'  printf "%s\\n" "{_PASS_REPLY}"\n'
        "fi\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))


def _install_absent_judge(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(tmp_path / "no-such-judge"))


def _item(*, reference: str) -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="feature",
        status="pending-approval",
        title="A judged slice",
        description=(
            "## Definition of Done\n\n- The dispatched slice lands its change.\n\n"
            f"References: {reference}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-23T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


_CHECKLIST = DefinitionOfReadyChecklist(
    single_coherent_done=True,
    autonomously_verifiable=True,
    autonomy_tiered=True,
    dependency_linked=True,
    repo_targeted=True,
    above_floor=True,
)


def _route_intake(*, repo: Path, reference: str) -> str:
    config = _config(repo=repo)
    append_work_item(path=config, item=_item(reference=reference))
    return str(
        unsafe_perform_io(
            apply_intake_dor(path=config, item_id=_ITEM_ID, checklist=_CHECKLIST).unwrap()
        )
    )


def _stored(*, repo: Path) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config(repo=repo)))[_ITEM_ID]


def _comments(*, repo: Path) -> str:
    return "\n".join(
        comment.text
        for comment in read_work_item_comments(path=_config(repo=repo), work_item_id=_ITEM_ID)
    )


def test_a_citation_the_judgement_did_not_return_is_a_mechanical_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The finding withholds ready and names the omitted heading verbatim."""
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)

    findings = filing_findings(item=_item(reference=_NON_GOVERNING), repo_root=repo)

    assert findings.withholds_ready
    assert any(_GOVERNING in finding for finding in findings.mechanical)


def test_a_citation_the_judgement_returned_adds_no_mechanical_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: without it, a finding is consistent with refusing everything."""
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)

    findings = filing_findings(item=_item(reference=_GOVERNING), repo_root=repo)

    assert not findings.withholds_ready


def test_a_judgement_that_could_not_be_taken_adds_no_mechanical_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure to measure is not evidence that a citation fails to govern."""
    repo = _repo(tmp_path=tmp_path)
    _install_absent_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)

    findings = filing_findings(item=_item(reference=_NON_GOVERNING), repo_root=repo)

    assert not findings.withholds_ready


def test_the_intake_route_records_the_mismatch_as_a_mechanical_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ledger comment on the item is the mechanical finding the display showed."""
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)
    config = _config(repo=repo)
    append_work_item(path=config, item=_item(reference=_NON_GOVERNING))

    routed = unsafe_perform_io(
        apply_intake_dor(path=config, item_id=_ITEM_ID, checklist=_CHECKLIST).unwrap()
    )

    assert routed != "ready"
    bodies = [
        comment.text for comment in read_work_item_comments(path=config, work_item_id=_ITEM_ID)
    ]
    assert any(body.startswith(MECHANICAL_FINDING_PREFIX) and _GOVERNING in body for body in bodies)
