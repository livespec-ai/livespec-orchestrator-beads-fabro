#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — fleet-launch hermetic harness script for the fleet-launch check.
# This directory is a stopgap; its first-class replacements are the livespec console
# application and the committed launch-loop tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# A repository-hold signal can arrive at any point in the launch wait loop.
# The loop must not evaluate an external clock in a command substitution at
# that point: Bash can defer or lose the pending signal trap while parsing it.

set -eu

TEST_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
LAUNCH_DIR=$(cd "$TEST_DIR/.." && pwd -P)

for launcher in dispatch-dual.sh resume-capped.sh; do
    path="$LAUNCH_DIR/$launcher"
    if grep -Eq '\$\(date \+%s\).*\$deadline' "$path"; then
        echo "$launcher evaluates its slot deadline through a command substitution" >&2
        exit 1
    fi
    if ! grep -qF '[ "$SECONDS" -lt "$wait_deadline" ]' "$path"; then
        echo "$launcher does not use the shell-native slot deadline in its wait loop" >&2
        exit 1
    fi
done
