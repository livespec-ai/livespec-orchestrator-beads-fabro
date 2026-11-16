"""Scenario 368 (work-item bd-ib-jo3bl4) — the publish fold keeps the authored message and runs no commit hook.

`publish_draft` folds a run branch that carries engine checkpoint commits into one
commit under the authored subject. The fold re-commits an already replay-checked
tree, so it must not run the repository's commit hooks: the red-green-replay hook
reads a staged test beside non-Python implementation as a Red moment, finds the test
passing and refuses, which ended factory runs at `needs_human` with
LIVESPEC_PUBLISH_DRAFT_HISTORY_SANITIZE_FAILED. The fold also carries the authored
commit's FULL message, so its TDD trailers survive. These cases execute the committed
node script in a local git fixture with a real bare origin whose commit hooks refuse
every commit:

- the fold publishes, the pushed head's tree equals the run branch's tree, and the
  pushed head carries the authored commit's full message;
- the pushed range holds no `fabro(` subject.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    parse_dot_graph,
)

_WORKFLOW = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
_PUBLISH_BRANCH = "feat/bd-ib-jo3bl4"
_AUTHORED = (
    "fix(workflow): an authored subject\n"
    "\n"
    "A body paragraph the fold must keep.\n"
    "\n"
    "TDD-Red-Test-File-Checksum: sha256:abc\n"
    "TDD-Green-Verified-At: 2026-11-16T22:00:00Z\n"
)


def _git(cwd: Path, *argv: str) -> str:
    result = subprocess.run(
        ["git", *argv], cwd=str(cwd), check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def _script() -> str:
    parsed = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    return (
        parsed.nodes["publish_draft"]["script"]
        .replace("{{ inputs.default_branch }}", "master")
        .replace("{{ inputs.conformance_hook_install }}", "")
    )


def _sandbox(*, tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    _ = _git(tmp_path, "init", "--bare", "-b", "master", str(origin))
    work = tmp_path / "work"
    work.mkdir()
    _ = _git(work, "init", "-b", "master")
    _ = _git(work, "config", "user.name", "fold-test")
    _ = _git(work, "config", "user.email", "fold-test@example.invalid")
    _ = (work / "base.txt").write_text("base\n", encoding="utf-8")
    _ = _git(work, "add", "base.txt")
    _ = _git(work, "commit", "-m", "base")
    _ = _git(work, "remote", "add", "origin", str(origin))
    _ = _git(work, "push", "-u", "origin", "master")
    _ = _git(work, "switch", "-c", "fabro/run/fold")
    (work / "tests").mkdir()
    _ = (work / "tests" / "test_change.py").write_text(
        "def test_it():\n    pass\n", encoding="utf-8"
    )
    _ = (work / "change.json").write_text("{}\n", encoding="utf-8")
    _ = _git(work, "add", "tests/test_change.py", "change.json")
    _ = _git(work, "commit", "-m", _AUTHORED)
    _ = (work / "checkpoint.txt").write_text("checkpoint\n", encoding="utf-8")
    _ = _git(work, "add", "checkpoint.txt")
    _ = _git(work, "commit", "-m", "fabro(01FOLD): janitor (success)")
    # From here every commit is refused, as the red-green-replay hook refuses a
    # staged test beside non-Python implementation: the fold must not run it.
    for name in ("pre-commit", "commit-msg"):
        hook = work / ".git" / "hooks" / name
        _ = hook.write_text(
            "#!/bin/sh\necho 'hook refused the fold' >&2\nexit 1\n", encoding="utf-8"
        )
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    return work


def _env(*, tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    _ = gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE")
    }
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
            "LIVESPEC_GIT_AUTHOR_NAME": "Fold Test",
            "LIVESPEC_GIT_AUTHOR_EMAIL": "fold-test@example.invalid",
            "LIVESPEC_PUBLISH_BRANCH": _PUBLISH_BRANCH,
        }
    )
    return env


def _publish(*, work: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", _script()],
        cwd=str(work),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_the_fold_publishes_the_run_tree_under_the_authored_message_with_no_hook(
    tmp_path: Path,
) -> None:
    work = _sandbox(tmp_path=tmp_path)
    run_tree = _git(work, "rev-parse", "HEAD^{tree}")

    publish = _publish(work=work, env=_env(tmp_path=tmp_path))

    assert publish.returncode == 0, publish.stderr
    pushed = _git(work, "ls-remote", "origin", f"refs/heads/{_PUBLISH_BRANCH}").split()[0]
    assert _git(work, "rev-parse", f"{pushed}^{{tree}}") == run_tree
    assert _git(work, "log", "-1", "--format=%B", pushed) == _AUTHORED.rstrip("\n")
    subjects = _git(work, "log", "--format=%s", f"master..{pushed}").splitlines()
    assert subjects == ["fix(workflow): an authored subject"]
