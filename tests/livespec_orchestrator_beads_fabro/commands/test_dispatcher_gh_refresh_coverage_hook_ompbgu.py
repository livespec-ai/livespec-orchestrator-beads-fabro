"""The sandbox `gh` wrapper runs its mint helper outside coverage's subprocess hook (bd-ib-ompbgu).

Measured by throughput-plans-coordinator on livespec-dev-tooling run 01M7SGZ18N7C
(bd-ib-pvtohb, failed at fix@2): the wrapper runs `python3 "$mint"` before every `gh` call, that
`python3` is the project venv's under `uv run pytest`, and pytest-cov's pth startup hook
instruments it, so `mint_app_token.py` counts as measured source and per-file coverage falls to
99.98 percent. The bundle moved to `$HOME/.claude/plugins/livespec-gh-refresh` while a
repository's coverage omit still names the old `/workspace/.livespec-gh-refresh/*` root.

The wrapper is installed by executing the RENDERED prepare steps for real in a throwaway git
clone, exactly as the sibling tests of this bundle do, and the helper is a `python3` stub that
records which coverage variables reached it.
"""

import subprocess
from pathlib import Path

import pytest

from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_gh_refresh_worktree import (
    _BUNDLE_DIRNAME,
    _chain_env,
    _git_repo,
    _rendered_prepare_scripts,
    _run_prepare_chain,
    _stub_path_dir,
    _write_executable,
)

_COVERAGE_VARIABLES = {
    "COVERAGE_PROCESS_START": "/sandbox/.coveragerc",
    "COV_CORE_SOURCE": "src",
    "COV_CORE_CONFIG": "/sandbox/pyproject.toml",
    "COV_CORE_DATAFILE": "/sandbox/.coverage",
    "COV_CORE_BRANCH": "enabled",
    "COV_CORE_CONTEXT": "unit",
}


def _wrapper_call(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Install the wrapper, put a recording `python3` stub in front, run `gh auth status`."""
    repo = _git_repo(root=tmp_path / "clone")
    bundle_root = repo / _BUNDLE_DIRNAME
    scripts = _rendered_prepare_scripts(monkeypatch=monkeypatch, bundle_root=bundle_root)
    capture = tmp_path / "gh-calls.txt"
    bin_dir = _stub_path_dir(root=tmp_path / "bin", capture=capture)
    _run_prepare_chain(scripts=scripts, repo=repo, bin_dir=bin_dir, tmp_path=tmp_path)
    # Only now: the helper fetch writes the bundle through the REAL python3.
    seen = tmp_path / "mint-coverage-env.txt"
    _write_executable(
        path=bin_dir / "python3",
        source="#!/usr/bin/env bash\n"
        "set -eu\n"
        "env | grep -E '^(COVERAGE_PROCESS_START|COV_CORE_[A-Z]+)=' >> \"$MINT_ARG_LOG\" || true\n"
        "printf minted-token\n",
    )
    env = {
        **_chain_env(bin_dir=bin_dir, capture=capture, mint_log=seen),
        **_COVERAGE_VARIABLES,
    }
    _ = subprocess.run(
        ["gh", "auth", "status"], cwd=repo, env=env, capture_output=True, text=True, check=True
    )
    return seen, capture


def test_the_mint_helper_runs_with_no_coverage_variable_in_its_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen, _capture = _wrapper_call(tmp_path=tmp_path, monkeypatch=monkeypatch)

    assert seen.read_text(encoding="utf-8") == ""


def test_the_minted_token_still_reaches_the_real_gh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seen, capture = _wrapper_call(tmp_path=tmp_path, monkeypatch=monkeypatch)

    assert capture.read_text(encoding="utf-8").splitlines() == [
        "args=auth status",
        "GH_TOKEN=minted-token",
        "GITHUB_TOKEN=minted-token",
    ]
