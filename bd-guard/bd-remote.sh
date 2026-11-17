#!/bin/sh
# bd-remote.sh — run a `bd` call ON the Dolt host over an already-open SSH
# ControlMaster connection (livespec-dev-tooling-tbhqye). One call is one SSH
# round trip instead of ~90 sequential Dolt round trips. The guard (bd-guard.sh)
# uses this as its REAL command ONLY when remote exec is configured and the
# control socket exists; it is never installed as `bd` itself.
#
# Wire format (contract with the server's forced command
# authorized-keys-bd-exec.sh): the single ssh command line
#     in <repo> bd <base64 of the NUL-separated bd argv>
# The client never reads or uses any SSH key: it only talks to the existing
# control socket (ssh -S ... -o ControlMaster=no).
#
# Local-vs-remote: calls that name caller-side files or connection details, a
# leading flag, or help/version/completion/send-metrics run LOCAL via the real
# bd (LIVESPEC_BD_REAL, default /usr/local/bin/bd-real).
#
# Fallback rule: before sending, `ssh -O check` must pass; if it fails nothing
# was sent, so the call runs locally and one line is logged to stderr and to the
# log file. Once the command is sent it is NEVER re-run locally (a write must
# never run twice): ssh's status is returned as is, and 255 (a transport failure
# that may follow the send) prints one error line and exits 255.

set -u

REAL="${LIVESPEC_BD_REAL:-/usr/local/bin/bd-real}"
CONF="${LIVESPEC_BD_REMOTE_CONF:-/usr/local/etc/livespec-bd-remote.conf}"
LOG="${LIVESPEC_BD_REMOTE_LOG:-${XDG_STATE_HOME:-${HOME:-/tmp}/.local/state}/livespec-bd-remote.log}"

_local() { exec "$REAL" "$@"; }

[ "$#" -ge 1 ] || _local "$@"
case "$1" in
    -* | help | version | completion | send-metrics) _local "$@" ;;
esac

# VERB ALLOWLIST and FLAG DENYLIST. THESE LISTS MUST MATCH the server wrapper
# (livespec-dev-tooling ansible/roles/authorized_keys_managed/files/
# authorized-keys-bd-exec.sh): anything the server denies runs LOCALLY here.
case "$1" in
    show | list | comments | comment | update | create | close | reopen | delete | dep \
        | search | label | tag | children | count | history | ready | duplicate \
        | duplicates | note | assign | priority | link | query | stale | status \
        | statuses | types | graph | epic | supersede | todo | q | state | set-state \
        | lint | promote | find-duplicates | version) ;;
    config)
        # Only `config get <key>` (exactly 3 args) for a key that does not look
        # like a secret; `config list/set`, bare config and secret keys run local.
        [ "${2:-}" = "get" ] && [ "$#" -eq 3 ] || _local "$@"
        # shellcheck disable=SC2018,SC2019  # ASCII-only, identical to the server wrapper
        _ck=$(printf '%s' "$3" | tr 'A-Z' 'a-z')
        case "$_ck" in
            *pass* | *token* | *secret* | *key* | *credential* | *auth*) _local "$@" ;;
        esac
        ;;
    *) _local "$@" ;;
esac

# FLAG DENYLIST by PATTERN, case-insensitive (mirrors the server wrapper): any
# flag that can name a host path, file, directory, URL, credentials file, the
# database connection or the shared database, in long form, attached short form
# (-fX) or short cluster (-vf), and any `@file` value. A lone -n, -q, -d, -v, -5
# stays allowed.
for _a in "$@"; do
    # shellcheck disable=SC2018,SC2019  # ASCII-only, identical to the server wrapper
    _l=$(printf '%s' "$_a" | tr 'A-Z' 'a-z')
    case "$_l" in
        --db | --db=* | --database* | --dolt-* | --host* | --port* | --global \
            | --profile* | --config* | --credentials* | --graph* | --from-* \
            | --*file* | --*path* | --*dir* | --*output* | --*url* | --*jsonl*) _local "$@" ;;
        --*) ;;
        -f | -c | -o) _local "$@" ;;
        -[a-z0-9]?*)
            case "${_l#-}" in *[fco]*) _local "$@" ;; esac ;;
    esac
    case "$_l" in @* | *=@*) _local "$@" ;; esac
done

CONTROL_SOCKET=""
SSH_TARGET=""
[ -r "$CONF" ] || _local "$@"
# shellcheck disable=SC1090
. "$CONF"
[ -n "$CONTROL_SOCKET" ] && [ -n "$SSH_TARGET" ] && [ -S "$CONTROL_SOCKET" ] || _local "$@"

_top=$(git rev-parse --show-toplevel 2>/dev/null) || _local "$@"
[ -d "$_top/.beads" ] || _local "$@"
# The tenant is the REPOSITORY name. In a worktree the toplevel's basename is
# the branch, so name the repo from the common git dir when it is a `.git`.
_common=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || _common=""
case "$_common" in
    */.git) _repo=$(basename "$(dirname "$_common")") ;;
    *) _repo=$(basename "$_top") ;;
esac
[ -n "$_repo" ] || _local "$@"

# NUL-join (no trailing NUL: the server appends its own terminator), one line.
_b64=$(
    {
        printf '%s' "$1"
        shift
        for _a in "$@"; do printf '\0%s' "$_a"; done
    } | base64 | tr -d '\n'
)
# `shift` above ran in a subshell; the parent's "$@" is intact for fallback.

# Liveness check BEFORE sending: if the master is not alive nothing has been
# sent, so a local run is safe. `-O check` does not read stdin; </dev/null keeps
# that explicit so the fallback still sees the original stdin.
if ! ssh -S "$CONTROL_SOCKET" -O check "$SSH_TARGET" >/dev/null 2>&1 </dev/null; then
    _msg="livespec bd-remote: ssh control master check failed; nothing sent, falling back to local bd"
    printf '%s\n' "$_msg" >&2
    { mkdir -p "$(dirname "$LOG")" && printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$_msg" >>"$LOG"; } 2>/dev/null || :
    _local "$@"
fi

# From here the command may have been sent: NEVER re-run locally (a write must
# never run twice), with ONE exception below. Return ssh's status as is; 255 is
# a transport failure that may have happened after the send, so say so and do not
# retry.
#
# Exception: the master's MaxSessions limit refuses the session BEFORE the remote
# command starts (ssh exits 255 with `Session open refused by peer` or
# `mux_client_request_session: session request failed` on its own stderr), so a
# local run is safe. ssh's stderr is captured through a fifo while still being
# passed straight to the caller's stderr. Only those two exact phrases count, and
# only when stdin is a terminal or /dev/null: with a piped stdin ssh may already
# have consumed part of it, so then we do NOT fall back.
_cap=""
_tmp=$(mktemp -d 2>/dev/null) || _tmp=""
if [ -n "$_tmp" ] && mkfifo "$_tmp/err" 2>/dev/null; then
    _cap="$_tmp/cap"
    : >"$_cap"
    tee "$_cap" <"$_tmp/err" >&2 &
    _teepid=$!
    ssh -S "$CONTROL_SOCKET" -o ControlMaster=no -o BatchMode=yes -o ConnectTimeout=5 \
        -T "$SSH_TARGET" "in $_repo bd $_b64" 2>"$_tmp/err"
    _rc=$?
    wait "$_teepid" 2>/dev/null || :
else
    ssh -S "$CONTROL_SOCKET" -o ControlMaster=no -o BatchMode=yes -o ConnectTimeout=5 \
        -T "$SSH_TARGET" "in $_repo bd $_b64"
    _rc=$?
fi
if [ "$_rc" -eq 255 ]; then
    if [ -n "$_cap" ] && { [ -t 0 ] || [ /dev/stdin -ef /dev/null ]; } \
        && grep -qE 'Session open refused by peer|mux_client_request_session: session request failed' "$_cap" 2>/dev/null; then
        rm -rf "$_tmp"
        _msg="livespec bd-remote: ssh session refused (MaxSessions) before the command started; falling back to local bd"
        printf '%s\n' "$_msg" >&2
        { mkdir -p "$(dirname "$LOG")" && printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$_msg" >>"$LOG"; } 2>/dev/null || :
        _local "$@"
    fi
    printf '%s\n' "bd-remote: connection to the VPS failed after the command was sent; not retried" >&2
fi
[ -n "$_tmp" ] && rm -rf "$_tmp"
exit "$_rc"
