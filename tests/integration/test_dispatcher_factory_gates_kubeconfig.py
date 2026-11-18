"""Integration-tier coverage of Scenario 381's rendered sandbox mount."""

from __future__ import annotations

from pathlib import Path

import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)

_COMMITTED = (
    "[workflow]\n" 'graph = "workflow.fabro"\n' "\n" "[run.environment]\n" 'id = "livespec-ci"\n'
)
_TOKEN = "test-oauth-token"
_GITHUB_TOKEN = "test-github-token"


def test_scenario_381_mount_is_read_only(tmp_path: Path) -> None:
    """A declared credential mounts at the gate client's path without being copied."""
    credential = tmp_path / "factory-gates.kubeconfig"
    _ = credential.write_text("sentinel-kubeconfig-contents\n", encoding="utf-8")

    rendered = render_run_config_overlay(
        committed_text=_COMMITTED,
        workflow_dir=tmp_path,
        token=_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
        gates_kubeconfig=credential,
    )

    assert rendered is not None
    assert tomli.loads(rendered)["run"]["sandbox"]["mounts"] == [
        {
            "source": str(credential),
            "target": "/etc/ci-runner/gates.kubeconfig",
            "read_only": True,
        }
    ]
    assert "sentinel-kubeconfig-contents" not in rendered
