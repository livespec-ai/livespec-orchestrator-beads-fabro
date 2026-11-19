#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — fleet-launch hermetic harness script for the fleet-launch check.
# This directory is a stopgap; its first-class replacements are the livespec console
# application and the committed launch-loop tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# Per-scenario watchdog for the hermetic fleet-launch harness (sourced by run-tests.sh).
#
# WHY. check-fleet-launch runs the harness inside the commit gate with no bound on any one
# scenario. A scenario that spins or hangs (2026-11-17: resume-capped.sh bd-ib-term in state R
# for 1h37m inside a factory run's Red commit) therefore stalls the whole gate with no verdict
# and no name for the stuck scenario. This watchdog fails the run fast and names the scenario.
#
# USE. Call `scenario "<label>"` where the harness used to `echo "--- <label>"`; it stamps the
# scenario's start time. Call `scenario_watchdog_start "$WORK"` once, after WORK exists, and
# `scenario_watchdog_stop` from the harness cleanup. When one scenario runs longer than
# HARNESS_SCENARIO_TIMEOUT_S (default 900) the watchdog prints one FAIL line naming it, kills
# the harness's descendant tree and then the harness itself, so the exit status is non-zero.

SCENARIO_TIMEOUT_S=${HARNESS_SCENARIO_TIMEOUT_S:-900}
SCENARIO_WATCHDOG_PID=""
SCENARIO_STATE_FILE=""
SCENARIO_STARTED=""
SCENARIO_LABEL=""
SCENARIO_ATTEMPT=""

_scenario_now() { printf '%(%s)T' -1; }

_scenario_write_state() {
    [ -n "$SCENARIO_STATE_FILE" ] || return 0
    printf '%s\t%s\t%s\n' "$SCENARIO_STARTED" "$SCENARIO_LABEL" "$SCENARIO_ATTEMPT" \
        > "$SCENARIO_STATE_FILE.tmp" \
        && mv -f "$SCENARIO_STATE_FILE.tmp" "$SCENARIO_STATE_FILE"
}

scenario() {
    echo "--- $1"
    SCENARIO_STARTED=$(_scenario_now)
    SCENARIO_LABEL=$1
    SCENARIO_ATTEMPT=""
    _scenario_write_state
}

# scenario_attempt <number>: record the currently executing repeated-case
# attempt without resetting the scenario watchdog's elapsed time.
scenario_attempt() {
    SCENARIO_ATTEMPT=$1
    _scenario_write_state
}

_scenario_kill_tree() {
    local parent=$1 child
    for child in $(pgrep -P "$parent" 2>/dev/null); do
        _scenario_kill_tree "$child"
    done
    kill -KILL "$parent" 2>/dev/null || true
}

scenario_watchdog_start() {
    SCENARIO_STATE_FILE="$1/scenario-current"
    printf '%s\t%s\n' "$(_scenario_now)" "(before the first scenario)" > "$SCENARIO_STATE_FILE"
    local harness_pid=$$
    (
        while sleep "${HARNESS_WATCHDOG_TICK_S:-2}"; do
            kill -0 "$harness_pid" 2>/dev/null || exit 0
            IFS=$'\t' read -r started label attempt < "$SCENARIO_STATE_FILE" || continue
            [ -n "$started" ] || continue
            if [ $(( $(_scenario_now) - started )) -gt "$SCENARIO_TIMEOUT_S" ]; then
                if [ -n "$attempt" ]; then
                    printf '  FAIL: scenario "%s" attempt %s ran longer than %ss; the harness is killed so a stuck scenario cannot stall the gate\n' \
                        "$label" "$attempt" "$SCENARIO_TIMEOUT_S" >&2
                else
                    printf '  FAIL: scenario "%s" ran longer than %ss; the harness is killed so a stuck scenario cannot stall the gate\n' \
                        "$label" "$SCENARIO_TIMEOUT_S" >&2
                fi
                for child in $(pgrep -P "$harness_pid" 2>/dev/null); do
                    [ "$child" = "$BASHPID" ] || _scenario_kill_tree "$child"
                done
                kill -TERM "$harness_pid" 2>/dev/null || true
                exit 0
            fi
        done
    ) &
    SCENARIO_WATCHDOG_PID=$!
}

scenario_watchdog_stop() {
    if [ -n "$SCENARIO_WATCHDOG_PID" ]; then
        kill "$SCENARIO_WATCHDOG_PID" 2>/dev/null || true
        wait "$SCENARIO_WATCHDOG_PID" 2>/dev/null || true
        SCENARIO_WATCHDOG_PID=""
    fi
}
