#!/bin/bash
# resume.sh <20-digit key> <repo-dir> <item>: start tmp/petri-canary/resume-capped.sh in its own systemd scope under
# factory-dispatch.slice (dev-host-disk-retention 00:2xZ 11-14: a resumed run's dispatcher loop is one of the per-run
# loops the slice is sized for). Same shape as ticket.sh: MemoryMax from the bound file, OOMPolicy=continue (systemd 257
# defaults to stop), unscoped fallback when the slice is not loaded. Output appends to the item's seq log.
set -u; KEY=$1; REPO=$2; ITEM=$3; SEAT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$SEAT_DIR/../config.sh"; L=$FLEET_LAUNCH_STATE_DIR; ORCH=$FLEET_LAUNCH_ORCH_REPO
SCOPE=(); MM=$(cat /etc/livespec/factory-dispatch-loop-memory-max 2>/dev/null)
if [ -n "$MM" ] && [ "$(systemctl --user show factory-dispatch.slice -p LoadState --value 2>/dev/null)" = loaded ]; then
  SCOPE=(systemd-run --user --scope --quiet --slice=factory-dispatch.slice -p MemoryMax=$MM -p OOMPolicy=continue --)
fi
# dev-host-disk-retention 00:3xZ: HIGH OOM score for dispatcher loops (killed before doltdb -900 or seat sessions);
# children inherit it; no privilege needed; launch without it if choom is absent.
command -v choom >/dev/null 2>&1 && SCOPE+=(choom -n 500 --)
cd "$ORCH" || exit 2
setsid nohup "${SCOPE[@]}" bash $ORCH/fleet-launch/resume-capped.sh "$KEY" "$REPO" "$ITEM" >> $L/seq-$ITEM.log 2>&1 < /dev/null &
echo "RESUME-QUEUED $ITEM key=$KEY pid=$! scope=$([ "${SCOPE[0]:-}" = systemd-run ] && echo "factory-dispatch.slice/MemoryMax=$MM" || echo unscoped) oom=$([ -n "$(printf %s " ${SCOPE[*]:-}" | grep -o choom)" ] && echo 500 || echo default) at $(date -u +%FT%TZ)"
