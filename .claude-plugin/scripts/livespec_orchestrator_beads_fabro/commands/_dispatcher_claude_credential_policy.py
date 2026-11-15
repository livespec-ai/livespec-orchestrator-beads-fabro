"""The dispatcher's declared Claude credential policy: which slots the factory may draw.

Orchestrator PR #5346 (R02/R10, plan epic overseer-iyfjbo) proposes
`dispatcher.claude_credential_policy`, a committed-only, non-secret object.
Its `mode` is exactly `numbered-slots` or `legacy-independent`. Under
`numbered-slots` its `slots` is a non-empty array of distinct
`CLAUDE_CODE_OAUTH_TOKEN__<SLOT>` variable names, and the factory pool is only
those declared slots the credential wrapper injects non-empty: an undeclared
numbered variable is never a pool slot, and the unnumbered
`CLAUDE_CODE_OAUTH_TOKEN` never is either. Under `legacy-independent`, `slots`
is absent and today's pool rule holds.

THE POLICY CARRIES VARIABLE NAMES ONLY, never a credential value or anything
derived from one, so it is safe to commit and to echo in a refusal.

COMMITTED-ONLY, like the session-headroom dials: it is deliberately NOT a
member of `_drive_config_schema.CONFIG_KEYS`, so no `drive --action set-config`
write can widen a dispatcher's allow-list.

AN ABSENT POLICY READS AS `None`, which today keeps the legacy pool rule. The
proposal's missing-policy refusal is deliberately left to the follow-up that
lands with the per-dispatcher slot census release gate, so this module can ship
before every dispatcher commits a policy. A policy that IS written but does not
parse is a different claim, and the caller fails closed on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from returns.io import IOResult
from returns.result import Failure, Result, Success

from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    PolicySettingUnreadable,
    read_dispatcher_config_value,
)

__all__: list[str] = [
    "CLAUDE_CREDENTIAL_POLICY_KEY",
    "LEGACY_INDEPENDENT",
    "NUMBERED_SLOTS",
    "ClaudeCredentialPolicy",
    "parse_claude_credential_policy",
    "resolve_claude_credential_policy",
]

CLAUDE_CREDENTIAL_POLICY_KEY: Final = "claude_credential_policy"
NUMBERED_SLOTS: Final = "numbered-slots"
LEGACY_INDEPENDENT: Final = "legacy-independent"
_SLOT_NAME: Final = re.compile(r"^CLAUDE_CODE_OAUTH_TOKEN__[A-Z0-9_]+$")


@dataclass(frozen=True, kw_only=True)
class ClaudeCredentialPolicy:
    """The declared mode and, under `numbered-slots`, the declared slot names."""

    mode: str
    slots: tuple[str, ...]


def parse_claude_credential_policy(
    *, value: object
) -> Result[ClaudeCredentialPolicy | None, PolicySettingUnreadable]:
    """The policy, `None` when unset, or the refusal naming what is malformed."""
    if value is None:
        return Success(None)
    if not isinstance(value, dict):
        return Failure(_unreadable(detail="must be an object"))
    policy = cast("dict[str, object]", value)
    mode = policy.get("mode")
    if mode == LEGACY_INDEPENDENT:
        if "slots" in policy:
            return Failure(_unreadable(detail="slots must be absent under legacy-independent"))
        return Success(ClaudeCredentialPolicy(mode=LEGACY_INDEPENDENT, slots=()))
    if mode != NUMBERED_SLOTS:
        return Failure(_unreadable(detail=f"mode must be {NUMBERED_SLOTS} or {LEGACY_INDEPENDENT}"))
    return _numbered_slots(value=policy.get("slots"))


def _numbered_slots(
    *, value: object
) -> Result[ClaudeCredentialPolicy | None, PolicySettingUnreadable]:
    if not isinstance(value, list) or not value:
        return Failure(_unreadable(detail="slots must be a non-empty array under numbered-slots"))
    names = cast("list[object]", value)
    if not all(isinstance(name, str) and _SLOT_NAME.match(name) for name in names):
        return Failure(
            _unreadable(detail="every slot must match ^CLAUDE_CODE_OAUTH_TOKEN__[A-Z0-9_]+$")
        )
    slots = tuple(cast("list[str]", names))
    if len(set(slots)) != len(slots):
        return Failure(_unreadable(detail="slots must be distinct"))
    return Success(ClaudeCredentialPolicy(mode=NUMBERED_SLOTS, slots=slots))


def resolve_claude_credential_policy(
    *, cwd: Path
) -> IOResult[ClaudeCredentialPolicy | None, PolicySettingUnreadable]:
    """Read the committed policy from this repository's `.livespec.jsonc`."""
    return read_dispatcher_config_value(cwd=cwd, key=CLAUDE_CREDENTIAL_POLICY_KEY).bind_result(
        lambda value: parse_claude_credential_policy(value=value)
    )


def _unreadable(*, detail: str) -> PolicySettingUnreadable:
    return PolicySettingUnreadable(
        setting=CLAUDE_CREDENTIAL_POLICY_KEY,
        detail=f"dispatcher.{CLAUDE_CREDENTIAL_POLICY_KEY} {detail}",
    )
