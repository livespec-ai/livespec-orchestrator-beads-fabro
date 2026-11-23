"""Contract coverage for completed-cycle timestamp derivations."""

from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec


def test_completed_cycle_timestamp_derivations_have_a_dedicated_module() -> None:
    """Keep timestamp parsing independent from the forge and Git probe."""
    assert (
        find_spec("livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_timestamps")
        is not None
    )
    timestamps = import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_timestamps"
    )
    elapsed_seconds = timestamps.elapsed_seconds
    assert elapsed_seconds(red_at="2026-11-23T10:00:00Z", green_at="2026-11-23T10:01:00Z") == (
        60,
        None,
    )


def test_completed_cycle_timestamp_derivations_reject_invalid_and_reversed_values() -> None:
    """Preserved provenance is the sole source of elapsed-cycle duration."""
    timestamps = import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_timestamps"
    )
    elapsed_seconds = timestamps.elapsed_seconds
    assert elapsed_seconds(red_at="not-a-time", green_at="2026-11-23T10:01:00Z") == (None, True)
    assert elapsed_seconds(red_at="2026-11-23T10:01:00Z", green_at="2026-11-23T10:00:00Z") == (
        None,
        True,
    )


def test_completed_cycle_timestamp_module_declares_its_public_surface() -> None:
    """Keep the module's intended imports explicit for mechanical checks."""
    timestamps = import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_timestamps"
    )
    assert timestamps.__all__ == ["elapsed_seconds", "red_order"]
