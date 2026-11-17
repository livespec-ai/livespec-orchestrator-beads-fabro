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

_FLOOR_MINIMUM = 0
_FLOOR_MAXIMUM = 100
_HORIZON_MINIMUM_MINUTES = 0
_HORIZON_MAXIMUM_MINUTES = 1440


def resolve_session_headroom_floor_percent(*, cwd: Path) -> IOResult[int, PolicySettingUnreadable]:
    """Read the committed floor, bounded to the clause's inclusive 0..100 range.

    The generic integer resolver in `_dispatcher_policy_settings` carries a
    minimum and no maximum, and this dial needs both: a floor above 100 is not
    a strict dial, it is one no reading can ever satisfy, so it would refuse
    every covered candidate in the repository forever.
    """
    return read_dispatcher_config_value(
        cwd=cwd, key=SESSION_HEADROOM_FLOOR_PERCENT_KEY
    ).bind_result(
        lambda value: _bounded_dial(
            value=value,
            setting=SESSION_HEADROOM_FLOOR_PERCENT_KEY,
            default=DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT,
            minimum=_FLOOR_MINIMUM,
            maximum=_FLOOR_MAXIMUM,
        )
    )


def resolve_session_headroom_horizon_minutes(
    *, cwd: Path
) -> IOResult[int, PolicySettingUnreadable]:
    """Read the committed horizon, bounded to the clause's inclusive 0..1440 range.

    The SECOND dial that needs a maximum as well as a minimum, and it needs one
    for the mirror-image reason the floor does: an unbounded horizon is not a
    stricter dial, it is one no projected exhaustion can ever fall outside, so a
    committed 4000 would refuse every covered candidate whose drain is
    measurable at all -- while reading, in the record, exactly like a horizon
    somebody chose.

    COMMITTED-ONLY, as the clause ratifies it, so -- like the floor -- it is
    deliberately NOT a member of `_drive_config_schema.CONFIG_KEYS`. That
    manifest is what makes a setting reachable over the `drive --action
    set-config` write surface, so the absent declaration IS the mechanism
    rather than a documentation choice.
    """
    return read_dispatcher_config_value(
        cwd=cwd, key=SESSION_HEADROOM_HORIZON_MINUTES_KEY
    ).bind_result(
        lambda value: _bounded_dial(
            value=value,
            setting=SESSION_HEADROOM_HORIZON_MINUTES_KEY,
            default=DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES,
            minimum=_HORIZON_MINIMUM_MINUTES,
            maximum=_HORIZON_MAXIMUM_MINUTES,
        )
    )


def resolve_session_headroom_weekly_floor_percent(
    *, cwd: Path
) -> IOResult[int, PolicySettingUnreadable]:
    """Read the committed seven-day reserve, bounded to the clause's inclusive 0..100 range.

    Bounded for the reason the five-hour floor is: a reserve above 100 is not a
    stricter dial, it is one no reading can satisfy, so it would refuse every
    covered Claude slot. Committed-only like the floor, and absent from
    `_drive_config_schema.CONFIG_KEYS`.
    """
    return read_dispatcher_config_value(
        cwd=cwd, key=SESSION_HEADROOM_WEEKLY_FLOOR_PERCENT_KEY
    ).bind_result(
        lambda value: _bounded_dial(
            value=value,
            setting=SESSION_HEADROOM_WEEKLY_FLOOR_PERCENT_KEY,
            default=DEFAULT_SESSION_HEADROOM_WEEKLY_FLOOR_PERCENT,
            minimum=_FLOOR_MINIMUM,
            maximum=_FLOOR_MAXIMUM,
        )
    )


def _bounded_dial(
    *, value: object, setting: str, default: int, minimum: int, maximum: int
) -> Result[int, PolicySettingUnreadable]:
    """One declared dial, or the refusal naming the range it fell outside.

    ONE grader for both dials rather than one apiece. They differ only in their
    bounds, and a second hand-rolled copy is how two dials written from the same
    clause come to disagree about whether "inclusive" includes its endpoints --
    which is exactly the boundary the clause states twice and an almost-correct
    implementation moves.
    """
    if value is None:
        return Success(default)
    if isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum:
        return Success(value)
    return Failure(
        PolicySettingUnreadable(
            setting=setting,
            detail=(
                f"dispatcher.{setting} must be an integer from "
                f"{minimum} through {maximum} inclusive; got {value!r}"
            ),
        )
    )
