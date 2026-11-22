"""Operator-facing rendering for Dispatcher terminal blocked outcomes."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_blocked_terminal_detail import (
    blocked_terminal_detail,
)
from livespec_orchestrator_beads_fabro.commands._fabro_escalation import FabroEscalation


def test_engine_escalation_names_the_failure_instead_of_a_human_gate() -> None:
    detail = blocked_terminal_detail(
        run_id="01M10CYZ8S9TNPZ2MW096NJW7V",
        server_url="https://fabro.example.test",
        escalation=FabroEscalation(
            next_node_id="needs_human",
            loop_failure_signatures=("review|deterministic|acp turn failed",),
        ),
    )

    assert "ESCALATED by the engine" in detail
    assert "recorded loop failure signature: review|deterministic|acp turn failed" in detail
    assert "parked at the in-loop human gate" not in detail


def test_engine_escalation_without_a_signature_says_so() -> None:
    detail = blocked_terminal_detail(
        run_id="01M10CYZ8S9TNPZ2MW096NJW7V",
        server_url=None,
        escalation=FabroEscalation(
            next_node_id="needs_human",
            loop_failure_signatures=(),
        ),
    )

    assert "recorded loop failure signature: none supplied" in detail
