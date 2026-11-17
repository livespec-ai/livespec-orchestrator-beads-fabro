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
# Fallback rule: if ssh itself cannot start the remote call (status 255) the
# call runs locally and one line is logged to stderr and to the log file. If the
# remote bd STARTED and returned any other status, that status is returned and
# the call is NEVER retried locally (a write must never run twice).

set -u

REAL="${LIVESPEC_BD_REAL:-/usr/local/bin/bd-real}"
CONF="${LIVESPEC_BD_REMOTE_CONF:-/usr/local/etc/livespec-bd-remote.conf}"
LOG="${LIVESPEC_BD_REMOTE_LOG:-${XDG_STATE_HOME:-${HOME:-/tmp}/.local/state}/livespec-bd-remote.log}"

_local() { exec "$REAL" "$@"; }

[ "$#" -ge 1 ] || _local "$@"
case "$1" in
    -* | help | version | completion | send-metrics) _local "$@" ;;
esac
for _a in "$@"; do
    case "$_a" in
        --db | --db=* | --database | --database=* | --dolt-* | --host | --host=* \
            | --port | --port=* | --file | --file=* | --body-file | --body-file=* \
            | --design-file | --design-file=* | -f | --path | --path=* | --dir \
            | --dir=* | --config | --config=* | --output | --output=* | -o \
            | --jsonl | --jsonl=*) _local "$@" ;;
    esac
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

ssh -S "$CONTROL_SOCKET" -o ControlMaster=no -o BatchMode=yes -o ConnectTimeout=5 \
    -T "$SSH_TARGET" "in $_repo bd $_b64"
_rc=$?
if [ "$_rc" -eq 255 ]; then
    _msg="livespec bd-remote: ssh could not start the remote call (status 255); falling back to local bd"
    printf '%s\n' "$_msg" >&2
    { mkdir -p "$(dirname "$LOG")" && printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$_msg" >>"$LOG"; } 2>/dev/null || :
    _local "$@"
fi
exit "$_rc"
