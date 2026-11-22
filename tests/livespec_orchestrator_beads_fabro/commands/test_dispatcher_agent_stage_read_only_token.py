"""An agent stage mints a READ-ONLY installation token (bd-ib-2cye52, ruling R301).

Stacked on bd-ib-ssipvb, whose dispatcher record (`agent-stage` in the bundle root) names the
node a run is executing, and whose guard already refuses publication from an agent stage. That
guard stops the publishing COMMANDS it knows; a token that can still publish is one command
spelling away from doing so. So when the recorded node is an agent stage the wrapper asks the
mint helper for a token with read permissions only, and sets that request itself: a value the
agent exported is cleared, and a publication node asks for nothing narrower than today.

The permission set is the subset the factory App is measured to be granted (2026-11-22: `issues`
and `actions` are refused with HTTP 422, `contents`, `metadata`, `pull_requests`, `checks` and
`statuses` are accepted). A refused mint exits non-zero and says so on stderr, so a permission
the App lacks fails the `gh` call loudly rather than quietly widening the token.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import gh_mint_helper_source

from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_agent_stage_record_ssipvb import (
    _RECORD_NAME,
    _agent_env,
    _installed_wrapper,
    _record_stage,
)
from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_gh_refresh_worktree import (
    _write_executable,
)

_PLUGIN_SCRIPTS = Path(__file__).resolve().parents[3] / ".claude-plugin" / "scripts"
_SCRUBBED = (
    "COVERAGE_PROCESS_START",
    "COV_CORE_",
    "LIVESPEC_AGENT_STAGE",
    "LIVESPEC_GH_TOKEN_SCOPE",
)


def _clean_environ() -> dict[str, str]:
    """The test process environment without coverage hooks or the scope variable."""
    return {k: v for k, v in os.environ.items() if not k.startswith(_SCRUBBED)}


def _scope_asked(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str | None, inherited: str | None
) -> str:
    """Run `gh pr view` through the installed wrapper; the scope the mint was asked for."""
    repo, bundle_root, bin_dir, capture = _installed_wrapper(
        tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    scope_file = tmp_path / "mint-scope.txt"
    _write_executable(
        path=bin_dir / "python3",
        source=f'#!/bin/sh\nprintf "%s" "${{LIVESPEC_GH_TOKEN_SCOPE:-full}}" > "{scope_file}"\n'
        "printf minted-token\n",
    )
    if stage is not None:
        _record_stage(record=bundle_root / _RECORD_NAME, stage=stage)
    env = _agent_env(bin_dir=bin_dir, capture=capture, tmp_path=tmp_path)
    if inherited is not None:
        env["LIVESPEC_GH_TOKEN_SCOPE"] = inherited
    result = subprocess.run(
        ["gh", "pr", "view", "1"], cwd=repo, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    return scope_file.read_text(encoding="utf-8")


@pytest.mark.parametrize("stage", ["implement", "proof_verify", "review_fix"])
def test_a_recorded_agent_stage_asks_for_a_read_only_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    asked = _scope_asked(tmp_path=tmp_path, monkeypatch=monkeypatch, stage=stage, inherited=None)

    assert asked == "read"


@pytest.mark.parametrize("stage", [None, "publish_draft", "pr_refresh", "pr"])
def test_a_publication_node_asks_for_the_full_token_whatever_the_environment_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str | None
) -> None:
    asked = _scope_asked(tmp_path=tmp_path, monkeypatch=monkeypatch, stage=stage, inherited="read")

    assert asked == "full"


def _mint_request_bodies(*, tmp_path: Path, scope: str | None) -> list[object]:
    """Run the rendered mint helper against a fake GitHub API; return each POST body."""
    bundle_root = tmp_path / f"mint-bundle-{scope}"
    (bundle_root / "bin").mkdir(parents=True)
    _write_executable(
        path=bundle_root / "bin" / "mint_app_token.py", source=gh_mint_helper_source()
    )
    (bundle_root / "_vendor").symlink_to(_PLUGIN_SCRIPTS / "_vendor")
    key = bundle_root / "key.pem"
    subprocess.run(["openssl", "genrsa", "-out", str(key), "2048"], check=True, capture_output=True)
    driver = bundle_root / "driver.py"
    driver.write_text(
        "import io, json, runpy, sys, urllib.request\n"
        "seen = []\n"
        "class Resp(io.BytesIO):\n"
        "    def __enter__(self): return self\n"
        "    def __exit__(self, *a): return False\n"
        "def fake(request, timeout=None):\n"
        "    seen.append(json.loads(request.data or b'null'))\n"
        "    return Resp(json.dumps({'token': 'tok'}).encode())\n"
        "urllib.request.urlopen = fake\n"
        "sys.argv = [sys.argv[1]]\n"
        "runpy.run_path(sys.argv[0], run_name='mint')\n"
        "sys.stderr.write(json.dumps(seen))\n",
        encoding="utf-8",
    )
    env = {
        **_clean_environ(),
        "GITHUB_APP_ID": "42",
        "GITHUB_PRIVATE_KEY": key.read_text(encoding="utf-8"),
        "GITHUB_APP_INSTALLATION_ID": "7",
    }
    if scope is not None:
        env["LIVESPEC_GH_TOKEN_SCOPE"] = scope
    done = subprocess.run(
        [sys.executable, str(driver), str(bundle_root / "bin" / "mint_app_token.py")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stderr.splitlines()[-1])


def test_the_mint_helper_requests_only_granted_read_permissions_for_a_read_scope(
    tmp_path: Path,
) -> None:
    """Scope `read` narrows the installation token; no scope keeps today's full token."""
    narrowed = _mint_request_bodies(tmp_path=tmp_path, scope="read")
    assert len(narrowed) == 1
    body = narrowed[0]
    assert isinstance(body, dict)
    permissions = body.get("permissions")
    assert isinstance(permissions, dict)
    assert {"contents", "pull_requests"} <= set(permissions)
    assert set(permissions.values()) == {"read"}
    assert not {"issues", "actions"} & set(permissions)

    assert _mint_request_bodies(tmp_path=tmp_path, scope=None) == [{}]
