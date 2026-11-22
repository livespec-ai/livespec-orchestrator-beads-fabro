"""A commit inside an implement, fix or review_fix turn takes the affected-tests gate.

The pre-commit hook reads the turn's stage from `LIVESPEC_AUTHORING_TURN`, which the
detached commit runner sets. These cases run the real hook script in a throwaway
repository against a fake `just` and `uv` that record what the hook asks for, so the
hook's routing is read from the recipes it calls rather than from a whole check run.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PRE_COMMIT = _REPO_ROOT / "dev-tooling" / "just-check-pre-commit.sh"
_CHECK_CHANGED = _REPO_ROOT / "dev-tooling" / "just-check-changed.sh"
_WORKFLOW = ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_WIDGET = ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/widget.py"
_FLEET_LAUNCH_GATE = "check-fleet-launch"
_AGGREGATE = f"check-skipping check-codex-skill-picker {_FLEET_LAUNCH_GATE}"
_RED_MODE = (
    "check-skipping check-coverage check-per-file-coverage check-check-coverage-incremental"
    f" check-codex-skill-picker {_FLEET_LAUNCH_GATE}"
)


def _run(*, argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, check=False)


def _git(*, repo: Path, arguments: list[str]) -> None:
    done = _run(argv=["git", *arguments], cwd=repo, env=os.environ.copy())
    assert done.returncode == 0, done.stderr


def _write_tool(*, directory: Path, name: str, body: str) -> None:
    path = directory / name
    _ = path.write_text(body, encoding="utf-8")
    _ = path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _repository(*, tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    """A repository with one baseline commit, and an environment whose tools are fakes."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo=repo, arguments=["init", "--quiet"])
    _git(repo=repo, arguments=["config", "user.name", "Test User"])
    _git(repo=repo, arguments=["config", "user.email", "test@example.invalid"])
    source = repo / _WIDGET
    source.parent.mkdir(parents=True)
    _ = source.write_text("VALUE = 0\n", encoding="utf-8")
    _git(repo=repo, arguments=["add", "."])
    _git(repo=repo, arguments=["commit", "--quiet", "-m", "baseline"])

    tools = tmp_path / "bin"
    tools.mkdir()
    log = tmp_path / "tools.log"
    _write_tool(
        directory=tools,
        name="uv",
        body=(
            "#!/usr/bin/env bash\n"
            'printf \'uv %s\\n\' "$*" >> "$FAKE_LOG"\n'
            "case \"$*\" in *'pre_commit_delegate run'*) exit 75 ;; esac\n"
            'exit "${FAKE_UV_STATUS:-0}"\n'
        ),
    )
    _write_tool(
        directory=tools,
        name="just",
        body=(
            "#!/usr/bin/env bash\n"
            'printf \'%s\\n\' "$*" >> "$FAKE_LOG"\n'
            'if [[ "$*" == check-changed ]]; then exit "${FAKE_CHANGED_STATUS:-0}"; fi\n'
            'if [[ "$*" == check-pre-commit-doc-only ]]; then exit "${FAKE_DOC_ONLY_STATUS:-0}"; fi\n'
            'if [[ "$*" == check-staged-precheck ]]; then exit "${FAKE_PRECHECK_STATUS:-0}"; fi\n'
        ),
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "LIVESPEC_AUTHORING_TURN",
            "LIVESPEC_AGENT_STAGE",
            "LIVESPEC_GATE_CONTEXT",
            # The gate Job exports the members it skips here; the hook appends them to
            # its aggregate call, so an ambient value would change the expected argv.
            "SKIP_TARGETS",
        }
    }
    environment["PATH"] = f"{tools}{os.pathsep}{environment['PATH']}"
    environment["FAKE_LOG"] = str(log)
    return repo, environment, log


def _stage(*, repo: Path, path: str, text: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(text, encoding="utf-8")
    _git(repo=repo, arguments=["add", path])


def _hook(
    *, tmp_path: Path, staged: dict[str, str], extra: dict[str, str]
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    repo, environment, log = _repository(tmp_path=tmp_path)
    for path, text in staged.items():
        _stage(repo=repo, path=path, text=text)
    done = _run(argv=["bash", str(_PRE_COMMIT)], cwd=repo, env={**environment, **extra})
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return done, [line for line in lines if not line.startswith("uv ")]


@pytest.mark.parametrize("stage", ["implement", "fix", "review_fix"])
def test_an_authoring_turn_commit_runs_the_affected_tests_gate_and_not_the_aggregate(
    *, tmp_path: Path, stage: str
) -> None:
    """The staged pre-check runs, then `just check-changed`, and the aggregate does not."""
    done, calls = _hook(
        tmp_path=tmp_path, staged={_WIDGET: "VALUE = 1\n"}, extra={"LIVESPEC_AUTHORING_TURN": stage}
    )

    assert done.returncode == 0, done.stderr
    assert calls == ["check-staged-precheck", "check-changed"]


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"LIVESPEC_AGENT_STAGE": "fix"},
        {"LIVESPEC_AUTHORING_TURN": "janitor"},
        {"LIVESPEC_AUTHORING_TURN": "implement_extra"},
    ],
)
def test_a_commit_outside_an_authoring_turn_keeps_the_full_aggregate(
    *, tmp_path: Path, extra: dict[str, str]
) -> None:
    """Only the commit runner's authoring-turn marker selects the gate; the guard variable does not."""
    done, calls = _hook(tmp_path=tmp_path, staged={_WIDGET: "VALUE = 1\n"}, extra=extra)

    assert done.returncode == 0, done.stderr
    assert calls == ["check-staged-precheck", _AGGREGATE]


@pytest.mark.parametrize("stage", ["implement", "fix", "review_fix"])
def test_an_authoring_turn_change_the_gate_cannot_scope_falls_back_to_the_full_aggregate(
    *, tmp_path: Path, stage: str
) -> None:
    """Exit 75 falls through to the aggregate in each authoring turn."""
    done, calls = _hook(
        tmp_path=tmp_path,
        staged={_WIDGET: "VALUE = 1\n"},
        extra={"LIVESPEC_AUTHORING_TURN": stage, "FAKE_CHANGED_STATUS": "75"},
    )

    assert done.returncode == 0, done.stderr
    assert calls == ["check-staged-precheck", "check-changed", _AGGREGATE]
    assert "running the full check aggregate" in done.stdout


def test_the_gates_refusal_refuses_the_commit_without_running_the_aggregate(
    *, tmp_path: Path
) -> None:
    """A failing test or an uncovered line is the gate's own verdict and ends the hook."""
    done, calls = _hook(
        tmp_path=tmp_path,
        staged={_WIDGET: "VALUE = 1\n"},
        extra={"LIVESPEC_AUTHORING_TURN": "review_fix", "FAKE_CHANGED_STATUS": "2"},
    )

    assert done.returncode == 2
    assert calls == ["check-staged-precheck", "check-changed"]
    assert "affected-tests gate refused the commit" in done.stderr


def test_a_failing_staged_precheck_refuses_before_the_gate_runs(*, tmp_path: Path) -> None:
    """Lint and type errors in the staged files are reported before any test runs."""
    done, calls = _hook(
        tmp_path=tmp_path,
        staged={_WIDGET: "VALUE = 1\n"},
        extra={"LIVESPEC_AUTHORING_TURN": "fix", "FAKE_PRECHECK_STATUS": "1"},
    )

    assert done.returncode == 1
    assert calls == ["check-staged-precheck"]


def test_a_red_commit_keeps_its_fast_path_in_an_authoring_turn(*, tmp_path: Path) -> None:
    """A staged test alone is a Red commit: it must fail, so no gate may demand it pass."""
    done, calls = _hook(
        tmp_path=tmp_path,
        staged={"tests/test_widget.py": "def test_widget() -> None:\n    assert False\n"},
        extra={"LIVESPEC_AUTHORING_TURN": "implement"},
    )

    assert done.returncode == 0, done.stderr
    assert calls == [_RED_MODE]


@pytest.mark.parametrize("stage", ["fix", "review_fix"])
def test_a_fix_turn_cannot_commit_a_test_its_item_did_not_touch(
    *, tmp_path: Path, stage: str
) -> None:
    """A foreign test is not a Red test for a repair turn and the hook refuses it.

    The item has no prior change to this test in the throwaway repository, so
    staging it during either repair turn models a janitor failure in another
    item's test.  A successful Red fast-path would let the repair weaken that
    test before the next janitor can name its owner.
    """
    foreign_test = "tests/test_another_items_contract.py"
    done, _ = _hook(
        tmp_path=tmp_path,
        staged={foreign_test: "def test_another_items_contract() -> None:\n    assert False\n"},
        extra={"LIVESPEC_AUTHORING_TURN": stage},
    )

    assert done.returncode != 0
    assert foreign_test in done.stderr


@pytest.mark.parametrize("stage", ["fix", "review_fix"])
@pytest.mark.parametrize("removal", ["delete", "rename"])
def test_a_fix_turn_cannot_remove_a_test_its_item_did_not_touch(
    *, tmp_path: Path, stage: str, removal: str
) -> None:
    """Deleting or renaming away another item's test is an edit of it, and the hook refuses it."""
    foreign_test = "tests/test_another_items_contract.py"
    repo, environment, _ = _repository(tmp_path=tmp_path)
    _stage(
        repo=repo, path=foreign_test, text="def test_another_items_contract() -> None:\n    pass\n"
    )
    _git(repo=repo, arguments=["commit", "--quiet", "-m", "another item's test"])
    if removal == "delete":
        _git(repo=repo, arguments=["rm", "--quiet", foreign_test])
    else:
        _git(repo=repo, arguments=["mv", foreign_test, "tests/test_renamed_contract.py"])

    done = _run(
        argv=["bash", str(_PRE_COMMIT)],
        cwd=repo,
        env={**environment, "LIVESPEC_AUTHORING_TURN": stage},
    )

    assert done.returncode != 0
    assert "LIVESPEC_FOREIGN_REPAIR_TEST" in done.stderr
    assert foreign_test in done.stderr


def test_a_workflow_graph_change_runs_the_doc_only_gates_then_the_graph_reading_tests(
    *, tmp_path: Path
) -> None:
    """A graph edit stages no `.py`, so the doc-only gates run and then the affected-tests gate."""
    done, calls = _hook(
        tmp_path=tmp_path,
        staged={_WORKFLOW: "digraph { }\n"},
        extra={"LIVESPEC_AUTHORING_TURN": "fix"},
    )

    assert done.returncode == 0, done.stderr
    assert calls == ["check-pre-commit-doc-only", "check-changed"]


def test_an_implement_turn_workflow_graph_change_runs_the_affected_tests_gate(
    *, tmp_path: Path
) -> None:
    """A graph edit is scoped in implement just as it is in fix or review_fix."""
    done, calls = _hook(
        tmp_path=tmp_path,
        staged={_WORKFLOW: "digraph { }\n"},
        extra={"LIVESPEC_AUTHORING_TURN": "implement"},
    )

    assert done.returncode == 0, done.stderr
    assert calls == ["check-pre-commit-doc-only", "check-changed"]


def test_a_workflow_graph_change_the_doc_only_gates_refuse_runs_no_tests(*, tmp_path: Path) -> None:
    """The graph-validity gates still bind a graph edit made inside a turn."""
    done, calls = _hook(
        tmp_path=tmp_path,
        staged={_WORKFLOW: "digraph { }\n"},
        extra={"LIVESPEC_AUTHORING_TURN": "fix", "FAKE_DOC_ONLY_STATUS": "1"},
    )

    assert done.returncode == 1
    assert calls == ["check-pre-commit-doc-only"]


def test_a_deleted_workflow_graph_runs_the_doc_only_gates_then_the_graph_reading_tests(
    *, tmp_path: Path
) -> None:
    """Deleting the graph is a change to it: the staged-deletion list still selects the gate."""
    repo, environment, log = _repository(tmp_path=tmp_path)
    _stage(repo=repo, path=_WORKFLOW, text="digraph { }\n")
    _git(repo=repo, arguments=["commit", "--quiet", "-m", "graph"])
    _git(repo=repo, arguments=["rm", "--quiet", _WORKFLOW])

    done = _run(
        argv=["bash", str(_PRE_COMMIT)],
        cwd=repo,
        env={**environment, "LIVESPEC_AUTHORING_TURN": "fix"},
    )

    assert done.returncode == 0, done.stderr
    calls = [
        line for line in log.read_text(encoding="utf-8").splitlines() if not line.startswith("uv ")
    ]
    assert calls == ["check-pre-commit-doc-only", "check-changed"]


def test_a_deleted_product_module_in_an_authoring_turn_runs_the_affected_tests_gate(
    *, tmp_path: Path
) -> None:
    """A deletion changes a module too, so it cannot silently take the doc-only path."""
    repo, environment, log = _repository(tmp_path=tmp_path)
    _git(repo=repo, arguments=["rm", "--quiet", _WIDGET])

    done = _run(
        argv=["bash", str(_PRE_COMMIT)],
        cwd=repo,
        env={**environment, "LIVESPEC_AUTHORING_TURN": "fix"},
    )

    assert done.returncode == 0, done.stderr
    calls = [
        line for line in log.read_text(encoding="utf-8").splitlines() if not line.startswith("uv ")
    ]
    assert calls == ["check-staged-precheck", "check-changed"]


def test_a_commit_staging_no_python_and_no_graph_keeps_the_doc_only_path(*, tmp_path: Path) -> None:
    """Nothing to scope tests to: the existing doc-only gates are the commit's gate."""
    done, calls = _hook(
        tmp_path=tmp_path,
        staged={"README.md": "notes\n"},
        extra={"LIVESPEC_AUTHORING_TURN": "fix"},
    )

    assert done.returncode == 0, done.stderr
    assert calls == ["check-pre-commit-doc-only"]


def test_a_merge_in_progress_is_graded_by_the_full_aggregate(*, tmp_path: Path) -> None:
    """A merge commit stages the merged tree, which no scoped gate speaks for."""
    repo, environment, log = _repository(tmp_path=tmp_path)
    _stage(repo=repo, path=_WIDGET, text="VALUE = 1\n")
    head = _run(argv=["git", "rev-parse", "HEAD"], cwd=repo, env=environment).stdout.strip()
    _ = (repo / ".git" / "MERGE_HEAD").write_text(f"{head}\n", encoding="utf-8")

    done = _run(
        argv=["bash", str(_PRE_COMMIT)],
        cwd=repo,
        env={**environment, "LIVESPEC_AUTHORING_TURN": "fix"},
    )

    assert done.returncode == 0, done.stderr
    assert "check-changed" not in log.read_text(encoding="utf-8")


def test_the_check_changed_recipe_runs_the_selection_and_passes_its_status_through(
    *, tmp_path: Path
) -> None:
    """The hook reads 75 from `just check-changed`, so the script must not swallow it."""
    repo, environment, log = _repository(tmp_path=tmp_path)

    done = _run(
        argv=["bash", str(_CHECK_CHANGED)], cwd=repo, env={**environment, "FAKE_UV_STATUS": "75"}
    )

    assert done.returncode == 75
    assert log.read_text(encoding="utf-8").splitlines() == [
        "uv run python dev-tooling/checks/_affected_tests_selection.py"
    ]
