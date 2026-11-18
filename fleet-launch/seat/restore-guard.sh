#!/bin/bash
# restore-guard.sh <item> <repo-dir> [--fresh|--redeliver <reason>]: refuse a PLAIN ticket for an item whose earlier work still exists.
# A plain ticket routes the run FRESH, and the fresh run's publish-branch reclaim closes the item's open pull request and
# deletes its branch (measured 2026-11-18, bd-ib-xbw2yk, #5527). Work that exists is restored through seeded-ticket.sh with
# the restore rider, never rebuilt. This check is the mechanical form of that rule (coordinator Rule G).
# Refuses (exit 6) when, on the repository's origin, the item has an open factory pull request (head feat/<item>), a
# refs/livespec/preserved-publish/<item>/* ref, or a commit on origin/master that names the item in its message. Exit 7
# when any of those facts could not be measured (never read as clear). A delivery commit is a refusal rather than proof that
# the item is complete: partial deliveries must be explicitly redelivered with their remaining reason recorded in the ledger.
# Passes (exit 0) when none exists, when SEAT_SEEDED_RULING=1 (seeded-ticket.sh sets it after its seed ruling read-back),
# or when the caller names an explicit `--fresh <reason>` or `--redeliver <reason>`. Needs-human refs are named by dispatch
# id, not item, so they are not matched here; the preserved-publish ref and the open pull request are what a reclaim destroys.
set -u
ITEM=${1:?usage: restore-guard.sh <item> <repo-dir> [--fresh|--redeliver <reason>]}; REPO=${2:?repo-dir}; shift 2
BYPASS_FLAG=""; BYPASS_REASON=""
case "${1:-}" in
  --fresh|--redeliver)
    BYPASS_FLAG=$1; BYPASS_REASON=${2:-}
    [ -n "$BYPASS_REASON" ] || { echo "REFUSED $ITEM: $BYPASS_FLAG needs a reason" >&2; exit 2; }
    ;;
  "") ;;
  *) echo "REFUSED $ITEM: unknown restore-guard option $1" >&2; exit 2 ;;
esac
[ "${SEAT_SEEDED_RULING:-}" = 1 ] && exit 0
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
  delivery_commit=$(git -C "$REPO" log -1 --format=%H --fixed-strings --grep="$ITEM" origin/master 2>/dev/null)
  [ -n "$delivery_commit" ] && found+=("delivery commit $delivery_commit on origin/master (reason: already delivered)")
else unread+=("origin/master delivery history"); fi
if [ ${#found[@]} -eq 0 ] && [ ${#unread[@]} -eq 0 ]; then exit 0; fi
if [ -n "$BYPASS_FLAG" ]; then echo "RESTORE-GUARD $ITEM: bypassed by $BYPASS_FLAG: $BYPASS_REASON"; exit 0; fi
if [ ${#unread[@]} -gt 0 ]; then
  echo "REFUSED $ITEM: could not measure: $(IFS='; '; echo "${unread[*]}"); not read as clear. Retry, or pass an explicit --fresh <reason> or --redeliver <reason>." >&2
  exit 7
fi
if [ ${#found[@]} -gt 0 ]; then
  echo "REFUSED $ITEM: a plain ticket routes FRESH and its reclaim would close or delete: $(IFS='; '; echo "${found[*]}"). Restore it with seeded-ticket.sh and the restore rider, or pass an explicit --fresh <reason>; use --redeliver <reason> only when work remains after the named delivery." >&2
  exit 6
fi
