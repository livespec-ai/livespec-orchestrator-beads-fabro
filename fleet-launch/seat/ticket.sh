#!/bin/bash
# ticket.sh <item> <repo-dir> <20-digit key>: one guarded gmktec ticket (seat 50a20bc8, post-reboot; coordinator load guard).
# Guard: GO -> launch. HOLD on procs_running alone -> re-read after 60 s (max 30 tries). Memory HOLD -> exit 3 (holds the wave).
set -u; ITEM=$1; REPO=$2; KEY=$3; SEAT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$SEAT_DIR/../config.sh"; L=$FLEET_LAUNCH_STATE_DIR; ORCH=$FLEET_LAUNCH_ORCH_REPO; GUARD=${SEAT_LOAD_GUARD:-$SEAT_DIR/load-guard.sh}
for t in $(seq 1 30); do
  g=$($GUARD); echo "GUARD $ITEM $g"
  # coordinator 16:5xZ: Mem < 40G holds ALL launches; procs_running_median5 >= 50 = no new launch (wait and re-read)
  m40=$(sed -n 's/.*MemAvailable=\([0-9]*\)G.*/\1/p' <<<"$g"); pr=$(sed -n 's/.*procs_running_median5=\([0-9]*\).*/\1/p' <<<"$g")
  if [ "${m40:-0}" -lt 40 ]; then echo "MEMORY-HOLD $ITEM: MemAvailable ${m40}G < 40G (coordinator rule): wave held"; exit 3; fi
  case "$g" in *" GO "*) [ "${pr:-99}" -lt 50 ] && break; echo "PROCS-WAIT $ITEM: procs_running_median5=$pr >= 50";; esac
  avail=$(sed -n 's/.*MemAvailable=\([0-9]*\)G.*/\1/p' <<<"$g"); psi=$(sed -n 's/.*avg10=\([0-9.]*\).*/\1/p' <<<"$g")
  if [ "${avail:-0}" -lt 24 ] || awk -v p="${psi:-9}" 'BEGIN{exit !(p>=5)}'; then echo "MEMORY-HOLD $ITEM: wave held"; exit 3; fi
  sleep 60
done
case "$g" in *" GO "*) [ "${pr:-99}" -lt 50 ] || { echo "PROCS never < 50 for $ITEM after 30 reads: not ticketed"; exit 4; };; *) echo "GUARD never GO for $ITEM after 30 reads"; exit 4;; esac
[ -e "$L/hold-item-$ITEM" ] && { echo "HOLD-ITEM present for $ITEM: not ticketed"; exit 5; }
EXTRA=(); [ "$(realpath -e "$REPO")" != "$(realpath -e "$ORCH")" ] && EXTRA=(REPO_OVERRIDE="$REPO"); [ -n "${EXTRA_ENV:-}" ] && EXTRA+=($EXTRA_ENV)
cd "$ORCH"
# dev-host-disk-retention 00:18Z 11-14 (#4575 applied): launch each ticket's launcher+drive+loop in its own scope under
# factory-dispatch.slice; MemoryMax from /etc/livespec/factory-dispatch-loop-memory-max; OOMPolicy=continue (systemd 257
# defaults to stop, which kills the loop when one child is OOM-killed). Unscoped fallback when the slice is not loaded.
SCOPE=(); MM=$(cat /etc/livespec/factory-dispatch-loop-memory-max 2>/dev/null)
if [ -n "$MM" ] && [ "$(systemctl --user show factory-dispatch.slice -p LoadState --value 2>/dev/null)" = loaded ]; then
  SCOPE=(systemd-run --user --scope --quiet --slice=factory-dispatch.slice -p MemoryMax=$MM -p OOMPolicy=continue --)
fi
# dev-host-disk-retention 00:3xZ: HIGH OOM score for dispatcher loops (killed before doltdb -900 or seat sessions);
# children inherit it; no privilege needed; launch without it if choom is absent.
command -v choom >/dev/null 2>&1 && SCOPE+=(choom -n 500 --)
setsid nohup env TICKET_NS=$KEY ONLY_GMK=1 MAX_WAIT_S=86400 FLEET_LAUNCH_ORCH_REPO=$ORCH FLEET_LAUNCH_SIZE_SCREEN=1 "${EXTRA[@]}" "${SCOPE[@]}" bash $ORCH/fleet-launch/dispatch-dual.sh "$ITEM" >> $L/seq-$ITEM.log 2>&1 < /dev/null &
echo "TICKETED $ITEM key=$KEY pgid=$! scope=$([ "${SCOPE[0]:-}" = systemd-run ] && echo "factory-dispatch.slice/MemoryMax=$MM" || echo unscoped) oom=$([ -n "$(printf %s " ${SCOPE[*]:-}" | grep -o choom)" ] && echo 500 || echo default) at $(date -u +%FT%TZ)"
