"""Contract coverage for completed-cycle timestamp derivations."""

from __future__ import annotations

from importlib.util import find_spec


def test_completed_cycle_timestamp_derivations_have_a_dedicated_module() -> None:
    """Keep timestamp parsing independent from the forge and Git probe."""
    assert (
        find_spec("livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_timestamps")
        is not None
    )
