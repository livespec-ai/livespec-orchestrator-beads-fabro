#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — part of fleet-launch/, a stopgap whose first-class
# replacements are the livespec console application and the committed launch-loop
# tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# parent-of.sh <item-id>: print the id of the item's parent (its native parent field, else its
# parent-child edge), or nothing for an item with no parent. Exit 0 either way; exit 1 when the item
# cannot be read. Run it in the tenant repository, under the tenant's credential wrapper: the
# launcher walks a queued item's parent chain with it to find the owning plan (config.sh,
# FLEET_LAUNCH_PARENT_CHAIN_COMMAND).
set -u
item=${1:?usage: parent-of.sh <item-id>}
out=$(bd show "$item" --json 2>/dev/null) || exit 1
printf '%s' "$out" | python3 -c '
import json, sys

data = json.load(sys.stdin)
record = data[0] if isinstance(data, list) and data else data
if not isinstance(record, dict):
    sys.exit(1)
parent = record.get("parent_id") or record.get("parent")
if isinstance(parent, dict):
    parent = parent.get("id")
if not parent:
    # `bd show` rows key the target `id` with the edge in `dependency_type`; `bd list` rows key it
    # `depends_on_id` with the edge in `type`.
    for row in record.get("dependencies") or []:
        if not isinstance(row, dict):
            continue
        if (row.get("dependency_type") or row.get("type")) == "parent-child":
            parent = row.get("depends_on_id") or row.get("id")
            break
if parent:
    print(parent)
'
