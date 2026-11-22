"""Integration journey for the plan-record artifact-paths contract.

The journey drives the public posting primitive through the hermetic ledger
client.  It reads the comment the primitive actually appended, rather than
testing the shared renderer in isolation, so both the optional and refusal
paths remain attached to the plan-record entry point.
"""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import VERDICT_CAPTURED
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import PlanDefinitionOfDone
from livespec_orchestrator_beads_fabro.commands._plan_record_post import (
    PlanRecordPost,
    run_post_plan_record_command,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_ASSERTION = "The released build runs in a real operator session."
_SESSION_ENV = "CLAUDE_CODE_SESSION_ID"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="artifact-paths-scenario",
        prefix="bd-ib",
        server_user="artifact-paths-scenario",
        database="artifact-paths-scenario",
        bd_path="bd",
        fake=True,
    )


def _client() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


class _NeverRuns:
    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        _ = timeout_seconds
        raise AssertionError(f"session identity should avoid the forge: {argv} in {cwd}")


def _payload(*, path: Path, artifact_paths: object | None = None) -> Path:
    build: dict[str, object] = {"release_tag": "v0.167.0", "installed_build": "0.167.0"}
    if artifact_paths is not None:
        build["artifact_paths"] = artifact_paths
    document = {
        "build": build,
        "assertions": [
            {
                "text": _ASSERTION,
                "steps": ["Install the released build."],
                "proof": "the build ran",
                "reproduced": None,
            }
        ],
    }
    _ = path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _post(*, repo: Path, epic_id: str, record_path: Path, emitted: list[str]) -> int:
    return run_post_plan_record_command(
        post=PlanRecordPost(
            repo=repo,
            epic_id=epic_id,
            verdict=VERDICT_CAPTURED,
            record_path=record_path,
        ),
        config=_config(),
        runner=_NeverRuns(),
        env={_SESSION_ENV: "artifact-path-capture"},
        emit=emitted.append,
    )


def _epic(*, repo: Path) -> str:
    created = plan.create_thread(
        project_root=repo,
        config=_config(),
        slug="artifact-path-record",
        title="Artifact paths record",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-11-22T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(statement="done", assertions=(_ASSERTION,)),
    )
    return str(created["epic_id"])


def test_plan_record_artifact_paths_render_omit_and_refuse_before_posting(tmp_path: Path) -> None:
    """Scenario: ordered paths render, omission stays absent, malformed input posts nothing."""
    reset_fake_singleton()
    rendered_repo = tmp_path / "rendered"
    rendered_repo.mkdir()
    rendered_epic = _epic(repo=rendered_repo)
    rendered_output: list[str] = []
    assert (
        _post(
            repo=rendered_repo,
            epic_id=rendered_epic,
            record_path=_payload(
                path=rendered_repo / "record.json",
                artifact_paths=[
                    "tools/shared_credentials_provisioning/",
                    "infra/shared-credentials/write-secret.sh",
                ],
            ),
            emitted=rendered_output,
        )
        == 0
    )
    rendered_body = str(_client().list_comments(issue_id=rendered_epic)[0]["text"])
    assert (
        "- artifact paths: tools/shared_credentials_provisioning/, "
        "infra/shared-credentials/write-secret.sh"
    ) in rendered_body

    reset_fake_singleton()
    omitted_repo = tmp_path / "omitted"
    omitted_repo.mkdir()
    omitted_epic = _epic(repo=omitted_repo)
    assert (
        _post(
            repo=omitted_repo,
            epic_id=omitted_epic,
            record_path=_payload(path=omitted_repo / "record.json"),
            emitted=[],
        )
        == 0
    )
    assert "artifact paths:" not in str(_client().list_comments(issue_id=omitted_epic)[0]["text"])

    reset_fake_singleton()
    malformed_repo = tmp_path / "malformed"
    malformed_repo.mkdir()
    malformed_epic = _epic(repo=malformed_repo)
    refused: list[str] = []
    assert (
        _post(
            repo=malformed_repo,
            epic_id=malformed_epic,
            record_path=_payload(path=malformed_repo / "record.json", artifact_paths=[""]),
            emitted=refused,
        )
        == 3
    )
    assert "artifact_paths" in "".join(refused)
    assert _client().list_comments(issue_id=malformed_epic) == []
