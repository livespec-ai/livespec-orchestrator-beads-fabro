"""A preserved descendant must refuse a resume before it can discard work."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import ResumeGather
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import ResumeObservation
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_preserved_descendant"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_resume_preserved_descendant.py"
)


def test_a_descending_preservation_refusal_names_the_ref_tip_head_and_plain_dispatch() -> None:
    """The remedial dispatch cannot hide which preserved work would be lost."""
    assert _MODULE_PATH.is_file()
    module: Any = importlib.import_module(_MODULE_NAME)

    refusal = module.descending_preservation_refusal(
        preservation_ref="refs/heads/needs-human/run-1",
        preservation_tip="b" * 40,
        published_head="a" * 40,
    )

    assert "refs/heads/needs-human/run-1" in refusal
    assert "b" * 40 in refusal
    assert "a" * 40 in refusal
    assert "dispatch" in refusal


class _Runner:
    """A readable preserved tip that descends from the pull request head."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        joined = " ".join(argv)
        if "merge-base --is-ancestor" in joined:
            return CommandResult(exit_code=0, stdout="", stderr="")
        if "^{tree}" in joined:
            tree = "1" * 40 if "a" * 40 in joined else "2" * 40
            return CommandResult(exit_code=0, stdout=f"{tree}\n", stderr="")
        raise AssertionError(f"unexpected command: {joined}")


def test_a_same_run_descending_ref_with_more_work_is_a_resume_refusal() -> None:
    """A resume onto the older published head would lose the preservation's commit."""
    module: Any = importlib.import_module(_MODULE_NAME)
    assert hasattr(module, "preserved_descendant")

    outcome = module.preserved_descendant(
        runner=_Runner(),
        repo=Path("/repo"),
        preservation=RecoverySeed(
            source_run_id="run-1",
            remote="origin",
            commit_sha="b" * 40,
            preservation_ref="refs/heads/needs-human/run-1",
            preservation_tip_sha="b" * 40,
        ),
        published_head="a" * 40,
        head_is_later=False,
    )

    assert outcome.preservation_ref == "refs/heads/needs-human/run-1"
    assert outcome.preservation_tip == "b" * 40
    assert outcome.published_head == "a" * 40


class _PublishedDescendantRunner:
    """A readable published head that contains every commit in the preservation."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        assert argv == [
            "git",
            "merge-base",
            "--is-ancestor",
            "b" * 40,
            "a" * 40,
        ]
        return CommandResult(exit_code=0, stdout="", stderr="")


def test_an_unattributed_published_descendant_allows_the_resume() -> None:
    """Commit ancestry settles a readable head even when its publishing row is absent."""
    module: Any = importlib.import_module(_MODULE_NAME)

    outcome = module.preserved_descendant(
        runner=_PublishedDescendantRunner(),
        repo=Path("/repo"),
        preservation=RecoverySeed(
            source_run_id="run-1",
            remote="origin",
            commit_sha="b" * 40,
            preservation_ref="refs/heads/needs-human/run-1",
            preservation_tip_sha="b" * 40,
        ),
        published_head="a" * 40,
        head_is_later=None,
    )

    assert outcome is None


class _DivergentRunner:
    """A readable pair whose published head does not contain the preserved tip."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        assert argv[:3] == ["git", "merge-base", "--is-ancestor"]
        return CommandResult(exit_code=1, stdout="", stderr="")


def _resume_protection_outcome(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, records: tuple[dict[str, object], ...]
) -> Any:
    """Run the real attribution path over a journal reading holding exactly `records`."""
    protection: Any = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_resume_protection"
    )
    seed = RecoverySeed(
        source_run_id="run-1",
        remote="origin",
        commit_sha="b" * 40,
        preservation_ref="refs/heads/needs-human/run-1",
        preservation_tip_sha="b" * 40,
    )
    monkeypatch.setattr(protection, "read_journal_records", lambda **_: records)
    monkeypatch.setattr(protection, "verified_preserved_seed", lambda **_: seed)
    gather = ResumeGather(
        observation=ResumeObservation(
            work_item_id="item",
            status="ready",
            pull_request=1,
            pull_request_head="a" * 40,
            liveness_observed=True,
        ),
        anchor=None,
        branch="feat/item",
        earlier_run_ids=("run-1",),
        workflow_name=None,
        publications=(("a" * 40, "run-2"),),
    )
    item = WorkItem(
        id="item",
        type="bug",
        status="ready",
        title="t",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-01-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return protection.protected_resume_seed(
        gather=gather,
        item=item,
        repo=tmp_path,
        runner=_DivergentRunner(),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
    )


def test_a_head_no_journal_row_attributes_names_the_head_row_and_its_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With neither run journaled, the refusal names the publishing run's missing row."""
    outcome = _resume_protection_outcome(monkeypatch=monkeypatch, tmp_path=tmp_path, records=())

    detail = outcome.detail
    assert detail.startswith("publishing-run-unobservable")
    assert "a" * 40 in detail
    assert "published head" in detail and "`dispatcher.py dispatch`" in detail
    assert "preserved run" not in detail


def test_a_preserved_run_without_a_journal_position_is_named_instead_of_the_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The head IS attributed to run-2, so only run-1's missing row may be named."""
    records: tuple[dict[str, object], ...] = ({"run_id": "run-2", "published_head": "a" * 40},)

    outcome = _resume_protection_outcome(
        monkeypatch=monkeypatch, tmp_path=tmp_path, records=records
    )

    detail = outcome.detail
    assert detail.startswith("publishing-run-unobservable")
    assert "preserved run run-1" in detail and "`dispatcher.py dispatch`" in detail
    assert "attributes published head" not in detail
