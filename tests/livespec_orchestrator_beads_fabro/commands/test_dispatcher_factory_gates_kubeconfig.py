"""The factory-declared gate kubeconfig reaches its sandbox as a read-only mount."""

from __future__ import annotations

from inspect import signature
from pathlib import Path

import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)

_COMMITTED = (
    "[workflow]\n" 'graph = "workflow.fabro"\n' "\n" "[run.environment]\n" 'id = "livespec-ci"\n'
)
_GATE_CLIENT_PATH = "/etc/ci-runner/gates.kubeconfig"
_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"


def test_existing_factory_gate_kubeconfig_is_a_read_only_sandbox_mount(tmp_path: Path) -> None:
    """Scenario 381: the credential is mounted at the gate client's path, never copied."""
    credential = tmp_path / "factory-gates.kubeconfig"
    _ = credential.write_text("sentinel-kubeconfig-contents\n", encoding="utf-8")

    # The Red assertion deliberately reads the public builder signature first:
    # without this projection the call below would raise TypeError, which proves
    # only that the keyword is unknown rather than that the mount is absent.
    assert "gates_kubeconfig" in signature(render_run_config_overlay).parameters

    rendered = render_run_config_overlay(
        committed_text=_COMMITTED,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        gates_kubeconfig=credential,
    )

    assert rendered is not None
    mount = tomli.loads(rendered)["run"]["sandbox"]["mounts"]
    assert mount == [
        {
            "source": str(credential),
            "target": _GATE_CLIENT_PATH,
            "read_only": True,
        }
    ]
    assert "sentinel-kubeconfig-contents" not in rendered
