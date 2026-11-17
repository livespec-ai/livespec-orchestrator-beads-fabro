"""Committed-only dispatcher settings for Claude session-headroom admission."""

from __future__ import annotations

from pathlib import Path

from returns.io import IOResult
from returns.result import Failure, Result, Success

from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT,
    DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES,
    DEFAULT_SESSION_HEADROOM_WEEKLY_FLOOR_PERCENT,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    PolicySettingUnreadable,
    read_dispatcher_config_value,
)

__all__: list[str] = [
    "SESSION_HEADROOM_FLOOR_PERCENT_KEY",
    "SESSION_HEADROOM_HORIZON_MINUTES_KEY",
    "SESSION_HEADROOM_WEEKLY_FLOOR_PERCENT_KEY",
    "resolve_session_headroom_floor_percent",
    "resolve_session_headroom_horizon_minutes",
    "resolve_session_headroom_weekly_floor_percent",
]

SESSION_HEADROOM_FLOOR_PERCENT_KEY = "session_headroom_floor_percent"
SESSION_HEADROOM_HORIZON_MINUTES_KEY = "session_headroom_horizon_minutes"
SESSION_HEADROOM_WEEKLY_FLOOR_PERCENT_KEY = "session_headroom_weekly_floor_percent"


def resolve_session_headroom_floor_percent(*, cwd: Path) -> IOResult[int, PolicySettingUnreadable]:
    """Read the five-hour floor, bounded to the ratified inclusive 0..100 range."""
    return _resolve_bounded(
        cwd=cwd,
        key=SESSION_HEADROOM_FLOOR_PERCENT_KEY,
        default=DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT,
        maximum=100,
    )


def resolve_session_headroom_horizon_minutes(
    *, cwd: Path
) -> IOResult[int, PolicySettingUnreadable]:
    """Read the projection horizon, bounded to the ratified inclusive 0..1440 range."""
    return _resolve_bounded(
        cwd=cwd,
        key=SESSION_HEADROOM_HORIZON_MINUTES_KEY,
        default=DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES,
        maximum=1440,
    )


def resolve_session_headroom_weekly_floor_percent(
    *, cwd: Path
) -> IOResult[int, PolicySettingUnreadable]:
    """Read the seven-day reserve, bounded to the ratified inclusive 0..100 range."""
    return _resolve_bounded(
        cwd=cwd,
        key=SESSION_HEADROOM_WEEKLY_FLOOR_PERCENT_KEY,
        default=DEFAULT_SESSION_HEADROOM_WEEKLY_FLOOR_PERCENT,
        maximum=100,
    )


def _resolve_bounded(
    *, cwd: Path, key: str, default: int, maximum: int
) -> IOResult[int, PolicySettingUnreadable]:
    return read_dispatcher_config_value(cwd=cwd, key=key).bind_result(
        lambda value: _bounded_dial(value=value, setting=key, default=default, maximum=maximum)
    )


def _bounded_dial(
    *, value: object, setting: str, default: int, maximum: int
) -> Result[int, PolicySettingUnreadable]:
    if value is None:
        return Success(default)
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= maximum:
        return Success(value)
    return Failure(
        PolicySettingUnreadable(
            setting=setting,
            detail=(
                f"dispatcher.{setting} must be an integer from 0 through {maximum} inclusive; "
                f"got {value!r}"
            ),
        )
    )
