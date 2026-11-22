"""The publication guard takes the stage from the dispatcher's record, never from the environment.

Measured 2026-11-21/22 (bd-ib-ssipvb): an agent stage ran
`env LIVESPEC_AGENT_STAGE=pr gh pr create` and `... gh pr merge --auto`, and a
plain `git push` authenticated through the `!gh auth git-credential` helper; the
guard read the stage from `LIVESPEC_AGENT_STAGE`, which the agent sets itself.

The first Red of this item (factory run 01M7YMS52TY7) was defective: its fixture
put `LIVESPEC_AGENT_STAGE=proof_verify` in the launching environment and then
asserted `env LIVESPEC_AGENT_STAGE=pr gh ...` is refused. The wrapper saw the same
argv, environment and parent as a direct launch under `pr`, so nothing the fixture
supplied told the two cases apart. These tests supply what the dispatcher records
for the node: a stage record file in the bundle root, naming the live launcher
process and the stage it launched. The launching environment says nothing about
the stage, so a variable the agent writes is the only thing that differs.
"""

import os
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_push import PUSH_ORIGIN_SOURCE

from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_gh_refresh_worktree import (
    _BUNDLE_DIRNAME,
    _chain_env,
    _git_repo,
    _rendered_prepare_scripts,
    _run_prepare_chain,
    _stub_path_dir,
    _write_executable,
)

_RECORD_NAME = "agent-stage"


def _record_stage(*, record: Path, stage: str) -> None:
    """The dispatcher's record: the live launcher's pid, then the node it launched."""
    record.write_text(f"{os.getpid()} {stage}\n", encoding="utf-8")


def _agent_env(*, bin_dir: Path, capture: Path, tmp_path: Path) -> dict[str, str]:
    env = _chain_env(bin_dir=bin_dir, capture=capture, mint_log=tmp_path / "mint-args.txt")
    env.pop("LIVESPEC_AGENT_STAGE", None)
    return env


def _installed_wrapper(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path, Path]:
    repo = _git_repo(root=tmp_path / "clone")
    bundle_root = repo / _BUNDLE_DIRNAME
    scripts = _rendered_prepare_scripts(monkeypatch=monkeypatch, bundle_root=bundle_root)
    capture = tmp_path / "gh-calls.txt"
    bin_dir = _stub_path_dir(root=tmp_path / "bin", capture=capture)
    _run_prepare_chain(scripts=scripts, repo=repo, bin_dir=bin_dir, tmp_path=tmp_path)
    _write_executable(
        path=bin_dir / "python3",
        source="#!/usr/bin/env bash\nset -eu\nprintf minted-token\n",
    )
    return repo, bundle_root, bin_dir, capture


def test_an_inline_stage_assignment_does_not_lift_the_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, bundle_root, bin_dir, capture = _installed_wrapper(
        tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    _record_stage(record=bundle_root / _RECORD_NAME, stage="proof_verify")

    result = subprocess.run(
        ["env", "LIVESPEC_AGENT_STAGE=pr", "gh", "pr", "create"],
        cwd=repo,
        env=_agent_env(bin_dir=bin_dir, capture=capture, tmp_path=tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "LIVESPEC_AGENT_PUBLICATION_DENIED: stage=proof_verify action=gh_pr_create" in result.stderr
    )
    assert not capture.exists()


def test_an_exported_stage_does_not_lift_the_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, bundle_root, bin_dir, capture = _installed_wrapper(
        tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    _record_stage(record=bundle_root / _RECORD_NAME, stage="proof_verify")

    result = subprocess.run(
        ["bash", "-c", "export LIVESPEC_AGENT_STAGE=pr; gh pr merge 7 --auto --rebase"],
        cwd=repo,
        env=_agent_env(bin_dir=bin_dir, capture=capture, tmp_path=tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "LIVESPEC_AGENT_PUBLICATION_DENIED: stage=proof_verify action=gh_pr_merge" in result.stderr
    )
    assert not capture.exists()


def test_the_push_helper_ignores_a_stage_the_agent_sets(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    helper = bin_dir / "push_origin"
    _write_executable(path=helper, source=PUSH_ORIGIN_SOURCE)
    _record_stage(record=tmp_path / _RECORD_NAME, stage="proof_verify")

    result = subprocess.run(
        ["env", "LIVESPEC_AGENT_STAGE=pr", str(helper), "git", "push", "origin", "HEAD:feature"],
        cwd=tmp_path,
        env={k: v for k, v in os.environ.items() if k != "LIVESPEC_AGENT_STAGE"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "LIVESPEC_AGENT_PUBLICATION_DENIED: stage=proof_verify action=push_origin" in result.stderr
    )


def _fake_git(*, bin_dir: Path) -> None:
    """A `git` whose every subcommand asks the credential helper, as git does over https."""
    _write_executable(
        path=bin_dir / "git",
        source="#!/usr/bin/env bash\ngh auth git-credential get </dev/null\nexit $?\n",
    )


def test_a_plain_git_push_is_refused_at_the_credential_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, bundle_root, bin_dir, capture = _installed_wrapper(
        tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    _record_stage(record=bundle_root / _RECORD_NAME, stage="proof_verify")
    _fake_git(bin_dir=bin_dir)

    result = subprocess.run(
        ["git", "push", "origin", "HEAD:refs/heads/feat/x"],
        cwd=repo,
        env=_agent_env(bin_dir=bin_dir, capture=capture, tmp_path=tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "LIVESPEC_AGENT_PUBLICATION_DENIED: stage=proof_verify action=git_push" in result.stderr
    assert not capture.exists()


def test_an_agent_stage_fetch_still_gets_a_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, bundle_root, bin_dir, capture = _installed_wrapper(
        tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    _record_stage(record=bundle_root / _RECORD_NAME, stage="proof_verify")
    _fake_git(bin_dir=bin_dir)

    result = subprocess.run(
        ["git", "fetch", "origin"],
        cwd=repo,
        env=_agent_env(bin_dir=bin_dir, capture=capture, tmp_path=tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert capture.read_text(encoding="utf-8").splitlines()[0] == "args=auth git-credential get"
