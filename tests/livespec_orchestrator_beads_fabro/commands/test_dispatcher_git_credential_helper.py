"""Credential withdrawal from Dispatcher-rendered agent environments."""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n\n[workflow]\ngraph = \"workflow.fabro\"\n"
    "\n[run.environment]\nid = \"livespec-ci\"\n"
)
_OAUTH_TOKEN = "oauth-token-value-that-must-not-leak"
_GITHUB_TOKEN = "github-token-value-that-must-not-leak"


def test_agent_overlay_has_no_forge_token_or_git_credential_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 202 leaves raw git and raw forge clients unauthenticated."""
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "stub-pem")

    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_OAUTH_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
    )

    assert rendered is not None
    for forbidden in (
        _GITHUB_TOKEN,
        "GITHUB_TOKEN =",
        "GH_TOKEN =",
        "GITHUB_APP_ID =",
        "GITHUB_PRIVATE_KEY =",
        "app-inputs.env",
        "gh auth git-credential",
        "credential.https://github.com.helper",
    ):
        assert forbidden not in rendered
