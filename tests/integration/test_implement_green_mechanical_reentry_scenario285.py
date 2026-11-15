"""Scenario 285: a purely mechanical Green refusal spends its own re-entry budget.

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch" -> "A
purely mechanical commit refusal has its own re-entry budget" (bd-ib-pyeiky,
with bd-ib-v5qotp's coverage-name alias). Each claim is observed by running the
materialized `commit-green.sh` against a real repository whose commit hook
refuses, and then the committed `green_admission` node script in the same
repository, so the classification, the handoff section and the admission's
budget accounting are read at the git boundary rather than from the source.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_implement_mechanical import (
    MECHANICAL_REENTRY_NODES,
    MechanicalReentryPolicy,
    RenderedMechanicalReentries,
    apply_mechanical_reentries,
    render_mechanical_reentries,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
    WorkflowPayload,
    prepare_workflow_payload,
)

_ROOT = Path(__file__).resolve().parents[2]
_GREEN = _ROOT / "dev-tooling" / "commit-green.sh"
_WORKFLOW = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item"
_RUN_ID = "current-run"


@pytest.fixture(autouse=True)
def _current_fabro_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name the engine run whose checkpoints the command script may fold."""
    monkeypatch.setenv("FABRO_RUN_ID", "run")


def _run(*, repo: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=repo, check=False, capture_output=True, text=True)


def _git(*, repo: Path, argv: list[str]) -> str:
    completed = _run(repo=repo, argv=["git", *argv])
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _git_path(*, repo: Path, name: str) -> Path:
    return repo / _git(repo=repo, argv=["rev-parse", "--git-path", name])


def _refusing_repository(*, tmp_path: Path, failed: tuple[str, ...]) -> Path:
    """A repository holding this run's Red commit, a Green checkpoint and a refusing hook."""
    repo = tmp_path / "repository"
    repo.mkdir(parents=True)
    _git(repo=repo, argv=["init", "--quiet"])
    _git(repo=repo, argv=["config", "user.name", "Test Author"])
    _git(repo=repo, argv=["config", "user.email", "author@example.invalid"])
    _git(repo=repo, argv=["config", "livespec.factoryRunId", _RUN_ID])
    _ = (repo / "implementation.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "implementation.py"])
    _git(repo=repo, argv=["commit", "--quiet", "-m", "chore: baseline"])
    _ = (repo / "test_feature.py").write_text("def test_feature() -> None: ...\n", "utf-8")
    _git(repo=repo, argv=["add", "test_feature.py"])
    _git(
        repo=repo, argv=["commit", "--quiet", "-m", "feat: red", "-m", f"Factory-Run-Id: {_RUN_ID}"]
    )
    _ = (repo / "implementation.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(
        repo=repo,
        argv=["commit", "--all", "--quiet", "-m", "fabro(run): green", "-m", "Fabro-Run: run"],
    )
    rows = "".join(f"  - {name}\\n" for name in failed)
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text(
        f"#!/bin/sh\nprintf 'Failed targets ({len(failed)}):\\n{rows}'\nexit 1\n", encoding="utf-8"
    )
    hook.chmod(0o755)
    _ = _git_path(repo=repo, name="livespec-implement-handoff.md").write_text(
        "## green\nDone.\n", encoding="utf-8"
    )
    return repo


def _commit_green(*, repo: Path, args: list[str]) -> str:
    """Run the refused Green amend and return the handoff it appended to."""
    completed = _run(repo=repo, argv=["bash", str(_GREEN), *args])
    assert completed.returncode == 1, completed.stderr
    return _git_path(repo=repo, name="livespec-implement-handoff.md").read_text(encoding="utf-8")


def _green_admission(*, repo: Path) -> subprocess.CompletedProcess[str]:
    graph = parse_dot_graph(text=(_WORKFLOW / "workflow.fabro").read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return _run(repo=repo, argv=["sh", "-c", str(graph.nodes["green_admission"]["script"])])


def _admissions(*, repo: Path, count: int | None = None) -> int:
    counter = _git_path(repo=repo, name="livespec-green-admission-count")
    if count is not None:
        _ = counter.write_text(f"{count}\n", encoding="utf-8")
    return int(counter.read_text(encoding="utf-8"))


def test_a_purely_mechanical_refusal_re_enters_green_without_its_ordinary_re_entry(
    tmp_path: Path,
) -> None:
    repo = _refusing_repository(tmp_path=tmp_path, failed=("check-per-file-coverage",))
    _ = _admissions(repo=repo, count=1)

    handoff = _commit_green(repo=repo, args=["2", "check-lint,check-per-file-coverage"])
    admitted = _green_admission(repo=repo)

    section = handoff.split("## commit_green", 1)[1]
    assert "Refusal: mechanical." in section
    assert "Mechanical failed targets: check-per-file-coverage" in section
    assert "Mechanical re-entries remaining: 1 of 2" in section
    assert admitted.returncode == 0, admitted.stderr
    assert "LIVESPEC_GREEN_MECHANICAL_REENTER" in admitted.stderr
    assert _admissions(repo=repo) == 1
    assert not _git_path(repo=repo, name="livespec-green-mechanical-reentry").exists()


def test_a_refusal_naming_a_substantive_target_spends_the_ordinary_re_entry(
    tmp_path: Path,
) -> None:
    repo = _refusing_repository(tmp_path=tmp_path, failed=("check-lint", "check-types"))
    _ = _admissions(repo=repo, count=1)

    handoff = _commit_green(repo=repo, args=["2", "check-lint"])
    admitted = _green_admission(repo=repo)

    section = handoff.split("## commit_green", 1)[1]
    assert "Refusal: ordinary. A failed target is not a declared mechanical target" in section
    assert "Mechanical re-entries remaining: 2 of 2" in section
    assert admitted.returncode == 0, admitted.stderr
    assert _admissions(repo=repo) == 2


def test_spent_mechanical_and_ordinary_re_entries_end_the_stage_naming_both_budgets(
    tmp_path: Path,
) -> None:
    repo = _refusing_repository(tmp_path=tmp_path, failed=("check-lint",))
    _ = _git_path(repo=repo, name="livespec-green-mechanical-reentries").write_text("1\n", "utf-8")
    _ = _admissions(repo=repo, count=3)

    handoff = _commit_green(repo=repo, args=["1", "check-lint"])
    admitted = _green_admission(repo=repo)

    cause = _git_path(repo=repo, name="livespec-stage-cause").read_text(encoding="utf-8")
    assert "the mechanical re-entries are spent" in handoff
    assert admitted.returncode != 0
    assert "LIVESPEC_IMPLEMENT_GREEN_BOUND_EXHAUSTED" in cause
    assert "both the mechanical re-entry budget (1 of 1 spent)" in cause
    assert "the ordinary re-entry budget (2 of 2 spent) are exhausted" in cause


def test_an_ordinary_exhaustion_with_mechanical_re_entries_left_says_so(tmp_path: Path) -> None:
    repo = _refusing_repository(tmp_path=tmp_path, failed=("check-types",))
    _ = _admissions(repo=repo, count=3)

    _ = _commit_green(repo=repo, args=["2", "check-lint"])
    admitted = _green_admission(repo=repo)

    cause = _git_path(repo=repo, name="livespec-stage-cause").read_text(encoding="utf-8")
    assert admitted.returncode != 0
    assert "the ordinary re-entry budget (2 of 2 spent) is exhausted" in cause
    assert "could not take a mechanical re-entry (0 of 2 spent)" in cause


@pytest.mark.parametrize(
    ("declared", "failed", "classification"),
    [
        ("check-per-file-coverage", ("check-check-coverage-incremental",), "mechanical"),
        ("check-check-coverage-incremental", ("check-per-file-coverage",), "mechanical"),
        (
            "check-per-file-coverage",
            ("check-check-coverage-incremental", "check-types"),
            "ordinary",
        ),
    ],
)
def test_the_two_per_file_coverage_names_classify_as_one_target(
    tmp_path: Path, declared: str, failed: tuple[str, ...], classification: str
) -> None:
    repo = _refusing_repository(tmp_path=tmp_path, failed=failed)

    handoff = _commit_green(repo=repo, args=["2", declared])

    assert f"Refusal: {classification}." in handoff


def test_no_declared_policy_classifies_every_refusal_as_ordinary(tmp_path: Path) -> None:
    repo = _refusing_repository(tmp_path=tmp_path, failed=())

    handoff = _commit_green(repo=repo, args=[])

    assert "Refusal: ordinary. The hook output names no failed target" in handoff
    assert "Mechanical re-entries remaining: 0 of 0" in handoff


def test_the_committed_graph_renders_the_budget_into_commit_green_and_the_loop_bounds() -> None:
    committed = (_WORKFLOW / "workflow.fabro").read_text(encoding="utf-8")

    rendered = render_mechanical_reentries(
        graph_text=committed,
        policy=MechanicalReentryPolicy(targets=("check-lint", "check-file-lloc"), reentries=2),
    )

    assert isinstance(rendered, RenderedMechanicalReentries), rendered
    graph = parse_dot_graph(text=rendered.text)
    assert not isinstance(graph, str), graph
    assert str(graph.nodes["commit_green"]["script"]).endswith(
        'livespec-commit-green.sh" 2 check-lint,check-file-lloc'
    )
    assert {node: graph.nodes[node]["max_visits"] for node in MECHANICAL_REENTRY_NODES} == {
        node: str(visits) for node, visits in rendered.node_visits.items()
    }
    assert rendered.node_visits["green"] == 6
    assert graph.nodes["green_incomplete_route"]["max_visits"] == "2"
    assert "implement_mechanical" in (_WORKFLOW / "workflow.toml").read_text(encoding="utf-8")


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _prepared(*, tmp_path: Path, implement: object, graph: str) -> WorkflowPayload | str:
    workflow = tmp_path / "workflow"
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.fabro").write_text(graph, encoding="utf-8")
    committed = workflow / "workflow.toml"
    _ = committed.write_text('_version = 1\n\n[workflow]\ngraph = "workflow.fabro"\n', "utf-8")
    config = {"livespec-orchestrator-beads-fabro": {"dispatcher": {"implement": implement}}}
    _ = (tmp_path / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    return prepare_workflow_payload(
        repo=tmp_path,
        committed=committed,
        payload_dir=tmp_path / "payload",
        journal=cast("Any", _Journal()),
        work_item_id="bd-ib-pyeiky",
        adapters={},
    )


def _loop_graph(*, nodes: tuple[str, ...]) -> str:
    blocks = "".join(
        f'    {node} [\n        timeout="60s"\n        max_visits=4\n    ]\n' for node in nodes
    )
    script = 'script="bash g.sh {{ inputs.implement_mechanical_reentries }} {{ inputs.implement_mechanical_targets }}"'
    return f'digraph G {{\n    graph [\n        stall_timeout="7200s"\n    ]\n{blocks}    x [\n        timeout="60s"\n        {script}\n    ]\n}}\n'


def test_preparing_the_payload_renders_the_declared_budget(tmp_path: Path) -> None:
    payload = _prepared(
        tmp_path=tmp_path,
        implement={"mechanical_targets": ["check-lint"]},
        graph=_loop_graph(nodes=MECHANICAL_REENTRY_NODES),
    )

    assert isinstance(payload, WorkflowPayload), payload
    text = payload.graph.read_text(encoding="utf-8")
    assert "bash g.sh 2 check-lint" in text
    assert text.count("max_visits=6") == len(MECHANICAL_REENTRY_NODES)


def test_preparing_the_payload_refuses_a_malformed_key_or_an_unbounded_loop_node(
    tmp_path: Path,
) -> None:
    malformed = _prepared(
        tmp_path=tmp_path / "malformed",
        implement={"mechanical_targets": "check-lint"},
        graph=_loop_graph(nodes=MECHANICAL_REENTRY_NODES),
    )
    unbounded = _prepared(
        tmp_path=tmp_path / "unbounded",
        implement={"mechanical_targets": ["check-lint"]},
        graph=_loop_graph(nodes=("green",)),
    )

    assert isinstance(malformed, str)
    assert "dispatcher.implement.mechanical_targets" in malformed
    assert isinstance(unbounded, str)
    assert "commit_green" in unbounded


def test_the_green_prompt_explains_a_mechanical_refusal_section() -> None:
    prompt = (_WORKFLOW / "prompts" / "green.md").read_text(encoding="utf-8")

    assert "`Refusal: mechanical.`" in prompt
    assert "`Refusal: ordinary.`" in prompt
    assert "mechanical re-entries remaining" in prompt


def test_an_unreadable_payload_graph_refuses_naming_it(tmp_path: Path) -> None:
    absent = tmp_path / "workflow.fabro"

    refusal = apply_mechanical_reentries(
        graph=absent, block={"implement": {"mechanical_targets": ["check-lint"]}}
    )

    assert refusal is not None
    assert str(absent) in refusal
