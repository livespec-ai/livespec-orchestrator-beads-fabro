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
# The strip runs INSIDE the target repository's committed credential_wrapper chain,
# never instead of it: the chain is resolved exactly as launch-lib.sh resolves it for
# an un-overridden launch (the committed argv run whole, a non-family one nested in the
# default wrapper), and the slot strip is the innermost hop. The first committed copy
# ran the bare default wrapper, so under route C (#5361: the family wrapper followed by a
# /bin/sh hop mapping GITHUB_APP_ID_ORG onto GITHUB_APP_ID) a slot-narrowed launch lost
# the hop and minted as the personal App. The live seat's with-tenant-slotstrip.sh
# (961ccb6f782b, 2026-11-15) composes the two in this order; this file matches it.
#
# The target repository is TW_REPO when set, else the current directory: every launcher
# `wrap` call runs in "$REPO".
#
# Usage: pass as WRAPPER= to dispatch-dual.sh: WRAPPER=<path>/with-livespec-env-slotnarrow.sh
set -u
FLEET_LAUNCH_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=fleet-launch/config.sh
. "$FLEET_LAUNCH_DIR/config.sh"
# launch-lib.sh reads the caller's REPO when sourced, so the target is named first.
REPO=${TW_REPO:-$PWD}
# shellcheck source=fleet-launch/launch-lib.sh
. "$FLEET_LAUNCH_DIR/launch-lib.sh"
[ "${1:-}" = "--" ] && shift
# This wrapper IS the launcher's override; beneath it the target's own committed argv is resolved.
unset WRAPPER
if ! resolve_tenant_wrapper; then
  echo "slotnarrow: the credential_wrapper of $REPO cannot be read; refusing to run the command under a guessed chain" >&2
  exit 78
fi
wrapper_chain
unset_args=()
for slot in $FLEET_LAUNCH_SLOTNARROW_EXCLUDED_SLOTS; do
  unset_args+=(-u "CLAUDE_CODE_OAUTH_TOKEN__$slot")
done
exec "${WRAP_CHAIN[@]}" bash -c '
  judge_var="CLAUDE_CODE_OAUTH_TOKEN__$1"; shift
  export CLAUDE_CODE_OAUTH_TOKEN="${!judge_var:-${CLAUDE_CODE_OAUTH_TOKEN:-}}"
  exec env "$@"' slotnarrow "$FLEET_LAUNCH_SLOTNARROW_JUDGE_SLOT" "${unset_args[@]}" "$@"
