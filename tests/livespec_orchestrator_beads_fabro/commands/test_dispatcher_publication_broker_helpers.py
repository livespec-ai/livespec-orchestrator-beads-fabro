"""The publication broker ships in the helper bundle and runs from it alone.

The broker used to be launched from the TARGET repository's clone
(`$(pwd)/.claude-plugin/scripts/bin/publication_broker.py`), which only this
orchestrator's own clone carries; every other target repository's proof_verify
and review stage lost its forge-write path. These tests materialize the bundle
the way the sandbox setup step does, into a scratch root that holds ONLY the
bundled files, and run the real broker as its own process from an unrelated
empty git repository, with no `PYTHONPATH`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_helper_registry as registry

_BROKER = "bin/publication_broker.py"


def _materialize_bundle(*, root: Path) -> None:
    for helper in registry.helper_registry():
        if helper.root != registry.GH_REFRESH_ROOT:
            continue
        target = root / helper.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(helper.compose())
        target.chmod(helper.mode)


def test_the_registry_names_the_broker_in_the_gh_refresh_bundle() -> None:
    names = {h.path for h in registry.helper_registry() if h.root == registry.GH_REFRESH_ROOT}

    assert _BROKER in names
    assert "lib/livespec_orchestrator_beads_fabro/commands/publication_broker.py" in names


def test_the_bundled_broker_refuses_a_merge_from_an_unrelated_clone(tmp_path: Path) -> None:
    bundle = tmp_path / "livespec-gh-refresh"
    _materialize_bundle(root=bundle)
    clone = tmp_path / "target-clone"
    clone.mkdir()
    subprocess.run(["git", "init", "-q", str(clone)], check=True, timeout=60)
    state = tmp_path / "broker-state"
    state.mkdir(mode=0o700)
    launch = state / "launch.json"
    launch.write_text(
        json.dumps(
            {
                "stage": "proof_verify",
                "pull_request_number": 73,
                "proof_asset_store": "proof-assets",
                "request_directory": str(state),
            }
        ),
        encoding="utf-8",
    )
    launch.chmod(0o600)
    credential = state / "credential"
    credential.write_text("bundle-secret\n", encoding="utf-8")
    credential.chmod(0o600)

    completed = subprocess.run(
        [
            sys.executable,
            str(bundle / _BROKER),
            "--launch-file",
            str(launch),
            "--credential-file",
            str(credential),
        ],
        input=json.dumps(
            {"operation": "merge", "claimed_stage": "proof_verify", "pull_request_number": 73}
        )
        + "\n",
        capture_output=True,
        text=True,
        check=False,
        cwd=clone,
        env={"PATH": os.environ["PATH"]},
        timeout=60,
    )

    assert not (clone / ".claude-plugin").exists()
    assert completed.returncode == 0, completed.stderr
    reply = json.loads(completed.stdout.splitlines()[0])
    assert "only a new comment" in str(reply["refusal"])
    assert "bundle-secret" not in completed.stdout + completed.stderr
