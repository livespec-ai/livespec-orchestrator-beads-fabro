"""A generated record file the default branch itself carries out of order passes.

Work-item bd-ib-myvlqz. Two factory runs ended `refresh-repair-exhausted` on the
same gate target, `generated-record-file:tests/heading-coverage-debt.json`,
because the DEFAULT BRANCH's own copy of that register was not in its
generator's order. A refresh repair regenerates the register, the next refresh
puts the default branch's bytes back, and the loop spends about 75 to 90 minutes
per round without ever converging.

The discriminator these cases pin is whose change makes the head's register
differ from its generator's output. When the head's file is byte-identical to the
default branch's AND the generator over the default branch's own tree produces
the same bytes as the generator over the head, the drift is the default
branch's: the head passes, and the stage names the target and the default-branch
commit it compared against. Any other drift is the pull request's own, and the
head fails exactly as before.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_record_file_regeneration
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_declaration import (
    PLUGIN_BLOCK,
)

_REGISTER = "register.json"
_ORDERED = '["a", "b"]\n'
_OUT_OF_ORDER = '["b", "a"]\n'


def _git(*, repo: Path, args: list[str]) -> str:
    done = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return done.stdout.strip()


def _program(*, tmp_path: Path) -> ModuleType:
    module = _dispatcher_record_file_regeneration
    path = tmp_path / module.RECORD_FILE_PROGRAM_FILENAME
    _ = path.write_text(module.record_file_program_source(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("livespec_record_file_resolution", path)
    assert spec is not None
    assert spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def _commit(*, repo: Path, message: str) -> str:
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "--quiet", "--no-verify", "-m", message])
    return _git(repo=repo, args=["rev-parse", "HEAD"])


def _default_branch(*, tmp_path: Path, register: str) -> tuple[Path, str]:
    """A repository whose default branch commit carries `register` as its register.

    The generator is the real shape: it derives the register from the registry
    that sits beside it, so `["a", "b"]` registry means an ordered register is
    `["a", "b"]`, and `["b", "a"]` is the default branch's own out-of-order copy.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo=repo, args=["init", "--quiet", "--initial-branch", "master"])
    _git(repo=repo, args=["config", "user.name", "Test"])
    _git(repo=repo, args=["config", "user.email", "test@example.com"])
    entries = [{"path": _REGISTER, "generator": ["./generate.sh"]}]
    _ = (repo / ".livespec.jsonc").write_text(
        "// a committed declaration\n"
        + json.dumps({PLUGIN_BLOCK: {"dispatcher": {"record_files": entries}}}),
        encoding="utf-8",
    )
    script = repo / "generate.sh"
    _ = script.write_text("#!/bin/sh\nexec cp registry.json register.json\n", encoding="utf-8")
    script.chmod(0o755)
    _ = (repo / "registry.json").write_text(_ORDERED, encoding="utf-8")
    _ = (repo / _REGISTER).write_text(register, encoding="utf-8")
    return (repo, _commit(repo=repo, message="default branch"))


def _check_head(
    *, program: ModuleType, tmp_path: Path, default: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, str]:
    monkeypatch.chdir(tmp_path / "repo")
    state = tmp_path / "state"
    state.mkdir()
    status = program.main(["--state-dir", str(state), "--check-head", "--default-ref", default])
    targets = (state / _dispatcher_record_file_regeneration.RECORD_FILE_TARGETS_FILENAME).read_text(
        encoding="utf-8"
    )
    return (status, targets)


def test_a_register_the_default_branch_carries_out_of_order_passes_and_names_its_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The head touches only an unrelated file, so the drift is the default branch's."""
    program = _program(tmp_path=tmp_path)
    repo, default = _default_branch(tmp_path=tmp_path, register=_OUT_OF_ORDER)
    _ = (repo / "unrelated.txt").write_text("a pull request change\n", encoding="utf-8")
    _ = _commit(repo=repo, message="the pull request")
    status, targets = _check_head(
        program=program, tmp_path=tmp_path, default=default, monkeypatch=monkeypatch
    )
    stderr = capsys.readouterr().err
    porcelain = _git(repo=repo, args=["status", "--porcelain"])
    worktrees = _git(repo=repo, args=["worktree", "list", "--porcelain"]).count("worktree ")
    assert status == 0
    assert targets == ""
    assert _REGISTER in stderr
    assert default in stderr
    assert porcelain == ""
    assert worktrees == 1


def test_a_register_made_stale_by_the_pull_request_s_own_change_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default branch is in order; the head's own registry change makes it stale."""
    program = _program(tmp_path=tmp_path)
    repo, default = _default_branch(tmp_path=tmp_path, register=_ORDERED)
    _ = (repo / "registry.json").write_text('["a", "b", "c"]\n', encoding="utf-8")
    _ = _commit(repo=repo, message="the pull request")
    status, targets = _check_head(
        program=program, tmp_path=tmp_path, default=default, monkeypatch=monkeypatch
    )
    assert status != 0
    assert targets.strip() == "generated-record-file:" + _REGISTER


def test_a_register_the_pull_request_hand_edited_over_a_drifted_default_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default branch drifts, but the head's register is not the default's bytes."""
    program = _program(tmp_path=tmp_path)
    repo, default = _default_branch(tmp_path=tmp_path, register=_OUT_OF_ORDER)
    _ = (repo / _REGISTER).write_text('["c"]\n', encoding="utf-8")
    _ = _commit(repo=repo, message="the pull request")
    status, targets = _check_head(
        program=program, tmp_path=tmp_path, default=default, monkeypatch=monkeypatch
    )
    assert status != 0
    assert targets.strip() == "generated-record-file:" + _REGISTER


def test_a_register_the_pull_request_changed_the_default_s_inputs_for_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both the default and the head drift, but the generator reads the head's own change."""
    program = _program(tmp_path=tmp_path)
    repo, default = _default_branch(tmp_path=tmp_path, register=_OUT_OF_ORDER)
    _ = (repo / "registry.json").write_text('["a", "b", "c"]\n', encoding="utf-8")
    _ = _commit(repo=repo, message="the pull request")
    status, targets = _check_head(
        program=program, tmp_path=tmp_path, default=default, monkeypatch=monkeypatch
    )
    assert status != 0
    assert targets.strip() == "generated-record-file:" + _REGISTER
