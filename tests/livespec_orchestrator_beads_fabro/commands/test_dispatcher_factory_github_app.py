"""Per-factory GitHub App declarations in Dispatcher run overlays."""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_factory
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import (
    DispatchPlan,
    build_plan,
)

_COMMITTED = (
    "[workflow]\n" 'graph = "workflow.fabro"\n' "\n" "[run.environment]\n" 'id = "livespec-ci"\n'
)
_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"


def _write_config(*, repo: Path, factory: dict[str, object]) -> None:
    payload = {
        "livespec-orchestrator-beads-fabro": {"dispatcher": {"factories": {"petri": factory}}}
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(payload), encoding="utf-8")


def _plan_for(*, repo: Path, github_app: object) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="bd-ib-iphzb7",
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.md",
        fabro_bin="/opt/fabro",
        fabro_factory_name="petri",
        fabro_factory_github_app=github_app,
        janitor=None,
        janitor_checkout=repo / "janitor",
    )


def _render(*, plan: DispatchPlan, repo: Path) -> str:
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED,
        workflow_dir=repo,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        github_app=plan.fabro_factory_github_app,
    )
    assert rendered is not None
    return rendered


def test_factory_github_app_is_never_projected_into_agent_run(tmp_path: Path) -> None:
    """A factory declaration never becomes an agent-readable App input."""
    _write_config(
        repo=tmp_path,
        factory={
            "github_app": {
                "app_id_secret": "PETRI_GITHUB_APP_ID",
                "private_key_secret": "PETRI_GITHUB_APP_PRIVATE_KEY",
            }
        },
    )
    target = resolve_fabro_factory(cwd=tmp_path, factory="petri")

    assert hasattr(target, "github_app")

    selected = _render(plan=_plan_for(repo=tmp_path, github_app=target.github_app), repo=tmp_path)
    assert "[run.integrations.github.app]" not in selected

    _write_config(repo=tmp_path, factory={})
    absent_target = resolve_fabro_factory(cwd=tmp_path, factory="petri")
    absent = _render(
        plan=_plan_for(repo=tmp_path, github_app=absent_target.github_app), repo=tmp_path
    )
    historical = render_run_config_overlay(
        committed_text=_COMMITTED,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )
    assert absent == historical
    assert "[run.integrations.github.app]" not in absent


def test_agent_stages_receive_no_github_app_input_or_minting_file(
    tmp_path: Path, monkeypatch
) -> None:
    """Scenario 202 keeps GitHub App inputs outside every agent-readable run surface."""
    _write_config(
        repo=tmp_path,
        factory={
            "github_app": {
                "app_id_secret": "PETRI_GITHUB_APP_ID",
                "private_key_secret": "PETRI_GITHUB_APP_PRIVATE_KEY",
            }
        },
    )
    for name, value in {
        "GITHUB_APP_ID": "42",
        "GITHUB_PRIVATE_KEY": "test-private-key",
        "GITHUB_APP_INSTALLATION_ID": "7",
        "GITHUB_API_URL": "https://api.github.com",
    }.items():
        monkeypatch.setenv(name, value)

    factory = resolve_fabro_factory(cwd=tmp_path, factory="petri")
    rendered = _render(plan=_plan_for(repo=tmp_path, github_app=factory.github_app), repo=tmp_path)

    assert "[run.integrations.github.app]" not in rendered
    assert "GITHUB_APP_ID = " not in rendered
    assert "GITHUB_PRIVATE_KEY = " not in rendered
    assert "GITHUB_APP_INSTALLATION_ID = " not in rendered
    assert "app-inputs.env" not in rendered
