"""An exhausted pr_refresh leaves the green pull request ready and names each round's target.

Work-item bd-ib-myvlqz. Two runs ended `refresh-repair-exhausted` and left their
verified pull request a draft for hours, with an ended-run reason naming only the
round count. Every case EXECUTES the shipped `pr_refresh` node bytes, taken
through `parse_dot_graph`, in a real throwaway clone against a real bare origin,
because both behaviours are shell: a substring assertion cannot tell an arm that
runs from one sitting behind an earlier `exit`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_BRANCH = "feat/bd-ib-myvlqz-fixture"
_SHARED = "shared.txt"
_ROUNDS = "livespec-refresh-repair-rounds"
_ENV_IDENTITY = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@example.invalid"}


def _git(*argv: str, cwd: Path) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COVERAGE_", "COV_CORE_"))}
    done = subprocess.run(
        ["git", *argv],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**env, **_ENV_IDENTITY},
    )
    return done.stdout.strip()


def _commit(*, cwd: Path, text: str, subject: str) -> str:
    _ = _git("config", "user.email", "t@example.invalid", cwd=cwd)
    _ = _git("config", "user.name", "Test", cwd=cwd)
    _ = (cwd / _SHARED).write_text(text, encoding="utf-8")
    _ = _git("add", _SHARED, cwd=cwd)
    _ = _git("commit", "--quiet", "-m", subject, cwd=cwd)
    return _git("rev-parse", "HEAD", cwd=cwd)


def _graph_script() -> str:
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script: str = graph.nodes["pr_refresh"]["script"]
    return (
        script.replace("{{ inputs.default_branch }}", "master")
        .replace("{{ inputs.sandbox_check_suite }}", "true")
        .replace("{{ inputs.conformance_hook_install }}", "")
    )


def _forge(*, root: Path) -> tuple[Path, Path]:
    """A `gh` on PATH that logs every call and reports the pull request unarmed."""
    bin_dir = root / "forge-bin"
    bin_dir.mkdir()
    log = root / "gh-calls.log"
    stub = bin_dir / "gh"
    _ = stub.write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {log}\n"
        "case \"$*\" in *autoMergeRequest*) printf 'null\\n' ;; esac\nexit 0\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return (bin_dir, log)


def _conflicted_run(*, root: Path, seeded_rounds: str | None) -> tuple[Path, Path, str]:
    """A published run whose refresh conflicts, optionally past two recorded rounds."""
    origin = root / "origin.git"
    origin.mkdir()
    _ = _git("init", "--bare", "--quiet", "--initial-branch=master", cwd=origin)
    seed = root / "seed"
    seed.mkdir()
    _ = _git("init", "--quiet", "--initial-branch=master", cwd=seed)
    _ = _commit(cwd=seed, text="base\n", subject="chore: seed")
    _ = _git("push", "--quiet", str(origin), "HEAD:refs/heads/master", cwd=seed)
    clone = root / "clone"
    _ = _git("clone", "--quiet", str(origin), str(clone), cwd=root)
    _ = _git("switch", "--quiet", "-c", "fabro/run/test", cwd=clone)
    published = _commit(cwd=clone, text="this run's edit\n", subject="feat: edit")
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=clone)
    state = clone / ".git" / "livespec-publication"
    state.mkdir(parents=True)
    _ = (state / "livespec-publish-head").write_text(published, encoding="utf-8")
    _ = _commit(cwd=seed, text="a conflicting default edit\n", subject="feat: advance")
    _ = _git("push", "--quiet", str(origin), "HEAD:refs/heads/master", cwd=seed)
    if seeded_rounds is not None:
        _ = (state / "livespec-refresh-repair-count").write_text("2\n", encoding="utf-8")
        _ = (state / _ROUNDS).write_text(seeded_rounds, encoding="utf-8")
    return (clone, state, published)


def _run(*, root: Path, clone: Path) -> tuple[subprocess.CompletedProcess[str], Path]:
    forge, log = _forge(root=root)
    done = subprocess.run(
        ["bash", "-c", _graph_script()],
        cwd=clone,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": f"{forge}:/usr/local/bin:/usr/bin:/bin",
            "HOME": str(root / "home"),
            "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
            "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(root / "no-gh-refresh"),
        },
    )
    return (done, log)


def test_a_repair_round_records_the_gate_target_it_was_spent_on(tmp_path: Path) -> None:
    clone, state, _published = _conflicted_run(root=tmp_path, seeded_rounds=None)
    done, _log = _run(root=tmp_path, clone=clone)
    rounds = (state / _ROUNDS).read_text(encoding="utf-8")
    assert done.returncode != 0
    assert rounds.startswith("round 1: conflicted-paths ")
    assert _SHARED in rounds


def test_an_exhausted_refresh_names_each_round_and_leaves_the_pull_request_ready(
    tmp_path: Path,
) -> None:
    seeded = (
        "round 1: failed-gate-targets generated-record-file:tests/register.json \n"
        "round 2: failed-gate-targets generated-record-file:tests/register.json \n"
    )
    clone, _state, published = _conflicted_run(root=tmp_path, seeded_rounds=seeded)
    done, log = _run(root=tmp_path, clone=clone)
    reason = (clone / ".git" / "livespec-needs-human-reason").read_text(encoding="utf-8")
    first = reason.splitlines()[0]
    calls = log.read_text(encoding="utf-8").splitlines()
    flagged = [c for c in calls if c.startswith("pr edit") and "--add-label do-not-merge" in c]
    readied = [c for c in calls if c.startswith("pr ready")]
    assert done.returncode == 0, done.stderr
    assert first.startswith("refresh-repair-exhausted:")
    assert published in first
    assert first.count("generated-record-file:tests/register.json") == 2
    assert "round 1" in first
    assert "round 2" in first
    assert flagged
    assert readied
    assert calls.index(flagged[0]) < calls.index(readied[0])
    assert "LIVESPEC_REFRESH_REPAIR_EXHAUSTED_READY" in done.stderr


def test_pr_refresh_asks_its_head_check_against_the_default_branch_it_refreshed_onto() -> None:
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script: str = graph.nodes["pr_refresh"]["script"]
    assert '--check-head --default-ref "$base"' in script
