"""Sandbox-local refreshing GitHub CLI wrapper projection for Dispatcher runs.

The bundle the wrapper needs is a set of helper programs the helper-fetch setup
step writes under the bundle root (`_dispatcher_helper_registry`): the mint
helper, the push helper, the wrapper's fixed tail, and the vendored GitHub-auth
support files, each one its own digest-verified file. This module names those
pieces and renders the one step that installs the wrapper over `gh`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    PrepareStep,
    render_prepare_step,
)

__all__: list[str] = [
    "DEFAULT_SANDBOX_GH_REFRESH_ROOT",
    "GH_MINT_HELPER_RELPATH",
    "GH_PUSH_HELPER_RELPATH",
    "GH_WRAPPER_TAIL_RELPATH",
    "SANDBOX_GH_REFRESH_ROOT_ENV_VAR",
    "gh_mint_helper_source",
    "gh_wrapper_tail_source",
    "github_auth_support_relpaths",
    "refreshing_gh_env_lines",
    "refreshing_gh_prepare_steps_block",
    "resolve_sandbox_gh_refresh_root",
]

_GITHUB_APP_ENV_KEYS = (
    "GITHUB_APP_ID",
    "GITHUB_PRIVATE_KEY",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_API_URL",
)
# The in-sandbox bundle root the dispatcher materializes the refreshing `gh`
# wrapper into. It holds the code that mints the run's forge credential, so it
# lives under the Dispatcher-materialized plugins root and OUTSIDE the run's
# working tree: an agent stage can edit and commit the working tree, and
# anything it writes there could act with the credential when a publication
# stage next runs. The value is a shell expression, expanded by the shell that
# runs each prepare step. The lever below exists so a test can execute the
# rendered steps for real against a temporary root; production never sets it.
# Mirrors `LIVESPEC_SANDBOX_OTEL_ENDPOINT` in `_dispatcher_projection`.
SANDBOX_GH_REFRESH_ROOT_ENV_VAR = "LIVESPEC_SANDBOX_GH_REFRESH_ROOT"

DEFAULT_SANDBOX_GH_REFRESH_ROOT = (
    "${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}/livespec-gh-refresh"
)

# Where each fixed piece of the bundle lands, relative to the bundle root. The
# helper-fetch setup step writes them (`_dispatcher_helper_registry`); the
# wrapper-install step below only reads them.
GH_MINT_HELPER_RELPATH = "bin/mint_app_token.py"
GH_PUSH_HELPER_RELPATH = "bin/push_origin"
GH_WRAPPER_TAIL_RELPATH = "bin/gh-wrapper-tail.sh"


def resolve_sandbox_gh_refresh_root(*, environ: Mapping[str, str]) -> str:
    """Resolve the in-sandbox `gh`-wrapper bundle root (override > default)."""
    override = environ.get(SANDBOX_GH_REFRESH_ROOT_ENV_VAR, "").strip()
    return override or DEFAULT_SANDBOX_GH_REFRESH_ROOT


_SUPPORT_ARCHIVE_RELPATHS = (
    Path("_vendor/livespec_runtime/__init__.py"),
    Path("_vendor/livespec_runtime/github_auth"),
    Path("_vendor/returns"),
    Path("_vendor/typing_extensions.py"),
)
_MINT_HELPER_SOURCE = """#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

bundle_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(bundle_root / "_vendor"))

from livespec_runtime.github_auth.config import load_github_app_config
from livespec_runtime.github_auth.errors import GithubAppAuthError
from livespec_runtime.github_auth.mint import DEFAULT_MINT_SEAMS
from livespec_runtime.github_auth.provider import InstallationTokenProvider
from returns.io import IOFailure, IOSuccess
from returns.pipeline import is_successful

# An agent stage's token is read-only: the wrapper sets this scope when the dispatcher-recorded
# node is an agent stage, and the installation token is then requested with read permissions
# only, so it cannot publish whatever a call does. The set is what the factory App is granted
# (issues and actions are refused with HTTP 422). A permission the App lacks fails the mint
# loudly (exit 3 below); the token is never silently widened.
_READ_ONLY_PERMISSIONS = {
    "checks": "read",
    "contents": "read",
    "metadata": "read",
    "pull_requests": "read",
    "statuses": "read",
}


def read_only_post(*, url, jwt):
    if not url.startswith("https://"):
        return IOFailure(GithubAppAuthError(detail=f"refusing non-https GitHub API URL {url!r}"))
    request = urllib.request.Request(
        url,
        data=json.dumps({"permissions": _READ_ONLY_PERMISSIONS}).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "livespec-runtime-github-auth",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30.0) as response:
            return IOSuccess(json.load(response))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return IOFailure(GithubAppAuthError(detail=f"GitHub App API call to {url} failed: {exc}"))


if len(sys.argv) != 1:
    sys.stderr.write("usage: mint_app_token.py\\n")
    raise SystemExit(2)

config = load_github_app_config(environ=os.environ)
if not is_successful(config):
    sys.stderr.write(f"ERROR: {config.failure().detail}\\n")
    raise SystemExit(3)

seams = DEFAULT_MINT_SEAMS
if os.environ.get("LIVESPEC_GH_TOKEN_SCOPE") == "read":
    seams = dataclasses.replace(seams, http_post=read_only_post)

try:
    token = InstallationTokenProvider(config=config.unwrap(), seams=seams).token()
except GithubAppAuthError as exc:
    sys.stderr.write(f"ERROR: {exc.detail}\\n")
    raise SystemExit(3) from exc

sys.stderr.write("github-token source: github-app-installation-token\\n")
sys.stdout.write(token)
"""

_AGENT_PUBLICATION_GUARD_SOURCE = r"""livespec_agent_publication_action() {
    case "${1:-} ${2:-}" in
        "pr create") printf '%s' gh_pr_create ;;
        "pr ready") printf '%s' gh_pr_ready ;;
        "pr merge") printf '%s' gh_pr_merge ;;
        "pr edit") printf '%s' gh_pr_edit ;;
        "api "*) livespec_agent_api_publication_action "$@" ;;
        "auth git-credential") livespec_agent_credential_action "${3:-}" ;;
        *) return 1 ;;
    esac
}

livespec_agent_api_publication_action() {
    shift
    endpoint=''
    method=''
    has_body=''
    unreadable=''
    query=''
    value_for=''
    for argument in "$@"; do
        case "$value_for" in
            method) method="$argument"; value_for='' ;;
            field) has_body=1; query="$query $argument"; value_for='' ;;
            typed_field)
                has_body=1
                query="$query $argument"
                case "${argument#*=}" in @*) unreadable=1 ;; esac
                value_for=''
                ;;
            input) has_body=1; unreadable=1; value_for='' ;;
            *)
                case "$argument" in
                    --method|-X) value_for=method ;;
                    --method=*) method="${argument#*=}" ;;
                    -X?*) method="${argument#-X}" ;;
                    -f|--raw-field) value_for=field ;;
                    -F|--field) value_for=typed_field ;;
                    --raw-field=*) has_body=1; query="$query ${argument#--raw-field=}" ;;
                    -f?*) has_body=1; query="$query ${argument#-f}" ;;
                    --field=*|-F?*)
                        has_body=1
                        attached="${argument#--field=}"
                        attached="${attached#-F}"
                        query="$query $attached"
                        case "${attached#*=}" in @*) unreadable=1 ;; esac
                        ;;
                    --input) value_for=input ;;
                    --input=*) has_body=1; unreadable=1 ;;
                    query=*|mutation=*) query="$query $argument" ;;
                    graphql|/repos/*|repos/*) endpoint="$argument" ;;
                esac
                ;;
        esac
    done
    if test -z "$method"; then
        if test -n "$has_body"; then method=POST; else method=GET; fi
    fi
    method=$(printf '%s' "$method" | tr '[:lower:]' '[:upper:]')
    case "$endpoint" in
        graphql)
            if test -n "$unreadable"; then
                printf '%s' gh_api_graphql_unreadable
                return 0
            fi
            query=$(printf '%s' "$query" | tr '[:upper:]' '[:lower:]')
            case "$query" in
                *mergepullrequest*) printf '%s' gh_api_graphql_merge ;;
                *createpullrequest*) printf '%s' gh_api_graphql_create ;;
                *markpullrequestreadyforreview*) printf '%s' gh_api_graphql_ready ;;
                *updatepullrequest*) printf '%s' gh_api_graphql_edit ;;
                *enablepullrequestautomerge*|*disablepullrequestautomerge*)
                    printf '%s' gh_api_graphql_auto_merge ;;
                *) return 1 ;;
            esac
            ;;
        /repos/*/pulls/*/merge|repos/*/pulls/*/merge)
            test "$method" = PUT && printf '%s' gh_api_merge
            ;;
        /repos/*/pulls|repos/*/pulls)
            test "$method" = POST && printf '%s' gh_api_create
            ;;
        /repos/*/pulls/*/*|repos/*/pulls/*/*)
            test "$method" = PATCH && printf '%s' gh_api_edit
            ;;
        /repos/*/pulls/*|repos/*/pulls/*)
            test "$method" != GET && test "$method" != HEAD && printf '%s' gh_api_edit
            ;;
        *) return 1 ;;
    esac
}

# The stage is the one the dispatcher recorded for the running agent node, in the bundle root,
# beside `bin/`: `<launcher pid> <stage>`. It is never read from LIVESPEC_AGENT_STAGE, which the
# agent sets inline (`env LIVESPEC_AGENT_STAGE=pr gh ...`) or exports. A record whose launcher is
# gone belongs to a finished node, so a later publication node is unguarded; an unreadable record
# is treated as an agent stage.
livespec_agent_recorded_stage() {
    record="$(dirname "$mint")/../agent-stage"
    test -e "$record" || return 1
    pid=''
    stage=''
    read -r pid stage <"$record" 2>/dev/null || true
    case "$pid" in
        ''|*[!0-9]*) printf '%s' unrecorded; return 0 ;;
    esac
    kill -0 "$pid" 2>/dev/null || return 1
    printf '%s' "$stage"
}

# git asks its credential helper the same question for a fetch and a push, so the helper looks
# at the git process that is asking: the nearest ancestor that is `git` itself (or a script
# named git), and the subcommand it was started with. Only the read subcommands are served; an
# unrecognised subcommand, or no git ancestor at all, is refused.
livespec_agent_credential_action() {
    test "${1:-}" = get || return 1
    pid=$$
    while test -n "$pid" && test "$pid" -gt 1; do
        arguments=()
        while IFS= read -r -d '' argument; do
            arguments+=("$argument")
        done <"/proc/$pid/cmdline" 2>/dev/null || true
        offset=''
        case "${arguments[0]:-}" in git|*/git) offset=1 ;; esac
        case "${arguments[1]:-}" in git|*/git) offset=2 ;; esac
        if test -n "$offset"; then
            subcommand=''
            skip=''
            for argument in "${arguments[@]:$offset}"; do
                if test -n "$skip"; then skip=''; continue; fi
                case "$argument" in
                    -C|-c|--git-dir|--work-tree|--namespace|--exec-path) skip=1 ;;
                    -*) ;;
                    *) subcommand="$argument"; break ;;
                esac
            done
            case "$subcommand" in
                fetch|pull|clone|ls-remote|submodule|remote) return 1 ;;
            esac
            # Over http git asks from its transport helper, `git remote-http`, a child of the
            # user's own `git fetch`/`git push`: that is not the command being classified, so
            # the walk goes on to its parent.
            case "$subcommand" in
                remote-http|remote-https) ;;
                *) printf '%s' git_push; return 0 ;;
            esac
        fi
        stat=$(cat "/proc/$pid/stat" 2>/dev/null) || break
        stat=${stat##*) }
        set -- $stat
        pid=${2:-}
    done
    printf '%s' git_credential
}

agent_stage="$(livespec_agent_recorded_stage)" || agent_stage=''
case "$agent_stage" in
    ''|publish_draft|pr_refresh|pr) ;;
    *)
        if action="$(livespec_agent_publication_action "$@")"; then
            printf 'LIVESPEC_AGENT_PUBLICATION_DENIED: stage=%s action=%s\n' \
                "$agent_stage" "$action" >&2
            exit 1
        fi
        ;;
esac

# An agent stage mints a read-only token: the wrapper decides the scope from the recorded stage
# and the mint command clears any value the agent exported.
mint_scope=''
case "$agent_stage" in
    ''|publish_draft|pr_refresh|pr) ;;
    *) mint_scope=read ;;
esac
"""


# The variables that make a python3 started under `uv run pytest` measure itself: coverage's own
# subprocess switch and pytest-cov's pth startup hook. The mint helper is no repository's source,
# so the wrapper starts it without them and no repository's coverage omit has to track where the
# bundle lives (bd-ib-ompbgu).
_COVERAGE_HOOK_VARIABLES = (
    "COVERAGE_PROCESS_START",
    "COV_CORE_SOURCE",
    "COV_CORE_CONFIG",
    "COV_CORE_DATAFILE",
    "COV_CORE_BRANCH",
    "COV_CORE_CONTEXT",
)
_MINT_COMMAND = (
    "env "
    + " ".join(f"-u {name}" for name in (*_COVERAGE_HOOK_VARIABLES, "LIVESPEC_GH_TOKEN_SCOPE"))
    + ' ${mint_scope:+LIVESPEC_GH_TOKEN_SCOPE=$mint_scope} python3 "$mint"'
)

_WRAPPER_TAIL = (
    _AGENT_PUBLICATION_GUARD_SOURCE
    + 'token="$('
    + _MINT_COMMAND
    + ')"\n'
    + """export GH_TOKEN="$token"
export GITHUB_TOKEN="$token"
exec "$real_gh" "$@"
"""
)


def refreshing_gh_prepare_steps_block() -> str:
    """Install the sandbox-local refreshing `gh` wrapper when App inputs exist.

    The bundle the wrapper runs -- the mint helper, the push helper, the wrapper's
    fixed tail and the vendored GitHub-auth support files -- is no longer carried
    here. The helper-fetch setup step writes it under the bundle root, from the
    installed build's own commit, digest-verified and hidden from the run's git
    worktree file by file (`_dispatcher_helper_fetch`, `_dispatcher_helper_registry`).
    So this step only installs the wrapper over `gh`: it moves the real binary
    aside once, writes the wrapper's two variable lines, and appends the fixed
    tail the fetch step landed.
    """
    if not github_app_env_present():
        return ""
    bundle_root = resolve_sandbox_gh_refresh_root(environ=os.environ)
    step = PrepareStep(script=_install_script(bundle_root=bundle_root))
    return "\n# --- Dispatcher-materialized livespec-refreshing-gh-wrapper ---\n" + (
        render_prepare_step(step=step)
    )


def _install_script(*, bundle_root: str) -> str:
    """Move the real `gh` aside once and write the wrapper that mints before every call."""
    return (
        "set -eu\n"
        f'mint="{bundle_root}/{GH_MINT_HELPER_RELPATH}"\n'
        f'tail_file="{bundle_root}/{GH_WRAPPER_TAIL_RELPATH}"\n'
        'real_gh="$(command -v gh)"\n'
        'case "$real_gh" in\n'
        "  /*) ;;\n"
        '  *) echo "gh did not resolve to an absolute path" >&2; exit 1 ;;\n'
        "esac\n"
        'wrapped_gh="${real_gh}.livespec-real"\n'
        'if [ ! -x "$wrapped_gh" ]; then mv "$real_gh" "$wrapped_gh"; fi\n'
        "printf '%s\\n' '#!/usr/bin/env bash' 'set -euo pipefail'"
        ' "mint=\\"$mint\\"" "real_gh=\\"$wrapped_gh\\"" > "$real_gh"\n'
        'cat "$tail_file" >> "$real_gh"\n'
        'chmod 755 "$real_gh"'
    )


def gh_mint_helper_source() -> str:
    """The App-token mint helper the wrapper runs before every `gh` call."""
    return _MINT_HELPER_SOURCE


def gh_wrapper_tail_source() -> str:
    """The fixed tail of the refreshing wrapper: the publication guard, the mint, the exec."""
    return _WRAPPER_TAIL


def github_auth_support_relpaths(*, scripts_root: Path) -> tuple[Path, ...]:
    """Every vendored file the mint helper imports, relative to `scripts_root`, sorted.

    The same set the support archive carried: each listed directory contributes
    its `.py` files and each listed file itself, so a cache's `__pycache__` never
    rides along.
    """
    found: list[Path] = []
    for relpath in _SUPPORT_ARCHIVE_RELPATHS:
        source = scripts_root / relpath
        if source.is_dir():
            found.extend(child.relative_to(scripts_root) for child in sorted(source.rglob("*.py")))
        else:
            found.append(relpath)
    return tuple(found)


def refreshing_gh_env_lines() -> str:
    """Project GitHub App inputs for the sandbox-local mint helper."""
    if not github_app_env_present():
        return ""
    return "".join(
        f"{key} = {json.dumps(value)}\n"
        for key in _GITHUB_APP_ENV_KEYS
        if (value := os.environ.get(key)) not in (None, "")
    )


def github_app_env_present() -> bool:
    """Whether the minimum GitHub App inputs are present."""
    return all(os.environ.get(key) not in (None, "") for key in _GITHUB_APP_ENV_KEYS[:2])
