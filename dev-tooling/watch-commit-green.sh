#!/usr/bin/env bash
#
# Run commit_green while retaining enough evidence to distinguish an idle hook
# from a slow one.  The record is deliberately git-local: it survives an
# amend, but a diagnostic run cannot accidentally add megabytes of samples to
# the commit it is observing.
#
# Usage: dev-tooling/watch-commit-green.sh [commit_green command [args...]]
#
# With no command, use the materialized command node program in this sandbox.
# Set WATCH_COMMIT_GREEN_RECORD to retain the record somewhere else.

set -euo pipefail

readonly MAX_WALL_SECONDS=2700
readonly MAX_STALLED_SECONDS=900
readonly SAMPLE_SECONDS=60

git_dir="$(git rev-parse --git-dir)"
record="${WATCH_COMMIT_GREEN_RECORD:-$git_dir/livespec-commit-green-watch.log}"
hook_output="$git_dir/livespec-commit-green-output"
child_output="$git_dir/livespec-commit-green-watch-child-output"
mkdir -p "$(dirname "$record")"
: > "$record"
: > "$child_output"
# The command node redirects its hook (and therefore pytest) output here.  A
# previous observation must not look like fresh progress in the first sample.
: > "$hook_output"

if (( $# == 0 )); then
    : "${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:=$HOME/.claude/plugins}"
    set -- "$LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT/livespec-commit-green.sh"
fi

started="$(date +%s)"
last_growth="$started"
last_size=0
ended_by="completed"

# A separate process group lets the timeout end the command and everything its
# hook spawned, without killing the watcher before it writes the last sample.
setsid "$@" >"$child_output" 2>&1 &
child_pid=$!

descendants() {
    local frontier="$1"
    local next=""
    local known=" $1 "
    local pid=""
    local ppid=""
    while [[ -n "$frontier" ]]; do
        next=""
        while read -r pid ppid; do
            [[ " $frontier " == *" $ppid "* ]] || continue
            [[ " $known " == *" $pid "* ]] && continue
            known+="$pid "
            next+="${next:+ }$pid"
        done < <(ps -eo pid=,ppid=)
        frontier="$next"
    done
    printf '%s\n' "${known# }"
}

sample() {
    local now="$1"
    local elapsed=$((now - started))
    local output_size=0
    local pids=""
    local pid_list=""
    if [[ -f "$hook_output" ]]; then
        output_size="$(wc -c < "$hook_output")"
    fi
    if (( output_size > last_size )); then
        last_size="$output_size"
        last_growth="$now"
    fi
    pids="$(descendants "$child_pid")"
    pids="${pids% }"
    pid_list="${pids// /,}"
    {
        printf '\n=== sample utc=%s elapsed_seconds=%s output_size=%s seconds_without_output_growth=%s ===\n' \
            "$(date -u +%FT%TZ)" "$elapsed" "$output_size" "$((now - last_growth))"
        printf '%s\n' '-- process tree (ps -eo pid,ppid,stat,wchan,etime,args) --'
        # Keep the literal command here: it makes a record independently
        # inspectable and includes wait channels (wchan) for lock/socket waits.
        ps -eo pid,ppid,stat,wchan,etime,args | awk -v wanted=" $pids " \
            'NR == 1 { print; next } index(wanted, " " $1 " ") { print }'
        printf '%s\n' '-- open locks and sockets (lsof) --'
        if command -v lsof >/dev/null 2>&1 && [[ -n "$pid_list" ]]; then
            lsof -nP -p "$pid_list" 2>&1 || true
        else
            printf '%s\n' 'lsof unavailable or observed process exited before sampling'
        fi
        if command -v lslocks >/dev/null 2>&1 && [[ -n "$pids" ]]; then
            printf '%s\n' '-- held locks (lslocks) --'
            for pid in $pids; do
                lslocks -p "$pid" 2>&1 || true
            done
        fi
    } >> "$record"
}

while kill -0 "$child_pid" 2>/dev/null; do
    now="$(date +%s)"
    sample "$now"
    if (( now - started >= MAX_WALL_SECONDS )); then
        ended_by="wall-time limit (${MAX_WALL_SECONDS}s)"
        kill -- "-$child_pid" 2>/dev/null || true
        break
    fi
    if (( now - last_growth >= MAX_STALLED_SECONDS )); then
        ended_by="no-output-growth limit (${MAX_STALLED_SECONDS}s)"
        kill -- "-$child_pid" 2>/dev/null || true
        break
    fi
    sleep "$SAMPLE_SECONDS"
done

set +e
wait "$child_pid"
child_status=$?
set -e
sample "$(date +%s)"
printf '\nobservation ended: %s; command exit status: %s; record: %s; pytest output: %s\n' \
    "$ended_by" "$child_status" "$record" "$hook_output" >> "$record"
cat "$record"

if [[ "$ended_by" != completed ]]; then
    exit 124
fi
exit "$child_status"
