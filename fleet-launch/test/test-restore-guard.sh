#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — fleet-launch hermetic harness script for the fleet-launch check.
# This directory is a stopgap; its first-class replacements are the livespec console
# application and the committed launch-loop tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# The seat restore guard refuses a PLAIN ticket for an item whose earlier work still exists (an open factory PR on
# feat/<item>, or a preserved-publish ref), because a plain ticket routes fresh and the reclaim closes that PR
# (2026-11-18, bd-ib-xbw2yk). Hermetic: a local bare repo is the origin and `gh` is a stub on PATH.
set -u
TEST_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
GUARD="$TEST_DIR/../seat/restore-guard.sh"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
git init -q --bare "$T/origin.git"
git init -q "$T/repo"; git -C "$T/repo" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
git -C "$T/repo" remote add origin "$T/origin.git"; git -C "$T/repo" push -q origin HEAD:refs/heads/master
mkdir "$T/bin"
cat > "$T/bin/gh" <<'STUB'
#!/bin/bash
[ "${STUB_GH_FAIL:-}" = 1 ] && exit 1
printf '%s' "${STUB_PRS:-}"
STUB
chmod +x "$T/bin/gh"
fail=0
run() { # expected_rc, label, env..., -- args...
    want=$1; label=$2; shift 2; envs=(); while [ "$1" != -- ]; do envs+=("$1"); shift; done; shift
    out=$(env PATH="$T/bin:$PATH" "${envs[@]}" bash "$GUARD" bd-ib-x "$T/repo" "$@" 2>&1); rc=$?
    if [ "$rc" = "$want" ]; then echo "ok   $label (rc=$rc)"; else echo "FAIL $label: wanted rc=$want got $rc: $out"; fail=1; fi
    LAST=$out
}
run 0 "no PR and no preserved ref passes" STUB_PRS= --
run 6 "an open factory PR is refused" STUB_PRS=5527 --
case "$LAST" in *seeded-ticket.sh*restore\ rider*) echo "ok   the refusal names seeded-ticket.sh with the restore rider";; *) echo "FAIL refusal text: $LAST"; fail=1;; esac
git -C "$T/repo" push -q origin HEAD:refs/livespec/preserved-publish/bd-ib-x/abc123
run 6 "a preserved-publish ref is refused" STUB_PRS= --
cat > "$T/ruler-ok" <<'RULER'
#!/bin/bash
printf '%s|%s|%s\n' "$1" "$2" "$3" >> "$RULER_LOG"; echo "FRESH-RULING  $1  by stub at now"
RULER
printf '#!/bin/bash\necho "boom" >&2; exit 1\n' > "$T/ruler-fail"; chmod +x "$T/ruler-ok" "$T/ruler-fail"
export RULER_LOG="$T/ruler.log"
run 0 "an explicit --fresh reason bypasses" STUB_PRS=5527 SEAT_FRESH_RULING_CMD="$T/ruler-ok" -- --fresh "measured: nothing worth restoring"
case "$LAST" in *bypassed*) echo "ok   the bypass is announced";; *) echo "FAIL bypass text: $LAST"; fail=1;; esac
[ "$(cat "$RULER_LOG")" = "bd-ib-x|$T/repo|measured: nothing worth restoring" ] && echo "ok   --fresh wrote the ruling naming the item and the reason" || { echo "FAIL ruling log: $(cat "$RULER_LOG")"; fail=1; }
: > "$RULER_LOG"
run 0 "--fresh records the ruling even when no earlier work exists" STUB_PRS= SEAT_FRESH_RULING_CMD="$T/ruler-ok" -- --fresh "reason two"
[ -s "$RULER_LOG" ] && echo "ok   the ruling is written with no PR and no preserved ref" || { echo "FAIL no ruling written on a clear item"; fail=1; }
run 8 "a failed ruling write refuses and names the failure" STUB_PRS=5527 SEAT_FRESH_RULING_CMD="$T/ruler-fail" -- --fresh "reason three"
case "$LAST" in *"ruling write failed"*boom*) echo "ok   the refusal names the failed write";; *) echo "FAIL refusal text: $LAST"; fail=1;; esac
# The unseamed writer path: a resolver that prints a notice on STDERR must still yield a clean plugin root.
mkdir -p "$T/plugin/scripts/bin"
cat > "$T/plugin/scripts/bin/registered_plugin_root.py" <<'RESOLVER'
import sys
sys.stderr.write("livespec: required credential env absent; re-invoking under credential_wrapper\n")
print(__file__.rsplit("/scripts/bin/", 1)[0])
RESOLVER
cat > "$T/plugin/scripts/bin/dispatcher.py" <<'DISPATCHER'
import sys
print("FRESH-RULING  " + sys.argv[sys.argv.index("--item") + 1] + "  by stub at now")
DISPATCHER
printf '#!/bin/bash\nshift\nexec "$@"\n' > "$T/wrapper"; chmod +x "$T/wrapper"
run 0 "a resolver notice on stderr does not corrupt the plugin root" STUB_PRS= SEAT_PLUGIN_ROOT="$T/plugin" SEAT_ENV_WRAPPER="$T/wrapper" -- --fresh "reason four"
case "$LAST" in *"fresh ruling recorded"*) echo "ok   the unseamed writer recorded the ruling";; *) echo "FAIL unseamed writer: $LAST"; fail=1;; esac
run 8 "an unresolvable plugin root refuses and names it" STUB_PRS= SEAT_PLUGIN_ROOT="$T/nonexistent" -- --fresh "reason five"
case "$LAST" in *"could not resolve the plugin root"*) echo "ok   the refusal names the unresolved root";; *) echo "FAIL root refusal: $LAST"; fail=1;; esac
run 2 "--fresh without a reason is refused" STUB_PRS=5527 -- --fresh
run 0 "a seeded ruling passes" STUB_PRS=5527 SEAT_SEEDED_RULING=1 --
git -C "$T/repo" push -q origin :refs/livespec/preserved-publish/bd-ib-x/abc123
run 7 "an unreadable PR list is never read as clear" STUB_GH_FAIL=1 --
exit "$fail"
