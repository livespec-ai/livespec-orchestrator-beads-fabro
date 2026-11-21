"""The dispatcher's declared Claude credential policy: which slots the factory may draw.

`SPECIFICATION/contracts.md` (v382, plan epic overseer-iyfjbo) defines
`dispatcher.claude_credential_policy`, a committed-only, non-secret object.
Its `mode` is exactly `numbered-slots` or `legacy-independent`. Under
`numbered-slots` its `slots` is a non-empty array of distinct
`CLAUDE_CODE_OAUTH_TOKEN__<SLOT>` variable names, and the factory pool is only
those declared slots the credential wrapper injects non-empty: an undeclared
numbered variable is never a pool slot, and the unnumbered
`CLAUDE_CODE_OAUTH_TOKEN` never is either. Under `legacy-independent`, `slots`
is absent and every non-empty numbered slot is a pool slot, the unnumbered
token being the sole slot only when no numbered slot is injected.

THE POLICY CARRIES VARIABLE NAMES ONLY, never a credential value or anything
derived from one, so it is safe to commit and to echo in a refusal.

COMMITTED-ONLY, like the session-headroom dials: it is deliberately NOT a
member of `_drive_config_schema.CONFIG_KEYS`, so no `drive --action set-config`
write can widen a dispatcher's allow-list.

AN ABSENT POLICY IS A CONFIGURATION REFUSAL, exactly as an invalid one is
(`SPECIFICATION/contracts.md`, "The dispatcher declares its Claude credential
policy", v382, and Scenario 376): an operation needing a Claude Code OAuth
credential MUST NOT infer `legacy-independent` from a missing declaration. So
the parser answers `Failure` for an absent value too, naming the key, and the
caller refuses on it before any claim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, cast

from returns.io import IOResult
from returns.result import Failure, Result, Success

from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    PolicySettingUnreadable,
    read_dispatcher_config_value,
)

__all__: list[str] = [
    "ADMITTED_SLOT_ABSENT",
    "CENTRAL_FACTORY_SELECTION",
    "CLAUDE_CREDENTIAL_POLICY_ABSENT",
    "CLAUDE_CREDENTIAL_POLICY_INVALID",
    "CLAUDE_CREDENTIAL_POLICY_KEY",
    "DEFAULT_CENTRAL_SELECTION_MAX_AGE_MINUTES",
    "LEGACY_INDEPENDENT",
    "LOCAL_RANKING",
    "NO_DECLARED_SLOT_INJECTED",
    "NUMBERED_SLOTS",
    "ClaudeCredentialPolicy",
    "ClaudeCredentialRefusal",
    "parse_claude_credential_policy",
    "policy_refusal",
    "resolve_claude_credential_policy",
]

CLAUDE_CREDENTIAL_POLICY_KEY: Final = "claude_credential_policy"
NUMBERED_SLOTS: Final = "numbered-slots"
LEGACY_INDEPENDENT: Final = "legacy-independent"
# `selection` values (`SPECIFICATION/contracts.md` "The dispatcher declares its Claude
# credential policy"): an absent `selection` is `local-ranking`.
LOCAL_RANKING: Final = "local-ranking"
CENTRAL_FACTORY_SELECTION: Final = "central-factory-selection"
DEFAULT_CENTRAL_SELECTION_MAX_AGE_MINUTES: Final = 60
_MAX_AGE_MINUTES_BOUNDS: Final = (1, 1440)
_SLOT_NAME: Final = re.compile(r"^CLAUDE_CODE_OAUTH_TOKEN__[A-Z0-9_]+$")
# The stable refusal causes. Stable because a did-not-run judgement record is
# capped per distinct cause, and each names what an operator must fix.
CLAUDE_CREDENTIAL_POLICY_ABSENT: Final = "dispatcher.claude_credential_policy-absent"
CLAUDE_CREDENTIAL_POLICY_INVALID: Final = "dispatcher.claude_credential_policy-invalid"
NO_DECLARED_SLOT_INJECTED: Final = "no-declared-slot-injected"
ADMITTED_SLOT_ABSENT: Final = "admitted-slot-absent"
_ABSENT_DETAIL: Final = (
    "is absent; declare mode numbered-slots or legacy-independent "
    "(an absent policy is never read as legacy-independent)"
)


@dataclass(frozen=True, kw_only=True)
class ClaudeCredentialPolicy:
    """The declared mode and, under `numbered-slots`, the declared slot names."""

    mode: str
    slots: tuple[str, ...]
    selection: str = LOCAL_RANKING
    central_selection_max_age_minutes: int = DEFAULT_CENTRAL_SELECTION_MAX_AGE_MINUTES


@dataclass(frozen=True, kw_only=True)
class ClaudeCredentialRefusal:
    """Why an operation needing a Claude Code OAuth credential may not run.

    `cause` is one stable token; `detail` is the operator-facing sentence naming
    the key or the declared slots. Neither ever carries a credential value.
    """

    cause: str
    detail: str
    # What a covered candidate's skip names when the bare `cause` would hide the
    # operative fact (the central factory selection record's own reason).
    condition: str | None = None

    @property
    def skip_condition(self) -> str:
        """The condition a skipped covered candidate carries."""
        return self.cause if self.condition is None else self.condition

    @property
    def configuration(self) -> bool:
        """Whether committing (or fixing) the policy is the remedy."""
        return self.cause in {CLAUDE_CREDENTIAL_POLICY_ABSENT, CLAUDE_CREDENTIAL_POLICY_INVALID}


def policy_refusal(*, unreadable: PolicySettingUnreadable) -> ClaudeCredentialRefusal:
    """The configuration refusal an absent or invalid policy produces."""
    absent = unreadable.detail.endswith(_ABSENT_DETAIL)
    return ClaudeCredentialRefusal(
        cause=CLAUDE_CREDENTIAL_POLICY_ABSENT if absent else CLAUDE_CREDENTIAL_POLICY_INVALID,
        detail=f"configuration refusal: {unreadable.detail}",
    )


def parse_claude_credential_policy(
    *, value: object
) -> Result[ClaudeCredentialPolicy, PolicySettingUnreadable]:
    """The policy, or the refusal naming what is absent or malformed."""
    if value is None:
        return Failure(_unreadable(detail=_ABSENT_DETAIL))
    if not isinstance(value, dict):
        return Failure(_unreadable(detail="must be an object"))
    policy = cast("dict[str, object]", value)
    mode = policy.get("mode")
    if mode == LEGACY_INDEPENDENT:
        if "slots" in policy:
            return Failure(_unreadable(detail="slots must be absent under legacy-independent"))
    elif mode != NUMBERED_SLOTS:
        return Failure(_unreadable(detail=f"mode must be {NUMBERED_SLOTS} or {LEGACY_INDEPENDENT}"))
    base = _with_selection(mode=cast("str", mode), policy=policy)
    if isinstance(base, Failure):
        return base
    return _with_slots(base=base.unwrap(), value=policy.get("slots"))


def _with_selection(
    *, mode: str, policy: dict[str, object]
) -> Result[ClaudeCredentialPolicy, PolicySettingUnreadable]:
    """The `selection` and `central_selection_max_age_minutes` half of the policy."""
    selection = policy.get("selection", LOCAL_RANKING)
    if selection not in {LOCAL_RANKING, CENTRAL_FACTORY_SELECTION}:
        return Failure(
            _unreadable(detail=f"selection must be {LOCAL_RANKING} or {CENTRAL_FACTORY_SELECTION}")
        )
    if selection == CENTRAL_FACTORY_SELECTION and mode != NUMBERED_SLOTS:
        return Failure(
            _unreadable(
                detail=f"selection {CENTRAL_FACTORY_SELECTION} requires mode {NUMBERED_SLOTS}"
            )
        )
    age = policy.get("central_selection_max_age_minutes", DEFAULT_CENTRAL_SELECTION_MAX_AGE_MINUTES)
    low, high = _MAX_AGE_MINUTES_BOUNDS
    if isinstance(age, bool) or not isinstance(age, int) or not low <= age <= high:
        return Failure(
            _unreadable(
                detail=(
                    f"central_selection_max_age_minutes must be an integer from {low} "
                    f"through {high}"
                )
            )
        )
    return Success(
        ClaudeCredentialPolicy(
            mode=mode,
            slots=(),
            selection=selection,
            central_selection_max_age_minutes=age,
        )
    )


def _with_slots(
    *, base: ClaudeCredentialPolicy, value: object
) -> Result[ClaudeCredentialPolicy, PolicySettingUnreadable]:
    """`base` once its `slots` are read: none under legacy, a validated list under numbered."""
    if base.mode == LEGACY_INDEPENDENT:
        return Success(base)
    return _numbered_slots(base=base, value=value)


def _numbered_slots(
    *, base: ClaudeCredentialPolicy, value: object
) -> Result[ClaudeCredentialPolicy, PolicySettingUnreadable]:
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
    return Success(replace(base, slots=slots))


def resolve_claude_credential_policy(
    *, cwd: Path
) -> IOResult[ClaudeCredentialPolicy, PolicySettingUnreadable]:
    """Read the committed policy from this repository's `.livespec.jsonc`."""
    return read_dispatcher_config_value(cwd=cwd, key=CLAUDE_CREDENTIAL_POLICY_KEY).bind_result(
        lambda value: parse_claude_credential_policy(value=value)
    )


def _unreadable(*, detail: str) -> PolicySettingUnreadable:
    return PolicySettingUnreadable(
        setting=CLAUDE_CREDENTIAL_POLICY_KEY,
        detail=f"dispatcher.{CLAUDE_CREDENTIAL_POLICY_KEY} {detail}",
    )
