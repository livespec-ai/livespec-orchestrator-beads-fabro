#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — report open work-items already named by origin/master.
#
# Usage: reconcile-delivered.sh <repo-dir>
#
# This is the fleet-level reconciliation complement to the per-ticket restore
# guard. It deliberately reports rather than closes: a commit can be a partial
# delivery, so the item's normal merge/acceptance path owns its disposition.
set -eu

LAUNCH_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=${1:?usage: reconcile-delivered.sh <repo-dir>}
. "$LAUNCH_DIR/config.sh"
. "$LAUNCH_DIR/launch-lib.sh"

if ! resolve_tenant_wrapper; then
  echo "REFUSED reconcile-delivered: $REPO/.livespec.jsonc credential_wrapper is unreadable" >&2
  exit 7
fi
if ! git -C "$REPO" fetch --quiet origin "+refs/heads/master:refs/remotes/origin/master"; then
  echo "REFUSED reconcile-delivered: origin/master delivery history could not be measured" >&2
  exit 7
fi

items=$(
  cd "$REPO"
  wrap -- bd list --json | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
if isinstance(payload, dict):
    for key in ("issues", "items"):
        if isinstance(payload.get(key), list):
            payload = payload[key]
            break
if not isinstance(payload, list):
    raise SystemExit("bd list --json did not return a work-item list")
for item in payload:
    if not isinstance(item, dict):
        continue
    item_id, status = item.get("id"), item.get("status")
    if isinstance(item_id, str) and isinstance(status, str):
        print(f"{item_id}\t{status}")
'
)

found=0
while IFS=$'\t' read -r item status; do
  [ -n "$item" ] || continue
  case "$status" in done|closed) continue ;; esac
  commit=$(origin_master_delivery_commit "$item" "$REPO")
  [ -n "$commit" ] || continue
  printf 'DELIVERED-OPEN item=%s status=%s commit=%s source=origin/master reason=delivery-commit-names-open-item\n' \
    "$item" "$status" "$commit"
  found=$((found + 1))
done <<< "$items"

printf 'DELIVERED-OPEN-SUMMARY count=%s\n' "$found"
