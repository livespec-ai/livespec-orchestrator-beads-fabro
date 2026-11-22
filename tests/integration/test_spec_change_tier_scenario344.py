"""Integration journey for Scenario 344's filing and re-judgement paths."""

from __future__ import annotations

import stat
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    recorded_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.unsafe import unsafe_perform_io

_HEADING = "## A governing clause"
_UNSTATED = (
    '{"kind": "unstated", "stated_by": [], "generalization_target": '
    f'"{_HEADING}", "rationale": "the ratified text does not state it"}}'
)
_STATED = (
    f'{{"kind": "stated", "stated_by": ["{_HEADING}"], '
    '"generalization_target": null, "rationale": "the clause states it"}'
)


@pytest.fixture(autouse=True)
def _fake_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="scenario344",
        prefix="bd-ib",
        server_user="scenario344",
        database="scenario344",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "SPECIFICATION" / "history" / "v001").mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}, '
        '"dispatcher": {"auto_approve_ready": true, "acp_nodes": {"dod_gate": '
        '{"agent": "claude-acp", "model": "claude-opus-5"}}}}}',
        encoding="utf-8",
    )
    _ = (repo / "SPECIFICATION" / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nThe clause body.\n", encoding="utf-8"
    )
    return repo


def _judge(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replies: tuple[str, ...]) -> None:
    calls = tmp_path / "judge-calls"
    _ = calls.touch()
    arms = "".join(f"{index}) echo '{reply}' ;;\n" for index, reply in enumerate(replies))
    script = tmp_path / "judge"
    _ = script.write_text(
        "#!/bin/sh\n"
        f'calls=$(wc -l < "{calls}" 2>/dev/null || true)\n'
        "case $calls in\n" + arms + "*) exit 1 ;;\nesac\n"
        f'echo call >> "{calls}"\n',
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))


def _item(*, item_id: str, description: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="pending-approval",
        title="Change observable behaviour",
        description=(
            f"{description}\n\n## Definition of Done\n\n- The requested behaviour works.\n\n"
            f"References: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-22T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_policy="ai-only",
    )


def _route(*, repo: Path, item_id: str) -> str:
    checklist = DefinitionOfReadyChecklist(
        single_coherent_done=True,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    )
    return unsafe_perform_io(
        apply_intake_dor(path=_config(repo=repo), item_id=item_id, checklist=checklist).unwrap()
    )


def _stored(*, repo: Path, item_id: str) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config(repo=repo)))[item_id]


def _record(*, repo: Path, item_id: str):
    return recorded_spec_change_tier(
        comments=tuple(
            comment.text
            for comment in read_work_item_comments(path=_config(repo=repo), work_item_id=item_id)
        )
    )


def test_scenario344_routes_unstated_behaviour_by_classification_and_rejudges_changed_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bug contract work holds; internal/stated work routes; changed text gets a fresh tier."""
    repo = _repo(tmp_path=tmp_path)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.intake_dor.judge_item_definition_of_done",
        lambda **_: SimpleNamespace(holds=False),
    )
    _judge(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        replies=(
            "bug",
            _UNSTATED,
            "bug",
            _STATED,
            "bug",
            _STATED,
            "bug",
            _STATED,
            "bug",
            _UNSTATED,
        ),
    )

    contract = _item(
        item_id="bd-ib-contract", description="Change a contract between repositories."
    )
    append_work_item(path=_config(repo=repo), item=contract)
    assert _route(repo=repo, item_id=contract.id) == "pending-approval"
    assert _stored(repo=repo, item_id=contract.id).status == "pending-approval"
    assert (
        _record(repo=repo, item_id=contract.id)
        or pytest.fail("contract classification was not recorded")
    ).is_spec_change

    internal = _item(
        item_id="bd-ib-internal", description="Refactor an internal implementation only."
    )
    append_work_item(path=_config(repo=repo), item=internal)
    assert _route(repo=repo, item_id=internal.id) == "ready"
    assert (
        _record(repo=repo, item_id=internal.id)
        or pytest.fail("internal classification was not recorded")
    ).is_spec_change is False

    stated = _item(item_id="bd-ib-stated", description="Restore the stated behaviour.")
    append_work_item(path=_config(repo=repo), item=stated)
    assert _route(repo=repo, item_id=stated.id) == "ready"
    assert (
        _record(repo=repo, item_id=stated.id)
        or pytest.fail("stated classification was not recorded")
    ).is_spec_change is False

    rejudge = _item(item_id="bd-ib-rejudge", description="Restore the stated behaviour.")
    append_work_item(path=_config(repo=repo), item=rejudge)
    assert dispatcher.main(argv=["classify-tier", "--repo", str(repo), "--item", rejudge.id]) == 0
    append_work_item(
        path=_config(repo=repo), item=replace(rejudge, description="Change a contract now.")
    )
    assert dispatcher.main(argv=["classify-tier", "--repo", str(repo), "--item", rejudge.id]) == 0
    comments = read_work_item_comments(path=_config(repo=repo), work_item_id=rejudge.id)
    assert len(comments) == 2
    assert (
        _record(repo=repo, item_id=rejudge.id)
        or pytest.fail("changed-item classification was not recorded")
    ).is_spec_change
