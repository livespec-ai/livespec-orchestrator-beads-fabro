"""Scenario 179: every commit-refusal brief names the failing files (bd-ib-b3qjzq).

`SPECIFICATION/contracts.md` section "ACP node timeouts" -> "Every commit-refusal
re-entry brief names the failing files from the full recorded output". The Red
and Green command programs are materialized into a plugins root beside the
commit runner, exactly as a dispatch lands them, and refused by a real commit
hook whose output ends in the per-target timing table; the
`review_fix_open_red_route` node is executed from the committed graph (a failed
fix settle re-enters `fix` directly, so `fix_open_red_route` never sees one).
Each brief must carry the same failing-file section the runner's builder prints
for that output, and a runner that fails still leaves the hook tail in place.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_registry import PLUGINS_ROOT
from livespec_orchestrator_beads_fabro.commands._dispatcher_implement_commit_programs import (
    COMMIT_GREEN_PROGRAM_FILENAME,
    COMMIT_RED_PROGRAM_FILENAME,
)

from tests.prepare_step_support import land_helpers

_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_RUN_ID = "current-run"
_TIMING_TAIL = "".join(f"0.{index}s check-target-{index}\\n" for index in range(100))
_HOOK = (
    "#!/bin/sh\n"
    "printf 'Name  Stmts  Miss  Cover  Missing\\n'\n"
    "printf 'pkg/a.py  10  2  80%%  4-5\\n'\n"
    "printf 'pkg/b.py  10  1  90%%  7\\n'\n"
    "printf 'Failed targets (1):\\n  - check-per-file-coverage\\n'\n"
    f"printf '{_TIMING_TAIL}'\n"
    "exit 1\n"
)
_RECORDED = (
    "pkg/a.py  10  2  80%  4-5\n"
    "pkg/b.py  10  1  90%  7\n"
    "Failed targets (1):\n  - check-per-file-coverage\n" + _TIMING_TAIL.replace("\\n", "\n")
)
_SECTION = (
    "failed targets: check-per-file-coverage\n"
    "failing files (2):\n"
    "- pkg/a.py: uncovered lines 4-5\n"
    "- pkg/b.py: uncovered lines 7\n"
)


@pytest.fixture(autouse=True)
def _current_fabro_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FABRO_RUN_ID", "run")


def _run(*, cwd: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, check=False, capture_output=True, text=True)


def _git(*, repo: Path, argv: list[str]) -> str:
    completed = _run(cwd=repo, argv=["git", *argv])
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _git_path(*, repo: Path, name: str) -> Path:
    return repo / _git(repo=repo, argv=["rev-parse", "--git-path", name])


def _repository(*, tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    _ = _run(cwd=tmp_path, argv=["git", "init", "--bare", "--quiet", str(origin)])
    repo = tmp_path / "repository"
    repo.mkdir()
    _git(repo=repo, argv=["init", "--quiet"])
    _git(repo=repo, argv=["config", "user.name", "Test Author"])
    _git(repo=repo, argv=["config", "user.email", "author@example.invalid"])
    _git(repo=repo, argv=["config", "livespec.factoryRunId", _RUN_ID])
    _ = (repo / "implementation.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "implementation.py"])
    _git(repo=repo, argv=["commit", "--quiet", "-m", "chore: baseline"])
    _git(repo=repo, argv=["remote", "add", "origin", str(origin)])
    _git(repo=repo, argv=["push", "--quiet", "origin", "HEAD:master"])
    _git(repo=repo, argv=["fetch", "--quiet", "origin", "master"])
    return repo


def _plugins(*, tmp_path: Path) -> Path:
    root = tmp_path / "plugins"
    _ = land_helpers(roots={PLUGINS_ROOT: root})
    assert (root / COMMIT_RUNNER_PROGRAM_FILENAME).is_file()
    return root


def _refusing_hook(*, repo: Path) -> None:
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text(_HOOK, encoding="utf-8")
    hook.chmod(0o755)


def _runner_section(*, plugins: Path, output: Path) -> str:
    """The landed runner's own builder, run in-process on a recorded output."""
    namespace: dict[str, object] = {"__name__": "livespec_commit_runner_under_test"}
    runner = plugins / COMMIT_RUNNER_PROGRAM_FILENAME
    exec(compile(runner.read_text(encoding="utf-8"), str(runner), "exec"), namespace)  # noqa: S102 — the landed program's exact source
    builder = namespace["failing_section"]
    assert callable(builder)
    return str(builder(output.read_text(encoding="utf-8")))


def _green_ready(*, repo: Path) -> None:
    """This run's Red commit with a Green checkpoint above it."""
    _ = (repo / "implementation.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(
        repo=repo,
        argv=["commit", "--all", "--quiet", "-m", "feat: red", "-m", f"Factory-Run-Id: {_RUN_ID}"],
    )
    _ = (repo / "implementation.py").write_text("VALUE = 3\n", encoding="utf-8")
    _git(
        repo=repo,
        argv=["commit", "--all", "--quiet", "-m", "fabro(run): green", "-m", "Fabro-Run: run"],
    )
    _refusing_hook(repo=repo)


def test_a_refused_red_commit_hands_off_the_failing_files(tmp_path: Path) -> None:
    plugins = _plugins(tmp_path=tmp_path)
    repo = _repository(tmp_path=tmp_path)
    _ = (repo / "test_feature.py").write_text("def test_feature() -> None: ...\n", "utf-8")
    _ = (repo / "implementation.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "-A"])
    _git(repo=repo, argv=["commit", "--quiet", "-m", "fabro(run): red", "-m", "Fabro-Run: run"])
    handoff = _git_path(repo=repo, name="livespec-implement-handoff.md")
    _ = handoff.write_text("## red\nRed test file: test_feature.py\n", encoding="utf-8")
    _refusing_hook(repo=repo)

    red = _run(cwd=repo, argv=["bash", str(plugins / COMMIT_RED_PROGRAM_FILENAME)])

    assert red.returncode == 1, red.stderr
    assert _SECTION in handoff.read_text(encoding="utf-8").split("## commit_red", 1)[1]


def test_a_refused_green_amend_hands_off_the_failing_files(tmp_path: Path) -> None:
    plugins = _plugins(tmp_path=tmp_path)
    repo = _repository(tmp_path=tmp_path)
    _green_ready(repo=repo)

    green = _run(cwd=repo, argv=["bash", str(plugins / COMMIT_GREEN_PROGRAM_FILENAME)])

    handoff = _git_path(repo=repo, name="livespec-implement-handoff.md").read_text(encoding="utf-8")
    output = _git_path(repo=repo, name="livespec-commit-green-output")
    assert green.returncode == 1, green.stderr
    assert _SECTION in handoff.split("## commit_green", 1)[1]
    assert _runner_section(plugins=plugins, output=output) == _SECTION


def test_a_program_without_the_runner_beside_it_says_the_section_is_unavailable(
    tmp_path: Path,
) -> None:
    repo = _repository(tmp_path=tmp_path)
    _green_ready(repo=repo)
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    program = lonely / COMMIT_GREEN_PROGRAM_FILENAME
    landed = _plugins(tmp_path=tmp_path) / COMMIT_GREEN_PROGRAM_FILENAME
    _ = program.write_text(landed.read_text(encoding="utf-8"), encoding="utf-8")

    green = _run(cwd=repo, argv=["bash", str(program)])

    handoff = _git_path(repo=repo, name="livespec-implement-handoff.md").read_text(encoding="utf-8")
    assert green.returncode == 1, green.stderr
    assert "failing files: unavailable, because the commit runner is not materialized" in handoff


def test_the_review_fix_open_red_brief_carries_the_settled_failed_run_s_failing_files(
    tmp_path: Path,
) -> None:
    route, live, brief = (
        "review_fix_open_red_route",
        "livespec-review-fix-live-commit",
        "livespec-review-fix-open-red-brief",
    )
    plugins = _plugins(tmp_path=tmp_path)
    repo = _repository(tmp_path=tmp_path)
    tests = repo / "tests"
    tests.mkdir()
    _ = (tests / "test_thing.py").write_text("# red\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "tests/test_thing.py"])
    _git(repo=repo, argv=["commit", "--quiet", "-m", "fix: red\n\nTDD-Red-Test-File-Checksum: abc"])
    recorded = tmp_path / "commit.output"
    _ = recorded.write_text(_RECORDED, encoding="utf-8")
    section = _runner_section(plugins=plugins, output=recorded)
    _ = _git_path(repo=repo, name=live).write_text(
        f"failed\n{section}\nCommit run x failed.\n", "utf-8"
    )
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script = str(graph.nodes[route]["script"]).replace("{{ inputs.default_branch }}", "master")

    routed = _run(cwd=repo, argv=["sh", "-c", script])

    written = _git_path(repo=repo, name=brief).read_text(encoding="utf-8")
    assert routed.returncode == 0, routed.stderr
    assert "- pkg/a.py: uncovered lines 4-5" in section
    assert written.startswith(section)


def test_a_failing_runner_still_hands_off_the_tail_and_says_why_the_section_is_missing(
    tmp_path: Path,
) -> None:
    repo = _repository(tmp_path=tmp_path)
    _green_ready(repo=repo)
    broken = tmp_path / "broken"
    broken.mkdir()
    program = broken / COMMIT_GREEN_PROGRAM_FILENAME
    landed = _plugins(tmp_path=tmp_path) / COMMIT_GREEN_PROGRAM_FILENAME
    _ = program.write_text(landed.read_text(encoding="utf-8"), encoding="utf-8")
    _ = (broken / COMMIT_RUNNER_PROGRAM_FILENAME).write_text("raise SystemExit(3)\n", "utf-8")

    green = _run(cwd=repo, argv=["bash", str(program)])

    handoff = _git_path(repo=repo, name="livespec-implement-handoff.md").read_text(encoding="utf-8")
    section = handoff.split("## commit_green", 1)[1]
    assert green.returncode == 1, green.stderr
    assert "failing files: unavailable (runner exited 3)" in section
    assert "Hook output (last 80 lines):" in section
    assert "0.99s check-target-99" in section
