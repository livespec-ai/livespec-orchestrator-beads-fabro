#!/usr/bin/env bash
# The seat load guard's /tmp rule is a share of the mounted tmpfs, not an absolute size: the same
# share of a 24G tmpfs (hetzner) and a 48G one (vps) must give the same verdict, and a size-blind
# 16G limit must not hold a 24G tmpfs at 16G used on a host whose memory is fine.
set -eu
TEST_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
GUARD="$TEST_DIR/../seat/load-guard.sh"
STUB=$(mktemp -d); trap 'rm -rf "$STUB"' EXIT
verdict() { # used_gb size_gb -> GO|HOLD on the /tmp rule alone
    printf '#!/bin/bash\nprintf "Used Size\\n %sG %sG\\n" %s %s\n' "$1" "$2" "$1" "$2" > "$STUB/df"
    chmod +x "$STUB/df"
    PATH="$STUB:$PATH" LDSEAT_TMP_HOLD_PCT= bash "$GUARD" | awk '{print $2}'
}
fail=0
check() { # used size expected
    got=$(verdict "$1" "$2")
    if [ "$got" = "$3" ]; then echo "ok   ${1}G of ${2}G -> $3"; else echo "FAIL ${1}G of ${2}G: wanted $3, got $got"; fail=1; fi
}
# These cases assume the host's memory and run queue are healthy, as the guard reads them live.
check 16 24 GO     # 66%: the hetzner reading that the old fixed 16G limit held
check 20 24 HOLD   # 83%
check 16 48 GO     # 33%
check 40 48 HOLD   # 83%: the same share holds a 48G tmpfs
exit "$fail"
