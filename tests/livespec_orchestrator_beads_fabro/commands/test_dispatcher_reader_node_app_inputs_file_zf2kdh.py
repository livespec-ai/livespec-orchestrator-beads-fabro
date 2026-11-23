"""INTERIM: command nodes that only READ the forge hold no App input in their environment (bd-ib-zf2kdh).

Coordinator ruling under R301, 2026-11-23: the workflow launches no broker or credential daemon
today, so the seven reader node groups (the setup chain, `janitor`, `proof_grade`,
`pr_refresh_head`, `verify_pr`, `recapture_route` and `non_converged`) read the forge through the
refreshing `gh` wrapper from an INTERIM 0600 file the wrapper-install step writes in the bundle
root, and carry no `GITHUB_*` input in their own environment. The file lives only for the run, and
`bd-ib-w64kr3` removes it under the run-level credential daemon.

A node whose environment still carries the inputs is a publication node and mints exactly as before;
a node without them mints a READ-ONLY token from the file.
"""

import stat
import subprocess
from pathlib import Path

import pytest

from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_agent_stage_record_ssipvb import (
    _agent_env,
    _installed_wrapper,
)
from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_gh_refresh_worktree import (
    _write_executable,
)

_INPUTS_FILE = "app-inputs.env"
_INPUT_NAMES = (
    "GITHUB_APP_ID",
    "GITHUB_PRIVATE_KEY",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_API_URL",
)


def _mint_sees(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, inputs_in_env: bool) -> str:
    """Run `gh pr view` through the installed wrapper; what the mint helper saw."""
    repo, _bundle_root, bin_dir, _capture = _installed_wrapper(
        tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    seen = tmp_path / "mint-saw.txt"
    _write_executable(
        path=bin_dir / "python3",
        source='#!/usr/bin/env bash\nset -eu\nprintf "scope=%s id=%s key=%s" '
        '"${LIVESPEC_GH_TOKEN_SCOPE:-full}" "${GITHUB_APP_ID:-}" "${GITHUB_PRIVATE_KEY:-}"'
        f' > "{seen}"\nprintf minted-token\n',
    )
    env = _agent_env(bin_dir=bin_dir, capture=tmp_path / "gh-calls.txt", tmp_path=tmp_path)
    for name in ("LIVESPEC_GH_TOKEN_SCOPE", "GH_TOKEN", "GITHUB_TOKEN"):
        env.pop(name, None)
    if not inputs_in_env:
        for name in _INPUT_NAMES:
            env.pop(name, None)
    result = subprocess.run(
        ["gh", "pr", "view", "1"], cwd=repo, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    return seen.read_text(encoding="utf-8")


def test_the_install_step_writes_an_owner_only_inputs_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo, bundle_root, _bin, _capture = _installed_wrapper(
        tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    inputs_file = bundle_root / _INPUTS_FILE
    assert inputs_file.is_file()
    assert stat.S_IMODE(inputs_file.stat().st_mode) == 0o600
    assert "GITHUB_APP_ID" in inputs_file.read_text(encoding="utf-8")


def test_a_node_without_the_inputs_mints_a_read_only_token_from_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saw = _mint_sees(tmp_path=tmp_path, monkeypatch=monkeypatch, inputs_in_env=False)

    assert saw == "scope=read id=42 key=stub-pem"


def test_a_node_that_still_carries_the_inputs_mints_the_full_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saw = _mint_sees(tmp_path=tmp_path, monkeypatch=monkeypatch, inputs_in_env=True)

    assert saw == "scope=full id=42 key=stub-pem"
