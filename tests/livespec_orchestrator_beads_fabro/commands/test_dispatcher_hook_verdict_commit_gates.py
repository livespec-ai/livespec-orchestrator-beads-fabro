"""Coverage for command-node commit-gate verdict records."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_verdict import (
    HookVerdict,
    _inspect_record,  # pyright: ignore[reportPrivateUsage]
    hook_verdict_for,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult


def _inspect(*, payload: object) -> FabroInspectResult:
    return FabroInspectResult(
        command=CommandResult(exit_code=0, stdout="", stderr=""),
        payload=payload,
        status_kind="failed",
        failure=None,
        events_payload=None,
    )


def test_a_commit_gate_command_record_keeps_its_explicit_nonzero_exit_code() -> None:
    payload = {
        "stages": {
            "commit_red@1": {
                "handler": "command",
                "state": "failed",
                "output": "Failed targets (1):\n  - check-types\n",
                "exit_code": 17,
            }
        }
    }

    assert hook_verdict_for(
        inspect=_inspect(payload=payload), stages=("commit_red@1",)
    ) == HookVerdict(node="commit_red", exit_code=17, failed_targets=("check-types",))


@pytest.mark.parametrize(
    ("record_key", "stage"),
    [
        ("044-commit_green@1", "commit_green@1"),
        ("commit_green@1", "044-commit_green@1"),
        ("044-commit_green@1", "045-commit_green@1"),
    ],
)
def test_a_commit_gate_record_is_found_across_the_engines_stage_key_spellings(
    *, record_key: str, stage: str
) -> None:
    payload = {
        "stages": {
            "043-commit_green@0": {
                "handler": "command",
                "state": "failed",
                "output": "Failed targets (1):\n  - check-stale\n",
            },
            record_key: {
                "handler": "command",
                "state": "failed",
                "output": "Failed targets (1):\n  - check-types\n",
                "exit_code": 3,
            },
        }
    }

    assert hook_verdict_for(inspect=_inspect(payload=payload), stages=(stage,)) == HookVerdict(
        node="commit_green", exit_code=3, failed_targets=("check-types",)
    )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        ["not an inspect record", {"stages": {}}],
        {"stages": {"commit_green@1": {"handler": "agent", "state": "failed"}}},
        {"stages": {"commit_green@1": {"handler": "command", "state": "succeeded"}}},
        {
            "stages": {
                "commit_green@1": {
                    "handler": "command",
                    "state": "failed",
                    "output": None,
                }
            }
        },
    ],
)
def test_a_commit_gate_requires_a_failed_command_record_with_text_output(
    *, payload: object
) -> None:
    assert hook_verdict_for(inspect=_inspect(payload=payload), stages=("commit_green@1",)) is None


def test_an_inspect_payload_list_without_a_record_is_empty() -> None:
    assert _inspect_record(payload=["not an inspect record"]) == {}
    assert _inspect_record(payload=None) == {}
