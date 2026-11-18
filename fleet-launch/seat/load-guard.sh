#!/bin/bash
# Load-guard reading for the dispatching host (originally measured on the vps, legacy-coordinator-agent, 2026-11-13 after the 15:53Z reboot).
# Memory decides: the 2026-11-13 overload was memory exhaustion (kbmemfree ~450 MB, %commit 105%, 126 blocked).
# CPU contention is the MEDIAN of 5 procs_running samples 1 s apart, so a burst of seats waking does not read as HOLD.
avail=$(awk '/MemAvailable/{printf "%d", $2/1048576}' /proc/meminfo)
psi=$(awk '/^some/{split($2,a,"="); print a[2]}' /proc/pressure/memory)
samples=""
for i in 1 2 3 4 5; do samples="$samples $(awk '/procs_running/{print $2}' /proc/stat)"; [ "$i" -lt 5 ] && sleep 1; done
run=$(echo $samples | tr ' ' '\n' | sort -n | sed -n 3p)
tmp=$(df --output=used -BG /tmp | tail -1 | tr -dc 0-9)
load=$(cut -d' ' -f1 /proc/loadavg)
ok=GO
[ "$avail" -lt 24 ] && ok=HOLD
awk -v p="$psi" 'BEGIN{exit !(p>=5)}' && ok=HOLD
[ "$run" -ge 54 ] && ok=HOLD
[ "$tmp" -ge 16 ] && ok=HOLD
echo "$(date -u +%H:%M:%SZ) $ok MemAvailable=${avail}G mem_psi_some_avg10=${psi} procs_running_median5=${run} tmp_used=${tmp}G load1=${load}"
[ "$ok" = GO ] || exit 1
