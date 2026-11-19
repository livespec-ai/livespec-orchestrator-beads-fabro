#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — fleet-launch hermetic harness script for the fleet-launch check.
# This directory is a stopgap; its first-class replacements are the livespec console
# application and the committed launch-loop tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# The per-scenario watchdog must turn a stuck scenario into a fast, named, non-zero failure,
# and must leave a scenario that finishes in time alone.

set -u

TEST_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

mini_harness() {
    local body=$1
    cat > "$WORK/mini.sh" <<MINI
#!/usr/bin/env bash
set -u
WORK="$WORK"
. "$TEST_DIR/scenario-watchdog.sh"
cleanup() { scenario_watchdog_stop; }
trap cleanup EXIT
scenario_watchdog_start "\$WORK"
$body
MINI
}

fail=0

# A stuck scenario is killed within a few ticks and named.
mini_harness 'scenario "1. fine"; scenario "2. the stuck one"; sleep 120; echo reached-the-end'
start=$SECONDS
out=$(HARNESS_SCENARIO_TIMEOUT_S=2 HARNESS_WATCHDOG_TICK_S=1 timeout 60 bash "$WORK/mini.sh" 2>&1)
rc=$?
elapsed=$((SECONDS - start))
if [ "$rc" -eq 0 ]; then echo "FAIL: a stuck scenario exited 0" >&2; fail=1; fi
case "$out" in *'2. the stuck one'*) ;; *) echo "FAIL: the stuck scenario was not named: $out" >&2; fail=1 ;; esac
case "$out" in *reached-the-end*) echo "FAIL: the stuck scenario ran to its end" >&2; fail=1 ;; esac
if [ "$elapsed" -gt 20 ]; then echo "FAIL: the watchdog took ${elapsed}s to fire" >&2; fail=1; fi

# A watchdog timeout during a repeated scenario names the attempt that was in
# progress, so a killed Scenario 10b run can be diagnosed without its log.
mini_harness 'scenario "10b. a queued launcher counts a held direct release as in flight"; scenario_attempt 17; sleep 120'
out=$(HARNESS_SCENARIO_TIMEOUT_S=2 HARNESS_WATCHDOG_TICK_S=1 timeout 60 bash "$WORK/mini.sh" 2>&1)
rc=$?
if [ "$rc" -eq 0 ]; then echo "FAIL: an attempted scenario timeout exited 0" >&2; fail=1; fi
case "$out" in *'attempt 17'*) ;; *) echo "FAIL: the watchdog timeout did not name the active attempt: $out" >&2; fail=1 ;; esac

# Control: scenarios that each finish inside the limit pass untouched, even when the whole
# run is longer than one limit.
mini_harness 'scenario "1. a"; sleep 1; scenario "2. b"; sleep 1; scenario "3. c"; sleep 1; echo reached-the-end'
out=$(HARNESS_SCENARIO_TIMEOUT_S=2 HARNESS_WATCHDOG_TICK_S=1 timeout 60 bash "$WORK/mini.sh" 2>&1)
rc=$?
if [ "$rc" -ne 0 ]; then echo "FAIL: a healthy run exited $rc: $out" >&2; fail=1; fi
case "$out" in *reached-the-end*) ;; *) echo "FAIL: the healthy run did not finish: $out" >&2; fail=1 ;; esac

[ "$fail" -eq 0 ] && echo "test-scenario-watchdog: ok"
exit "$fail"
