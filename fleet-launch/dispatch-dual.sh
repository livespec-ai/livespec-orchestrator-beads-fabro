#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — fleet launch for one work-item.
#
# A stopgap captured from the launcher the factory seats ran by hand during plan
# petri-factory-on-gmktec (tmp/petri-canary/dispatch-dual-r681b.sh), reconciled
# with that running copy on 2026-11-15 (bd-ib-yax6gv). Its first-class
# replacements are the livespec console application and the committed
# launch-loop tool bd-ib-jr6w7v; see README.md for why it exists and when it is
# retired.
#
# It is a CALLER-side launch loop (SPECIFICATION/contracts.md, "Dispatcher admission,
# WIP cap, and post-merge acceptance": "A caller MAY add gates of its own for
# conditions the Dispatcher does not own"). It decides only WHEN to invoke
# `drive --action impl:<item>`; every admission condition stays the Dispatcher's.
#
# Usage: dispatch-dual.sh <item-id>
# Environment (all optional):
#   FLEET_LAUNCH_BUILD_OVERRIDE=<build>   run THIS launch on that candidate orchestrator build (a
#                          directory name under the plugin cache) instead of the build installed_plugins.json
#                          names; a build not materialized there refuses. Unset: the installed build.
#   REPO_OVERRIDE=<path>   the tenant repository (default: this orchestrator repo)
#   WRAPPER=<path>         override the tenant credential wrapper chain (default: the
#                          target repository's committed credential_wrapper, a
#                          non-family one nested inside the default wrapper)
#   ONLY_GMK=1             launch onto the petri factory (gmktec :32276, or the candidate
#                          :32278 when the gmktec target setting says so) only, taking a
#                          FIFO ticket at start
#   ONLY_HL=1              launch onto the mi-homelab instance (gmktec :32277) only
#   ONLY_ARM=1             launch onto the homelab-worker-arm64 instance (gmktec :32279)
#                          only, once it is enrolled
#   CAPTURE_NULL=1         dispatch naming NO factory, and require the run's argv to
#   CAPTURE_EXPECT=<name>    carry --server of the registry-resolved CAPTURE_EXPECT
#   TICKET_NS=<ns>         reuse a queue position (restart without losing FIFO order); under
#                          priority ticketing it is honored only when it names an existing
#                          ticket for this item, never to place a fresh ticket
#   REWORK=1               ask the Dispatcher's loop dry-run instead of the ready set
#   RELEASE_BLOCKED=1      run resolve-blocked:<item>:ready just before launching
#
# Gates, in order: the Dispatcher's own ready set (retried a bounded number of polls);
# the host-only screen; the repository hold and the canary repository hold; the
# repository WIP gate (counted claims plus in-flight launches against wip_cap, one
# above for a breakage-exception item; an unreadable count never holds); the
# per-factory FIFO (a launcher behind the head re-checks only its place, and preflights
# while queued); the shared fleet cap (the gmktec, candidate and mi-homelab boards plus
# launches not yet listed; the arm64 lane counts against its own cap); the gmktec hold
# with its allowlist and priority-1 releases; the origin-tip checkout refresh, the size
# screen and the launch-time Definition-of-Done preflight; the factory's own ceiling and
# idle CPU; the mutex, the launch-point hold re-reads and a binding re-count that
# includes this launch's in-flight marker; and a usable-credential probe. An unreadable
# board counts as UNKNOWN and is never green.
set -u
FLEET_LAUNCH_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=fleet-launch/config.sh
. "$FLEET_LAUNCH_DIR/config.sh"
# shellcheck source=fleet-launch/board-snapshot.sh
. "$FLEET_LAUNCH_DIR/board-snapshot.sh"

LAUNCHER_ARGS=("$@")
SELF=$FLEET_LAUNCH_DIR/$(basename "${BASH_SOURCE[0]}")
ITEM=${1:?usage: dispatch-dual.sh <item-id>}
SEAT=$FLEET_LAUNCH_SEAT
REPO=${REPO_OVERRIDE:-$FLEET_LAUNCH_ORCH_REPO}
REPO_NAME=$(basename "$REPO")
REPO_HOLD_FILE="$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$REPO_NAME"
OUT=$FLEET_LAUNCH_STATE_DIR
GMK=$FLEET_LAUNCH_GMK_SERVER
GMK_CANDIDATE=$FLEET_LAUNCH_GMK_CANDIDATE_SERVER
HL=$FLEET_LAUNCH_HL_SERVER
ARM=$FLEET_LAUNCH_ARM_SERVER
# The gmktec factory hold file: while it exists no launch goes onto a gmktec factory instance,
# except one the freeze allowlist or priority 1 releases. The path is assigned here, in the
# launcher, from its host value in config.sh, and checked before every gmktec launch.
GMK_HOLD_FILE=$FLEET_LAUNCH_HOLD_FILE
FABRO=$FLEET_LAUNCH_FABRO
FABRO_BOARD=$FLEET_LAUNCH_FABRO_BOARD
INFLIGHT=$FLEET_LAUNCH_INFLIGHT_DIR
GMK_Q=$FLEET_LAUNCH_GMK_QUEUE_DIR
GMK_CLAIMS=$FLEET_LAUNCH_GMK_CLAIM_DIR
GMK_LOCK=$FLEET_LAUNCH_GMK_LOCK_DIR
# shellcheck source=fleet-launch/launch-lib.sh
. "$FLEET_LAUNCH_DIR/launch-lib.sh"
# Under the gate runner's stall cap this detaches into its own session and exits; see launch-lib.sh.
detach_if_under_gate_runner
# A gate-runner launch detaches before supervision, so its new session keeps a
# supervisor rather than leaving a worker the original launcher can no longer signal.
if [ -z "${FLEET_LAUNCH_SIGNAL_SUPERVISOR_CHILD:-}" ]; then
  signal_supervisor=${FLEET_LAUNCH_SIGNAL_SUPERVISOR:-"$FLEET_LAUNCH_DIR/signal-supervisor.sh"}
  exec bash "$signal_supervisor" "$SELF" "${LAUNCHER_ARGS[@]}"
fi
# A mi-homelab or arm64 launcher orders its ticket only among tickets of its own class
# (ticket line server=hl); a gmktec launcher ignores those. The mutex and the fleet cap are shared.
FIFO_CLASS=gmk; [ -n "${ONLY_HL:-}${ONLY_ARM:-}" ] && FIFO_CLASS=hl
deadline=$(( $(date +%s) + FLEET_LAUNCH_MAX_WAIT_S ))
wait_deadline=$(( SECONDS + FLEET_LAUNCH_MAX_WAIT_S ))
ticket=""; ticket_number=""; item_claim=""; lock=""; marker=""; FLEET_CAP=0; plugin=""; build=""
# Resolve before any gate can pass the directory to a helper or credential
# probe. A registry failure is therefore reported as itself, never as a bad
# credential against an empty cache path.
plugin=$(installed_plugin_dir) || exit 70
build=${plugin##*/}
# Non-run exit accounting: a launcher that exits before its run lists writes one terminal line and,
# when its item still reads ready, one ledger comment naming the dropped ticket (Scenario 312).
run_listed=0; terminal_written=0; exit_cause=""; exit_comment=if-ready; ready_refusals=0
gmk_rows=""; hl_rows=""; candidate_rows=""; arm_rows=""
gmk_live=U; hl_live=U; candidate_live=U; arm_live=U; markers=U; fleet=U; arm_inflight=U; gmk_idle=""
WIP_COUNTED=""; WIP_CAP=""; WIP_EFFECTIVE=""; WIP_CLAIMS=""; WIP_INFLIGHT=""
WIP_SHARED_FILE="$FLEET_LAUNCH_WIP_SHARED_DIR/wip-act.$REPO_NAME"
WIP_STATUSES_FILE="$FLEET_LAUNCH_WIP_CACHE_DIR/wip-claimed-cache.$REPO_NAME.json.statuses"
# The judge-model environment: every non-empty host value reaches each preflight and drive.
JUDGE_ENV=()
[ -n "$FLEET_LAUNCH_DOD_JUDGEMENT_MODEL" ] && JUDGE_ENV+=("LIVESPEC_DOD_JUDGEMENT_MODEL=$FLEET_LAUNCH_DOD_JUDGEMENT_MODEL")
[ -n "$FLEET_LAUNCH_DRIFT_JUDGE_MODEL" ] && JUDGE_ENV+=("LIVESPEC_DRIFT_JUDGE_MODEL=$FLEET_LAUNCH_DRIFT_JUDGE_MODEL")
[ -n "$FLEET_LAUNCH_REFLECTOR_MODEL" ] && JUDGE_ENV+=("LIVESPEC_REFLECTOR_MODEL=$FLEET_LAUNCH_REFLECTOR_MODEL")
mkdir -p "$OUT"

# A bash launcher keeps executing the script content it started with, so code added to this file
# after a launcher started never reached it (bd-ib-5ycmsm). The wait loop therefore compares this
# file on disk with the content the launcher started on and re-executes itself when they differ,
# keeping its pid, its queue ticket and its give-up deadline. Replace the file atomically (write
# beside it, then mv): an in-place edit corrupts a running bash.
script_version() { sha256sum < "$1" 2>/dev/null | cut -c1-12; }
START_VERSION=$(script_version "/proc/$$/fd/255")
[ -n "$START_VERSION" ] || START_VERSION=$(script_version "$SELF")
bad_version=""
if [ "${FLEET_LAUNCH_REEXEC_PID:-}" = "$$" ]; then
  [ -f "${FLEET_LAUNCH_REEXEC_TICKET:-}" ] && grep -q "pid=$$ " "$FLEET_LAUNCH_REEXEC_TICKET" && { ticket=$FLEET_LAUNCH_REEXEC_TICKET; ticket_number=${ticket##*/}; ticket_number=${ticket_number%-"$SEAT"}; }
  case ${FLEET_LAUNCH_REEXEC_DEADLINE:-} in ''|*[!0-9]*) ;; *) deadline=$FLEET_LAUNCH_REEXEC_DEADLINE ;; esac
  wait_deadline=$(( SECONDS + deadline - $(date +%s) ))
  echo "$(date -u +%FT%TZ) launcher re-executed on script version $START_VERSION: keeping ticket ${ticket##*/}"
fi
unset FLEET_LAUNCH_REEXEC_PID FLEET_LAUNCH_REEXEC_TICKET FLEET_LAUNCH_REEXEC_DEADLINE
# script_changed: the script on disk differs from the running content and parses.
script_changed() {
  local now; now=$(script_version "$SELF")
  [ -n "$now" ] && [ "$now" != "$START_VERSION" ] || return 1
  bash -n "$SELF" 2>/dev/null && return 0
  [ "$now" = "$bad_version" ] || echo "$(date -u +%FT%TZ) launcher script changed on disk ($now) but does not parse: keep running $START_VERSION"
  bad_version=$now
  return 1
}
# reexec_on_script_change: call only where this launcher holds no mutex and no in-flight marker.
reexec_on_script_change() {
  script_changed || return 0
  echo "$(date -u +%FT%TZ) launcher script changed on disk ($START_VERSION -> $(script_version "$SELF")): re-exec, keeping ticket ${ticket##*/}"
  export FLEET_LAUNCH_REEXEC_PID=$$ FLEET_LAUNCH_REEXEC_TICKET=$ticket FLEET_LAUNCH_REEXEC_DEADLINE=$deadline
  exec bash "$SELF" "${LAUNCHER_ARGS[@]}"
}

drop_ticket() { [ -n "$ticket" ] && rm -f "$ticket"; ticket=""; }
# ticket_namespace_is_restart: TICKET_NS is a restart only when it names a ticket that already exists
# in the queue for THIS item.  Under priority ticketing a caller therefore cannot hand-place a fresh
# ticket: a number naming no existing ticket for the item is ignored and the position is computed.
ticket_namespace_is_restart() {
  local file
  [ -n "${TICKET_NS:-}" ] || return 1
  case "$TICKET_NS" in */*) return 1 ;; esac
  file="$GMK_Q/$TICKET_NS-$SEAT"
  [ -f "$file" ] && ticket_fields "$file" && [ "$TK_ITEM" = "$ITEM" ]
}
# priority_ticketing_configured: the priorities record must be readable.  The record and the
# parent-chain command default to the committed config.sh values, so a host that keeps its latest
# priorities record at FLEET_LAUNCH_PRIORITIES_RECORD is ranked with no further setup; a host with no
# record keeps the ordinary timestamp FIFO.
priority_ticketing_configured() {
  [ -n "${FLEET_LAUNCH_PRIORITIES_RECORD:-}" ] && [ -r "$FLEET_LAUNCH_PRIORITIES_RECORD" ] \
    && [ -n "${FLEET_LAUNCH_PARENT_CHAIN_COMMAND:-}" ] && [ -x "$FLEET_LAUNCH_PARENT_CHAIN_COMMAND" ]
}
# priority_ticket_key: walk the item's parent chain at ticket time, reading the priorities record
# (one "<rank> <plan-id>" line per ranked plan) afresh.  The parent command runs in the tenant
# repository under its credential wrapper.  An unranked or unresolvable chain receives the final rank,
# never an operator-provided slot.
priority_ticket_key() {
  local node="$ITEM" parent rank hops=0
  while [ "$hops" -lt 64 ]; do
    rank=$(awk -v plan="$node" '$2 == plan { print $1; exit }' "$FLEET_LAUNCH_PRIORITIES_RECORD")
    case "$rank" in
      ''|*[!0-9]*) ;;
      *) printf '%05d' "$((10#$rank))"; return 0 ;;
    esac
    parent=$(cd "$REPO" && wrap -- "$FLEET_LAUNCH_PARENT_CHAIN_COMMAND" "$node" 2>/dev/null) || return 1
    parent=${parent%%$'\n'*}
    [ -n "$parent" ] || return 1
    node=$parent
    hops=$((hops + 1))
  done
  return 1
}
# claim_item: one launcher per queued item.  The claim is a symlink named for the item whose target is
# the owning pid; creating a symlink is atomic, so of any number of launchers started at once exactly
# one creates it and the rest read its owner.  A claim whose owner is dead is moved aside and retaken.
# Returns 0 when this launcher holds the claim and 2 when another live launcher does.
claim_item() {
  local link="$GMK_CLAIMS/$ITEM" holder stale tries=0
  mkdir -p "$GMK_CLAIMS" || return 1
  while [ "$tries" -lt 8 ]; do
    tries=$((tries + 1))
    if ln -s "$$" "$link" 2>/dev/null; then item_claim=$link; return 0; fi
    holder=$(readlink "$link" 2>/dev/null) || continue
    if [ "$holder" = "$$" ]; then item_claim=$link; return 0; fi
    case "$holder" in ''|*[!0-9]*) ;; *) kill -0 "$holder" 2>/dev/null && return 2 ;; esac
    stale="$link.stale.$$"
    mv -T "$link" "$stale" 2>/dev/null || continue
    # Only the dead owner's claim may be discarded; a live one moved by a race is put straight back.
    if [ "$(readlink "$stale")" = "$holder" ]; then rm -f "$stale"; else mv -T "$stale" "$link" 2>/dev/null || rm -f "$stale"; fi
  done
  return 1
}
release_item_claim() {
  [ -n "$item_claim" ] && [ "$(readlink "$item_claim" 2>/dev/null)" = "$$" ] && rm -f "$item_claim"
  item_claim=""
}
# existing_live_ticket_for_item: a ticket of another live launcher for this item, as a second
# guard for launchers that predate the claim.
existing_live_ticket_for_item() {
  local f
  for f in "$GMK_Q"/*; do
    [ -e "$f" ] || continue
    ticket_fields "$f" || continue
    [ "$TK_ITEM" = "$ITEM" ] && [ -n "$TK_PID" ] && [ "$TK_PID" != "$$" ] && kill -0 "$TK_PID" 2>/dev/null && return 0
  done
  return 1
}
# ensure_ticket: returns 0 holding a ticket, 2 when another live launcher already owns this item, and 1
# when no ticket could be written.  A priority ticket is named <rank>-<ns>, its rank walked from the
# item's parent chain to the owning plan's rank in the priorities record at this moment.
ensure_ticket() {
  local overwrite=0 claim_rc
  [ -n "$ticket" ] && [ -f "$ticket" ] && return
  mkdir -p "$GMK_Q"
  # Only a queued launcher (ONLY_GMK, ONLY_HL or ONLY_ARM) takes a ticket at start, so only it is
  # held to one launcher per item.
  if [ -n "${ONLY_GMK:-}${ONLY_HL:-}${ONLY_ARM:-}" ]; then
    claim_item; claim_rc=$?
    [ "$claim_rc" = 0 ] || return "$claim_rc"
    if existing_live_ticket_for_item; then release_item_claim; return 2; fi
  fi
  if [ -z "$ticket_number" ]; then
    if priority_ticketing_configured; then
      if ticket_namespace_is_restart; then ticket_number=$TICKET_NS; overwrite=1
      else ticket_number="$(priority_ticket_key || printf 99999)-$(date +%s%N)"; fi
    elif [ -n "${TICKET_NS:-}" ]; then ticket_number=$TICKET_NS; overwrite=1
    else ticket_number=$(date +%s%N); fi
  fi
  ticket="$GMK_Q/$ticket_number-$SEAT"
  if [ "$overwrite" = 1 ]; then
    echo "owner=$SEAT pid=$$ item=$ITEM" > "$ticket" || { ticket=""; return 1; }
  elif ! ( set -o noclobber; echo "owner=$SEAT pid=$$ item=$ITEM" > "$ticket" ) 2>/dev/null; then
    ticket=""
    return 1
  fi
  [ "$FIFO_CLASS" = hl ] && echo "server=hl" >> "$ticket"
  echo "$(date -u +%FT%TZ) gmktec FIFO ticket taken at start: ${ticket##*/}"
}
# yield_ticket <cause>: mark the ticket as yielding, with exactly one held= line naming the rule it yields
# under. A ticket that already names that cause is left alone; one naming another cause is re-marked.
# The queue directory's time is touched so a queued launcher woken by directory changes re-reads its place.
yield_ticket() {
  [ -n "$ticket" ] && [ -f "$ticket" ] || return 0
  grep -qx "held=$1" "$ticket" && return 0
  sed -i '/^held=/d' "$ticket"
  echo "held=$1" >> "$ticket"
  touch "$GMK_Q" 2>/dev/null
}
restore_ticket() {
  [ -n "$ticket" ] && [ -f "$ticket" ] || return 0
  grep -q '^held=' "$ticket" || return 0
  sed -i '/^held=/d' "$ticket"
  touch "$GMK_Q" 2>/dev/null
}
ticket_yielding_wip() { [ -n "$ticket" ] && [ -f "$ticket" ] && grep -qx 'held=repository-wip' "$ticket"; }
repository_hold_applies() {
  local raw compact content
  HOLD_KINDS=all
  # Read the file once, so reason, until and kinds all come from one version of it.
  content=$(cat "$REPO_HOLD_FILE" 2>/dev/null)
  HOLD_REASON=$(printf '%s\n' "$content" | sed -n '/^reason:/ { s/^reason:[[:space:]]*//; p; q; }')
  HOLD_UNTIL=$(printf '%s\n' "$content" | sed -n '/^until:/ { s/^until:[[:space:]]*//; p; q; }')
  [ -e "$REPO_HOLD_FILE" ] || return 1
  raw=$(printf '%s\n' "$content" | sed -n '/^kinds:/ { s/^kinds:[[:space:]]*//; p; q; }')
  compact=$(printf '%s' "$raw" | tr -d '[:space:]')
  case "$compact" in
    dispatch|resume|dispatch,resume|resume,dispatch) HOLD_KINDS=$compact ;;
  esac
  [ "$HOLD_KINDS" = all ] && return 0
  case ",$HOLD_KINDS," in *",$1,"*) return 0 ;; esac
  return 1
}
repository_hold_details() {
  local details="kinds=$HOLD_KINDS"
  [ -n "$HOLD_REASON" ] && details="$details reason=$HOLD_REASON"
  [ -n "$HOLD_UNTIL" ] && details="$details until=$HOLD_UNTIL"
  printf '%s' "$details"
}
log_repository_hold() {
  echo "$(date -u +%FT%TZ) repository hold present ($REPO_HOLD_FILE): $(repository_hold_details): yield FIFO head"
}
log_canary_hold() {
  echo "$(date -u +%FT%TZ) canary repository hold present ($CANARY_HOLD_FILE): $(canary_hold_text): yield FIFO head"
}
# launch_hold_applies: succeeds when a hold applying to an impl launch exists, setting HOLD_SOURCE
# (repository, canary or gmktec) and HOLD_DESC, the text of the hold it read.
launch_hold_applies() {
  if repository_hold_applies dispatch; then
    HOLD_SOURCE=repository; HOLD_DESC="repository hold ($REPO_HOLD_FILE): $(repository_hold_details)"
    return 0
  fi
  if canary_held; then
    HOLD_SOURCE=canary; HOLD_DESC="canary repository hold ($CANARY_HOLD_FILE): $(canary_hold_text)"
    return 0
  fi
  if [ "$FIFO_CLASS" != hl ] && [ -e "$GMK_HOLD_FILE" ] && gmk_held; then
    HOLD_SOURCE=gmktec
    HOLD_DESC="gmktec hold ($GMK_HOLD_FILE): $(gmk_hold_text)"
    return 0
  fi
  return 1
}
give_up() {
  give_up_line="no slot within ${FLEET_LAUNCH_MAX_WAIT_S}s: give up item=$ITEM queue-ticket=${ticket:-none}"
  echo "$give_up_line"
  exit_cause="${give_up_line%% item=*}"
  exit 75
}
release_lock() {
  if [ -n "$lock" ] && grep -q "pid=$$ " "$lock/holder" 2>/dev/null; then rm -f "$lock/holder"; rmdir "$lock" 2>/dev/null; fi
  lock=""
}
# item_status is defined ahead of the exit path below, because a signal can end the launcher at any
# point after its traps are set; a helper defined later reads as "command not found".
item_status() {
  local out
  out=$(cd "$REPO" && wrap -- python3 "$FLEET_LAUNCH_DIR/ledger-item.py" status "$plugin" "$REPO" "$ITEM" 2>/dev/null) || return 1
  out=$(printf '%s\n' "$out" | sed -n 's/^LEDGER-STATUS //p' | tail -n 1)
  [ -n "$out" ] && printf '%s' "$out"
}
# write_terminal <cause>: the one terminal line of a launcher that exits without a run.
write_terminal() {
  echo "$(date -u +%FT%TZ) terminal: item=$ITEM ticket=${ticket_number:-none} cause=$1"
  terminal_written=1
}
# ledger_comment <body>: one ledger comment on the item, through the installed build's store seam.
ledger_comment() {
  [ -n "$plugin" ] || plugin=$(installed_plugin_dir) || return 1
  (cd "$REPO" && wrap -- python3 "$FLEET_LAUNCH_DIR/ledger-item.py" comment "$plugin" "$REPO" "$ITEM" "$1") >/dev/null 2>&1
}
# report_dropped_ticket <cause>: one ledger comment naming the dropped ticket and the cause, when the item
# still reads ready (or exit_comment=always). The ticket is not re-taken: this launcher is exiting.
report_dropped_ticket() {
  local status body
  [ -n "$plugin" ] || plugin=$(installed_plugin_dir) || return 1
  status=$(item_status) || status=unreadable
  [ "$exit_comment" = always ] || [ "$status" = ready ] || return 0
  body="Fleet launcher $SEAT exited for $ITEM before its run listed: ticket ${ticket_number:-none} was dropped and not re-taken (cause: $1). This exit was not a run ending, and the item read $status. Remedy: launch it again, passing TICKET_NS=${ticket_number:-<none>} to keep its queue place."
  ledger_comment "$body" \
    || echo "$(date -u +%FT%TZ) ledger comment for $ITEM failed: the dropped ticket ${ticket_number:-none} was not recorded"
}
# on_exit: every exit before the run lists. The terminal line is written before the ticket file is removed.
on_exit() {
  local rc=$? cause=""
  trap - EXIT
  if [ -n "${FLEET_LAUNCH_SIGNAL_CAUSE_FILE:-}" ] && [ -r "$FLEET_LAUNCH_SIGNAL_CAUSE_FILE" ]; then
    IFS= read -r exit_cause < "$FLEET_LAUNCH_SIGNAL_CAUSE_FILE" || :
  fi
  if [ "$run_listed" = 0 ] && [ "$terminal_written" = 0 ]; then
    case "$rc" in
      143) cause=${exit_cause:-"signal TERM (this exit was not a run ending)"} ;;
      130) cause=${exit_cause:-"signal INT (this exit was not a run ending)"} ;;
      129) cause=${exit_cause:-"signal HUP (this exit was not a run ending)"} ;;
      *) cause=${exit_cause:-"exit rc=$rc before its run listed"} ;;
    esac
    write_terminal "$cause"
  fi
  drop_ticket; release_item_claim; release_lock; [ -n "$marker" ] && rm -f "$marker"
  [ -n "$cause" ] && report_dropped_ticket "$cause"
  return 0
}
trap on_exit EXIT
# signal-supervisor.sh records INT, HUP, and TERM before forwarding Bash's default action.  Bash 5.2
# can fail to parse a string trap action while a command substitution is active, and its EXIT cleanup
# otherwise observes a zero status for such a default-signal exit.

# The tenant credential wrapper is resolved once: a target whose committed credential_wrapper
# cannot be read launches nothing.
if ! resolve_tenant_wrapper; then
  write_terminal credential-wrapper-unreadable
  echo "$(date -u +%FT%TZ) the credential_wrapper of $REPO/.livespec.jsonc cannot be read: no launch"
  report_dropped_ticket credential-wrapper-unreadable
  exit 75
fi

rows_count() { if [ "$1" = U ]; then echo U; else printf '%s' "$1" | grep -c .; fi; }

# drive_alive_for <item>: a drive.py impl dispatch for the item is alive. Candidates need the real
# argv shape; a bare `pgrep -f` also matched any shell whose command line merely contained the pattern.
drive_alive_for() {
  local p a
  for p in $(pgrep -u "$(id -u)" -f -- "drive.py .*--action impl:$1( |$)" 2>/dev/null); do
    mapfile -d '' -t a < "/proc/$p/cmdline" 2>/dev/null || continue
    # The real argv shape: one element whose basename is drive.py and one element that IS impl:<item>.
    printf '%s\n' "${a[@]}" | sed 's|.*/||' | grep -qxF -- drive.py || continue
    printf '%s\n' "${a[@]}" | grep -qxF -- "impl:$1" && return 0
  done
  return 1
}

# marker_snapshot: live in-flight marker paths, item ids, listed observations and
# the factory each marker names, tab-separated, or U when the directory cannot be
# read. Taken BEFORE the boards are read: a launcher drops its marker only after a
# board lists its run, so a marker that vanishes after this snapshot belongs to a
# run the later board read lists. Reading the boards first undercounted a run that
# listed between the two reads (bd-ib-uhcn36, run 01M6H3VFB451).
marker_snapshot() {
  local f p it listed factory entries=""
  mkdir -p "$INFLIGHT" 2>/dev/null
  [ -d "$INFLIGHT" ] && [ -r "$INFLIGHT" ] && [ -x "$INFLIGHT" ] || { echo U; return; }
  for f in "$INFLIGHT"/*; do
    [ -e "$f" ] || continue
    [ -r "$f" ] || { echo U; return; }
    p=$(grep -oE 'pid=[0-9]+' "$f" | head -1 | cut -d= -f2)
    it=$(grep -oE 'item=[^ ]+' "$f" | head -1 | cut -d= -f2)
    factory=$(grep -oE 'factory=[^ ]+' "$f" | head -1 | cut -d= -f2)
    # A dead-pid marker is stale only when no drive.py impl dispatch for its item is alive.
    if ! { [ -n "$p" ] && kill -0 "$p" 2>/dev/null; }; then
      [ -n "$it" ] && drive_alive_for "$it" || continue
    fi
    listed=0
    grep -qx 'listed=1' "$f" 2>/dev/null && listed=1
    entries="${entries}${f}"$'\t'"${it}"$'\t'"${listed}"$'\t'"${factory:-petri}"$'\n'
  done
  printf '%s' "$entries"
}

# mark_marker_listed <marker>: retain the observed transition in a marker whose
# launcher is gone but whose drive can still merge-poll after the run ends.
mark_marker_listed() {
  local marker="$1"
  [ -e "$marker" ] || return
  grep -qx 'listed=1' "$marker" 2>/dev/null || printf 'listed=1\n' >> "$marker" 2>/dev/null
}

# unlisted_markers <snapshot> <listed-rows> <fleet|arm>: count a snapshot marker until its
# run lists. After a board observation has recorded that transition, the marker
# stays out of the count even after the run has left the board. The arm64 lane's
# markers are counted apart from the fleet's, because that lane has its own cap.
unlisted_markers() {
  local snapshot="$1" listed="$2" lane="$3" marker it was_listed factory n=0
  [ "$snapshot" = U ] && { echo U; return; }
  while IFS=$'\t' read -r marker it was_listed factory; do
    [ -n "$it" ] || continue
    if [ "$lane" = arm ]; then [ "$factory" = homelab-worker-arm64 ] || continue
    else [ "$factory" = homelab-worker-arm64 ] && continue; fi
    if printf '%s\n' "$listed" | awk -v it="$it" '$4==it {found=1} END{exit !found}'; then
      mark_marker_listed "$marker"
      continue
    fi
    [ "$was_listed" = 1 ] && continue
    n=$((n + 1))
  done <<EOF_SNAPSHOT
$snapshot
EOF_SNAPSHOT
  echo "$n"
}

# read_boards [direct]: sets gmk_live, candidate_live, hl_live, arm_live, markers, fleet and
# arm_inflight (a number, or U when any reading is unknown). The fleet is the gmktec, candidate
# and mi-homelab boards plus launches not yet listed; the arm64 lane is outside that sum and is
# read only once the enrolment marker exists. The boards come from the shared snapshot
# (board-snapshot.sh) unless "direct" asks for the factory itself.
read_boards() {
  local snapshot reader=board_rows
  [ "${1:-}" = direct ] && reader=board_rows_direct
  snapshot=$(marker_snapshot)
  gmk_rows=$("$reader" "$FABRO_BOARD" "$GMK")
  hl_rows=$("$reader" "$FABRO_BOARD" "$HL")
  candidate_rows=$("$reader" "$FABRO_BOARD" "$GMK_CANDIDATE")
  if [ -e "$FLEET_LAUNCH_ARM_ENROLLED_FILE" ]; then arm_rows=$("$reader" "$FABRO_BOARD" "$ARM"); else arm_rows=""; fi
  gmk_live=$(rows_count "$gmk_rows"); hl_live=$(rows_count "$hl_rows")
  candidate_live=$(rows_count "$candidate_rows"); arm_live=$(rows_count "$arm_rows")
  if [ "$gmk_live" = U ] || [ "$hl_live" = U ] || [ "$candidate_live" = U ] || [ "$arm_live" = U ]; then markers=U; fleet=U; arm_inflight=U; return; fi
  markers=$(unlisted_markers "$snapshot" "$(printf '%s\n%s\n%s\n' "$gmk_rows" "$candidate_rows" "$hl_rows")" fleet)
  if [ "$markers" = U ]; then fleet=U; arm_inflight=U; return; fi
  fleet=$(( gmk_live + candidate_live + hl_live + markers ))
  local arm_markers
  arm_markers=$(unlisted_markers "$snapshot" "$arm_rows" arm)
  if [ "$arm_markers" = U ]; then arm_inflight=U; else arm_inflight=$(( arm_live + arm_markers )); fi
}
fleet_summary() {
  printf 'gmktec=%s hl=%s markers=%s fleet=%s cap=%s candidate=%s arm64=%s' "$gmk_live" "$hl_live" "$markers" "$fleet" "${FLEET_CAP:-?}" "$candidate_live" "$arm_live"
}
# gmk_target: the instance a gmktec launch goes to, read on every gate pass from the gmktec target
# setting. Anything other than the word `candidate`, and an absent file, selects the default instance.
gmk_target() {
  [ -r "$FLEET_LAUNCH_GMK_TARGET_FILE" ] && [ "$(tr -d '[:space:]' < "$FLEET_LAUNCH_GMK_TARGET_FILE" 2>/dev/null)" = candidate ] && echo candidate || echo petri
}
gt() { awk "BEGIN{exit !($1 > $2)}"; }
mpstat_idle() { ssh -o BatchMode=yes -o ConnectTimeout=15 "$1" 'mpstat 5 2' 2>/dev/null | awk '/^Average/ {print $NF}'; }
fleet_green() {
  read_fleet_cap; read_boards
  [ "$fleet" != U ] && [ "$FLEET_CAP" -gt 0 ] && [ "$fleet" -lt "$FLEET_CAP" ]
}
# bind_count <factory>: write this launch's marker, then re-count with it included; proceed only at or
# under the cap. The arm64 lane binds against its own cap, outside the fleet sum.
bind_count() {
  marker="$INFLIGHT/$(date +%s%N)-$SEAT-$ITEM"
  mkdir -p "$INFLIGHT" 2>/dev/null
  echo "owner=$SEAT pid=$$ item=$ITEM factory=$1 at=$(date -u +%FT%TZ)" > "$marker" || { marker=""; return 1; }
  read_fleet_cap; read_boards direct
  if [ "$1" = homelab-worker-arm64 ]; then
    if [ "$arm_inflight" != U ] && [ "$arm_inflight" -le "$FLEET_LAUNCH_ARM_CAP" ]; then return 0; fi
    echo "$(date -u +%FT%TZ) binding count with our marker (arm64): arm_inflight=$arm_inflight cap=$FLEET_LAUNCH_ARM_CAP: delete marker, skip"
    rm -f "$marker"; marker=""; return 1
  fi
  if [ "$fleet" != U ] && [ "$FLEET_CAP" -gt 0 ] && [ "$fleet" -le "$FLEET_CAP" ]; then return 0; fi
  echo "$(date -u +%FT%TZ) binding count with our marker: fleet=$fleet cap=${FLEET_CAP:-?}: delete marker, skip"
  rm -f "$marker"; marker=""; return 1
}
gmk_idle_green() {
  local floor; floor=$(gmk_idle_floor)
  gmk_idle=$(mpstat_idle "$FLEET_LAUNCH_GMK_SSH"); [ -n "$gmk_idle" ] && gt "$gmk_idle" "$floor"
}
gmk_green() {
  [ "$gmk_live" != U ] && [ "$gmk_live" -lt "$(gmk_cap)" ] || return 1
  gmk_idle_green
}
candidate_green() {
  [ "$candidate_live" != U ] && [ "$candidate_live" -lt "$(candidate_cap)" ] || return 1
  gmk_idle_green
}
gmk_slot_green() { if [ "$(gmk_target)" = candidate ]; then candidate_green; else gmk_green; fi; }
hl_green() { [ "$hl_live" != U ] && [ "$hl_live" -lt "$(hl_cap)" ]; }
arm_green() { [ -e "$FLEET_LAUNCH_ARM_ENROLLED_FILE" ] && [ "$arm_inflight" != U ] && [ "$arm_inflight" -lt "$FLEET_LAUNCH_ARM_CAP" ]; }
holder_dead() {
  local age h pid
  age=$(( $(date +%s) - $(stat -c %Y "$1/holder" 2>/dev/null || date +%s) ))
  [ "$age" -gt "$FLEET_LAUNCH_MUTEX_HOLD_S" ] || return 1
  h=$(cat "$1/holder" 2>/dev/null)
  pid=$(printf '%s' "$h" | grep -oE 'pid[=:] *[0-9]+' | grep -oE '[0-9]+' | head -1)
  [ -n "$pid" ] || return 1
  ! kill -0 "$pid" 2>/dev/null
}
# take_mutex <queue-dir> <lock-dir>: FIFO ticket, FLEET_LAUNCH_MUTEX_POLL_S polls, abandon after FLEET_LAUNCH_ABANDON_S.
take_mutex() {
  local q="$1" l="$2" queued
  mkdir -p "$q"
  # Keep the ticket through the launch-point hold re-read, so a newly-created
  # hold can yield it instead of losing its FIFO place.
  ensure_ticket
  queued=$(date +%s)
  while [ $(( $(date +%s) - queued )) -lt "$FLEET_LAUNCH_ABANDON_S" ]; do
    if [ -d "$l" ] && holder_dead "$l"; then echo "$(date -u +%FT%TZ) dead holder on $l: $(cat "$l/holder" 2>/dev/null); removing"; rm -f "$l/holder"; rmdir "$l" 2>/dev/null; fi
    if [ ! -d "$l" ] && [ "$(oldest_live_ticket "$q")" = "$ticket" ] && mkdir "$l" 2>/dev/null; then
      lock="$l"; echo "owner=$SEAT pid=$$ item=$ITEM at=$(date -u +%FT%TZ)" > "$l/holder"; return 0
    fi
    sleep "$FLEET_LAUNCH_MUTEX_POLL_S"
  done
  return 1
}
# wait_queue_change: return when the FIFO queue directory changes (a ticket added, dropped or
# re-marked), or after FLEET_LAUNCH_QUEUE_WAIT_S. A launcher behind the head does no other work.
wait_queue_change() {
  local stamp="$OUT/.qstamp.$$" waited=0 step="$FLEET_LAUNCH_POLL_S"
  { : > "$stamp"; } 2>/dev/null || { nap "$FLEET_LAUNCH_QUEUE_WAIT_S"; return; }
  while awk -v w="$waited" -v b="$FLEET_LAUNCH_QUEUE_WAIT_S" 'BEGIN{exit !(w < b)}'; do
    nap "$step"
    waited=$(awk -v w="$waited" -v s="$step" 'BEGIN{print w + s}')
    [ "$GMK_Q" -nt "$stamp" ] && break
  done
  rm -f "$stamp"
}

# drive_refusal_kind <drive-json-file>: prints goal-minijinja-preflight when the drive's JSON output
# reports that dispatch stage failed (it fails identically on every retry until the item's record is
# repaired), refused when any stage or status in it ends in -refused (a permanent refusal reported
# with a non-zero exit, as the host-only refusal is), or nothing.
drive_refusal_kind() {
  python3 - "$1" <<'PY' 2>/dev/null
import json
import sys


def walk(node):
    if isinstance(node, dict):
        if node.get("stage") == "goal-minijinja-preflight" and node.get("status") == "failed":
            return "goal-minijinja-preflight"
        for key in ("stage", "status"):
            if str(node.get(key, "")).endswith("-refused"):
                return "refused"
        for value in node.values():
            found = walk(value)
            if found:
                return found
    if isinstance(node, list):
        for value in node:
            found = walk(value)
            if found:
                return found
    return ""


try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        text = handle.read()
    document = json.loads(text[text.find("{"):]) if "{" in text else {}
except (OSError, ValueError):
    sys.exit(1)
kind = walk(document)
print(kind)
sys.exit(0 if kind else 1)
PY
}

# --- the repository WIP gate --------------------------------------------------------------------
# The target repository's counted-claims count comes from the Dispatcher's own capacity projection
# through wip-claimed-count.py, never from a count of this launcher's own. The launcher reads the
# shared per-repository result file before it spawns anything, refreshes it once per
# FLEET_LAUNCH_WIP_SHARED_TTL_S under a lock, and adds this repository's in-flight launches whose
# item is not yet active (never its own marker) on every pass from the cached statuses. This is an
# early yield, not an admission decision: the Dispatcher still applies its own WIP cap to every
# drive, so a count that cannot be read never holds.
now_s() { printf -v NOW '%(%s)T' -1; }
wip_helper() {
  local build_dir
  build_dir=$(installed_plugin_dir) || return 1
  (cd "$REPO" && wrap -- python3 "$FLEET_LAUNCH_DIR/wip-claimed-count.py" "$build_dir" "$REPO" "$INFLIGHT" "$ITEM" --cache-dir "$FLEET_LAUNCH_WIP_CACHE_DIR" --ttl "$FLEET_LAUNCH_WIP_CACHE_TTL_S" 2>/dev/null)
}
wip_json_field() { python3 -c 'import json,sys; print(int(json.load(sys.stdin)[sys.argv[1]]))' "$1" 2>/dev/null; }
wip_shared_refresh() {
  local lk="$WIP_SHARED_FILE.lk" at report base cap
  now_s
  if ! mkdir "$lk" 2>/dev/null; then
    at=; read -r at 2>/dev/null < "$lk/at"
    case "$at" in ''|*[!0-9]*) at=0 ;; esac
    [ $((NOW - at)) -gt 180 ] && rm -rf "$lk"
    return 1
  fi
  printf '%s\n' "$NOW" > "$lk/at"
  report=$(wip_helper) || { rm -rf "$lk"; return 1; }
  base=$(printf '%s' "$report" | wip_json_field counted_claims)
  cap=$(printf '%s' "$report" | wip_json_field wip_cap)
  case "$base" in ''|*[!0-9]*) rm -rf "$lk"; return 1 ;; esac
  case "$cap" in ''|*[!0-9]*) rm -rf "$lk"; return 1 ;; esac
  now_s
  printf '%s %s %s\n' "$NOW" "$base" "$cap" > "$WIP_SHARED_FILE.$$" && mv -f "$WIP_SHARED_FILE.$$" "$WIP_SHARED_FILE"
  rm -rf "$lk"
  return 0
}
# in_flight_addition: this repository's launches already past the FIFO (a live in-flight marker)
# whose item the cached statuses report as not yet active, excluding this launcher's own marker.
in_flight_addition() {
  local f st n=0
  [ -d "$INFLIGHT" ] || { echo 0; return; }
  for f in "$INFLIGHT"/*; do
    [ -e "$f" ] || continue
    ticket_fields "$f" || continue
    [ -n "$TK_PID" ] && kill -0 "$TK_PID" 2>/dev/null || continue
    [ -n "$TK_ITEM" ] && [ "$TK_ITEM" != "$ITEM" ] || continue
    st=$(grep -m1 -- "^$TK_ITEM " "$WIP_STATUSES_FILE" 2>/dev/null); st=${st#* }
    [ -n "$st" ] || continue
    [ "$st" = active ] || n=$((n + 1))
  done
  echo "$n"
}
wip_green() {
  local ts base cap add report
  WIP_COUNTED=""; WIP_CAP=""; WIP_EFFECTIVE=""; WIP_CLAIMS=""; WIP_INFLIGHT=""
  base=""; cap=""; add=0
  if [ "$FLEET_LAUNCH_WIP_SHARED_TTL_S" -gt 0 ]; then
    now_s; ts=
    read -r ts base cap 2>/dev/null < "$WIP_SHARED_FILE"
    case "$ts" in ''|*[!0-9]*) ts=0 ;; esac
    if [ $((NOW - ts)) -ge "$FLEET_LAUNCH_WIP_SHARED_TTL_S" ]; then
      if wip_shared_refresh; then ts=; base=; cap=; read -r ts base cap 2>/dev/null < "$WIP_SHARED_FILE"
      elif [ $((NOW - ts)) -ge $((FLEET_LAUNCH_WIP_SHARED_TTL_S * 6)) ]; then base=""
      fi
    fi
    add=$(in_flight_addition)
  elif report=$(wip_helper); then
    base=$(printf '%s' "$report" | wip_json_field counted_claims)
    cap=$(printf '%s' "$report" | wip_json_field wip_cap)
    add=$(printf '%s' "$report" | wip_json_field in_flight_addition); add=${add:-0}
  fi
  case "$base" in ''|*[!0-9]*) echo "$(date -u +%FT%TZ) repository WIP count unreadable: not holding, the Dispatcher's own cap still applies"; return 0 ;; esac
  case "$cap" in ''|*[!0-9]*) echo "$(date -u +%FT%TZ) repository WIP count unreadable: not holding, the Dispatcher's own cap still applies"; return 0 ;; esac
  WIP_CLAIMS=$base; WIP_INFLIGHT=$add; WIP_COUNTED=$((base + add)); WIP_CAP=$cap; WIP_EFFECTIVE=$cap
  if grep -qxF -- "$ITEM" "$FLEET_LAUNCH_BREAKAGE_EXCEPTION_FILE" 2>/dev/null; then WIP_EFFECTIVE=$(( cap + 1 )); fi
  [ "$WIP_COUNTED" -lt "$WIP_EFFECTIVE" ]
}
log_wip_at_cap() {
  echo "$(date -u +%FT%TZ) repository WIP at cap: counted=$WIP_COUNTED cap=$WIP_CAP effective=$WIP_EFFECTIVE item=$ITEM (claims=$WIP_CLAIMS in-flight=$WIP_INFLIGHT): yield FIFO head"
}

# refresh_checkout: bring the target checkout to the fetched tip of origin's default branch. The branch
# is the one the remote's HEAD names, read with `git ls-remote --symref`, never assumed to be master.
# One refresh at a time per checkout. Prints the failing step and returns non-zero when it fails.
refresh_checkout() {
  local lock_file="$OUT/checkout-refresh-$REPO_NAME.lock"
  (
    flock -w 300 9 || { echo lock; exit 1; }
    branch=$(git -C "$REPO" ls-remote --symref origin HEAD 2>/dev/null | sed -n 's|^ref: refs/heads/\(.*\)[[:space:]]HEAD$|\1|p' | head -n 1)
    [ -n "$branch" ] || { echo default-branch; exit 1; }
    git -C "$REPO" fetch -q origin "$branch" 2>/dev/null || { echo fetch; exit 1; }
    git -C "$REPO" merge --ff-only -q FETCH_HEAD 2>/dev/null || { echo fast-forward; exit 1; }
    [ "$(git -C "$REPO" rev-parse HEAD 2>/dev/null)" = "$(git -C "$REPO" rev-parse FETCH_HEAD 2>/dev/null)" ] || { echo not-at-tip; exit 1; }
  ) 9>"$lock_file"
}
# checkout_at_origin_tip: refresh the checkout, or make a non-run exit that launches nothing and
# holds no factory slot (the exit trap removes any marker and the ticket).
checkout_at_origin_tip() {
  local step
  step=$(refresh_checkout) && return 0
  write_terminal "checkout-not-at-origin-tip step=${step:-unknown}"
  echo "$(date -u +%FT%TZ) checkout of $REPO is not at the origin tip (step ${step:-unknown}): no launch"
  report_dropped_ticket "checkout-not-at-origin-tip step=${step:-unknown}"
  exit 75
}
# size_screen: the pre-launch screen of the materialized workflow.toml against Fabro's per-file cap.
# A HOLD or ERROR verdict writes hold-item-<item> (owner, end condition and next step named), makes a
# non-run exit and is never re-ticketed; the seat re-screens the item once the launch build changes.
size_screen() {
  [ "$FLEET_LAUNCH_SIZE_SCREEN" = 1 ] || return 0
  local report="$OUT/$ITEM-size-screen.txt" hold="$FLEET_LAUNCH_ITEM_HOLD_DIR/hold-item-$ITEM" src verdict
  python3 -I "$FLEET_LAUNCH_SIZE_SCREEN_COMMAND" --repo "$REPO" --item "$ITEM" --threshold "$FLEET_LAUNCH_SIZE_SCREEN_THRESHOLD" > "$report" 2>&1; src=$?
  if [ "$src" = 0 ]; then echo "$(date -u +%FT%TZ) size screen LAUNCH: $(grep -m1 -iE 'bytes|LAUNCH' "$report" | cut -c1-200)"; return 0; fi
  [ "$src" = 3 ] && verdict=OVER-THRESHOLD || verdict=ERROR
  if [ ! -e "$hold" ]; then
    {
      printf '%s\n' "SIZE-SCREEN, NO AUTO RE-TICKET (launcher size_screen $(date -u +%FT%TZ), rc=$src): materialized workflow.toml screen verdict $verdict at threshold $FLEET_LAUNCH_SIZE_SCREEN_THRESHOLD B (Fabro cap 524,288 B). $(tail -2 "$report" | tr '\n' ' ' | cut -c1-400) Re-ticket after the compression fix rolls (re-screen first)."
      printf '%s\n' "OWNER: legacy-dispatcher-agent." "END CONDITION: the workflow.toml compression fix is in the launch build AND a re-run of wfsize-screen.py for this item returns LAUNCH." "NEXT STEP: legacy-dispatcher-agent re-screens this item each pass after a launch-build roll; on LAUNCH it lifts this file and re-tickets."
    } > "$hold.tmp.$$" && mv "$hold.tmp.$$" "$hold"
  fi
  [ -n "$marker" ] && { rm -f "$marker"; marker=""; }
  release_lock
  write_terminal "size-screen verdict=$verdict rc=$src"
  echo "$(date -u +%FT%TZ) size screen HOLD rc=$src: $(tail -1 "$report" | cut -c1-300): no slot, no launch, hold-item written"
  exit_comment=always
  report_dropped_ticket "size-screen verdict=$verdict rc=$src"
  exit 4
}

echo "=== fleet-launch dispatch $ITEM at $(date -u +%FT%TZ) (wrapper: $(wrapper_description))"
ready_check() {
  local p pick
  p=$(installed_plugin_dir) || return 1
  if [ -n "${REWORK:-}" ]; then
    # A rework:pending row is `active`, so it is never in ready_items(); ask the Dispatcher's own loop
    # selection (the path drive impl:<id> runs) whether it would pick this item.
    pick=$(cd "$REPO" && wrap -- python3 "$p/scripts/bin/dispatcher.py" loop --repo "$REPO" --budget 1 --item "$ITEM" --dry-run --json --invoker "claude:$SEAT" 2>/dev/null)
    if printf '%s' "$pick" | python3 -c 'import json,sys; rows=json.loads(sys.stdin.read() or "[]"); sys.exit(0 if any(r.get("stage")=="loop-pick" and r.get("status")=="dry-run" and r.get("work_item_id")==sys.argv[1] for r in rows) else 3)' "$ITEM"; then
      echo "READY-CHECK $ITEM: REWORK, the Dispatcher's loop dry-run picks it"; return 0
    fi
    echo "READY-CHECK $ITEM: REWORK, the Dispatcher's loop dry-run does NOT pick it"; return 3
  fi
  (cd "$REPO" && wrap -- python3 "$FLEET_LAUNCH_DIR/ready-set-check.py" "$p" "$REPO" "$ITEM" 2>/dev/null)
}
# ready_refused: one refused ready-set check. The refusal is retried on the next poll until
# FLEET_LAUNCH_READY_RETRY_POLLS polls have been tried; then the launcher gives up, naming the last reason
# and the polls tried in its terminal line and, unconditionally, in a ledger comment on the item.
ready_refused() {
  local reason=${rcout:-no output, rc=$rcrc}
  ready_refusals=$((ready_refusals + 1))
  echo "$(date -u +%FT%TZ) ready-set check refused (rc=$rcrc, poll $ready_refusals of $FLEET_LAUNCH_READY_RETRY_POLLS): $1"
  [ "$ready_refusals" -lt "$FLEET_LAUNCH_READY_RETRY_POLLS" ] && return 0
  exit_cause="ready-set check refused: last reason: $reason; $ready_refusals polls tried"
  exit_comment=always
  exit 3
}
# host_only_screen: the shared factory-safety routing predicate, obtained from the Dispatcher, never
# re-implemented here. A host-only verdict is a non-run exit with one ledger comment; a command that
# cannot answer is not read as host_only: false, and the next gate (the Dispatcher's own refusal) applies.
host_only_screen() {
  local p verdict reason
  p=$(installed_plugin_dir) || return 1
  verdict=$(cd "$REPO" && wrap -- python3 "$p/scripts/bin/dispatcher.py" host-only --repo "$REPO" --item "$ITEM" --json 2>/dev/null) || { echo "$(date -u +%FT%TZ) host-only screen could not answer: proceeding, the Dispatcher's own refusal still applies"; return 0; }
  reason=$(printf '%s' "$verdict" | python3 -c 'import json,sys
try:
    d = json.loads(sys.stdin.read() or "{}")
except ValueError:
    sys.exit(1)
if d.get("host_only") is True:
    print(d.get("reason") or "host-only")
    sys.exit(0)
sys.exit(3)' 2>/dev/null); local rc=$?
  if [ "$rc" = 0 ]; then
    write_terminal host-only
    echo "$(date -u +%FT%TZ) host-only screen: $ITEM is host-only ($reason): no mutex, no preflight, no launch"
    exit_comment=always
    [ -n "$plugin" ] || plugin="$p"
    ledger_comment "Fleet launcher $SEAT dropped ticket ${ticket_number:-none} for $ITEM: the Dispatcher's host-only predicate reports it host-only ($reason). No factory may run it; this exit was not a run ending and the item's status is unchanged." \
      || echo "$(date -u +%FT%TZ) ledger comment for $ITEM failed: the host-only drop of ticket ${ticket_number:-none} was not recorded"
    terminal_written=1; exit_cause=""
    exit 5
  fi
  [ "$rc" = 3 ] || echo "$(date -u +%FT%TZ) host-only screen could not answer: proceeding, the Dispatcher's own refusal still applies"
  return 0
}
# tier_hold_screen: the Dispatcher's own spec-change tier hold predicate (the drain's admission filter),
# obtained from the Dispatcher, never re-implemented here, and answered BEFORE any launch ticket is taken so a
# held item costs no ticket, mutex turn or launcher pass. A hold is a non-run exit with one terminal line naming
# the hold reason and the linked proposed-change topic; a command that cannot answer (an installed build that
# predates it) is not read as unheld-by-proof, and the next gate (the Dispatcher's own refusal) applies.
tier_hold_screen() {
  local p verdict held
  p="$FLEET_LAUNCH_PLUGIN_CACHE/$(installed_build)"
  verdict=$(cd "$REPO" && wrap -- python3 "$p/scripts/bin/dispatcher.py" tier-hold --repo "$REPO" --item "$ITEM" --json 2>/dev/null) || { echo "$(date -u +%FT%TZ) tier-hold screen could not answer: proceeding, the Dispatcher's own refusal still applies"; return 0; }
  held=$(printf '%s' "$verdict" | python3 -c 'import json,sys
try:
    d = json.loads(sys.stdin.read() or "{}")
except ValueError:
    sys.exit(1)
if d.get("spec_change_hold") is True:
    print("%s %s" % (d.get("reason") or "held", d.get("topic") or "(none linked)"))
    sys.exit(0)
sys.exit(3)' 2>/dev/null); local rc=$?
  if [ "$rc" = 0 ]; then
    write_terminal tier-hold
    echo "$(date -u +%FT%TZ) tier-hold screen: $ITEM is held at the spec-change tier (reason and topic: $held): no ticket, no mutex, no preflight, no launch"
    exit_comment=always
    [ -n "$plugin" ] || plugin="$p"
    ledger_comment "Fleet launcher $SEAT exited for $ITEM before taking a launch ticket: the Dispatcher's spec-change tier hold predicate reports it held (reason and linked proposed-change topic: $held). This exit was not a run ending and the item's status is unchanged." \
      || echo "$(date -u +%FT%TZ) ledger comment for $ITEM failed: the tier-hold exit was not recorded"
    terminal_written=1; exit_cause=""
    exit 5
  fi
  [ "$rc" = 3 ] || echo "$(date -u +%FT%TZ) tier-hold screen could not answer: proceeding, the Dispatcher's own refusal still applies"
  return 0
}
tier_hold_screen
# A gmktec-only launch takes its FIFO ticket NOW and holds it while it polls, so a launcher queued
# later cannot win the next freed slot ahead of it, and a refusal retried below keeps its place.
if [ -n "${ONLY_GMK:-}" ] || [ -n "${ONLY_HL:-}" ] || [ -n "${ONLY_ARM:-}" ]; then
  ensure_ticket
  ticket_rc=$?
  if [ "$ticket_rc" = 2 ]; then
    echo "$(date -u +%FT%TZ) queue ticket already has a live launcher for $ITEM: do not start a duplicate"
    terminal_written=1
    exit 0
  fi
  [ "$ticket_rc" = 0 ] || { echo "$(date -u +%FT%TZ) could not take queue ticket for $ITEM"; exit 75; }
fi
# A seat-gated release starts blocked, so it cannot pass the ordinary ready-set
# check until its release valve runs.  Defer that check until after this
# launcher has taken the same FIFO, mutex, cap and in-flight-marker path as a
# queued launch; the post-release re-check below remains the admission guard.
if [ -n "${RELEASE_BLOCKED:-}" ]; then
  echo "$(date -u +%FT%TZ) seat-gated release: defer ready-set check until after capped FIFO binding"
else
  while :; do
    # See the repository-hold loop below: default TERM can reach EXIT cleanup
    # with a zero child status, so retain its cause while this retry waits too.
    exit_cause="signal TERM (this exit was not a run ending)"
    rcout=$(ready_check); rcrc=$?; echo "$(date -u +%FT%TZ) $rcout"
    if [ $rcrc = 0 ]; then exit_cause=""; break; fi
    ready_refused "$rcout"
    sleep "$FLEET_LAUNCH_POLL_S"
  done
fi
host_only_screen

# A queued launcher takes its Definition-of-Done preflight while it waits; a pass
# is reusable for FLEET_LAUNCH_PREFLIGHT_REUSE_S when it reaches the FIFO head.
pf_ok_at=0
queue_preflight_done=0
head_preflight_done=0
launch_preflight() {
  local now prc pf="$OUT/$ITEM-preflight-launch.txt"; now=$(date +%s)
  [ $(( now - pf_ok_at )) -lt "$FLEET_LAUNCH_PREFLIGHT_REUSE_S" ] && return 0
  # The preflight reads the checkout, so the checkout is brought to the origin tip first, and the
  # materialized workflow is screened for size before a model call is spent.
  checkout_at_origin_tip
  size_screen
  (cd "$REPO" && wrap -- env "${JUDGE_ENV[@]}" "$FLEET_LAUNCH_ORCH_REPO/dev-tooling/dod-preflight.sh" "$ITEM") > "$pf" 2>&1; prc=$?
  if [ $prc = 0 ]; then pf_ok_at=$now; echo "$(date -u +%FT%TZ) launch-time preflight PASS"; return 0; fi
  if [ $prc = 1 ]; then echo "$(date -u +%FT%TZ) launch-time preflight FAILED: $(tail -1 "$pf" | cut -c1-300): no slot, no launch"; exit_cause="launch-time preflight failed"; exit 4; fi
  # A fenced JSON verdict makes dod-preflight.sh exit 2; a failed outcome inside it is a finding.
  if [ $prc = 2 ] && grep -q '^{"outcome": "failed"' "$pf"; then echo "$(date -u +%FT%TZ) launch-time preflight FAILED (fenced verdict): $(grep -m1 '^{"outcome": "failed"' "$pf" | cut -c1-300): no slot, no launch"; exit_cause="launch-time preflight failed (fenced verdict)"; exit 4; fi
  echo "$(date -u +%FT%TZ) launch-time preflight TOOL FAILURE rc=$prc: no slot, no launch"; exit_cause="launch-time preflight tool failure rc=$prc"; exit 70
}
# early_preflight: a launcher queued within FLEET_LAUNCH_PREFLIGHT_AHEAD_MAX of the FIFO head runs
# its preflight (and the ready-set check before it) while it waits, once, so the next head launches
# at once; a held launcher does not, because a held preflight would be re-run every reuse window.
early_preflight() {
  [ "$queue_preflight_done" = 0 ] || return 0
  [ "$FIFO_CLASS" = hl ] || ! gmk_held || return 0
  scan_queue "$GMK_Q"
  [ "$RANK" -ge 1 ] && [ "$RANK" -le "$FLEET_LAUNCH_PREFLIGHT_AHEAD_MAX" ] || return 0
  if ! wip_green; then return 0; fi
  if [ -z "${RELEASE_BLOCKED:-}" ]; then
    rcout=$(ready_check); rcrc=$?
    if [ $rcrc != 0 ]; then ready_refused "$rcout"; return 0; fi
  fi
  queue_preflight_done=1
  echo "$(date -u +%FT%TZ) concurrent preflight: FIFO rank $RANK of $FLEET_LAUNCH_PREFLIGHT_AHEAD_MAX: preflighting while queued"
  launch_preflight
}
# head_preflight_while_capped: the head, with no reusable pass, starts its preflight while it waits
# for fleet capacity, once per launcher, instead of after the cap frees.
head_preflight_while_capped() {
  [ "$FIFO_CLASS" = hl ] && return 0
  [ "$head_preflight_done" = 1 ] && return 0
  gmk_held && return 0
  [ $(( $(date +%s) - pf_ok_at )) -lt "$FLEET_LAUNCH_PREFLIGHT_REUSE_S" ] && return 0
  head_preflight_done=1
  if [ -z "${RELEASE_BLOCKED:-}" ]; then
    rcout=$(ready_check); rcrc=$?
    if [ $rcrc != 0 ]; then ready_refused "$rcout"; return 0; fi
  fi
  echo "$(date -u +%FT%TZ) head preflight while the fleet is not green: overlapping the cap wait"
  launch_preflight
}

target=""; taken=0
# The give-up deadline is checked only AFTER the first evaluation, so a launcher
# whose start-up alone outlasts FLEET_LAUNCH_MAX_WAIT_S on a loaded host still
# reads the boards and reports why it gave up instead of giving up blind.
evaluated=0
last_ahead=""
# --- holds re-read until admission --------------------------------------------------------------
# After the drive is invoked the launcher re-reads every hold that applies to its launch on each poll
# it makes while waiting for the run to list, until the item reads active, the run lists or the
# drive exits. A hold set while the item still reads something other than active stops the drive.
drive_admitted=0
drive_stopped=0
descendant_pids() {
  local child
  for child in $(pgrep -P "$1" 2>/dev/null); do descendant_pids "$child"; echo "$child"; done
}
stop_drive() {
  local pids stop_deadline
  pids="$(descendant_pids "$drive_pid") $drive_pid"
  # shellcheck disable=SC2086 # a word-split pid list is the intent
  kill -TERM $pids 2>/dev/null
  stop_deadline=$(( SECONDS + FLEET_LAUNCH_STOP_GRACE_S ))
  while kill -0 "$drive_pid" 2>/dev/null && [ "$SECONDS" -lt "$stop_deadline" ]; do sleep 0.1; done
  # shellcheck disable=SC2086
  kill -KILL $pids 2>/dev/null
  wait "$drive_pid" 2>/dev/null
}
# drive_hold_poll: one poll. Returns 10 after it stopped the drive for a hold; otherwise 0.
drive_hold_poll() {
  local status
  [ "$drive_admitted" = 1 ] && return 0
  launch_hold_applies || return 0
  status=$(item_status)
  if [ "$status" = active ]; then drive_admitted=1; return 0; fi
  stop_drive
  rm -f "$marker"; marker=""; release_lock
  status=$(item_status) || status=active
  if [ "$status" = active ]; then stopped_after_admission; fi
  ensure_ticket
  case "$HOLD_SOURCE" in repository) yield_ticket repository-hold ;; canary) yield_ticket canary-hold ;; esac
  echo "$(date -u +%FT%TZ) hold set before admission: stopped the drive for $ITEM (ticket ${ticket_number:-none}): $HOLD_DESC"
  drive_stopped=1
  return 10
}
# stopped_after_admission: the drive admitted the item before the stop took effect. The terminal
# line is written first, then the one ledger comment; no ticket is re-taken.
stopped_after_admission() {
  local body
  echo "$(date -u +%FT%TZ) hold set before admission: stopped the drive for $ITEM (ticket ${ticket_number:-none}): $HOLD_DESC"
  write_terminal stopped-after-admission
  body="Fleet launcher $SEAT stopped its drive for $ITEM after a hold appeared (${HOLD_DESC}), but the drive had already admitted the item, so the item reads active with a pending claim stamp. This exit was not a run ending: ticket ${ticket_number:-none} was dropped and not re-taken. Remedy: the operator move valve (drive --action move:$ITEM:<status>) for the claim."
  ledger_comment "$body" \
    || echo "$(date -u +%FT%TZ) ledger comment for $ITEM failed: the stopped-after-admission note was not recorded"
  exit 75
}
# launch_point_clear <factory>: the re-reads every launch makes under the mutex, after the binding count.
# Succeeds when nothing stops the launch; otherwise it has released the marker and the mutex (and
# yielded the ticket for a repository or canary hold) and logged why.
launch_point_clear() {
  if script_changed; then
    rm -f "$marker"; marker=""; release_lock; echo "$(date -u +%FT%TZ) launcher script changed on disk before launch: released the mutex and marker, keeping the ticket"; return 1
  elif repository_hold_applies dispatch; then
    rm -f "$marker"; marker=""; yield_ticket repository-hold; log_repository_hold; release_lock; return 1
  elif canary_held; then
    rm -f "$marker"; marker=""; yield_ticket canary-hold; log_canary_hold; release_lock; return 1
  elif [ "$1" != mi-homelab ] && [ "$1" != homelab-worker-arm64 ] && gmk_held; then
    rm -f "$marker"; marker=""; release_lock; echo "$(date -u +%FT%TZ) hold file present at the launch point ($GMK_HOLD_FILE): released the mutex and marker, keeping the ticket"; return 1
  fi
  return 0
}

while :; do
  target=""; drive_stopped=0; drive_admitted=0
  while [ -z "$target" ]; do
    reexec_on_script_change
    # TERM uses bash's default action because bash 5.2 can fail to parse a
    # TERM trap while a command substitution is active.  Arm the non-run exit
    # description before the hold read so EXIT cleanup still records TERM when
    # bash reports a successful interrupted child wait to that cleanup.
    exit_cause="signal TERM (this exit was not a run ending)"
    if repository_hold_applies dispatch; then
      [ "$evaluated" = 0 ] || [ "$SECONDS" -lt "$wait_deadline" ] || give_up
      evaluated=1
      ensure_ticket
      yield_ticket repository-hold
      log_repository_hold
      sleep "$FLEET_LAUNCH_POLL_S"
      continue
    fi
    if canary_held; then
      [ "$evaluated" = 0 ] || [ "$SECONDS" -lt "$wait_deadline" ] || give_up
      evaluated=1
      ensure_ticket
      yield_ticket canary-hold
      log_canary_hold
      sleep "$FLEET_LAUNCH_POLL_S"
      continue
    fi
    if [ -n "$ticket" ] && [ -f "$ticket" ]; then
      # A ticket yielding on the repository WIP gate re-reads only that count until it has room.
      if ticket_yielding_wip; then
        if ! wip_green; then
          [ "$evaluated" = 0 ] || [ "$SECONDS" -lt "$wait_deadline" ] || give_up
          evaluated=1
          sleep "$FLEET_LAUNCH_WIP_POLL_S"; continue
        fi
        restore_ticket
        echo "$(date -u +%FT%TZ) repository WIP has room (counted=$WIP_COUNTED cap=$WIP_CAP): FIFO place restored"
      fi
      # Head-only polling: a launcher behind the head re-checks only its place, woken by a change to the
      # queue directory, and spends that wait on its own Definition-of-Done preflight.
      scan_queue "$GMK_Q"; ahead=$OLT
      if [ -n "$ahead" ] && [ "$ahead" != "$ticket" ]; then
        [ "$evaluated" = 0 ] || [ "$SECONDS" -lt "$wait_deadline" ] || give_up
        evaluated=1
        if [ "$ahead" != "$last_ahead" ]; then echo "$(date -u +%FT%TZ) queued behind an older gmktec ticket: $(tr '\n' ' ' < "$ahead" 2>/dev/null | sed 's/ *$//')"; fi
        last_ahead=$ahead
        early_preflight
        wait_queue_change
        continue
      fi
    fi
    # The repository WIP gate runs before anything that costs a model call: a launcher whose repository
    # is at its cap keeps its ticket, yields the FIFO head and runs no preflight until the count drops.
    if ! wip_green; then
      [ "$evaluated" = 0 ] || [ "$SECONDS" -lt "$wait_deadline" ] || give_up
      evaluated=1
      ensure_ticket
      yield_ticket repository-wip
      log_wip_at_cap
      sleep "$FLEET_LAUNCH_WIP_POLL_S"
      continue
    fi
    restore_ticket
    [ "$evaluated" = 0 ] || [ "$SECONDS" -lt "$wait_deadline" ] || give_up
    evaluated=1
    gmk_idle=
    if [ -n "${ONLY_ARM:-}" ]; then
      # The arm64 lane is gated on its own capacity only; the fleet is read for the summary.
      read_fleet_cap; read_boards
    elif ! fleet_green; then
      echo "$(date -u +%FT%TZ) fleet not green: $(fleet_summary)"
      head_preflight_while_capped
      sleep "$FLEET_LAUNCH_POLL_S"; continue
    fi
    # Re-check the ready set before spending a preflight, so a launcher whose item left the ready set
    # while it waited exits instead of burning one (bounded by the same retry rule as the first check).
    # A seat-gated release stays blocked until its valve runs after the bind, so it is not re-checked here.
    if [ -z "${RELEASE_BLOCKED:-}" ]; then
      rcout=$(ready_check); rcrc=$?
      if [ $rcrc != 0 ]; then ready_refused "$rcout"; sleep "$FLEET_LAUNCH_POLL_S"; continue; fi
    fi
    # A held gmktec launcher skips its model-backed preflight while the hold lasts, so it runs once
    # after the lift, just before launch.
    if [ "$FIFO_CLASS" != hl ] && gmk_held; then echo "$(date -u +%FT%TZ) hold file present ($GMK_HOLD_FILE): $(gmk_hold_text): preflight skipped while held, wait"; sleep "$FLEET_LAUNCH_POLL_S"; continue; fi
    launch_preflight
    if [ -n "${ONLY_ARM:-}" ]; then
      if arm_green; then
        echo "$(date -u +%FT%TZ) homelab-worker-arm64 green (arm_inflight=$arm_inflight cap=$FLEET_LAUNCH_ARM_CAP fleet=$fleet): queue for the gmktec mutex"
        if take_mutex "$GMK_Q" "$GMK_LOCK"; then
          taken=$(date +%s)
          if bind_count homelab-worker-arm64 && [ "$arm_live" -lt "$FLEET_LAUNCH_ARM_CAP" ]; then
            if launch_point_clear homelab-worker-arm64; then drop_ticket; target=homelab-worker-arm64; break; fi
            continue
          fi
          [ -n "$marker" ] && { rm -f "$marker"; marker=""; }
          echo "$(date -u +%FT%TZ) under the gmktec mutex: homelab-worker-arm64 no longer green (arm_inflight=$arm_inflight fleet=$fleet): release"; release_lock
        fi
      else echo "$(date -u +%FT%TZ) homelab-worker-arm64 not green: enrolled=$([ -e "$FLEET_LAUNCH_ARM_ENROLLED_FILE" ] && echo yes || echo no) arm_inflight=$arm_inflight cap=$FLEET_LAUNCH_ARM_CAP"; fi
      sleep "$FLEET_LAUNCH_POLL_S"; continue
    fi
    if [ -n "${ONLY_HL:-}" ]; then
      if hl_green; then
        echo "$(date -u +%FT%TZ) mi-homelab green (live=$hl_live fleet=$fleet): queue for the gmktec mutex"
        if take_mutex "$GMK_Q" "$GMK_LOCK"; then
          taken=$(date +%s)
          if bind_count mi-homelab && hl_green; then
            if launch_point_clear mi-homelab; then drop_ticket; target=mi-homelab; break; fi
            continue
          fi
          [ -n "$marker" ] && { rm -f "$marker"; marker=""; }
          echo "$(date -u +%FT%TZ) under the gmktec mutex: mi-homelab no longer green (hl=$hl_live fleet=$fleet): release"; release_lock
        fi
      else echo "$(date -u +%FT%TZ) mi-homelab not green: live=$hl_live cap=$(hl_cap)"; fi
      sleep "$FLEET_LAUNCH_POLL_S"; continue
    fi
    if [ "$(gmk_target)" = candidate ]; then
      # The gmktec target setting selects the candidate instance: launch onto it only while its live run
      # count is below the candidate cap. An absent cap reads as 0 and an unreadable count holds.
      if { [ -z "${CAPTURE_NULL:-}" ] || [ "${CAPTURE_EXPECT:-}" = petri ] || [ "${CAPTURE_EXPECT:-}" = candidate ]; } && candidate_green; then
        echo "$(date -u +%FT%TZ) gmktec candidate green (live=$candidate_live cap=$(candidate_cap) fleet=$fleet): queue for the gmktec mutex"
        if take_mutex "$GMK_Q" "$GMK_LOCK"; then
          taken=$(date +%s)
          if bind_count candidate && candidate_green && [ "$(gmk_target)" = candidate ]; then
            if launch_point_clear candidate; then drop_ticket; target=candidate; break; fi
            continue
          fi
          [ -n "$marker" ] && { rm -f "$marker"; marker=""; }
          echo "$(date -u +%FT%TZ) under the gmktec mutex: candidate no longer green (live=$candidate_live fleet=$fleet): release"; release_lock
        fi
      else echo "$(date -u +%FT%TZ) gmktec candidate not green: live=$candidate_live cap=$(candidate_cap)"; fi
      sleep "$FLEET_LAUNCH_POLL_S"; continue
    fi
    if { [ -z "${CAPTURE_NULL:-}" ] || [ "${CAPTURE_EXPECT:-}" = petri ] || [ "${CAPTURE_EXPECT:-}" = candidate ]; } && gmk_green; then
      echo "$(date -u +%FT%TZ) gmktec green (live=$gmk_live hl=$hl_live idle=$gmk_idle fleet=$fleet): queue for the gmktec mutex"
      if take_mutex "$GMK_Q" "$GMK_LOCK"; then
        taken=$(date +%s)
        if bind_count petri && gmk_green && [ "$(gmk_target)" = petri ]; then
          if launch_point_clear petri; then drop_ticket; target=petri; break; fi
          continue
        fi
        [ -n "$marker" ] && { rm -f "$marker"; marker=""; }
        echo "$(date -u +%FT%TZ) under the gmktec mutex: no longer green (gmktec=$gmk_live fleet=$fleet): release"; release_lock
      fi
      sleep "$FLEET_LAUNCH_POLL_S"; continue
    fi
    echo "$(date -u +%FT%TZ) no factory green: gmktec=$gmk_live (idle ${gmk_idle:-?}) markers=$markers fleet=$fleet/$FLEET_CAP"
    sleep "$FLEET_LAUNCH_POLL_S"
  done

  # Release the launch mutex right after the binding count; the in-flight marker stays until the run
  # lists or the dispatch exits.
  release_lock; echo "$(date -u +%FT%TZ) mutex released after the count (marker kept)"
  case "$target" in
    petri)
      FABRO_DEV_TOKEN__petri=$(ssh -o BatchMode=yes "$FLEET_LAUNCH_GMK_SSH" cat "$FLEET_LAUNCH_GMK_SERVER_ENV" | sed -n 's/^FABRO_DEV_TOKEN=//p' | tail -n 1)
      export FABRO_DEV_TOKEN__petri
      tserver=$GMK ;;
    candidate)
      FABRO_DEV_TOKEN__candidate=$(ssh -o BatchMode=yes "$FLEET_LAUNCH_GMK_SSH" cat "$FLEET_LAUNCH_GMK_CANDIDATE_SERVER_ENV" | sed -n 's/^FABRO_DEV_TOKEN=//p' | tail -n 1)
      export FABRO_DEV_TOKEN__candidate
      tserver=$GMK_CANDIDATE ;;
    homelab-worker-arm64) tserver=$ARM ;;
    *) tserver=$HL ;;
  esac
  if [ -n "${CAPTURE_NULL:-}" ]; then
    cexp=${CAPTURE_EXPECT:-petri}
    # A gmktec capture launch expects whichever gmktec instance the target setting selected.
    case "$cexp:$target" in petri:candidate|candidate:petri) cexp=$target ;; esac
    [ "$target" = "$cexp" ] || { echo "CAPTURE_NULL but target=$target (expected $cexp): refuse"; exit_cause="CAPTURE_NULL target $target is not the expected $cexp"; exit 70; }
    case "$target" in
      # The repositories' default_factory is petri, so a registry-resolved launch would land on :32276:
      # a candidate or arm64 capture names its instance.
      candidate|homelab-worker-arm64) export LIVESPEC_FABRO_FACTORY=$target; echo "$(date -u +%FT%TZ) CAPTURE_NULL: target=$target, LIVESPEC_FABRO_FACTORY=$target" ;;
      *) unset LIVESPEC_FABRO_FACTORY; echo "$(date -u +%FT%TZ) CAPTURE_NULL: LIVESPEC_FABRO_FACTORY unset, no --factory" ;;
    esac
  else
    export LIVESPEC_FABRO_FACTORY=$target
  fi
  checkout_at_origin_tip
  plugin=$(installed_plugin_dir) || { rm -f "$marker"; marker=""; release_lock; exit_cause="build unresolved"; exit 70; }
  build=${plugin##*/}
  build_version=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$plugin/plugin.json" 2>/dev/null)
  cred=$(cd "$REPO" && wrap -- timeout 120 python3 "$plugin/scripts/bin/dispatcher.py" claude-cred-status 2>&1); cred_rc=$?
  # stderr is kept: a credential_wrapper refusal ("required credential env absent", naming the missing
  # variables) is the only record of WHY the probe failed, and discarding it printed an empty probe output.
  printf '%s\n' "$cred" | grep -q "is usable" || { echo "$(date -u +%FT%TZ) credential probe NOT usable (rc=$cred_rc): hold, no launch"; printf '%s\n' "$cred" | tail -12 | cut -c1-600; rm -f "$marker"; marker=""; release_lock; exit_cause="credential probe not usable"; exit 75; }
  echo "$(date -u +%FT%TZ) credential probe usable (HTTP 200)"
  if [ -n "${RELEASE_BLOCKED:-}" ]; then
    rel=$(cd "$REPO" && wrap -- python3 "$plugin/scripts/bin/drive.py" --repo "$REPO" --action "resolve-blocked:${ITEM}:ready" --invoker "claude:$SEAT" --json 2>&1); rrc=$?
    echo "$(date -u +%FT%TZ) resolve-blocked:${ITEM}:ready rc=$rrc $(printf '%s' "$rel" | tr '\n' ' ' | cut -c1-300)"
    [ $rrc = 0 ] || { echo "release refused: no launch"; exit_cause="resolve-blocked release refused rc=$rrc"; exit 75; }
  fi
  rcout=$(ready_check); rcrc=$?
  if [ $rcrc != 0 ]; then
    # This launcher has dropped its ticket at the bind: release the marker, re-take the ticket at the same
    # number and poll again, up to the same bound as the first check.
    echo "$(date -u +%FT%TZ) ready-set re-check refused before launch: $rcout"; rm -f "$marker"; marker=""; release_lock
    ready_refused "$rcout"; ensure_ticket; sleep "$FLEET_LAUNCH_POLL_S"; continue
  fi
  # The configured ACP overrides: one --acp-node argument per non-empty, non-comment line, in file order.
  ACP_ARGS=()
  if [ -s "$FLEET_LAUNCH_ACP_OVERRIDES_FILE" ]; then
    while IFS= read -r line || [ -n "$line" ]; do case "$line" in ""|"#"*) ;; *) ACP_ARGS+=(--acp-node "$line") ;; esac; done < "$FLEET_LAUNCH_ACP_OVERRIDES_FILE"
  fi
  echo "$(date -u +%FT%TZ) acp overrides: $(( ${#ACP_ARGS[@]} / 2 )) --acp-node arguments from $FLEET_LAUNCH_ACP_OVERRIDES_FILE"
  echo "$(date -u +%FT%TZ) LAUNCH target=$target head=$(git -C "$REPO" rev-parse --short HEAD) build=$build build-source=$(build_source) version=${build_version:-?}"
  # One-shot: this item's freeze-allowlist line is consumed at LAUNCH, so a pre-listing re-ticket
  # waits behind the hold like any other ticket.
  [ "$target" = mi-homelab ] || [ "$target" = homelab-worker-arm64 ] || consume_allowlist_line LAUNCH
  # The drive is EXEC'd in its subshell so the wrapper chain is this launcher's direct child and
  # `wait "$drive_pid"` reaps it. A subshell that ends in the `wrap` function instead leaves the
  # chain a grandchild: when stop_drive kills both, the chain is re-parented to PID 1 (or a
  # subreaper) and stays a zombie wherever that parent does not reap orphans, as CI containers do
  # not, so `kill -0` keeps reading the stopped drive as alive (Scenario 330 cases 20a and 20e
  # failed only in CI on 2026-11-15). The harness runs under a non-reaping subreaper for the same
  # reason, so this shape is now checked everywhere.
  (cd "$REPO" && wrapper_chain && exec "${WRAP_CHAIN[@]}" env LIVESPEC_FACTORY_READ_WRAPPER="$FLEET_LAUNCH_DEFAULT_WRAPPER" "${JUDGE_ENV[@]}" python3 "$plugin/scripts/bin/drive.py" --repo "$REPO" --action "impl:$ITEM" --invoker "claude:$SEAT" "${ACP_ARGS[@]}" --json) > "$OUT/$ITEM-r267.json" 2>"$OUT/$ITEM-r267.stderr" &
  drive_pid=$!
  if [ -n "${CAPTURE_NULL:-}" ]; then
    # Watch for the first fabro run of THIS item and check that its argv names the expected server.
    # A candidate counts only when its argv[0] basename is fabro and argv[1] is run: a bare `pgrep -f`
    # also matched seat shells whose command line merely contained "fabro run" and the item id.
    is_fabro_run() { local a0="" a1=""; { IFS= read -r -d '' a0 && IFS= read -r -d '' a1; } < "/proc/$1/cmdline" 2>/dev/null || return 1; [ "${a0##*/}" = fabro ] && [ "$a1" = run ]; }
    while kill -0 "$drive_pid" 2>/dev/null; do
      fp=$(pgrep -u "$(id -u)" -f "fabro run" | while read -r p; do is_fabro_run "$p" && grep -qa -- "$ITEM" "/proc/$p/environ" "/proc/$p/cmdline" 2>/dev/null && echo "$p"; done | head -1)
      if [ -z "$fp" ]; then
        # Fall back to any fabro run descended from the drive, walking /proc/<pid>/stat.
        for p in $(pgrep -f "fabro run"); do is_fabro_run "$p" || continue; anc=$p; hop=$p; while [ "$anc" -gt 1 ]; do [ "$anc" = "$drive_pid" ] && { fp=$p; break 2; }; anc=""; read -r _ _ _ anc _ < "/proc/$hop/stat" 2>/dev/null; [ -n "$anc" ] || break; hop=$anc; done; done
      fi
      if [ -n "$fp" ]; then
        argv=$(tr '\0' ' ' < "/proc/$fp/cmdline" 2>/dev/null)
        echo "$(date -u +%FT%TZ) CAPTURE fabro run pid=$fp argv: $argv" | tee "$OUT/$ITEM-r267.capture-argv"
        # An exited or zombie process reads an empty cmdline: that is "process gone", not a bad argv.
        if [ -z "${argv// /}" ]; then echo "$(date -u +%FT%TZ) CAPTURE fabro run pid=$fp EXITED before its argv could be read: not a bad argv, no kill; see the drive outcome"; break; fi
        if printf '%s' "$argv" | grep -q -- "--server $tserver"; then echo "$(date -u +%FT%TZ) CAPTURE argv OK: --server $tserver"; else
          kill -TERM "$fp" 2>/dev/null; echo "$(date -u +%FT%TZ) CAPTURE FAILURE: argv lacks --server $tserver; killed fabro run pid $fp"; fi
        break
      fi
      drive_hold_poll || break
      sleep "$FLEET_LAUNCH_LISTING_POLL_S"
    done
  fi
  run_row=""
  while [ "$drive_stopped" = 0 ]; do
    run_row=$(board_rows "$FABRO" "$tserver" | awk -v it="$ITEM" '$4==it {print; exit}')
    if [ -n "$run_row" ]; then run_listed=1; echo "$(date -u +%FT%TZ) LISTED on $target: $run_row"; break; fi
    if ! kill -0 "$drive_pid" 2>/dev/null; then echo "$(date -u +%FT%TZ) drive exited before listing"; break; fi
    drive_hold_poll || break
    if [ -n "$lock" ] && [ $(( $(date +%s) - taken )) -ge "$FLEET_LAUNCH_MUTEX_HOLD_S" ]; then echo "$(date -u +%FT%TZ) mutex hold elapsed: release (marker kept until listing or drive exit)"; release_lock; fi
    sleep "$FLEET_LAUNCH_LISTING_POLL_S"
  done
  [ "$drive_stopped" = 1 ] && continue
  break
done
release_lock; rm -f "$marker"; marker=""
echo "$(date -u +%FT%TZ) target=$target build=$build version=${build_version:-?} listed=${run_row:-none}" > "$OUT/$ITEM-r267.verdict"
wait "$drive_pid"; rc=$?
echo "$(date -u +%FT%TZ) drive rc=$rc"
echo "$(date -u +%FT%TZ) drive rc=$rc" >> "$OUT/$ITEM-r267.verdict"
# A successful drive can submit its run after the listing poll read a shared,
# still-young snapshot. Read the factory directly once more before classifying
# that exit as early: re-ticketing an item whose run has already listed can
# strand the launcher behind its own run at the fleet cap.
if [ -z "$run_row" ] && [ "$rc" -eq 0 ]; then
  run_row=$(board_rows_direct "$FABRO" "$tserver" | awk -v it="$ITEM" '$4==it {print; exit}')
  if [ -n "$run_row" ]; then
    run_listed=1
    echo "$(date -u +%FT%TZ) LISTED after drive exit on $target: $run_row"
  fi
fi
early_exit_state="$FLEET_LAUNCH_RETICKET_STATE_DIR/$ITEM.early-exits"
early_exit_log="$FLEET_LAUNCH_RETICKET_STATE_DIR/$ITEM.reticket.log"
if [ -n "$run_row" ]; then
  # A launched run listed: the consecutive early-exit count for this item starts over.
  rm -f "$early_exit_state"
else
  # The drive ended without its run listing, whatever its exit status: a drive that exits 0 first is an
  # early exit too, so the item is never dropped from the queue.
  detail=$(python3 -I -c 'import json,sys
t=open(sys.argv[1]).read(); d=json.loads(t[t.find("{"):]) if "{" in t else {}; s=(d.get("dispatcher") or {}).get("stdout_json")
print("; ".join(str(x.get("stage"))+" "+str(x.get("status"))+": "+str(x.get("detail")) for x in (s if isinstance(s,list) else []) if isinstance(x,dict)) or "no stdout_json detail")' "$OUT/$ITEM-r267.json" 2>/dev/null)
  echo "$(date -u +%FT%TZ) early-exit detail: ${detail:-<unreadable>}"
  # A goal template preflight failure fails the same way on every retry until the item's record is
  # repaired, and a stage or status ending in -refused is a permanent refusal: neither is re-ticketed.
  refusal=$(drive_refusal_kind "$OUT/$ITEM-r267.json") || refusal=""
  if [ -n "$refusal" ]; then
    write_terminal "$refusal"
    report_dropped_ticket "$refusal"
    exit "$rc"
  fi
  # A permanent pre-dispatch refusal (exit 5) is not an early exit either.
  if [ "$rc" -eq 5 ]; then
    write_terminal refused
    report_dropped_ticket "refused: $(grep -m1 '^REFUSED:' "$OUT/$ITEM-r267.stderr" 2>/dev/null | sed 's/{[{%#]/( /g' | cut -c1-400)"
    exit "$rc"
  fi
  # A zero exit with no final board listing is only re-ticketed while the
  # ledger still says ready. Once the item has moved on, this launcher has no
  # run to wait for and must record its non-run exit rather than take a ticket.
  if [ "$rc" -eq 0 ]; then
    exit_item_status=$(item_status) || exit_item_status=unreadable
    if [ "$exit_item_status" != ready ]; then
      write_terminal "drive-exit-early drive-exit=0 item-status=$exit_item_status"
      exit 0
    fi
  fi
  # Any other exit before the run lists re-takes a ticket at the same ticket number, after a
  # delay set by how many consecutive early exits this item has had, unless the item has had more
  # than FLEET_LAUNCH_RETICKET_MAX_IN_WINDOW of them inside the window. The mutex and the in-flight
  # marker are already released, and no ticket is held while the launcher waits.
  mkdir -p "$FLEET_LAUNCH_RETICKET_STATE_DIR"
  now_s; printf '%s\n' "$NOW" >> "$early_exit_log"
  in_window=$(awk -v cut=$(( NOW - FLEET_LAUNCH_RETICKET_WINDOW_S )) '$1 >= cut' "$early_exit_log" 2>/dev/null | grep -c .)
  if [ "$in_window" -gt "$FLEET_LAUNCH_RETICKET_MAX_IN_WINDOW" ]; then
    write_terminal "reticket-bound early-exits-in-window=$in_window window=${FLEET_LAUNCH_RETICKET_WINDOW_S}s"
    exit_comment=always
    report_dropped_ticket "reticket-bound: $in_window early exits within ${FLEET_LAUNCH_RETICKET_WINDOW_S}s; a person decides the next ticket"
    exit "$rc"
  fi
  early_exits=$(tr -dc 0-9 < "$early_exit_state" 2>/dev/null); early_exits=$(( ${early_exits:-0} + 1 ))
  printf '%s\n' "$early_exits" > "$early_exit_state"
  case $early_exits in 1) delay=$FLEET_LAUNCH_RETICKET_DELAY_1_S ;; 2) delay=$FLEET_LAUNCH_RETICKET_DELAY_2_S ;; *) delay=$FLEET_LAUNCH_RETICKET_DELAY_3_S ;; esac
  write_terminal "drive-exit-early drive-exit=$rc early-exits=$early_exits re-ticket-after=${delay}s"
  echo "$(date -u +%FT%TZ) drive exited before listing (rc=$rc, consecutive early exits $early_exits): re-ticket item=$ITEM at ticket ${ticket_number:-none} after ${delay}s"
  sleep "$delay" & wait $!
  exec env TICKET_NS="${ticket_number:-}" bash "$SELF" "${LAUNCHER_ARGS[@]}"
fi
[ "$run_listed" = 1 ] || exit_cause="drive exited before its run listed (drive rc=$rc)"
exit "$rc"
