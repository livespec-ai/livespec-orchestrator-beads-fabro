"""Whether THIS HOST's environment carries a usable dispatch credential.

Split from `_dispatcher_credentials` by cohesion. That module PROJECTS
credentials into a sandbox overlay -- it writes a mode-600 run-config overlay
and renders env tables for a run that does not exist yet. This one asks the
opposite-facing question: does the machine running the Dispatcher right now hold
a credential the sandbox could use, and is it actually usable rather than merely
present? Nothing here writes an overlay, and nothing in the overlay renderer
probes a provider.

THE PROBE SEAM LIVES HERE WITH ITS CALLERS. `probe_claude_credential` is
resolved through THIS module's namespace, so a caller that stands the probe in
stands in the one the whole dispatch path uses. That identity is the reason
`assess_credential_status` is public at all: the loop's bounded credential
re-probe needs the TYPED `condition`, not a refusal string it would have to
pattern-match, because it waits on exactly one condition (a provider-limit or
rate-limit refusal) and must exit its wait on every other.

THE RESOLUTION AND THE ASSESSMENT ARE SEPARATE ENTRY POINTS, FOR ONE CALLER. The
re-probe wait must assess the credential the wrapper holds NOW rather than the
one this process was launched with, so it resolves its own value and hands it to
`assess_resolved_credential`. `assess_credential_status` is that same call over
`os.environ`, which keeps both paths on ONE probe seam and ONE absent-credential
refusal; a re-probe that duplicated the assessment instead would be free to
classify a condition differently from the dispatch path that reports it.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    SessionHeadroomPolicy,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_projection import (
    SEVEN_DAY_FLOOR_SKIP_KIND,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    ClaudeCredentialStatus,
    absent_claude_credential_status,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential_io import (
    probe_claude_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential_policy import (
    ClaudeCredentialRefusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_wrapper import (
    WRAPPER_INJECTED_CREDENTIAL_ENV_NAMES,
    credential_wrapper_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    admission_slot_chooser_registered,
    select_factory_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import utc_now_iso

__all__: list[str] = [
    "CheckedCredentialEnv",
    "assess_credential_status",
    "assess_resolved_credential",
    "check_credential_env",
    "checked_credential_env",
    "dispatch_required_credentials_text",
    "projected_credential",
]


def dispatch_required_credentials_text() -> str:
    """The per-wrapper credential set, as the refusal an operator reads names it.

    Composed from the list `_dispatcher_credential_wrapper` owns, which is also
    the set the loop's credential re-resolution empties for its child. ONE list,
    so the refusal naming what the wrapper must inject and the re-resolution
    emptying what it injected cannot come to disagree about which names those
    are.
    """
    return ", ".join(WRAPPER_INJECTED_CREDENTIAL_ENV_NAMES)


def projected_credential(*, repo: Path) -> str | ClaudeCredentialRefusal:
    """The env-var NAME the dispatch would project, or the policy's refusal.

    Public so the re-probe wait can ask the credential wrapper for the SAME name
    the dispatch would project. Resolving it in the wait rather than re-deriving
    one there is what keeps a pool-slot selection from being observed by the
    assessment and ignored by the re-resolution.
    """
    choice = select_factory_credential(
        repo=repo,
        environ=os.environ,
        home=Path.home(),
        warn=lambda message: sys.stderr.write(f"livespec-dispatch: {message}\n"),
    )
    return choice if isinstance(choice, ClaudeCredentialRefusal) else choice.env_name


def assess_resolved_credential(
    *,
    repo: Path,
    token: str,
    probe: Callable[..., ClaudeCredentialStatus] | None = None,
) -> ClaudeCredentialStatus:
    """Assess a credential value the CALLER resolved: absence, else ONE bounded probe.

    Public because the refusal STRING is not the whole answer. The loop's
    bounded credential re-probe -- the admission-time probe-refusal clause of
    the provider spend-containment rules in `SPECIFICATION/contracts.md` --
    waits on ONE condition — a provider-limit or rate-limit refusal —
    and must exit its wait on every other, so it needs the typed
    `condition` rather than prose it would have to pattern-match. Keeping the
    assessment here rather than duplicating it in the re-probe module also
    keeps ONE probe seam: `probe_claude_credential` is resolved through this
    module's namespace, so a caller that stands the probe in stands in the one
    the whole dispatch path uses.
    """
    if token == "":
        return absent_claude_credential_status(wrapper_text=credential_wrapper_text(repo=repo))
    selected_probe = probe if probe is not None else probe_claude_credential
    return selected_probe(token=token)


def assess_credential_status(
    *,
    repo: Path,
    probe: Callable[..., ClaudeCredentialStatus] | None = None,
) -> ClaudeCredentialStatus:
    """Assess the credential THIS PROCESS was launched with, through the one seam above.

    A policy refusal assesses as an absent credential; `check_credential_env`
    reports the refusal itself before reaching here.
    """
    env_name = projected_credential(repo=repo)
    token = "" if isinstance(env_name, ClaudeCredentialRefusal) else os.environ.get(env_name, "")
    return assess_resolved_credential(repo=repo, token=token, probe=probe)


@dataclass(frozen=True, kw_only=True)
class CheckedCredentialEnv:
    """The env-var NAME whose credential passed the pre-launch check."""

    env_name: str


def check_credential_env(
    *,
    repo: Path,
    probe: Callable[..., ClaudeCredentialStatus] | None = None,
) -> str | None:
    """Fail fast unless the exact sandbox model credential is usable.

    Presence is not sufficient: this bounded live probe uses the same
    ``CLAUDE_CODE_OAUTH_TOKEN`` projected into the sandbox and refuses
    before launch when it is revoked, exhausted/rate-limited, denied, or
    cannot be assessed. Values and response bodies are never logged.
    """
    checked = checked_credential_env(repo=repo, probe=probe)
    return checked if isinstance(checked, str) else None


def checked_credential_env(
    *,
    repo: Path,
    probe: Callable[..., ClaudeCredentialStatus] | None = None,
) -> CheckedCredentialEnv | str:
    """The credential the projection then reads, or the pre-launch refusal.

    ONE selection serves the check and the projection, so the probe assesses the
    very slot the overlay carries. A refusal under the declared Claude credential
    policy (absent or invalid, no declared slot injected, or the admitted slot
    gone) refuses here, before anything is minted.
    """
    # An admitted launch already has the evaluation's memoized chooser.  Reusing
    # it avoids a second provider reading; only a bypass launch builds a policy
    # to apply the same weekly reserve before it chooses a slot.
    policy = (
        None
        if admission_slot_chooser_registered()
        else headroom_gate.session_headroom_policy(
            repo=repo, now_iso=utc_now_iso(), journal_path=None, register_chooser=False
        )
    )
    env_name = projected_credential(repo=repo)
    if isinstance(env_name, ClaudeCredentialRefusal):
        return f"C-mode dispatch refused before sandbox launch: {env_name.detail}"
    if policy is not None:
        weekly_refusal = _weekly_reserve_refusal(env_name=env_name, policy=policy)
        if weekly_refusal is not None:
            return weekly_refusal
    status = assess_resolved_credential(repo=repo, token=os.environ.get(env_name, ""), probe=probe)
    if status.usable:
        return CheckedCredentialEnv(env_name=env_name)
    return (
        f"C-mode dispatch refused before sandbox launch: {status.message} "
        f"Observed condition: {status.condition}. Remedy: {status.remedy} "
        "The dispatch target's credential_wrapper must inject the full "
        f"per-wrapper credential set: {dispatch_required_credentials_text()}."
    )


def _weekly_reserve_refusal(*, env_name: str, policy: SessionHeadroomPolicy) -> str | None:
    """Refuse the selected slot only for the admission policy's weekly floor.

    The pool assessment records the exact skip kind for every numbered slot.
    Reusing that result keeps the launcher strict below the reserve while
    preserving admission's equality, absent-weekly-reading and zero-floor
    behaviour.  The provider-rejection and five-hour arms remain their own
    launch checks rather than being relabelled as a reserve refusal here.
    """
    readings = policy.pool_read() if policy.pool_read is not None else ()
    for reading in readings:
        if reading.slot is not None and reading.slot.slot == env_name:
            if reading.slot.skip_kind == SEVEN_DAY_FLOOR_SKIP_KIND:
                return (
                    "C-mode dispatch refused before sandbox launch: selected credential "
                    f"{env_name} has a seven-day-floor headroom skip."
                )
            return None
    return None
