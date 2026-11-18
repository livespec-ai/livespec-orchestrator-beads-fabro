#!/usr/bin/env bash
# The seat load guard's /tmp rule is a share of the mounted tmpfs, not an absolute size: the same
# share of a 24G tmpfs (hetzner) and a 48G one (vps) must give the same verdict, and a size-blind
# 16G limit must not hold a 24G tmpfs at 16G used on a host whose memory is fine.
set -eu
TEST_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
GUARD="$TEST_DIR/../seat/load-guard.sh"
STUB=$(mktemp -d); trap 'rm -rf "$STUB"' EXIT
# Healthy host state as fixtures, so ONLY the /tmp share decides: the guard also holds on MemAvailable below 24G, memory
# pressure at 5 or above and a run queue at 54 or above, and a real runner or gate pod can trip any of them.
mkdir -p "$STUB/proc/pressure"
printf 'MemAvailable:   104857600 kB\n' > "$STUB/proc/meminfo"
printf 'some avg10=0.00 avg60=0.00 avg300=0.00 total=0\n' > "$STUB/proc/pressure/memory"
printf 'procs_running 1\n' > "$STUB/proc/stat"
printf '0.10 0.10 0.10 1/100 1\n' > "$STUB/proc/loadavg"
verdict() { # used_gb size_gb -> GO|HOLD on the /tmp rule alone
    printf '#!/bin/bash\nprintf "Used Size\\n %sG %sG\\n" %s %s\n' "$1" "$2" "$1" "$2" > "$STUB/df"
    chmod +x "$STUB/df"
    env PATH="$STUB:$PATH" LDSEAT_PROC_ROOT="$STUB/proc" LDSEAT_TMP_HOLD_PCT="$FIXTURE_SHARE" bash "$GUARD" | awk '{print $2}'
}
# A fixture share, never the committed one: the test drives the share computation, it does not pin config.
FIXTURE_SHARE=75
fail=0
check() { # used size expected
    got=$(verdict "$1" "$2")
    if [ "$got" = "$3" ]; then echo "ok   ${1}G of ${2}G -> $3"; else echo "FAIL ${1}G of ${2}G: wanted $3, got $got"; fail=1; fi
}
# The host reads are fixtures (above), so these verdicts do not depend on the machine running the test.
check 16 24 GO     # 66%: held by the old size-blind 16G limit
check 20 24 HOLD   # 83%
check 16 48 GO     # 33%
check 40 48 HOLD   # 83%: the same share holds a 48G tmpfs
exit "$fail"
