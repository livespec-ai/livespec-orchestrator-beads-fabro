#!/bin/bash
# PROVISIONAL / EXPERIMENTAL — fleet-launch seat load guard read before each ticket.
# This directory is a stopgap; its first-class replacements are the livespec console
# application and the committed launch-loop tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# Load-guard reading for the dispatching host (originally measured on the vps, legacy-coordinator-agent, 2026-11-13 after the 15:53Z reboot).
# Memory decides: the 2026-11-13 overload was memory exhaustion (kbmemfree ~450 MB, %commit 105%, 126 blocked).
# CPU contention is the MEDIAN of 5 procs_running samples 1 s apart, so a burst of seats waking does not read as HOLD.
# The /tmp limit is a share of the mounted tmpfs, from fleet-launch/config.sh (LDSEAT_TMP_HOLD_PCT).
if [ -z "${LDSEAT_TMP_HOLD_PCT:-}" ]; then
  # shellcheck source=fleet-launch/config.sh
  . "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../config.sh"
fi
# The live host reads come from LDSEAT_PROC_ROOT (default /proc); only the hermetic test points it elsewhere.
PROC=${LDSEAT_PROC_ROOT:-/proc}
avail=$(awk '/MemAvailable/{printf "%d", $2/1048576}' "$PROC/meminfo")
psi=$(awk '/^some/{split($2,a,"="); print a[2]}' "$PROC/pressure/memory")
samples=""
for i in 1 2 3 4 5; do samples="$samples $(awk '/procs_running/{print $2}' "$PROC/stat")"; [ "$i" -lt 5 ] && sleep 1; done
run=$(echo $samples | tr ' ' '\n' | sort -n | sed -n 3p)
read -r tmp tmp_size < <(df --output=used,size -BG /tmp | tail -1 | tr -dc '0-9 ')
tmp_pct=$(( tmp * 100 / (tmp_size > 0 ? tmp_size : 1) ))
load=$(cut -d' ' -f1 "$PROC/loadavg")
ok=GO
[ "$avail" -lt 24 ] && ok=HOLD
awk -v p="$psi" 'BEGIN{exit !(p>=5)}' && ok=HOLD
[ "$run" -ge 54 ] && ok=HOLD
[ "$tmp_pct" -ge "$LDSEAT_TMP_HOLD_PCT" ] && ok=HOLD
echo "$(date -u +%H:%M:%SZ) $ok MemAvailable=${avail}G mem_psi_some_avg10=${psi} procs_running_median5=${run} tmp_used=${tmp}G/${tmp_size}G(${tmp_pct}%) load1=${load}"
[ "$ok" = GO ] || exit 1
