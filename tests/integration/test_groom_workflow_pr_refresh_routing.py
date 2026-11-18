"""The groom workflow's `pr_refresh` node, EXECUTED, not only compared by bytes.

`test_scripted_publication_stages.py` proves the groom copy of `pr_refresh` is
byte-identical to the implement-work-item copy. Identical bytes are an
intention: this module runs the groom graph's own node in a real throwaway clone
against a real bare origin, so the three behaviours of work-item bd-ib-myvlqz
(livespec-orchestrator-beads-fabro#5489) are observed on the groom copy itself.

- An exhausted refresh names each round's failed gate target, labels the pull
  request `do-not-merge`, and only then marks it ready for review.
- A repair round records the target it was spent on.
- A generated record file the default branch already carries out of generator
  order is not spent as a repair round, and the stage names the default-branch
  commit it compared against.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_declaration import (
    PLUGIN_BLOCK,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_regeneration import (
    RECORD_FILE_PROGRAM_FILENAME,
    record_file_program_source,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GROOM_WORKFLOW = _REPO_ROOT / ".fabro" / "workflows" / "groom-work-item" / "workflow.fabro"
_BRANCH = "feat/bd-ib-myvlqz-groom-fixture"
_SHARED = "shared.txt"
_REGISTER = "register.json"
_ROUNDS = "livespec-refresh-repair-rounds"
_IDENTITY = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _git(*argv: str, cwd: Path) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COVERAGE_", "COV_CORE_"))}
    done = subprocess.run(
        ["git", *argv],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**env, **_IDENTITY},
    )
    return done.stdout.strip()


def _commit(*, cwd: Path, files: dict[str, str], subject: str) -> str:
    for name, text in files.items():
        _ = (cwd / name).write_text(text, encoding="utf-8")
        if name.endswith(".sh"):
            (cwd / name).chmod(0o755)
    _ = _git("add", "-A", cwd=cwd)
    _ = _git("commit", "--quiet", "-m", subject, cwd=cwd)
    return _git("rev-parse", "HEAD", cwd=cwd)


def _groom_script() -> str:
    graph = parse_dot_graph(text=_GROOM_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script: str = graph.nodes["pr_refresh"]["script"]
    return (
        script.replace("{{ inputs.default_branch }}", "master")
        .replace("{{ inputs.sandbox_check_suite }}", "false")
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


def _plugins(*, root: Path) -> Path:
    """The sandbox plugins root the refresh stage reads its materialized programs from."""
    plugins = root / "plugins"
    plugins.mkdir()
    _ = (plugins / RECORD_FILE_PROGRAM_FILENAME).write_text(
        record_file_program_source(), encoding="utf-8"
    )
    _ = (plugins / "livespec-run-plugin-gate.py").write_text("", encoding="utf-8")
    return plugins


def _world(*, root: Path, seed_files: dict[str, str]) -> tuple[Path, Path, Path]:
    """A bare origin, its seed clone, and a run clone on its own branch."""
    origin = root / "origin.git"
    origin.mkdir()
    _ = _git("init", "--bare", "--quiet", "--initial-branch=master", cwd=origin)
    seed = root / "seed"
    seed.mkdir()
    _ = _git("init", "--quiet", "--initial-branch=master", cwd=seed)
    _ = _commit(cwd=seed, files=seed_files, subject="chore: seed")
    _ = _git("push", "--quiet", str(origin), "HEAD:refs/heads/master", cwd=seed)
    clone = root / "clone"
    _ = _git("clone", "--quiet", str(origin), str(clone), cwd=root)
    _ = _git("switch", "--quiet", "-c", "fabro/run/test", cwd=clone)
    return (origin, seed, clone)


def _publish(*, origin: Path, clone: Path, files: dict[str, str]) -> str:
    published = _commit(cwd=clone, files=files, subject="feat: the run's edit")
    _ = _git("push", "--quiet", str(origin), f"HEAD:refs/heads/{_BRANCH}", cwd=clone)
    state = clone / ".git" / "livespec-publication"
    state.mkdir(parents=True)
    _ = (state / "livespec-publish-head").write_text(published, encoding="utf-8")
    return published


def _advance(*, origin: Path, seed: Path, files: dict[str, str]) -> None:
    _ = _commit(cwd=seed, files=files, subject="feat: advance the default branch")
    _ = _git("push", "--quiet", str(origin), "HEAD:refs/heads/master", cwd=seed)


def _run(*, root: Path, clone: Path) -> tuple[subprocess.CompletedProcess[str], Path]:
    forge, log = _forge(root=root)
    done = subprocess.run(
        ["bash", "-c", _groom_script()],
        cwd=clone,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": f"{forge}:/usr/local/bin:/usr/bin:/bin",
            "HOME": str(root / "home"),
            "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
            "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(root / "no-gh-refresh"),
            "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(_plugins(root=root)),
            **_IDENTITY,
        },
    )
    return (done, log)


def _conflicted_run(*, root: Path, seeded_rounds: str | None) -> tuple[Path, Path, str]:
    """A published run whose refresh conflicts, optionally past two recorded rounds."""
    origin, seed, clone = _world(root=root, seed_files={_SHARED: "base\n"})
    published = _publish(origin=origin, clone=clone, files={_SHARED: "this run's edit\n"})
    _advance(origin=origin, seed=seed, files={_SHARED: "a conflicting default edit\n"})
    state = clone / ".git" / "livespec-publication"
    if seeded_rounds is not None:
        _ = (state / "livespec-refresh-repair-count").write_text("2\n", encoding="utf-8")
        _ = (state / _ROUNDS).write_text(seeded_rounds, encoding="utf-8")
    return (clone, state, published)


def test_a_groom_repair_round_records_the_gate_target_it_was_spent_on(tmp_path: Path) -> None:
    clone, state, _published = _conflicted_run(root=tmp_path, seeded_rounds=None)
    done, _log = _run(root=tmp_path, clone=clone)
    rounds = (state / _ROUNDS).read_text(encoding="utf-8")
    assert done.returncode != 0
    assert rounds.startswith("round 1: conflicted-paths ")
    assert _SHARED in rounds


def test_an_exhausted_groom_refresh_names_each_round_and_leaves_the_pull_request_ready(
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
    assert flagged
    assert readied
    assert calls.index(flagged[0]) < calls.index(readied[0])
    assert "LIVESPEC_REFRESH_REPAIR_EXHAUSTED_READY" in done.stderr


def test_a_groom_refresh_does_not_spend_a_round_on_drift_the_default_branch_carries(
    tmp_path: Path,
) -> None:
    """The default branch carries an out-of-order register; the run only edits another file.

    The declared check suite is `false`, so the stage still ends in a repair round,
    but on the SUITE and not on the register: the head check passed the register
    and named the default-branch commit it compared against.
    """
    entries = [{"path": _REGISTER, "generator": ["./generate.sh"]}]
    declaration = "// a committed declaration\n" + json.dumps(
        {PLUGIN_BLOCK: {"dispatcher": {"record_files": entries}}}
    )
    origin, seed, clone = _world(
        root=tmp_path,
        seed_files={
            ".livespec.jsonc": declaration,
            "generate.sh": "#!/bin/sh\nexec cp registry.json register.json\n",
            "registry.json": '["a", "b"]\n',
            _REGISTER: '["b", "a"]\n',
        },
    )
    _ = _publish(origin=origin, clone=clone, files={_SHARED: "the run's edit\n"})
    _advance(origin=origin, seed=seed, files={"other.txt": "an unrelated default edit\n"})
    default = _git("rev-parse", "HEAD", cwd=seed)
    done, _log = _run(root=tmp_path, clone=clone)
    state = clone / ".git" / "livespec-publication"
    rounds = (state / _ROUNDS).read_text(encoding="utf-8")
    assert "LIVESPEC_RECORD_FILE_DEFAULT_CARRIED" in done.stderr
    assert _REGISTER in done.stderr
    assert default in done.stderr
    assert "generated-record-file" not in rounds
    assert rounds.startswith("round 1: failed-gate-targets")
