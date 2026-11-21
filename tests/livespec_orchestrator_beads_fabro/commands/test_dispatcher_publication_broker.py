"""The trusted broker's workflow-derived stage boundary.

Scenario 202 permits an agent-stage broker request only when its authority comes
from the workflow node that launched it.  An agent-controlled request field must
not be able to turn a proof-stage comment into a `pr`-stage request.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import cast

import livespec_orchestrator_beads_fabro.commands._acp_candidate_secrets as _commands_anchor

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_publication_broker"
_MODULE_PATH = Path(cast("str", _commands_anchor.__file__)).parent / (
    "_dispatcher_publication_broker.py"
)


def _module() -> ModuleType:
    """Import the broker only after asserting its deliberate module boundary exists."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def test_a_request_claiming_pr_is_refused_when_the_workflow_launched_proof_verify() -> None:
    """The broker trusts the launch stage, never the stage supplied by an agent."""
    module = _module()

    refusal = module.refusal_for(
        request=module.BrokerRequest(
            operation="comment",
            claimed_stage="pr",
            pull_request_number=73,
        ),
        launch=module.WorkflowLaunch(stage="proof_verify", pull_request_number=73),
    )

    assert isinstance(refusal, str)
    assert "pr" in refusal
    assert "workflow" in refusal
