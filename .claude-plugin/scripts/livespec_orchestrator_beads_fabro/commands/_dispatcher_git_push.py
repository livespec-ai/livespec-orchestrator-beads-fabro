"""Push-time authentication for script nodes, installed beside the mint helper.

The engine's URL credential outranks every credential helper. A process-only
URL rewrite removes it without changing the clone's config. The replacement
helper reads a newly minted token from a one-use file, and never stores it.
Wrapping the command also preserves the publication lease program and each
node's existing hook policy.

A hook or gate that the pushed command starts runs as the same user as this
helper, so it can read `/proc/<pid>/environ` and `/proc/<pid>/cmdline` of every
ancestor. The helper therefore hands the App inputs over a pipe to one
replacement shell, which holds them in unexported variables and starts the
command from an environment without them. The shell that received the inputs
through its environment is gone by then, so no process between the command and
the helper's caller carries a credential in its environment or arguments.
"""

__all__: list[str] = ["PUSH_ORIGIN_SOURCE"]

PUSH_ORIGIN_SOURCE = r"""#!/usr/bin/env bash
set +x
set -eu
# The stage is the dispatcher's record for the running agent node (`<launcher pid> <stage>`, in
# the bundle root above this helper's bin/), never LIVESPEC_AGENT_STAGE, which the agent sets.
agent_stage=''
record="$(dirname "$0")/../agent-stage"
if test -e "$record"; then
    pid=''
    read -r pid agent_stage <"$record" 2>/dev/null || true
    case "$pid" in
        ''|*[!0-9]*) agent_stage=unrecorded ;;
        *) kill -0 "$pid" 2>/dev/null || agent_stage='' ;;
    esac
fi
case "$agent_stage" in
    ''|publish_draft|pr_refresh|pr) ;;
    *)
        printf 'LIVESPEC_AGENT_PUBLICATION_DENIED: stage=%s action=push_origin\n' \
            "$agent_stage" >&2
        exit 1
        ;;
esac
url=$(git remote get-url --push origin)
case "$url" in
    https://*|http://*) ;;
    *) exec "$@" ;;
esac
rest=${url#*://}
authority=${rest%%/*}
host=${authority##*@}
clean="${url%%://*}://$host/${rest#*/}"
api=${GITHUB_API_URL:-https://api.github.com}
api=${api#*://}
api=${api%%/*}
if test "$api" = api.github.com; then api=github.com; fi
if test "$host" != "$api"; then
    echo 'LIVESPEC_PUSH_AUTH_HOST: origin is not the configured GitHub host' >&2
    exit 1
fi
old_password=''
case "$authority" in
    *@*) old_user=${authority%@*}; old_password=${old_user#*:} ;;
esac
mint="$(dirname "$0")/mint_app_token.py"
# Git starts its pre-push hook after it has asked its credential helper for the
# remote's credentials.  Keep a minted token in this one-use file only until
# that helper has answered, then remove it before Git starts repository code.
#
# The shell that holds the minting inputs is not this one.  This shell replaces
# itself (exec) with a runner whose environment and arguments carry none of the
# App inputs: they reach the runner over file descriptor 3 and live only in its
# unexported variables.  A hook or gate is a descendant of the runner, and can
# read `/proc/<pid>/environ` and `/proc/<pid>/cmdline` of every ancestor, so an
# `env -u` around the pushed command alone would still leave the secrets in the
# environment of each shell above it.  The helper's configuration contains only
# the transient token path, never a credential value.
token_file=$(mktemp "${TMPDIR:-/tmp}/livespec-push-token.XXXXXX")
chmod 600 "$token_file"
# Append to inherited process config so hook policy and callers' config survive.
export GIT_CONFIG_COUNT=${GIT_CONFIG_COUNT:-0}
add_config() {
    export "GIT_CONFIG_KEY_$GIT_CONFIG_COUNT=$1"
    export "GIT_CONFIG_VALUE_$GIT_CONFIG_COUNT=$2"
    GIT_CONFIG_COUNT=$((GIT_CONFIG_COUNT + 1))
}
add_config "url.$clean.insteadOf" "$url"
add_config "credential.$clean.helper" ''
add_config "credential.$clean.helper" '!f() {
    cat >/dev/null
    if test "$1" = get; then
        token=$(cat "'"$token_file"'")
        rm -f "'"$token_file"'"
        printf "username=x-access-token\npassword=%s\n" "$token"
    fi
}; f'
add_config http.extraHeader ''
add_config "http.$clean.extraHeader" ''
read -r -d '' runner <<'RUNNER' || true
set +x
set -u
mint=$1
token_file=$2
shift 2
trap 'rm -f "$token_file"' EXIT
trap 'exit 1' HUP INT TERM
IFS= read -r -d '' app_id <&3 || true
IFS= read -r -d '' private_key <&3 || true
IFS= read -r -d '' installation_id <&3 || true
IFS= read -r -d '' old_password <&3 || true
exec 3<&-
# Keep diagnostics in memory until credentials have been removed. In particular,
# trace output or an origin error must not print URL credentials or Basic auth.
redact_output() {
    local secret encoded
    for secret in "$token" "$old_password"; do
        if test -n "$secret"; then
            output=${output//"$secret"/[redacted]}
        fi
    done
    encoded=$(printf 'x-access-token:%s' "$token" | base64 | tr -d '\n')
    output=${output//"$encoded"/[redacted]}
}
mint_token() {
    # The inputs are exported only inside this subshell, for the one mint.
    (
        export GITHUB_APP_ID="$app_id" GITHUB_PRIVATE_KEY="$private_key"
        if test -n "$installation_id"; then
            export GITHUB_APP_INSTALLATION_ID="$installation_id"
        fi
        exec python3 "$mint" 2>/dev/null
    )
}
for attempt in 1 2; do
    # A separate provider process forces a new installation-token mint each time.
    if ! token=$(mint_token) || test -z "$token"; then
        echo 'LIVESPEC_PUSH_AUTH_MINT: installation token could not be minted' >&2
        exit 1
    fi
    umask 077
    printf %s "$token" > "$token_file"
    if output=$("$@" 2>&1); then status=0; else status=$?; fi
    redact_output
    printf '%s\n' "$output"
    if test "$status" -eq 0 || test "$attempt" -eq 2; then exit "$status"; fi
    case "$output" in
        *'HTTP 401'*|*'error: 401'*|*'Authentication failed'*|*'Invalid username or token'*)
            echo 'LIVESPEC_PUSH_AUTH_RETRY: authentication refused; reminting once' >&2 ;;
        *) exit "$status" ;;
    esac
done
RUNNER
exec 3< <(printf '%s\0' "${GITHUB_APP_ID-}" "${GITHUB_PRIVATE_KEY-}" \
    "${GITHUB_APP_INSTALLATION_ID-}" "$old_password")
exec env -u GH_TOKEN -u GITHUB_TOKEN -u GITHUB_APP_ID \
    -u GITHUB_PRIVATE_KEY -u GITHUB_APP_INSTALLATION_ID \
    -u LIVESPEC_PUSH_TOKEN bash -c "$runner" bash "$mint" "$token_file" "$@"
"""
