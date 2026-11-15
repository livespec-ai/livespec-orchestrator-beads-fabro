#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — part of fleet-launch/, a stopgap whose first-class
# replacements are the livespec console application and the committed launch-loop
# tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# Narrows the Claude credential pool a FAMILY-tenant launch runs under. Admission's
# pool is every non-empty CLAUDE_CODE_OAUTH_TOKEN__<slot> in the dispatcher's
# environment, and no sanctioned per-slot exclusion exists, so this wrapper removes
# the slots named in FLEET_LAUNCH_SLOTNARROW_EXCLUDED_SLOTS from that environment,
# and points the unnumbered CLAUDE_CODE_OAUTH_TOKEN at FLEET_LAUNCH_SLOTNARROW_JUDGE_SLOT
# so the host-side Definition-of-Done judges (which fall back to the unnumbered
# token when no admission-chosen slot is injected) keep a credential. An INTERIM,
# recorded, reversible operator setting (legacy-coordinator-agent ruling, 2026-11-14,
# widened 2026-11-15); the root fix is an admission weekly-percent floor key. Slot
# names only are read here; no credential value is ever printed.
#
# Usage: pass as WRAPPER= to dispatch-dual.sh: WRAPPER=<path>/with-livespec-env-slotnarrow.sh
set -u
FLEET_LAUNCH_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=fleet-launch/config.sh
. "$FLEET_LAUNCH_DIR/config.sh"
[ "${1:-}" = "--" ] && shift
unset_args=()
for slot in $FLEET_LAUNCH_SLOTNARROW_EXCLUDED_SLOTS; do
  unset_args+=(-u "CLAUDE_CODE_OAUTH_TOKEN__$slot")
done
exec "$FLEET_LAUNCH_DEFAULT_WRAPPER" -- bash -c '
  judge_var="CLAUDE_CODE_OAUTH_TOKEN__$1"; shift
  export CLAUDE_CODE_OAUTH_TOKEN="${!judge_var:-${CLAUDE_CODE_OAUTH_TOKEN:-}}"
  exec env "$@"' slotnarrow "$FLEET_LAUNCH_SLOTNARROW_JUDGE_SLOT" "${unset_args[@]}" "$@"
