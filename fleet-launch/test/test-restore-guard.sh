#!/usr/bin/env bash
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
git -C "$T/repo" -c user.email=t@t -c user.name=t commit -q --allow-empty -m "fix: deliver bd-ib-x"
delivering_commit=$(git -C "$T/repo" rev-parse HEAD)
git -C "$T/repo" push -q origin HEAD:refs/heads/master
run 6 "a delivered origin/master commit is refused" STUB_PRS= --
case "$LAST" in *"$delivering_commit"*origin/master*) echo "ok   the refusal names the delivering commit and origin/master reason";; *) echo "FAIL delivered-commit refusal text: $LAST"; fail=1;; esac
run 6 "an open factory PR is refused" STUB_PRS=5527 --
case "$LAST" in *seeded-ticket.sh*restore\ rider*) echo "ok   the refusal names seeded-ticket.sh with the restore rider";; *) echo "FAIL refusal text: $LAST"; fail=1;; esac
git -C "$T/repo" push -q origin HEAD:refs/livespec/preserved-publish/bd-ib-x/abc123
run 6 "a preserved-publish ref is refused" STUB_PRS= --
run 0 "an explicit --fresh reason bypasses" STUB_PRS=5527 -- --fresh "measured: nothing worth restoring"
case "$LAST" in *bypassed*) echo "ok   the bypass is announced";; *) echo "FAIL bypass text: $LAST"; fail=1;; esac
run 2 "--fresh without a reason is refused" STUB_PRS=5527 -- --fresh
run 0 "a seeded ruling passes" STUB_PRS=5527 SEAT_SEEDED_RULING=1 --
git -C "$T/repo" push -q origin :refs/livespec/preserved-publish/bd-ib-x/abc123
run 7 "an unreadable PR list is never read as clear" STUB_GH_FAIL=1 --
exit "$fail"
