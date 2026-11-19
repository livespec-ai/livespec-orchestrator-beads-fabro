"""An incomplete Green turn re-enters green once, then fails naming partial progress.

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch" -> "An
implement turn that ends incomplete does not succeed": a `green` turn whose
completion field reports the work incomplete re-enters `green` while its budget
remains, and once that budget is spent the stage ends failed with a cause naming
partial progress. The split graph realizes the decision in the
`green_incomplete_route` command node, whose script runs here against a scratch
repository exactly as the engine runs it, read from the committed graph.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_wip_capture import (
    WIP_CAPTURE_PROGRAM_FILENAME,
    wip_capture_program_source,
)

_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_NODE = "green_incomplete_route"
_PARTIAL = (
    "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS: the implement turn completion field does not "
    "state the work-item Definition of Done complete"
)


def _run(*, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True)


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _ = _run(cwd=tmp_path, args=["git", "init", "-q", str(repo)])
    return repo


def _script() -> str:
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return str(graph.nodes[_NODE]["script"])


def test_the_first_incomplete_turn_re_enters_green_and_clears_its_record(tmp_path: Path) -> None:
    """The first incomplete ending is a re-entry, with the previous turn's record cleared."""
    repo = _repo(tmp_path=tmp_path)
    git_dir = repo / ".git"
    (git_dir / "livespec-stage-cause").write_text(
        f"stage: implement\ncause: {_PARTIAL}\n", encoding="utf-8"
    )
    (git_dir / "livespec-implement-completion").write_text(
        '{"definition_of_done_complete": false}\n', encoding="utf-8"
    )

    result = _run(cwd=repo, args=["sh", "-c", _script()])

    facts = (
        result.returncode == 0,
        "LIVESPEC_GREEN_INCOMPLETE_REENTER" in result.stderr,
        (git_dir / "livespec-green-incomplete-reentries").read_text(encoding="utf-8") == "1\n",
        not (git_dir / "livespec-stage-cause").exists(),
        not (git_dir / "livespec-implement-completion").exists(),
    )
    assert all(facts), (facts, result.stderr)


def test_a_spent_reentry_fails_with_the_partial_progress_cause_standing(tmp_path: Path) -> None:
    """Once the re-entry is spent the node fails and the cause names partial progress."""
    repo = _repo(tmp_path=tmp_path)
    git_dir = repo / ".git"
    (git_dir / "livespec-green-incomplete-reentries").write_text("1\n", encoding="utf-8")
    (git_dir / "livespec-stage-cause").write_text(
        f"stage: implement\ncause: {_PARTIAL}\n", encoding="utf-8"
    )

    result = _run(cwd=repo, args=["sh", "-c", _script()])

    cause = (git_dir / "livespec-stage-cause").read_text(encoding="utf-8")
    facts = (
        result.returncode != 0,
        _PARTIAL in result.stderr,
        _PARTIAL in cause,
    )
    assert all(facts), (facts, result.stderr, cause)


def test_a_spent_reentry_with_no_recorded_cause_still_names_partial_progress(
    tmp_path: Path,
) -> None:
    """A missing cause file never leaves the failed stage without a partial-progress cause."""
    repo = _repo(tmp_path=tmp_path)
    git_dir = repo / ".git"
    (git_dir / "livespec-green-incomplete-reentries").write_text("1\n", encoding="utf-8")

    result = _run(cwd=repo, args=["sh", "-c", _script()])

    cause = (git_dir / "livespec-stage-cause").read_text(encoding="utf-8")
    facts = (
        result.returncode != 0,
        "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS" in result.stderr,
        "stage: implement\ncause: LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS" in cause,
    )
    assert all(facts), (facts, result.stderr, cause)


def test_a_spent_reentry_captures_the_committed_partial_progress_before_failing(
    tmp_path: Path,
) -> None:
    """Scenario 317: an exhausted incomplete Green path preserves its run tip."""
    origin = tmp_path / "origin.git"
    _ = _run(
        cwd=tmp_path,
        args=["git", "init", "-q", "--bare", "--initial-branch=master", str(origin)],
    )
    repo = _repo(tmp_path=tmp_path)
    for args in (
        ["git", "config", "user.name", "Fixture"],
        ["git", "config", "user.email", "fixture@example.invalid"],
        ["git", "checkout", "-q", "-b", "master"],
        ["git", "remote", "add", "origin", str(origin)],
    ):
        assert _run(cwd=repo, args=args).returncode == 0
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    assert _run(cwd=repo, args=["git", "add", "base.txt"]).returncode == 0
    assert _run(cwd=repo, args=["git", "commit", "-qm", "base"]).returncode == 0
    assert _run(cwd=repo, args=["git", "push", "-q", "origin", "master"]).returncode == 0
    assert _run(cwd=repo, args=["git", "checkout", "-qb", "fabro/run/01PARTIAL"]).returncode == 0
    (repo / "partial.txt").write_text("committed partial progress\n", encoding="utf-8")
    assert _run(cwd=repo, args=["git", "add", "partial.txt"]).returncode == 0
    assert _run(cwd=repo, args=["git", "commit", "-qm", "partial progress"]).returncode == 0
    run_tip = _run(cwd=repo, args=["git", "rev-parse", "HEAD"]).stdout.strip()

    capture_root = tmp_path / "capture"
    capture = capture_root / "bin" / WIP_CAPTURE_PROGRAM_FILENAME
    capture.parent.mkdir(parents=True)
    capture.write_text(wip_capture_program_source(), encoding="utf-8")
    capture.chmod(0o755)
    git_dir = repo / ".git"
    (git_dir / "livespec-green-incomplete-reentries").write_text("1\n", encoding="utf-8")
    (git_dir / "livespec-stage-cause").write_text(
        f"stage: implement\ncause: {_PARTIAL}\n", encoding="utf-8"
    )
    environment = dict(os.environ)
    environment["LIVESPEC_SANDBOX_GH_REFRESH_ROOT"] = str(capture_root)
    environment["LIVESPEC_PUBLISH_BRANCH"] = "feat/bd-ib-azrhxg"

    result = subprocess.run(
        ["sh", "-c", _script()],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    ref = "refs/livespec/wip/bd-ib-azrhxg/01PARTIAL/1"
    preserved_tip = _run(
        cwd=origin, args=["git", "rev-parse", "--verify", "-q", ref]
    ).stdout.strip()

    assert result.returncode != 0
    assert preserved_tip == run_tip
