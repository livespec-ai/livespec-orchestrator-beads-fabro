# shellcheck shell=bash
# PROVISIONAL / EXPERIMENTAL — fleet-launch's shared launcher functions.
#
# This directory is a stopgap; its first-class replacements are the livespec
# console application and the committed launch-loop tool bd-ib-jr6w7v (see
# README.md). Sourced by dispatch-dual.sh, resume-capped.sh and resume-repo.sh
# after config.sh. It defines functions only and reads the caller's REPO, ITEM,
# ticket and FIFO_CLASS variables; it changes nothing on disk unless a function
# below says so.
#
# Like config.sh and board-snapshot.sh, this file is read when a launcher starts
# and is not part of the launcher version launcher-versions.sh reports.

# --- the gate runner's stall cap ----------------------------------------------
# `just gate-start` (dev-tooling/gate-run.sh) ends the gate's WHOLE process group after
# LIVESPEC_SUITE_GREEN_STALL_SECONDS (900) without output. A launcher started through it was
# killed with its drive at 15m07s on four gate runs on 2026-11-17 while the factory run went on,
# so no host-side watchdog owned the run and a needs_human item sat active and claimed until
# reconcile-runs. The runner exports LIVESPEC_GATE_RUN_PROGRESS_STAMP into everything it runs;
# that variable is the marker.
#
# detach_if_under_gate_runner: call it once, right after launch-lib.sh is sourced, from a
# launcher that has set SELF and LAUNCHER_ARGS. Under the marker it re-executes the launcher in
# a NEW SESSION (setsid nohup) with the marker removed, so neither the runner's process-group
# kill nor a recursive detach can reach it, writes the child's output to a log file under
# FLEET_LAUNCH_STATE_DIR, names the detached pid and that log on stdout, and exits 0 at once.
# FLEET_LAUNCH_ALLOW_UNDER_GATE=1 opts out and runs in place. The detached child records one
# line naming its own pid, session and parent, then runs the launcher as it always did.
detach_if_under_gate_runner() {
  local log pid session stamp=absent
  if [ -n "${FLEET_LAUNCH_DETACHED_FROM:-}" ]; then
    session=$(sed 's/^.*) //' "/proc/$$/stat" 2>/dev/null | awk '{print $4}')
    [ -z "${LIVESPEC_GATE_RUN_PROGRESS_STAMP:-}" ] || stamp=present
    printf '%s detached launcher: pid=%s session=%s parent=%s gate-stamp=%s\n' "$(date -u +%FT%TZ)" "$$" "${session:-unknown}" \
      "$FLEET_LAUNCH_DETACHED_FROM" "$stamp"
    return 0
  fi
  [ -n "${LIVESPEC_GATE_RUN_PROGRESS_STAMP:-}" ] || return 0
  [ "${FLEET_LAUNCH_ALLOW_UNDER_GATE:-}" = 1 ] && return 0
  mkdir -p "$FLEET_LAUNCH_STATE_DIR" || { echo "fleet-launch: cannot create $FLEET_LAUNCH_STATE_DIR to detach under the gate runner" >&2; exit 1; }
  log="$FLEET_LAUNCH_STATE_DIR/detached-$(basename "$SELF" .sh)-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
  env -u LIVESPEC_GATE_RUN_PROGRESS_STAMP FLEET_LAUNCH_DETACHED_FROM="$$" setsid nohup bash "$SELF" "${LAUNCHER_ARGS[@]}" > "$log" 2>&1 < /dev/null &
  pid=$!
  printf 'fleet-launch: started under the gate runner, whose %ss stall cap would end this launcher and its drive; detached pid %s, log file %s\n' \
    "${LIVESPEC_SUITE_GREEN_STALL_SECONDS:-900}" "$pid" "$log"
  exit 0
}

# --- tenant credential wrapper -----------------------------------------------
# Every launch-time command that reaches the target repository's ledger or
# Dispatcher runs under that repository's committed `credential_wrapper`, the
# argv its own .livespec.jsonc declares, and a declared argv is ALWAYS run as
# written: the launcher never drops or shortens it. (A 2026-11-15 defect keyed on
# argv[0]'s BASENAME collapsed route C's argv -- the family wrapper followed by a
# /bin/sh hop that maps GITHUB_APP_ID_ORG onto GITHUB_APP_ID -- to the bare family
# wrapper, so launches minted as the personal App, which livespec-ai repositories
# refuse.) The resolver decides only NESTING: an argv whose first word is the
# default wrapper path itself runs as written (mode `committed`); any other
# tenant's argv runs NESTED inside the default wrapper, which supplies the Claude
# and fabro credentials the launcher's own steps need, with the family
# BEADS_DOLT_PASSWORD removed so the tenant's wrapper injects its own (mode
# `tenant`). No declared argv is the bare default wrapper (mode `default`).
# WRAPPER=<path> still overrides the whole chain (mode `override`).
TENANT_WRAPPER=()
TENANT_WRAPPER_MODE=default
# resolve_tenant_wrapper: sets TENANT_WRAPPER_MODE to override, default, committed,
# tenant or unreadable, and TENANT_WRAPPER to the declared argv. Returns 1 on unreadable.
resolve_tenant_wrapper() {
  local argv_file="$REPO/.livespec.jsonc" line
  TENANT_WRAPPER=()
  if [ -n "${WRAPPER:-}" ]; then TENANT_WRAPPER_MODE=override; return 0; fi
  if [ ! -e "$argv_file" ]; then TENANT_WRAPPER_MODE=default; return 0; fi
  if [ ! -r "$argv_file" ]; then TENANT_WRAPPER_MODE=unreadable; return 1; fi
  mapfile -t TENANT_WRAPPER < <(python3 - "$argv_file" <<'PY' 2>/dev/null
import json
import re
import sys

try:
    text = open(sys.argv[1], encoding="utf-8").read()
except OSError:
    print("UNREADABLE")
    sys.exit(0)
match = re.search(r'"credential_wrapper"\s*:\s*(\[[^\]]*\])', text)
if match is None:
    if '"credential_wrapper"' in text:
        print("UNREADABLE")
    sys.exit(0)
try:
    argv = json.loads(re.sub(r"//[^\n]*", "", match.group(1)))
except ValueError:
    print("UNREADABLE")
    sys.exit(0)
if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
    print("UNREADABLE")
    sys.exit(0)
for a in argv:
    print(a)
PY
)
  if [ "${#TENANT_WRAPPER[@]}" -eq 0 ]; then TENANT_WRAPPER_MODE=default; return 0; fi
  for line in "${TENANT_WRAPPER[@]}"; do
    [ "$line" = UNREADABLE ] && { TENANT_WRAPPER=(); TENANT_WRAPPER_MODE=unreadable; return 1; }
  done
  # Keyed on the declared argv's PRESENCE and its first word's exact path, never on a basename:
  # the argv is kept whole in both modes and only the nesting differs.
  if [ "${TENANT_WRAPPER[0]}" = "$FLEET_LAUNCH_DEFAULT_WRAPPER" ]; then TENANT_WRAPPER_MODE=committed; return 0; fi
  TENANT_WRAPPER_MODE=tenant
  return 0
}
# wrapper_chain: fills WRAP_CHAIN with the argv prefix the resolved mode runs a command under, so a
# caller that must `exec` (the slot-narrowing wrapper) composes the same chain `wrap` runs.
WRAP_CHAIN=()
wrapper_chain() {
  case $TENANT_WRAPPER_MODE in
    override) WRAP_CHAIN=("$WRAPPER" --) ;;
    committed) WRAP_CHAIN=("${TENANT_WRAPPER[@]}") ;;
    tenant) WRAP_CHAIN=("$FLEET_LAUNCH_DEFAULT_WRAPPER" -- env -u BEADS_DOLT_PASSWORD "${TENANT_WRAPPER[@]}") ;;
    *) WRAP_CHAIN=("$FLEET_LAUNCH_DEFAULT_WRAPPER" --) ;;
  esac
}
# wrap -- <command...>: run one launch-time command under the resolved wrapper chain.
wrap() {
  [ "${1:-}" = "--" ] && shift
  wrapper_chain
  "${WRAP_CHAIN[@]}" "$@"
}
# wrapper_description: one phrase for the log line.
wrapper_description() {
  case $TENANT_WRAPPER_MODE in
    override) printf 'WRAPPER=%s' "$WRAPPER" ;;
    committed) printf 'committed %s argv, %d words, run as written' "${TENANT_WRAPPER[0]##*/}" "${#TENANT_WRAPPER[@]}" ;;
    tenant) printf 'tenant %s nested in %s' "${TENANT_WRAPPER[0]##*/}" "${FLEET_LAUNCH_DEFAULT_WRAPPER##*/}" ;;
    *) printf 'default %s' "${FLEET_LAUNCH_DEFAULT_WRAPPER##*/}" ;;
  esac
}

# --- the installed plugin build ----------------------------------------------
installed_build() {
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print([e["version"] for e in d["plugins"][sys.argv[2]] if e.get("projectPath")==sys.argv[3]][0])' \
    "$FLEET_LAUNCH_PLUGIN_REGISTRY" "$FLEET_LAUNCH_PLUGIN_KEY" "$REPO" 2>/dev/null
}

# --- caps read live from state files -------------------------------------------
# read_cap_file <file> <fallback>: the one number a cap file holds, or the fallback.
read_cap_file() {
  local value=""
  [ -r "$1" ] && value=$(tr -dc 0-9 < "$1" 2>/dev/null)
  printf '%s' "${value:-$2}"
}
read_decimal_file() {
  local value=""
  [ -r "$1" ] && value=$(tr -dc 0-9. < "$1" 2>/dev/null)
  printf '%s' "${value:-$2}"
}
# shellcheck disable=SC2034 # read by the launchers' gates
read_fleet_cap() { FLEET_CAP=$(read_cap_file "$FLEET_LAUNCH_FLEET_CAP_FILE" 0); }
gmk_cap() { read_cap_file "$FLEET_LAUNCH_GMK_CAP_FILE" "$FLEET_LAUNCH_GMK_CAP"; }
hl_cap() { read_cap_file "$FLEET_LAUNCH_HL_CAP_FILE" "$FLEET_LAUNCH_HL_CAP"; }
candidate_cap() { read_cap_file "$FLEET_LAUNCH_GMK_CANDIDATE_CAP_FILE" "${FLEET_LAUNCH_GMK_CANDIDATE_CAP:-0}"; }
gmk_idle_floor() { read_decimal_file "$FLEET_LAUNCH_GMK_IDLE_FLOOR_FILE" "$FLEET_LAUNCH_GMK_MIN_IDLE"; }

# --- the gmktec hold, its releases and the canary hold -----------------------
# gmk_p1: the item has priority 1 in the ledger, read once per launcher; a priority
# that cannot be read is not priority 1, so the hold applies.
gmk_p1() {
  local out
  if [ -z "${ITEM_P1+x}" ]; then
    ITEM_P1=0
    [ -n "${plugin:-}" ] || plugin="$FLEET_LAUNCH_PLUGIN_CACHE/$(installed_build)"
    out=$(cd "$REPO" && wrap -- python3 "$FLEET_LAUNCH_DIR/ledger-item.py" priority "$plugin" "$REPO" "$ITEM" 2>/dev/null) || out=""
    out=$(printf '%s\n' "$out" | sed -n 's/^LEDGER-PRIORITY //p' | tail -n 1)
    [ "$out" = 1 ] && ITEM_P1=1
  fi
  [ "$ITEM_P1" = 1 ]
}
# allowlisted <item>: the freeze allowlist names the item, read at every check.
allowlisted() { grep -qxF -- "$1" "$FLEET_LAUNCH_FREEZE_ALLOWLIST_FILE" 2>/dev/null; }
# gmk_held: the gmktec hold file exists and releases neither by the allowlist nor by priority 1.
gmk_held() {
  [ -e "$GMK_HOLD_FILE" ] || return 1
  allowlisted "$ITEM" && return 1
  gmk_p1 && return 1
  return 0
}
gmk_hold_text() { tr '\n' ' ' < "$GMK_HOLD_FILE" 2>/dev/null | cut -c1-300 | sed 's/ *$//'; }
# consume_allowlist_line <LAUNCH|RESUME>: remove this item's one-shot line under the shared lock
# and log the grant, when the hold exists and the line is present.
consume_allowlist_line() {
  [ -e "$GMK_HOLD_FILE" ] && allowlisted "$ITEM" || return 0
  (
    flock -w 30 9 || exit 0
    { grep -vxF -- "$ITEM" "$FLEET_LAUNCH_FREEZE_ALLOWLIST_FILE" || true; } > "$FLEET_LAUNCH_FREEZE_ALLOWLIST_FILE.tmp.$$"
    mv "$FLEET_LAUNCH_FREEZE_ALLOWLIST_FILE.tmp.$$" "$FLEET_LAUNCH_FREEZE_ALLOWLIST_FILE"
    echo "$(date -u +%FT%TZ) $ITEM consumed at $1 pid=$$ build=${build:-unknown}" >> "$FLEET_LAUNCH_FREEZE_ALLOWLIST_CONSUMED_LOG"
  ) 9>"$FLEET_LAUNCH_FREEZE_ALLOWLIST_LOCK"
  echo "$(date -u +%FT%TZ) ONE-SHOT: freeze-allowlist line for $ITEM consumed at $1 ($(date -u +%FT%TZ))"
}
CANARY_HOLD_FILE="$FLEET_LAUNCH_CANARY_HOLD_DIR/canary-hold-repo-${REPO##*/}"
# canary_held: the target repository's canary hold exists and the exemption list does not name
# the item. The list is read at every check; an absent or unreadable list exempts no item.
canary_held() {
  [ -e "$CANARY_HOLD_FILE" ] || return 1
  grep -qxF -- "$ITEM" "$FLEET_LAUNCH_CANARY_EXEMPT_FILE" 2>/dev/null && return 1
  return 0
}
canary_hold_text() { head -c 300 "$CANARY_HOLD_FILE" 2>/dev/null | tr '\n' ' ' | sed 's/ *$//'; }

# --- the FIFO queue ------------------------------------------------------------
# Every launcher's ticket lives in one directory; a mi-homelab or arm64 launcher writes
# `server=hl` into its ticket and orders only among such tickets, while a gmktec launcher
# ignores them (the shared mutex and the fleet cap are unchanged).
# ticket_fields <file>: TK_PID, TK_ITEM, TK_HL (server=hl), TK_YIELD (held= or wip-wait=1).
ticket_fields() {
  local -a lines; local l
  TK_PID=; TK_ITEM=; TK_HL=0; TK_YIELD=0
  mapfile -t lines 2>/dev/null < "$1" || return 1
  for l in "${lines[@]}"; do
    if [ -z "$TK_PID" ]; then case "$l" in *pid=[0-9]*) TK_PID=${l#*pid=}; TK_PID=${TK_PID%%[!0-9]*} ;; esac; fi
    if [ -z "$TK_ITEM" ]; then case "$l" in *item=?*) TK_ITEM=${l#*item=}; TK_ITEM=${TK_ITEM%%[[:space:]]*} ;; esac; fi
    case "$l" in server=hl*) TK_HL=1 ;; held=*|wip-wait=1*) TK_YIELD=1 ;; esac
  done
  return 0
}
# report_stall <ticket-file> <pid>: a queue reader met a ticket whose launcher is no longer alive.
# Written to stderr, because the reader runs in a command substitution, and before the ticket is removed.
report_stall() {
  local f="$1" it name
  name=${f##*/}
  it=$(grep -oE 'item=[^ ]+' "$f" 2>/dev/null | head -1 | cut -d= -f2)
  echo "$(date -u +%FT%TZ) stall: item=${it:-unknown} ticket=${name%%-*} dead-pid=${2:-none}: the launcher for ticket file $name is gone"
} >&2
# scan_queue <queue-dir>: OLT is the oldest live ticket of this launcher's FIFO class that is not
# yielding and, while the gmktec hold exists, whose item the hold does not hold; RANK is this
# launcher's rank among those (0 when it is not ranked). Dead tickets are removed. The glob is
# ordered under C collation, so a ticket number extending a shorter one never sorts ahead of it.
scan_queue() {
  local LC_ALL=C
  local q="$1" f n=0 self_released=0
  OLT=; RANK=0
  # Only a launcher the hold does not hold skips held tickets: a held launcher cannot launch anyway,
  # and keeping the full order among held launchers lets them bind in ticket order at the lift.
  if [ "${FIFO_CLASS:-gmk}" != hl ] && [ -e "$GMK_HOLD_FILE" ] && ! gmk_held; then self_released=1; fi
  for f in "$q"/*; do
    [ -e "$f" ] || continue
    ticket_fields "$f" || continue
    if [ -n "$TK_PID" ] && kill -0 "$TK_PID" 2>/dev/null; then
      if [ "${FIFO_CLASS:-gmk}" = hl ]; then [ "$TK_HL" = 1 ] || continue; else [ "$TK_HL" = 1 ] && continue; fi
      [ "$TK_YIELD" = 1 ] && continue
      # Held queue head skipped: while the gmktec hold exists, another launcher's gmktec ticket whose
      # item the allowlist does not name is skipped like a yielding ticket; it keeps its number.
      if [ "$self_released" = 1 ] && [ "$f" != "${ticket:-}" ] && [ -n "$TK_ITEM" ] \
         && ! allowlisted "$TK_ITEM"; then continue; fi
      n=$((n+1)); [ -n "$OLT" ] || OLT=$f
      # shellcheck disable=SC2034 # the launcher's queued preflight reads RANK
      [ "$f" = "${ticket:-}" ] && { RANK=$n; return 0; }
    else
      report_stall "$f" "$TK_PID"
      rm -f "$f"
    fi
  done
  return 0
}
# oldest_live_ticket <queue-dir>: the oldest ticket scan_queue would bind next.
oldest_live_ticket() { scan_queue "$1"; printf '%s' "$OLT"; }
# nap <seconds>: a wait that forks nothing after its first call (a fifo read with a timeout).
_nap_fd=
nap() {
  if [ -z "$_nap_fd" ]; then
    local fifo="${TMPDIR:-/tmp}/fleet-launch-nap.$$" fd
    if mkfifo "$fifo" 2>/dev/null && exec {fd}<>"$fifo"; then _nap_fd=$fd; fi
    rm -f "$fifo" 2>/dev/null
  fi
  if [ -n "$_nap_fd" ]; then read -r -t "$1" -u "$_nap_fd" _ 2>/dev/null; else sleep "$1"; fi
  return 0
}
