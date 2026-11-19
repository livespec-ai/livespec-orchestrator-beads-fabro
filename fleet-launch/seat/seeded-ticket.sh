#!/bin/bash
# PROVISIONAL / EXPERIMENTAL — fleet-launch seat seeded relaunch ticket.
# This directory is a stopgap; its first-class replacements are the livespec console
# application and the committed launch-loop tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# seeded-ticket.sh <item> <repo-dir> <full-ref> <expected-sha-prefix> <20-digit key> <reason...>: post-lift SEEDED relaunch (coordinator 3e750bae lift rules):
# origin ref check -> empty-diff check vs merge base (must be NON-empty) -> seed ruling (read back) -> release to ready -> admission auto -> ticket.
set -u; IT=$1; REPO=$2; REF=$3; SHA=$4; KEY=$5; shift 5; REASON="$*"
SEAT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$SEAT_DIR/../config.sh"; ORCH=$FLEET_LAUNCH_ORCH_REPO
W=/usr/local/bin/with-livespec-env.sh
# The installed plugin build the target repository is registered to, never a pinned build id.
PR=$(python3 "${SEAT_PLUGIN_ROOT:?set SEAT_PLUGIN_ROOT to the installed plugin root}/scripts/bin/registered_plugin_root.py" --repo "$REPO") || exit 2; P=$PR/scripts/bin
cd "$REPO" || exit 2
full=$(git ls-remote origin "$REF" | awk '{print $1}'); [ -n "$full" ] || { echo "SEED-FAIL $IT: $REF not on origin"; exit 3; }
case "$full" in $SHA*) ;; *) echo "SEED-FAIL $IT: $REF at $full, expected $SHA"; exit 3;; esac
git fetch -q origin "+$REF:refs/tmp-seed-$IT" || { echo "SEED-FAIL $IT: fetch"; exit 3; }
mb=$(git merge-base "refs/tmp-seed-$IT" origin/master); if git diff --quiet "$mb" "refs/tmp-seed-$IT"; then echo "SEED-FAIL $IT: EMPTY diff vs merge base $mb"; exit 4; fi
echo "EMPTY-DIFF-CHECK $IT: NON-empty $(git diff --shortstat "$mb" "refs/tmp-seed-$IT")"
$W -- python3 $P/dispatcher.py seed-ruling --invoker claude:legacy-dispatcher-agent --repo "$REPO" --item "$IT" --ref "$REF" --commit "$full" --reason "$REASON" 2>&1 | grep -E "^RULED|rror" | cut -c1-200
st=$($W -- bd show "$IT" --json 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);d=d[0] if isinstance(d,list) else d;print(d.get('status'),d.get('assignee'))")
case "$st" in blocked*) $W -- python3 $P/drive.py --action "resolve-blocked:$IT:ready" --repo "$REPO" --json 2>&1 | grep -E '"summary"' | cut -c1-160;; esac
$W -- python3 $P/drive.py --action "move:$IT:ready" --repo "$REPO" --json 2>&1 | grep -E '"summary"' | cut -c1-160
$W -- python3 $P/drive.py --action "set-admission:$IT:auto" --repo "$REPO" --json 2>&1 | grep -E '"summary"' | cut -c1-160
cd "$ORCH" && SEAT_SEEDED_RULING=1 bash "$SEAT_DIR/ticket.sh" "$IT" "$REPO" "$KEY" 2>&1 | tail -1
