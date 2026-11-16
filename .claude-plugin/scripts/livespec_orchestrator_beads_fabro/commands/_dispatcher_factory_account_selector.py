"""Select the factory Claude credential env var: a slot the declared policy allows.

THE DECLARED POLICY DECIDES THE POOL, READ ON EVERY CALL. `select_factory_credential`
resolves `dispatcher.claude_credential_policy` from the repository it is handed
each time it runs (`SPECIFICATION/contracts.md` v382, "The dispatcher declares
its Claude credential policy"), so the credential-status probe, the re-probe
wait, the availability probe, the projection and the judgement all apply it
whether or not an admission pass ran first. An absent or invalid policy is a
configuration refusal (`ClaudeCredentialRefusal`), never an inferred
`legacy-independent`.

Under `numbered-slots` the pool is the declared slots injected non-empty, in
declaration order. The slot admission chose wins while it is still injected;
when it is gone the consumer REFUSES rather than choosing another credential;
with no admission choice the first declared injected slot is named; and with
no declared slot injected the call refuses `no-declared-slot-injected`, naming
each declared slot as absent or empty. The unnumbered token and undeclared
numbered variables are never named.

Under `legacy-independent` the pool is every non-empty numbered slot (the
unnumbered token only when none is), and without an admission choice the
caam-published interactive profile still steers the pick as it always did.

The caam-anthropic-loop publishes, on the host it runs on, the account it
selected for interactive spend to a fixed record (livespec-overseer
SPECIFICATION v049; `overseer/caam_selection_record.py` is the writer). The
record is READ, never written, here, and only the PROFILE NAME (never any
credential material).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_claude_credential_policy as credential_policy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential_policy import (
    ADMITTED_SLOT_ABSENT,
    NO_DECLARED_SLOT_INJECTED,
    NUMBERED_SLOTS,
    ClaudeCredentialPolicy,
    ClaudeCredentialRefusal,
    policy_refusal,
)

__all__: list[str] = [
    "SELECTED_ACCOUNT_RECORD_REL",
    "FactoryCredentialChoice",
    "admission_credential_refusal",
    "claude_credential_policy_for",
    "factory_credential_env_name",
    "injected_credential_slots",
    "parse_selected_profile",
    "policy_pool_slots",
    "read_selected_profile",
    "register_admission_slot_chooser",
    "resolve_factory_credential_env_name",
    "select_factory_credential",
    "selected_account_record_path",
]

# Byte-identical to the writer's relative path (overseer/caam_selection_record.py
# SELECTION_RECORD_REL): a FIXED `~/.local/state` location, deliberately NOT
# XDG-configurable, so writer and reader cannot drift via divergent env resolution.
SELECTED_ACCOUNT_RECORD_REL: Final = Path(".local/state/caam-usage-rotate/selected-account.json")
_PROFILE_KEY: Final = "profile"
_SLOT_PREFIX: Final = "CLAUDE_CODE_OAUTH_TOKEN__"

# The admission pass's chooser: a callable returning the env-var NAME of the slot
# it chose, or None. Held at module scope because admission and every credential
# consumer run in ONE dispatcher process and the consumers take no policy argument.
_ADMISSION_CHOOSER: dict[str, Callable[[], str | None]] = {}


@dataclass(frozen=True, kw_only=True)
class FactoryCredentialChoice:
    """The chosen credential env-var NAME and, when it fell back, why.

    `fallback_reason` is None only when the choice needed no fallback; it is a
    non-secret, operator-facing string in every fallback case.
    """

    env_name: str
    fallback_reason: str | None


def claude_credential_policy_for(*, repo: Path) -> ClaudeCredentialPolicy | ClaudeCredentialRefusal:
    """This repository's committed policy, or the configuration refusal naming its defect."""
    resolved = credential_policy.resolve_claude_credential_policy(cwd=repo)
    if not is_successful(resolved):
        return policy_refusal(unreadable=unsafe_perform_io(resolved.failure()))
    return unsafe_perform_io(resolved.unwrap())


def injected_credential_slots(
    *, environ: Mapping[str, str], policy: ClaudeCredentialPolicy
) -> tuple[str, ...]:
    """Every pool slot's env-var NAME under the declared `policy`.

    A slot is injected when its variable is present and non-empty. Under
    `numbered-slots` the pool is only the DECLARED injected slots, in declaration
    order, and may be empty. Under `legacy-independent` it is every injected
    numbered slot, sorted, and the unnumbered token only when no numbered slot is.
    """
    if policy.mode == NUMBERED_SLOTS:
        return tuple(name for name in policy.slots if environ.get(name))
    numbered = tuple(
        sorted(name for name, value in environ.items() if name.startswith(_SLOT_PREFIX) and value)
    )
    if numbered:
        return numbered
    return (CLAUDE_OAUTH_TOKEN_ENV,) if environ.get(CLAUDE_OAUTH_TOKEN_ENV) else ()


def policy_pool_slots(*, repo: Path, environ: Mapping[str, str]) -> tuple[str, ...]:
    """The pool `repo`'s declared policy allows; none under an absent or invalid one."""
    resolved = claude_credential_policy_for(repo=repo)
    if isinstance(resolved, ClaudeCredentialRefusal):
        return ()
    return injected_credential_slots(environ=environ, policy=resolved)


def admission_credential_refusal(
    *,
    resolved: ClaudeCredentialPolicy | ClaudeCredentialRefusal,
    environ: Mapping[str, str],
) -> ClaudeCredentialRefusal | None:
    """Why no covered candidate may be admitted, or `None` when the pool may be assessed."""
    if isinstance(resolved, ClaudeCredentialRefusal):
        return resolved
    if resolved.mode == NUMBERED_SLOTS and not injected_credential_slots(
        environ=environ, policy=resolved
    ):
        return _no_declared_slot_refusal(policy=resolved, environ=environ)
    return None


def _no_declared_slot_refusal(
    *, policy: ClaudeCredentialPolicy, environ: Mapping[str, str]
) -> ClaudeCredentialRefusal:
    states = ", ".join(
        f"{name} ({'empty' if name in environ else 'absent'})" for name in policy.slots
    )
    return ClaudeCredentialRefusal(
        cause=NO_DECLARED_SLOT_INJECTED,
        detail=(
            f"{NO_DECLARED_SLOT_INJECTED}: dispatcher.claude_credential_policy declares "
            f"{states}; neither the unnumbered {CLAUDE_OAUTH_TOKEN_ENV} nor an undeclared "
            "numbered variable is substituted"
        ),
    )


def register_admission_slot_chooser(*, chooser: Callable[[], str | None] | None) -> None:
    """Install (or, with `None`, clear) the admission pass's slot chooser."""
    if chooser is None:
        _ADMISSION_CHOOSER.clear()
    else:
        _ADMISSION_CHOOSER["chooser"] = chooser


def selected_account_record_path(*, home: Path) -> Path:
    return home / SELECTED_ACCOUNT_RECORD_REL


def _slot_env_name(*, profile: str) -> str:
    # "anthropic-3" -> "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3": env-var names carry
    # no hyphens, so the profile is upper-cased with hyphens folded to underscores.
    normalized = profile.strip().upper().replace("-", "_")
    return f"{_SLOT_PREFIX}{normalized}"


def parse_selected_profile(*, record_text: str) -> str | None:
    """The published `profile` value, or None for any unusable record.

    Tolerant by contract: malformed JSON, a non-object root, or a missing,
    non-string, or empty `profile` all read as "no selection" so the caller
    falls back rather than raising.
    """
    try:
        parsed = json.loads(record_text)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    record = cast("dict[str, object]", parsed)
    profile = record.get(_PROFILE_KEY)
    if not isinstance(profile, str) or profile.strip() == "":
        return None
    return profile.strip()


def read_selected_profile(*, home: Path) -> str | None:
    """Read the published profile name from the host record, tolerating absence."""
    try:
        record_text = selected_account_record_path(home=home).read_text(encoding="utf-8")
    except OSError:
        return None
    return parse_selected_profile(record_text=record_text)


def resolve_factory_credential_env_name(
    *,
    selected_profile: str | None,
    available_env_names: frozenset[str],
) -> FactoryCredentialChoice:
    """Pure: choose the credential env-var NAME from the selection and the env.

    Prefer the per-profile pool slot when the loop published a profile AND that
    slot is present in the injected env; otherwise name the unnumbered token and
    say why. Never raises; the fallback is always a valid choice.
    """
    if selected_profile is None:
        return FactoryCredentialChoice(
            env_name=CLAUDE_OAUTH_TOKEN_ENV,
            fallback_reason="no caam-published account selection record",
        )
    slot = _slot_env_name(profile=selected_profile)
    if slot in available_env_names:
        return FactoryCredentialChoice(env_name=slot, fallback_reason=None)
    return FactoryCredentialChoice(
        env_name=CLAUDE_OAUTH_TOKEN_ENV,
        fallback_reason=f"no {slot} in the injected env for published profile {selected_profile!r}",
    )


def factory_credential_env_name(
    *,
    home: Path,
    available_env_names: frozenset[str],
) -> FactoryCredentialChoice:
    """Impure convenience: read the host record, then resolve against the env."""
    return resolve_factory_credential_env_name(
        selected_profile=read_selected_profile(home=home),
        available_env_names=available_env_names,
    )


def select_factory_credential(
    *,
    repo: Path,
    environ: Mapping[str, str],
    home: Path,
    warn: Callable[[str], object],
) -> FactoryCredentialChoice | ClaudeCredentialRefusal:
    """Resolve the credential env-var name under `repo`'s policy, or refuse.

    The policy is read HERE, on every call, so no caller depends on an admission
    pass having run first. The caller reads `environ[choice.env_name]` for a
    choice and refuses the operation for a `ClaudeCredentialRefusal`. `warn` is
    invoked once, with a non-secret message, when a legacy-independent pick fell
    back to the unnumbered token.
    """
    resolved = claude_credential_policy_for(repo=repo)
    if isinstance(resolved, ClaudeCredentialRefusal):
        return resolved
    pool = injected_credential_slots(environ=environ, policy=resolved)
    chooser = _ADMISSION_CHOOSER.get("chooser")
    admitted = None if chooser is None else chooser()
    if admitted is not None and admitted in pool:
        return FactoryCredentialChoice(env_name=admitted, fallback_reason=None)
    if resolved.mode == NUMBERED_SLOTS:
        return _declared_slot_choice(policy=resolved, pool=pool, admitted=admitted, environ=environ)
    choice = factory_credential_env_name(
        home=home,
        available_env_names=frozenset(environ),
    )
    if choice.fallback_reason is not None:
        _ = warn(
            f"factory credential slot fallback — using {choice.env_name}: {choice.fallback_reason}"
        )
    return choice


def _declared_slot_choice(
    *,
    policy: ClaudeCredentialPolicy,
    pool: tuple[str, ...],
    admitted: str | None,
    environ: Mapping[str, str],
) -> FactoryCredentialChoice | ClaudeCredentialRefusal:
    """Under `numbered-slots`: a declared, injected slot, or the refusal saying why not.

    The caam-published interactive selection plays no part: the Dispatcher MUST
    NOT read it to choose a slot.
    """
    if admitted is not None:
        return ClaudeCredentialRefusal(
            cause=ADMITTED_SLOT_ABSENT,
            detail=(
                f"{ADMITTED_SLOT_ABSENT}: the slot admission chose, {admitted}, is absent or "
                "empty here; refusing rather than choosing another credential"
            ),
        )
    if pool:
        return FactoryCredentialChoice(env_name=pool[0], fallback_reason=None)
    return _no_declared_slot_refusal(policy=policy, environ=environ)
