#!/usr/bin/env bash
# Repeat the fleet-launch scenario that has intermittently hung in a factory
# sandbox.  This is deliberately a process-tree diagnostic rather than a
# wrapper around `timeout`: the evidence must be collected while the stuck
# descendants are still alive.
set -euo pipefail

readonly scenario='scenario312'
readonly harness='dev-tooling/just-check-fleet-launch.sh'
readonly poll_seconds='0.1'

usage() {
    echo "usage: diagnose-fleet-launch-hang.sh [iterations]" >&2
}

if [ "$#" -gt 1 ]; then
    usage
    exit 2
fi

iterations=${1:-20}
if ! [[ "$iterations" =~ ^[1-9][0-9]*$ ]]; then
    echo "diagnose-fleet-launch-hang: iterations must be a positive integer" >&2
    exit 2
fi

# Keep the outer diagnostic limit independent from the harness watchdog so a
# caller can shorten this probe without modifying the harness itself.  The
# normal 15 minute setting matches the harness's scenario watchdog default.
iteration_timeout_seconds=${FLEET_LAUNCH_DIAGNOSTIC_TIMEOUT_S:-${HARNESS_SCENARIO_TIMEOUT_S:-900}}
if ! [[ "$iteration_timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
    echo "diagnose-fleet-launch-hang: FLEET_LAUNCH_DIAGNOSTIC_TIMEOUT_S must be a positive integer" >&2
    exit 2
fi

if [ ! -x "$harness" ] && [ ! -f "$harness" ]; then
    echo "diagnose-fleet-launch-hang: missing harness: $harness" >&2
    exit 2
fi

now_nanoseconds() {
    date +%s%N
}

elapsed_seconds() {
    awk -v start="$1" -v end="$2" 'BEGIN { printf "%.3f", (end - start) / 1000000000 }'
}

# Emit the root followed by every currently living descendant.  Reading the
# parent relationship once per pass makes this work in the stripped-down
# factory image without requiring pstree.
iteration_processes() {
    local root=$1
    local -a known=("$root")
    local candidate parent known_process
    local changed=1

    while [ "$changed" -eq 1 ]; do
        changed=0
        while read -r candidate parent; do
            for parent in "${known[@]}"; do
                if [ "$candidate" != "$parent" ] && [ "$(ps -o ppid= -p "$candidate" 2>/dev/null | tr -d ' ')" = "$parent" ]; then
                    for known_process in "${known[@]}"; do
                        if [ "$candidate" = "$known_process" ]; then
                            continue 2
                        fi
                    done
                    known+=("$candidate")
                    changed=1
                    break
                fi
            done
        done < <(ps -eo pid=,ppid=)
    done

    printf '%s\n' "${known[@]}"
}

print_stuck_iteration() {
    local iteration=$1
    local root=$2
    local elapsed=$3
    local -a processes=()
    local process joined wchan

    mapfile -t processes < <(iteration_processes "$root")
    joined=$(IFS=,; echo "${processes[*]}")
    printf 'diagnose-fleet-launch-hang: timeout scenario=%s iteration=%s wall_seconds=%s limit_seconds=%s pid=%s\n' \
        "$scenario" "$iteration" "$elapsed" "$iteration_timeout_seconds" "$root"
    printf 'diagnose-fleet-launch-hang: process tree scenario=%s iteration=%s\n' "$scenario" "$iteration"
    ps -o pid=,ppid=,stat=,etime=,args= --forest -p "$joined" 2>&1 || true
    printf 'diagnose-fleet-launch-hang: wchan scenario=%s iteration=%s\n' "$scenario" "$iteration"
    for process in "${processes[@]}"; do
        if [ -r "/proc/$process/wchan" ]; then
            wchan=$(<"/proc/$process/wchan")
        else
            wchan='unreadable'
        fi
        printf 'pid=%s wchan=%s\n' "$process" "$wchan"
    done
}

stop_iteration() {
    local root=$1
    kill -TERM -- "-$root" 2>/dev/null || true
    sleep 1
    kill -KILL -- "-$root" 2>/dev/null || true
}

run_iteration() {
    local iteration=$1
    local start now elapsed status

    start=$(now_nanoseconds)
    # A new session lets timeout cleanup cover every ordinary child the harness
    # creates, while preserving the tree long enough to print its evidence.
    setsid bash "$harness" "$scenario" &
    iteration_pid=$!
    while kill -0 "$iteration_pid" 2>/dev/null; do
        now=$(now_nanoseconds)
        elapsed=$(elapsed_seconds "$start" "$now")
        if awk -v elapsed="$elapsed" -v limit="$iteration_timeout_seconds" 'BEGIN { exit !(elapsed >= limit) }'; then
            print_stuck_iteration "$iteration" "$iteration_pid" "$elapsed"
            stop_iteration "$iteration_pid"
            wait "$iteration_pid" || true
            printf 'diagnose-fleet-launch-hang: scenario=%s iteration=%s exit=124 wall_seconds=%s\n' \
                "$scenario" "$iteration" "$elapsed"
            return 124
        fi
        sleep "$poll_seconds"
    done

    if wait "$iteration_pid"; then
        status=0
    else
        status=$?
    fi
    now=$(now_nanoseconds)
    elapsed=$(elapsed_seconds "$start" "$now")
    printf 'diagnose-fleet-launch-hang: scenario=%s iteration=%s exit=%s wall_seconds=%s\n' \
        "$scenario" "$iteration" "$status" "$elapsed"
    return "$status"
}

overall_status=0
for ((iteration = 1; iteration <= iterations; iteration++)); do
    if run_iteration "$iteration"; then
        :
    else
        status=$?
        # A timeout is the diagnostic's terminal result: its evidence is most
        # useful immediately, and a full harness would only obscure the hang.
        if [ "$status" -eq 124 ]; then
            exit "$status"
        fi
        overall_status=$status
    fi
done

full_start=$(now_nanoseconds)
if bash "$harness"; then
    full_status=0
else
    full_status=$?
fi
full_end=$(now_nanoseconds)
full_elapsed=$(elapsed_seconds "$full_start" "$full_end")
printf 'diagnose-fleet-launch-hang: scenario=full-harness exit=%s wall_seconds=%s\n' \
    "$full_status" "$full_elapsed"

if [ "$overall_status" -ne 0 ]; then
    exit "$overall_status"
fi
exit "$full_status"
