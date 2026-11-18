#!/usr/bin/env bash
# `--redeliver` bypasses the delivery screen only after its reason is durable.
set -eu
TEST_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
TICKET="$TEST_DIR/../seat/ticket.sh"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
git init -q --bare "$T/origin.git"
git init -q "$T/repo"
git -C "$T/repo" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
git -C "$T/repo" remote add origin "$T/origin.git"
git -C "$T/repo" push -q origin HEAD:refs/heads/master
git -C "$T/repo" -c user.email=t@t -c user.name=t commit -q --allow-empty -m 'fix: deliver bd-ib-redeliver'
git -C "$T/repo" push -q origin HEAD:refs/heads/master
mkdir "$T/bin"
cat > "$T/bin/gh" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
cat > "$T/bin/python3" <<'STUB'
#!/usr/bin/env bash
case "$1" in
  */ledger-item.py) printf '%s\n' "$6" > "$REDELIVER_COMMENT" ;;
  *) printf '%s\n' "$FAKE_PLUGIN" ;;
esac
STUB
cat > "$T/wrapper" <<'STUB'
#!/usr/bin/env bash
[ "$1" = -- ] && shift
exec "$@"
STUB
cat > "$T/load-guard" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' 'GUARD MemAvailable=0G procs_running_median5=0'
STUB
chmod +x "$T/bin/gh" "$T/bin/python3" "$T/wrapper" "$T/load-guard"
set +e
out=$(env PATH="$T/bin:$PATH" WRAPPER="$T/wrapper" SEAT_LOAD_GUARD="$T/load-guard" \
  REDELIVER_COMMENT="$T/comment" FAKE_PLUGIN="$T/plugin" \
  bash "$TICKET" bd-ib-redeliver "$T/repo" 01234567890123456789 --redeliver 'remaining byte bound' 2>&1)
rc=$?
set -e
[ "$rc" = 3 ] || { echo "FAIL redelivery did not reach the post-screen load guard (rc=$rc): $out" >&2; exit 1; }
case "$(cat "$T/comment")" in
  *'reason: remaining byte bound'*'partial delivery'*) ;;
  *) echo "FAIL redelivery reason was not recorded: $(cat "$T/comment")" >&2; exit 1 ;;
esac
case "$out" in *'REDELIVER bd-ib-redeliver: recorded reason: remaining byte bound'*) ;; *) echo "FAIL redelivery was not announced: $out" >&2; exit 1 ;; esac
echo "ok   redelivery records its reason before continuing past the delivery screen"
