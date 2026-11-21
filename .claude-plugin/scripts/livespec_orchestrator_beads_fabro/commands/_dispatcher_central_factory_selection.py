"""The central factory selection record: which one slot a factory dispatch may draw.

`SPECIFICATION/contracts.md`, "Under `central-factory-selection`, the central
factory selection names the slot" (Scenario 378). Under `selection:
central-factory-selection` the Dispatcher reads ONE identity-only file,
`factory-selected-account.json`, that livespec-overseer's account rotation
publishes and its enrolled-host delivery writes onto every listed host
(`overseer/caam_factory_selection.py`, `caam_delivery_factory_record.py`). It
carries `profile`, `account_uuid`, `written_at` and `reason`, and never any
credential value.

The named slot is `CLAUDE_CODE_OAUTH_TOKEN__<PROFILE>`, the profile upper-cased
with each hyphen replaced by an underscore. It is the ONLY pool slot for the
evaluation. When no usable slot can be named, covered candidates are skipped
with `no-central-factory-selection`, which carries the record's own `reason` or
which condition held.

THIS IS NOT THE INTERACTIVE SELECTION. The interactive record
(`selected-account.json`) stays unread in every mode under `numbered-slots`; the
two files differ in name and this module reads only the factory one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential_policy import (
    CENTRAL_FACTORY_SELECTION,
    ClaudeCredentialPolicy,
    ClaudeCredentialRefusal,
)
from livespec_orchestrator_beads_fabro.effects import IsoDatetimeParseFailure, parse_iso_datetime

__all__: list[str] = [
    "FACTORY_SELECTION_RECORD_REL",
    "NO_CENTRAL_FACTORY_SELECTION",
    "CentralFactorySelection",
    "central_selection_for",
    "derived_slot_name",
    "read_central_factory_selection",
]

# Byte-identical to the writer's relative path (overseer/caam_factory_selection.py
# FACTORY_SELECTION_RECORD_REL): a FIXED `~/.local/state` location.
FACTORY_SELECTION_RECORD_REL: Final = Path(
    ".local/state/caam-usage-rotate/factory-selected-account.json"
)
NO_CENTRAL_FACTORY_SELECTION: Final = "no-central-factory-selection"
_SLOT_PREFIX: Final = "CLAUDE_CODE_OAUTH_TOKEN__"


@dataclass(frozen=True, kw_only=True)
class CentralFactorySelection:
    """What the record said and what it resolved to; carries no credential value.

    `slot` is the env-var NAME to assess and project, or `None` when `refusal`
    says why none is usable. `profile` and `written_at` are echoed for the
    journal whenever the record parsed far enough to carry them.
    """

    profile: str | None
    written_at: str | None
    slot: str | None
    refusal: ClaudeCredentialRefusal | None
    reason: str | None


def derived_slot_name(*, profile: str) -> str:
    """`anthropic-5` -> `CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_5`."""
    return f"{_SLOT_PREFIX}{profile.upper().replace('-', '_')}"


def read_central_factory_selection(
    *,
    home: Path,
    policy: ClaudeCredentialPolicy,
    environ: Mapping[str, str],
    now: datetime,
) -> CentralFactorySelection:
    """Read the record under `home` and derive the one slot, or the named skip."""
    loaded = _load(home=home)
    if isinstance(loaded, CentralFactorySelection):
        return loaded
    profile, stamp, written, reason = loaded
    if profile is None:
        return _skipped(
            condition="record names no account" + ("" if reason is None else f": {reason}"),
            written_at=stamp,
            reason=reason,
        )
    slot = derived_slot_name(profile=profile)
    minutes = policy.central_selection_max_age_minutes
    condition = (
        f"stale record: written_at {stamp} is more than {minutes} minutes old"
        if now - written > timedelta(minutes=minutes)
        else f"named slot {slot} is not declared by the policy"
        if slot not in policy.slots
        else f"named slot {slot} is not injected non-empty"
        if not environ.get(slot)
        else None
    )
    if condition is not None:
        return _skipped(condition=condition, profile=profile, written_at=stamp, reason=reason)
    return CentralFactorySelection(
        profile=profile, written_at=stamp, slot=slot, refusal=None, reason=reason
    )


def central_selection_for(
    *,
    policy: ClaudeCredentialPolicy | ClaudeCredentialRefusal,
    environ: Mapping[str, str],
    home: Path,
    now: datetime,
) -> CentralFactorySelection | None:
    """The central factory selection under `central-factory-selection`, else `None`."""
    if isinstance(policy, ClaudeCredentialRefusal) or policy.selection != CENTRAL_FACTORY_SELECTION:
        return None
    return read_central_factory_selection(home=home, policy=policy, environ=environ, now=now)


def _load(*, home: Path) -> CentralFactorySelection | tuple[str | None, str, datetime, str | None]:
    """The record's `(profile, written_at, instant, reason)`, or the skip it earned."""
    try:
        parsed: object = json.loads(
            (home / FACTORY_SELECTION_RECORD_REL).read_text(encoding="utf-8")
        )
    except FileNotFoundError:
        return _skipped(condition="record absent")
    except (OSError, ValueError):
        return _skipped(condition="record unreadable or does not parse")
    if not isinstance(parsed, dict):
        return _skipped(condition="record does not parse: not an object")
    record = cast("dict[str, object]", parsed)
    profile = record.get("profile")
    stamp = record.get("written_at")
    reason = record.get("reason")
    written = _instant(text=stamp) if isinstance(stamp, str) else None
    if written is None or not (profile is None or (isinstance(profile, str) and profile)):
        return _skipped(condition="record does not parse: unusable profile or written_at")
    return (
        profile,
        cast("str", stamp),
        written,
        reason if isinstance(reason, str) else None,
    )


def _instant(*, text: str) -> datetime | None:
    """The record's `%Y-%m-%dT%H:%M:%SZ` instant as an aware datetime, or `None`."""
    parsed = parse_iso_datetime(text=text.removesuffix("Z") + "+00:00")
    return None if isinstance(parsed, IsoDatetimeParseFailure) else parsed


def _skipped(
    *,
    condition: str,
    profile: str | None = None,
    written_at: str | None = None,
    reason: str | None = None,
) -> CentralFactorySelection:
    return CentralFactorySelection(
        profile=profile,
        written_at=written_at,
        slot=None,
        refusal=ClaudeCredentialRefusal(
            cause=NO_CENTRAL_FACTORY_SELECTION,
            detail=f"{NO_CENTRAL_FACTORY_SELECTION}: {condition}",
            condition=f"{NO_CENTRAL_FACTORY_SELECTION}: {condition}",
        ),
        reason=reason,
    )
