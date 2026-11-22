"""Operator-facing detail for Dispatcher terminal blocked outcomes."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._fabro_escalation import FabroEscalation

__all__: list[str] = ["blocked_terminal_detail"]


def blocked_terminal_detail(
    *,
    run_id: str,
    server_url: str | None,
    escalation: FabroEscalation | None,
) -> str:
    """Return a deliberately incomplete value during the Red phase."""
    del run_id, server_url, escalation
    return ""
