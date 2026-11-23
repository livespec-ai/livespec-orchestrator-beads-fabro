"""Preserved timestamp derivations for completed-cycle measurement."""

from __future__ import annotations

from datetime import datetime

from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt


def elapsed_seconds(*, red_at: str, green_at: str) -> tuple[int | None, bool | None]:
    """Use Red-to-Green provenance, never a merge timestamp."""
    red = _instant(value=red_at)
    green = _instant(value=green_at)
    if red is None or green is None or green < red:
        return (None, True)
    return (round((green - red).total_seconds()), None)


def red_order(*, red_at: str) -> tuple[int, float]:
    """Sort readable Red timestamps first without dropping unreadable pairs."""
    instant = _instant(value=red_at)
    return (1, 0.0) if instant is None else (0, instant.timestamp())


def _instant(*, value: str) -> datetime | None:
    """Parse this trailer's UTC spelling, returning None for invalid provenance."""
    normalized = value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value
    parsed = attempt(action=lambda: datetime.fromisoformat(normalized), exceptions=(ValueError,))
    return None if isinstance(parsed, AttemptFailure) else parsed
