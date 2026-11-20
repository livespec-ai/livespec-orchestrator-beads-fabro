#!/bin/bash
# PROVISIONAL / EXPERIMENTAL — fleet-launch seat guard that refuses a plain ticket for an item whose earlier work exists.
# This directory is a stopgap; its first-class replacements are the livespec console
# application and the committed launch-loop tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# restore-guard.sh <item> <repo-dir> [--fresh|--redeliver <reason>]: refuse a PLAIN ticket for an item whose earlier work still exists.
# A plain ticket routes the run FRESH, and the fresh run's publish-branch reclaim closes the item's open pull request and
# deletes its branch (measured 2026-11-18, bd-ib-xbw2yk, #5527). Work that exists is restored through seeded-ticket.sh with
# the restore rider, never rebuilt. This check is the mechanical form of that rule (coordinator Rule G).
# Refuses (exit 6) when, on the repository's origin, the item has an open factory pull request (head feat/<item>), a
# refs/livespec/preserved-publish/<item>/* ref, or a commit on origin/master that names the item in its message. Exit 7
# when any of those facts could not be measured (never read as clear). A delivery commit is a refusal rather than proof that
# the item is complete: partial deliveries must be explicitly redelivered with their remaining reason recorded in the ledger.
# Passes (exit 0) when neither exists, when SEAT_SEEDED_RULING=1 (seeded-ticket.sh sets it after its seed ruling read-back),
# or when the caller names an explicit `--fresh <reason>` or `--redeliver <reason>`. An explicit `--fresh <reason>` ALSO records the ruling: it writes
# the livespec-fresh-ruling comment through `dispatcher.py fresh-ruling` BEFORE the guard reads anything, so recovery routing
# reads the item's route as fresh instead of seeding it from a preserved work-in-progress ref (bd-ib-2yibku, measured on
# bd-ib-qjdiwl run 01M7RWJ8751N). When that write fails it refuses (exit 8) and the ticket launches nothing; SEAT_FRESH_RULING_CMD
# replaces the writer and SEAT_ENV_WRAPPER the credential wrapper for a hermetic test. Needs-human refs are named by dispatch id, not item, so they are
# not matched here; the preserved-publish ref and the open pull request are what a reclaim destroys.
set -u
ITEM=${1:?usage: restore-guard.sh <item> <repo-dir> [--fresh|--redeliver <reason>]}; REPO=${2:?repo-dir}; shift 2
LAUNCH_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$LAUNCH_DIR/config.sh"
. "$LAUNCH_DIR/launch-lib.sh"
FRESH=""
REDELIVER=""
case "${1:-}" in
  --fresh) FRESH=${2:-}; [ -n "$FRESH" ] || { echo "REFUSED $ITEM: --fresh needs a reason" >&2; exit 2; } ;;
  --redeliver) REDELIVER=${2:-}; [ -n "$REDELIVER" ] || { echo "REFUSED $ITEM: --redeliver needs a reason" >&2; exit 2; } ;;
  "") ;;
  *) echo "REFUSED $ITEM: unknown restore-guard option $1" >&2; exit 2 ;;
esac
[ "${SEAT_SEEDED_RULING:-}" = 1 ] && exit 0
if [ -n "$FRESH" ]; then
  if [ -n "${SEAT_FRESH_RULING_CMD:-}" ]; then ruled=$($SEAT_FRESH_RULING_CMD "$ITEM" "$REPO" "$FRESH" 2>&1); rc=$?
  else
    # The root is the resolver's STDOUT alone: it prints a credential re-exec notice on stderr, which must not become
    # part of the path (measured on the v0.343.4 capture, 2026-11-19).
    root_err=$(mktemp)
    root=$(python3 "${SEAT_PLUGIN_ROOT:?set SEAT_PLUGIN_ROOT to the installed plugin root}/scripts/bin/registered_plugin_root.py" --repo "$REPO" 2>"$root_err"); rc=$?
    if [ "$rc" = 0 ]; then
      ruled=$("${SEAT_ENV_WRAPPER:-/usr/local/bin/with-livespec-env.sh}" -- python3 "$root/scripts/bin/dispatcher.py" fresh-ruling --invoker "${SEAT_INVOKER:-claude:fleet-launch-seat}" --repo "$REPO" --item "$ITEM" --reason "$FRESH" 2>&1); rc=$?
    else ruled="could not resolve the plugin root: $(tail -n 1 "$root_err")"; fi
    rm -f "$root_err"
  fi
  case "$ruled" in *FRESH-RULING*) [ "$rc" = 0 ] || rc=8;; *) [ "$rc" != 0 ] || rc=8;; esac
  if [ "$rc" != 0 ]; then echo "REFUSED $ITEM: the --fresh ruling write failed (rc=$rc): $(printf %s "$ruled" | tail -n 1 | cut -c1-200); nothing is launched." >&2; exit 8; fi
  echo "RESTORE-GUARD $ITEM: fresh ruling recorded: $FRESH"
fi
slug=$(git -C "$REPO" remote get-url origin 2>/dev/null | sed -E 's#^(git@github.com:|https://github.com/)##; s#\.git$##')
found=(); unread=()
if [ -z "$slug" ]; then unread+=("origin of $REPO")
elif prs=$(gh pr list -R "$slug" --head "feat/$ITEM" --state open --json number --jq '.[].number' 2>/dev/null); then
  [ -n "$prs" ] && found+=("open pull request #$(echo $prs | tr ' ' ',')")
else unread+=("open pull requests of $slug"); fi
if refs=$(git -C "$REPO" ls-remote origin "refs/livespec/preserved-publish/$ITEM/*" 2>/dev/null); then
  [ -n "$refs" ] && found+=("preserved-publish ref $(echo "$refs" | awk '{print $2}' | head -1)")
else unread+=("preserved-publish refs"); fi
if git -C "$REPO" fetch --quiet origin "+refs/heads/master:refs/remotes/origin/master" 2>/dev/null; then
  delivery_commit=$(origin_master_delivery_commit "$ITEM" "$REPO" 2>/dev/null)
  [ -n "$delivery_commit" ] && found+=("delivery commit $delivery_commit on origin/master (reason: already delivered)")
else unread+=("origin/master delivery history"); fi
if [ ${#found[@]} -eq 0 ] && [ ${#unread[@]} -eq 0 ]; then exit 0; fi
if [ -n "$FRESH" ]; then echo "RESTORE-GUARD $ITEM: bypassed by --fresh: $FRESH"; exit 0; fi
if [ -n "$REDELIVER" ]; then echo "RESTORE-GUARD $ITEM: bypassed by --redeliver: $REDELIVER"; exit 0; fi
if [ ${#found[@]} -gt 0 ]; then
  echo "REFUSED $ITEM: a plain ticket routes FRESH and its reclaim would close or delete: $(IFS='; '; echo "${found[*]}"). Restore it with seeded-ticket.sh and the restore rider, or pass an explicit --fresh <reason>; use --redeliver <reason> only when work remains after the named delivery." >&2
  exit 6
fi
echo "REFUSED $ITEM: could not measure: $(IFS='; '; echo "${unread[*]}"); not read as clear. Retry, or pass an explicit --fresh <reason> or --redeliver <reason>." >&2
exit 7
