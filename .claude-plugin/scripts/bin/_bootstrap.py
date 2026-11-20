"""Pre-livespec_orchestrator_beads_fabro-import bootstrap: sys.path setup + Python version check.

Imported by every bin/*.py wrapper before any livespec_orchestrator_beads_fabro import.
Lives under bin/ so the wrappers can `raise SystemExit(main())` per the
shebang-wrapper contract.

At the tail of `bootstrap()` — AFTER the sys.path inserts make the vendored
`livespec_runtime` importable — the credential self-heal chokepoint runs. It
delegates the decision to the pure `decide_credentials` brain in
`livespec_runtime.credentials` and performs the impure act it prescribes:
proceed normally, re-exec the process through the project's configured
`credential_wrapper` (so the wrapper injects the missing tenant secret), or
fail with an actionable diagnostic. This covers every bin/*.py CLI that calls
`bootstrap()` at once, so a bare invocation without `BEADS_DOLT_PASSWORD`
self-heals instead of failing deep in the beads backend with a raw auth error.

That re-exec runs through `sudo`, which rebuilds the environment from its own
policy, so it is also the point where non-secret session markers can be
silently DESTROYED — see `_marker_forwarded_argv`, which carries the
unattended-plan-resume marker and publishing-identity session ids across it.
"""

import atexit
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

from _payload import (
    PayloadRefusal,
    payload_relative_argv,
    release_payload,
    retain_payload,
)

if TYPE_CHECKING:
    from livespec_runtime.credentials import CredentialDecision

__all__: list[str] = ["bootstrap"]

# The tenant secret every beads-backed orchestrator CLI needs at call time —
# the DEFAULT `required` set; wrappers with a different secret surface pass
# their own (see `bootstrap`).
_REQUIRED_CREDENTIALS = ("BEADS_DOLT_PASSWORD",)
# The family tenant password authenticates the SHARED dolt-server tenant DB.
# An EMBEDDED, self-contained Dolt ledger (initialized with no `--server`)
# needs none, so it is dropped from `required` for a non-server project.
# (This is the env-var NAME, not a secret value.)
_TENANT_ENV_NAME = "BEADS_DOLT_PASSWORD"
_BEADS_CONFIG_RELPATH = (".beads", "config.yaml")
_SERVER_MODE_MARKER = "dolt.mode:server"
_LIVESPEC_CONFIG_FILENAME = ".livespec.jsonc"
_CREDENTIAL_FAIL_EXIT = 3
# A payload this invocation cannot keep running from is a PRECONDITION failure,
# and it shares the credential refusal's exit code because both say the same
# thing to a caller: the environment is not fit to dispatch from, nothing was
# claimed, and no factory run was started.
_PAYLOAD_FAIL_EXIT = 3
# The unattended-plan-resume marker. NOT a secret and never a member of
# `required`: the credential self-heal neither needs it nor injects it — it
# only has to stop DESTROYING it (see `_marker_forwarded_argv`). The name is
# re-declared here rather than imported from
# `commands._plan_timeline.UNATTENDED_ENV_VAR` because this runs at the
# pre-package boundary, and a credential self-heal must not start depending on
# the store layer importing cleanly; `tests/bin/
# test_bootstrap_unattended_marker_forwarding.py` pins the two spellings equal.
_PLAN_UNATTENDED_ENV_NAME = "LIVESPEC_PLAN_UNATTENDED"
# The agent-session variables that establish a proof poster's identity. This
# pre-package bootstrap cannot import `_dispatcher_proof_identity`, so the
# tuple is re-declared here and forwards only values an invoking session set.
_AGENT_SESSION_ENV_VARS = ("CODEX_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "PI_SESSION_ID")
# `env` is the POSIX command that runs its own operand with NAME=value applied.
_ENV_COMMAND = "env"
# The target-owner App is projected by every livespec-ai target's committed
# credential wrapper.  It remains distinct from the host-default App so the
# post-wrapper entry can prove the projection actually took effect.
_TARGET_APP_ID_ENV = "GITHUB_APP_ID_ORG"


def bootstrap(
    *,
    required: tuple[str, ...] = _REQUIRED_CREDENTIALS,
    force_credential_wrapper: bool = False,
    force_credential_wrapper_for_command: str | None = None,
) -> None:
    """Set up sys.path, then run the credential self-heal chokepoint.

    `required` names the secret env vars THIS bin wrapper needs at call
    time; the default is the tenant-wide `BEADS_DOLT_PASSWORD` every
    beads-touching CLI consumes. The Dispatcher requires the tenant secret
    PLUS the GitHub App env (GITHUB_APP_ID + GITHUB_PRIVATE_KEY); the
    mint-app-token CLI requires the App env ALONE (a GitHub token mint has
    no business demanding the Dolt password). Either way the set resolves
    ONLY through the governed project's credential_wrapper
    (github-app-auth Pillar 2: missing secrets re-exec through the wrapper
    when one is configured, and FAIL CLOSED when none is — never a fleet
    fallback).
    """
    if sys.version_info < (3, 10):
        sys.stderr.write(
            "livespec-orchestrator-beads-fabro requires Python 3.10+; install via uv.\n"
        )
        raise SystemExit(127)
    source_root = Path(__file__).resolve().parent.parent.parent
    payload = retain_payload(source_root=source_root, environ=os.environ)
    if isinstance(payload, PayloadRefusal):
        _ = sys.stderr.write(payload.message + "\n")
        raise SystemExit(_PAYLOAD_FAIL_EXIT)
    for path in (payload.scripts_root, payload.vendor_root):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
    # Registered BEFORE the credential self-heal can re-exec, and keyed on the
    # payload this process OWNS, so the tree outlives every child the
    # invocation waits on and is removed exactly once, by its creator.
    _ = atexit.register(release_payload, payload=payload)
    selected_command = sys.argv[1] if len(sys.argv) > 1 else None
    _self_heal_credentials(
        required=_effective_required(required=required, cwd=Path.cwd()),
        argv=payload_relative_argv(
            argv=sys.argv, source_root=source_root, payload_root=payload.root
        ),
        force_credential_wrapper=(
            force_credential_wrapper
            or (
                force_credential_wrapper_for_command is not None
                and selected_command == force_credential_wrapper_for_command
            )
        ),
    )


def _tenant_secret_required(*, cwd: Path) -> bool:
    """Whether this beads CLI invocation needs the family tenant secret.

    `BEADS_DOLT_PASSWORD` authenticates the SHARED dolt-server tenant DB. A
    dispatch against an EMBEDDED ledger — a self-contained Dolt store
    provisioned in embedded mode (no `--server`), e.g. the disposable
    livespec-e2e golden-master target — needs no such password. So require it
    only when the governed project's beads ledger is server-mode (its
    `.beads/config.yaml` declares `dolt.mode: server`), and fail CLOSED
    (require) when that config is absent or unreadable.
    """
    config_path = cwd.joinpath(*_BEADS_CONFIG_RELPATH)
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return True
    return any(line.strip().replace(" ", "") == _SERVER_MODE_MARKER for line in text.splitlines())


def _effective_required(*, required: tuple[str, ...], cwd: Path) -> tuple[str, ...]:
    """Drop the family tenant secret from `required` for an embedded ledger.

    Only the tenant-password env var is mode-conditional; every other member
    of `required` (the GitHub App env) stays unconditionally required.
    """
    if _tenant_secret_required(cwd=cwd):
        return required
    return tuple(name for name in required if name != _TENANT_ENV_NAME)


def _read_credential_wrapper() -> list[str]:
    """Return the top-level `credential_wrapper` argv-prefix from the governed
    project's `.livespec.jsonc`, tolerating any read/parse quirk as `[]`.

    Fail-open toward "no wrapper": a missing file, malformed JSONC, a
    non-object root, or a non-list value all yield `[]` — which, when the
    secret is also missing, produces the actionable `Fail` diagnostic rather
    than crashing bootstrap on a config quirk.
    """
    # Deferred import: the package is on sys.path only AFTER `bootstrap()`'s
    # inserts run, so this cannot be a module-level import.
    from livespec_orchestrator_beads_fabro.commands._jsonc import JsoncParseError, loads

    config_path = Path.cwd() / _LIVESPEC_CONFIG_FILENAME
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        parsed = loads(text=raw_text)
    except JsoncParseError:
        return []
    if not isinstance(parsed, dict):
        return []
    mapping = cast("dict[str, object]", parsed)
    raw_wrapper = mapping.get("credential_wrapper", [])
    if not isinstance(raw_wrapper, list):
        return []
    return [str(token) for token in cast("list[object]", raw_wrapper)]


def _marker_forwarded_argv(
    *,
    reexec_argv: Sequence[str],
    credential_wrapper: Sequence[str],
    environ: Mapping[str, str],
) -> list[str]:
    """Carry session markers across the credential re-exec.

    The wrapper is a `sudo -n` escalation, and sudo rebuilds the environment
    from its own policy: the reference `with-livespec-env.sh` forwards
    `WRAPPER_STAGE` and `OP_ENV_WRAPPER_CACHE_TTL` and nothing else. So a
    `LIVESPEC_PLAN_UNATTENDED` set by the overseer daemon on the session it
    restarts does NOT survive into the wrapped process, and the plan resume
    there reads an unattended session as attended — `ask=True`, no error, a
    hands-off restart parked on a picker nobody is present to answer.

    What sudo cannot strip is the COMMAND it was asked to run. `reexec_argv` is
    `[*credential_wrapper, executable, *argv]`, so splicing `env NAME=value`
    in at `len(credential_wrapper)` puts the assignment after the wrapper's
    own `--` separator — inside the command, where it is applied by `env` in
    the already-escalated process rather than inherited through it. That is the
    same remedy operators are given for the wrapper by hand; the alternatives
    were rejected on evidence. Editing `with-livespec-env.sh` would make a
    plugin behaviour depend on a host file no clone provisions, and
    `OPENV_PRESERVE_VARS` is applied AFTER the stage-0 escalation that already
    dropped the variable.

    Only NON-EMPTY values are forwarded. The plan marker's empty string is not
    truthy to `is_unattended_session`; the agent-session values are likewise
    omitted so an invocation with no session identity remains eligible for the
    forge-login fallback. This never AUTHORS a marker — an attended human
    session's argv is returned unchanged, which keeps the overseer daemon its
    only setter and leaves publishing identity computed by the child.
    """
    forwarded = [
        f"{name}={value}"
        for name in (_PLAN_UNATTENDED_ENV_NAME, *_AGENT_SESSION_ENV_VARS)
        if (value := environ.get(name, ""))
    ]
    if not forwarded:
        return list(reexec_argv)
    separator_index = len(credential_wrapper)
    return [
        *reexec_argv[:separator_index],
        _ENV_COMMAND,
        *forwarded,
        *reexec_argv[separator_index:],
    ]


def _credential_decision(
    *,
    required: tuple[str, ...],
    credential_wrapper: list[str],
    argv: list[str],
    force_credential_wrapper: bool,
) -> "CredentialDecision":
    """Choose credentials, preferring the target projection when requested."""
    from livespec_runtime.credentials import (
        CREDENTIAL_REEXEC_ARGV_MARKER,
        CREDENTIAL_REEXEC_SENTINEL,
        Fail,
        Proceed,
        Reexec,
        decide_credentials,
    )

    decision = decide_credentials(
        required=required,
        credential_wrapper=credential_wrapper,
        environ=os.environ,
        executable=sys.executable,
        argv=argv,
    )
    already_reexeced = (
        CREDENTIAL_REEXEC_ARGV_MARKER in argv or os.environ.get(CREDENTIAL_REEXEC_SENTINEL) == "1"
    )
    if not force_credential_wrapper:
        return decision
    if already_reexeced:
        expected_app_id = os.environ.get(_TARGET_APP_ID_ENV)
        actual_app_id = os.environ.get("GITHUB_APP_ID")
        if isinstance(decision, Proceed) and expected_app_id and actual_app_id != expected_app_id:
            return Fail(
                message=(
                    "target repository App identity mismatch before run creation: "
                    f"expected App id {expected_app_id}, received App id "
                    f"{actual_app_id or '<absent>'}."
                )
            )
        return decision
    if not credential_wrapper:
        return Fail(
            message=(
                "target repository App selection requires a credential_wrapper "
                "in .livespec.jsonc."
            )
        )
    return Reexec(argv=(*credential_wrapper, sys.executable, *argv))


def _strip_credential_reexec_marker(*, marker: str) -> None:
    if marker in sys.argv:
        sys.argv[:] = [arg for arg in sys.argv if arg != marker]


def _run_credential_wrapper(
    *,
    reexec_argv: Sequence[str],
    credential_wrapper: Sequence[str],
    required: tuple[str, ...],
) -> subprocess.CompletedProcess[bytes]:
    """Run the credential wrapper or fail cleanly when it cannot start."""
    from livespec_runtime.credentials import (
        CREDENTIAL_REEXEC_ARGV_MARKER,
        wrapper_launch_failure,
    )

    try:
        return subprocess.run(  # noqa: S603
            _marker_forwarded_argv(
                reexec_argv=[*reexec_argv, CREDENTIAL_REEXEC_ARGV_MARKER],
                credential_wrapper=credential_wrapper,
                environ=os.environ,
            ),
            capture_output=True,
            check=False,
        )
    except (FileNotFoundError, PermissionError):
        failure = wrapper_launch_failure(
            required=required,
            credential_wrapper=credential_wrapper,
        )
        _ = sys.stderr.write(failure.message + "\n")
        raise SystemExit(_CREDENTIAL_FAIL_EXIT) from None


def _self_heal_credentials(
    *,
    required: tuple[str, ...] = _REQUIRED_CREDENTIALS,
    argv: list[str] | None = None,
    force_credential_wrapper: bool = False,
) -> None:
    """Decide-and-perform the credential self-heal at the bin chokepoint.

    The pure decision lives in the vendored `livespec_runtime.credentials`;
    this thin performer supplies the live inputs (parsed wrapper, environ,
    interpreter, argv) and carries out the prescribed impure act.
    `required` is the calling wrapper's own secret set (see `bootstrap`).

    `argv` is the command the re-exec should rebuild, defaulting to this
    process's own. `bootstrap()` passes the PAYLOAD-relative form, so a
    wrapper launched around an eviction still has a program file to open.
    """
    # Deferred imports: the vendored tree is on sys.path only AFTER
    # `bootstrap()`'s inserts run.
    from livespec_runtime.credentials import (
        CREDENTIAL_REEXEC_ARGV_MARKER,
        CREDENTIAL_REEXEC_SENTINEL,
        Fail,
        Proceed,
        Reexec,
    )
    from typing_extensions import assert_never

    credential_wrapper = _read_credential_wrapper()
    decision_argv = sys.argv if argv is None else argv
    decision = _credential_decision(
        required=required,
        credential_wrapper=credential_wrapper,
        argv=decision_argv,
        force_credential_wrapper=force_credential_wrapper,
    )
    _strip_credential_reexec_marker(marker=CREDENTIAL_REEXEC_ARGV_MARKER)
    match decision:
        case Proceed():
            return
        case Fail(message=message):
            _ = sys.stderr.write(message + "\n")
            raise SystemExit(_CREDENTIAL_FAIL_EXIT)
        case Reexec(argv=reexec_argv):
            _ = sys.stderr.write(
                "livespec: required credential env absent; re-invoking under credential_wrapper\n"
            )
            os.environ[CREDENTIAL_REEXEC_SENTINEL] = "1"
            completed = _run_credential_wrapper(
                reexec_argv=reexec_argv,
                credential_wrapper=credential_wrapper,
                required=required,
            )
            stdout = completed.stdout or b""
            stderr = completed.stderr or b""
            if stdout:
                _ = sys.stdout.buffer.write(stdout)
                _ = sys.stdout.flush()
            if stderr:
                _ = sys.stderr.buffer.write(stderr)
                _ = sys.stderr.flush()
            raise SystemExit(completed.returncode)
        case _:
            assert_never(decision)
