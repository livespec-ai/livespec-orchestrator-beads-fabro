#!/bin/bash
# PROVISIONAL / EXPERIMENTAL — fleet-launch seat helper that adds an item to the launch freeze allowlist.
# This directory is a stopgap; its first-class replacements are the livespec console
# application and the committed launch-loop tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# allowlist-add.sh <item>: add ONE one-shot freeze-allowlist line (consumed by the launcher at LAUNCH) under the shared lock.
# Seat helper (legacy-dispatcher-agent [0edd4c], 2026-11-15; scoped STOP-AT-SECOND hold: only LIFTED-repo items may be listed).
set -u; IT=$1; SEAT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$SEAT_DIR/../config.sh"; O=$FLEET_LAUNCH_STATE_DIR
( flock -w 30 9 || exit 3; grep -qxF "$IT" "$O/freeze-allowlist" 2>/dev/null || echo "$IT" >> "$O/freeze-allowlist"; echo "ALLOWLISTED $IT $(date -u +%T)" ) 9>"$O/freeze-allowlist.lock"
