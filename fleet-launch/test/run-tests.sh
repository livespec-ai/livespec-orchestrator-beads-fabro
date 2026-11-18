#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — part of fleet-launch/, a stopgap whose first-class
# replacements are the livespec console application and the committed launch-loop
# tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# Hermetic test harness for dispatch-dual.sh, the provisional launcher.
#
# WHY A HARNESS AND NOT A SYNTAX CHECK. `bash -n` accepts a launcher that has
# silently stopped reading a factory board: the edit that appended a trailing
# comment to a multi-statement line dropped the mi-homelab board read on
# 2026-10-24 and parsed perfectly. `SPECIFICATION/contracts.md` §"Provisional
# fleet launch scripts" therefore states outright that "A syntax check alone
# MUST NOT be treated as satisfying this obligation", and names the five gates
# the cases below exercise.
#
# HOW IT IS HERMETIC. Every host value dispatch-dual.sh reads is assigned in
# config.sh behind a `FLEET_LAUNCH_` environment override, so the launcher is
# pointed at a stub `fabro` serving board FIXTURES, a stub credential wrapper
# that answers for the ready-set check, the Definition-of-Done preflight, the
# credential probe and `drive.py`, a stub `ssh` on a prepended PATH, and
# throwaway queue, lock, in-flight and state directories. No real factory, no
# real `drive` dispatch, no network, no host mutation. bash plus POSIX utilities
# only, so it runs on any runner.
#
# EVERY REFUSAL CASE CARRIES ITS OWN POSITIVE CONTROL — the same inputs with the
# one gate opened, which MUST launch. A refusal that is never contrasted with a
# launch passes equally well when the launcher refuses everything, which is the
# failure this directory's README records as its most expensive defect.
#
# Exit 0 iff every case passes; non-zero with a summary otherwise.

set -uo pipefail

HARNESS_DIR=$(cd -- "$(dirname -- "$0")" && pwd -P)
LAUNCH_DIR=$(cd -- "$HARNESS_DIR/.." && pwd -P)
LAUNCHER="$LAUNCH_DIR/dispatch-dual.sh"
RESUME_LAUNCHER="$LAUNCH_DIR/resume-capped.sh"

if [ ! -f "$LAUNCHER" ] || [ ! -f "$RESUME_LAUNCHER" ]; then
    echo "run-tests.sh: launcher not found" >&2
    exit 1
fi

# shellcheck source=fleet-launch/test/scenario-watchdog.sh
. "$(dirname "$0")/scenario-watchdog.sh"

HARNESS_SLICE=${1:-all}
case "$HARNESS_SLICE" in
    all|scenario242|scenario297|scenario307|scenario312|scenario316|scenario330|queue-position|launcher-reexec|parity|gate-detach|probe-stderr) ;;
    *)
        echo "usage: run-tests.sh [scenario242|scenario297|scenario307|scenario312|scenario316|scenario330|queue-position|launcher-reexec|parity|gate-detach|probe-stderr]" >&2
        exit 2
        ;;
esac

# GNU sleep accepts hundredth-second durations.  That is the smallest useful
# non-zero launcher poll: zero would make the bounded loops spin rather than
# wait for the state they observe.  Export it because the stub wrapper runs in
# a child shell while it holds a launcher's preflight.
export HARNESS_POLL_S=0.01

WORK=$(mktemp -d)
LOAD_PIDS=""
stop_load() {
    local load_pid
    for load_pid in $LOAD_PIDS; do kill "$load_pid" 2>/dev/null || true; done
    for load_pid in $LOAD_PIDS; do wait "$load_pid" 2>/dev/null || true; done
    LOAD_PIDS=""
}
cleanup() {
    scenario_watchdog_stop
    stop_load
    rm -rf "$WORK"
}
trap cleanup EXIT
scenario_watchdog_start "$WORK"

PASS=0
FAIL=0
pass() { PASS=$((PASS + 1)); printf '  ok:   %s\n' "$1"; }
fail() { FAIL=$((FAIL + 1)); printf '  FAIL: %s\n' "$1" >&2; }

# The two stub server URLs. They are opaque to the launcher, which only passes
# them to `fabro ps -a --server`, so the stub discriminates boards on them.
GMK_URL="https://stub-gmktec.invalid:32276"
HL_URL="https://stub-mi-homelab.invalid:32277"
CANDIDATE_URL="https://stub-candidate.invalid:32278"
ARM_URL="https://stub-arm64.invalid:32279"

# --- the stubs ---------------------------------------------------------------
STUB="$WORK/stub"
mkdir -p "$STUB/bin"

# The stub `fabro`. `ps -a --server <url>` answers from a board FIXTURE file:
#   absent file  -> exit 1, which the launcher must read as an UNREADABLE board
#   empty file   -> exit 0 with nothing on stdout, a RETIRED/idle board
#   otherwise    -> the fixture, header line first
# It also lists one synthetic row per driven marker the stub `drive.py` wrote
# for that server, so a launch that has dispatched becomes visible on the board
# exactly as a real run does.
cat > "$STUB/fabro" <<'FABRO_STUB'
#!/usr/bin/env bash
set -u
server=""
previous=""
for argument in "$@"; do
    if [ "$previous" = --server ]; then server=$argument; fi
    previous=$argument
done
case $server in
    "$STUB_SERVER_GMK") board=$STUB_BOARD_GMK ;;
    "$STUB_SERVER_HL") board=$STUB_BOARD_HL ;;
    "$STUB_SERVER_CANDIDATE") board=$STUB_BOARD_CANDIDATE ;;
    "$STUB_SERVER_ARM") board=$STUB_BOARD_ARM ;;
    *) echo "stub fabro: no board fixture for server '$server'" >&2; exit 1 ;;
esac
# Every listing request is recorded, one server per line, so a case can count what the
# factory would have been asked; STUB_PS_DELAY_S makes a listing slow, as the petri server's is.
if [ -n "${STUB_PS_LOG:-}" ]; then printf '%s\n' "$server" >> "$STUB_PS_LOG"; fi
# Case 20c can hold the first board poll it observes after the item becomes
# active. The harness releases the stub drive only once this rendezvous exists,
# then releases the board read after the driven marker is present. Thus the
# listing's ordering is observed rather than inferred from a sleep.
if [ -n "${STUB_PS_ACTIVE_LISTING_RENDEZVOUS_FILE:-}" ] \
    && [ "$(cat "$STUB_ITEM_STATUS_FILE" 2>/dev/null)" = active ] \
    && [ ! -e "$STUB_PS_ACTIVE_LISTING_RENDEZVOUS_FILE" ]; then
    : > "$STUB_PS_ACTIVE_LISTING_RENDEZVOUS_FILE"
    deadline=$(( $(date +%s) + ${HARNESS_PREFLIGHT_HANG_GUARD_S:-300} ))
    while [ ! -e "$STUB_PS_ACTIVE_LISTING_RELEASE_FILE" ] && [ "$(date +%s)" -lt "$deadline" ]; do
        sleep "$HARNESS_POLL_S"
    done
fi
if [ -n "${STUB_PS_DELAY_S:-}" ]; then sleep "$STUB_PS_DELAY_S"; fi
# A TERM test holds the direct board read that follows take_mutex, when the
# launcher has written its holder file but has not yet released the mutex.
if [ -n "${STUB_TERM_MUTEX_GATE:-}" ] && [ -f "$FLEET_LAUNCH_GMK_LOCK_DIR/holder" ]; then
    : > "$STUB_TERM_MUTEX_GATE"
    sleep 0.05
fi
# An absent fixture is the unreadable board: non-zero exit, nothing on stdout.
if [ ! -f "$board" ]; then
    echo "stub fabro: board unreadable" >&2
    exit 1
fi
rows="$(mktemp)"
trap 'rm -f "$rows"' EXIT
if [ -s "$board" ]; then tail -n +2 "$board" >> "$rows"; fi
for marker in "$STUB_DRIVEN_DIR"/* "$STUB_RESUMED_DIR"/*; do
    [ -e "$marker" ] || continue
    marker_server=$(cut -d' ' -f1 "$marker")
    marker_item=$(cut -d' ' -f2 "$marker")
    [ "$marker_server" = "$server" ] || continue
    printf 'DRIVEN000001 stub-repo running 2026-10-25 0m05s %s\n' "$marker_item" >> "$rows"
    : > "$STUB_DRIVE_LISTED_DIR/$marker_item"
done
# A one-shot hook that runs AFTER this read has captured its rows and before it
# prints them.  It lets the harness move a launch from "in flight, unlisted" to
# "listed" exactly between a launcher's board read and its marker read, which
# is the window a concurrent impl launcher hits on a loaded host.
if [ -n "${STUB_PS_AFTER_READ_HOOK:-}" ] && [ "$server" = "$STUB_SERVER_GMK" ] \
    && [ ! -e "$STUB_PS_AFTER_READ_HOOK.done" ]; then
    : > "$STUB_PS_AFTER_READ_HOOK.done"
    bash "$STUB_PS_AFTER_READ_HOOK"
fi
# An idle board says so with an exit of zero and an empty stdout; `No runs
# found.` goes to stderr, which is what the launcher counts as a real zero.
if [ ! -s "$rows" ] && [ ! -s "$board" ]; then
    echo "No runs found." >&2
    exit 0
fi
printf 'RUN ID       REPO      STATUS    DATE       DURATION  ITEM\n'
cat "$rows"
FABRO_STUB

# The stub credential wrapper, invoked as `wrapper -- <command...>`. It answers
# for each command the launcher routes through the wrapper, keyed on the
# BASENAME of the script being run, and records every `drive.py` dispatch.
cat > "$STUB/wrapper" <<'WRAPPER_STUB'
#!/usr/bin/env bash
set -u
if [ "${1:-}" = -- ]; then shift; fi
if [ "${1:-}" = env ]; then
    # A real wrapper execs `env`, which applies -u and K=V and then runs the command. A nested
    # tenant wrapper (an executable path, not a bare interpreter) is handed the command exactly as
    # env would hand it, so the tenant stub observes what reached it.
    shift
    while [ "$#" -gt 0 ]; do
        case $1 in
            -u) unset "$2"; shift 2 ;;
            *=*) export "$1"; shift ;;
            *) break ;;
        esac
    done
    if [ "${1:-}" != "${1#/}" ] && [ -x "$1" ]; then exec "$@"; fi
fi
for argument in "$@"; do
    case ${argument##*/} in
        ready-set-check.py)
            if [ -n "${STUB_READY_BLOCKED_UNTIL_RELEASE:-}" ] && [ ! -s "$STUB_RELEASE_LOG" ]; then
                printf 'READY-CHECK stub: blocked until the seat-gated release runs\n'
                exit 3
            fi
            if [ -n "${STUB_READY_REFUSALS:-}" ]; then
                # Refuse the first STUB_READY_REFUSALS calls with STUB_READY_REASON and record what the
                # launcher held at each call: its FIFO ticket, the launch mutex and an in-flight marker.
                count=$(( $(cat "$STUB_READY_COUNTER" 2>/dev/null || echo 0) + 1 ))
                printf '%s\n' "$count" > "$STUB_READY_COUNTER"
                ticket_state=none; lock_state=none; marker_state=none
                if find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -print -quit | grep . >/dev/null; then ticket_state=present; fi
                if [ -d "$STUB_LOCK_DIR" ]; then lock_state=held; fi
                if find "$STUB_INFLIGHT_DIR" -type f -print -quit | grep . >/dev/null; then marker_state=present; fi
                printf 'call=%s ticket=%s mutex=%s marker=%s\n' "$count" "$ticket_state" "$lock_state" "$marker_state" >> "$STUB_READY_OBSERVATIONS"
                if [ "$count" -le "$STUB_READY_REFUSALS" ]; then
                    printf 'READY-CHECK stub: NOT in the ready set (%s)\n' "$STUB_READY_REASON"
                    exit 3
                fi
            fi
            printf 'READY-CHECK stub: in the ready set\n'
            exit "${STUB_READY_EXIT:-0}"
            ;;
        wip-claimed-count.py)
            # The capacity projection read: a counted-claims count and a wip_cap, both from files
            # a case rewrites while a launcher runs, or an unreadable answer. Every call is recorded.
            printf '%s\n' "$(date +%s%N)" >> "$STUB_WIP_CALLS"
            [ ! -e "${STUB_WIP_UNREADABLE_FILE:-/nonexistent}" ] || exit 1
            printf '{"counted_claims": %s, "in_flight_addition": 0, "wip_cap": %s, "cache": "stub"}\n' \
                "$(cat "$STUB_WIP_COUNT_FILE")" "$(cat "$STUB_WIP_CAP_FILE")"
            exit 0
            ;;
        dod-preflight.sh)
            item=${!#}
            printf '%s %s\n' "$(date +%s%N)" "$item" >> "$STUB_PREFLIGHT_LOG"
            [ -z "${STUB_PREFLIGHT_HEAD_LOG:-}" ] || git rev-parse HEAD >> "$STUB_PREFLIGHT_HEAD_LOG"
            if [ "$item" = "${STUB_PREFLIGHT_SLOW_ITEM:-}" ]; then
                # HELD until the harness creates the release file (bounded by
                # STUB_PREFLIGHT_SLOW_S), not slept for a fixed time.  The older
                # launcher therefore cannot bind before the harness has seen the
                # younger launcher's queued preflight, however slow the host is.
                # A fixed sleep raced launcher start-up and failed under CI load
                # (bd-ib-x7bwug, PR #4235).
                deadline=$(( $(date +%s) + STUB_PREFLIGHT_SLOW_S ))
                while [ ! -e "${STUB_PREFLIGHT_RELEASE:-/nonexistent}" ] \
                    && [ "$(date +%s)" -lt "$deadline" ]; do
                    sleep "$HARNESS_POLL_S"
                done
            fi
            if [ "$item" = "${STUB_PREFLIGHT_FAIL_ITEM:-}" ]; then
                printf 'stub queued preflight failure\n'
                exit 1
            fi
            printf 'stub launch-time Definition-of-Done preflight\n'
            exit "${STUB_PREFLIGHT_EXIT:-0}"
            ;;
        ledger-item.py)
            mode=""
            seen=0
            for token in "$@"; do
                if [ "$seen" = 1 ] && [ -z "$mode" ]; then mode=$token; fi
                case ${token##*/} in ledger-item.py) seen=1 ;; esac
            done
            case $mode in
                status)
                    if [ -e "$STUB_ITEM_STATUS_UNREADABLE_FILE" ]; then
                        printf 'unreadable at launcher re-read\n' > "$STUB_ITEM_STATUS_RE_READ_OBSERVATION_FILE"
                        exit 1
                    fi
                    # The launcher's re-read after the stop is the first status call made
                    # once every stub drive process is gone.  Case 20e's admitted arm
                    # holds that read until the TERM watcher has run its trap and its
                    # delayed writer has stored `active`, so the order is decided by
                    # these files and not by how long the stop grace took.  The wait is
                    # bounded only so a hung watcher cannot hang the harness.
                    if [ -n "${STUB_ITEM_STATUS_AWAIT_POST_STOP:-}" ] && [ -s "$STUB_DRIVE_PIDS" ]; then
                        stub_drives_gone=1
                        while read -r stub_drive_pid; do
                            if kill -0 "$stub_drive_pid" 2>/dev/null; then stub_drives_gone=0; fi
                        done < "$STUB_DRIVE_PIDS"
                        if [ "$stub_drives_gone" = 1 ]; then
                            deadline=$(( $(date +%s) + 10 ))
                            while [ ! -e "$STUB_ITEM_STATUS_ADMISSION_WRITTEN_FILE" ] \
                                && [ "$(date +%s)" -lt "$deadline" ]; do
                                sleep "$HARNESS_POLL_S"
                            done
                            if [ "$(cat "$STUB_ITEM_STATUS_FILE")" = active ]; then
                                printf 'active before launcher re-read\n' > "$STUB_ITEM_STATUS_RE_READ_OBSERVATION_FILE"
                            elif [ ! -e "$STUB_ITEM_STATUS_POST_STOP_RENDEZVOUS_FILE" ]; then
                                printf 'ready at launcher re-read: the TERM watcher never ran its trap\n' > "$STUB_ITEM_STATUS_RE_READ_OBSERVATION_FILE"
                            else
                                printf 'ready at launcher re-read: the TERM watcher ran but its writer stored nothing\n' > "$STUB_ITEM_STATUS_RE_READ_OBSERVATION_FILE"
                            fi
                        fi
                    fi
                    item_status=$(cat "$STUB_ITEM_STATUS_FILE")
                    if [ "$item_status" = active ] && [ -n "${STUB_ITEM_STATUS_ACTIVE_READ_RENDEZVOUS_FILE:-}" ]; then
                        : > "$STUB_ITEM_STATUS_ACTIVE_READ_RENDEZVOUS_FILE"
                    fi
                    printf 'LEDGER-STATUS %s\n' "$item_status"
                    ;;
                comment) printf '%s\n' "${!#}" >> "$STUB_LEDGER_COMMENTS" ;;
                priority) printf 'LEDGER-PRIORITY %s\n' "$(cat "$STUB_ITEM_PRIORITY_FILE" 2>/dev/null || echo 2)" ;;
            esac
            exit 0
            ;;
        dispatcher.py)
            subcommand=""
            seen=0
            for token in "$@"; do
                if [ "$seen" = 1 ] && [ -z "$subcommand" ]; then subcommand=$token; fi
                case ${token##*/} in dispatcher.py) seen=1 ;; esac
            done
            case $subcommand in
                host-only)
                    # The shared factory-safety predicate: a case supplies the verdict JSON, or the
                    # command cannot answer, or the item is not host-only.
                    [ ! -e "${STUB_HOST_ONLY_UNANSWERABLE_FILE:-/nonexistent}" ] || exit 1
                    if [ -s "${STUB_HOST_ONLY_JSON:-/nonexistent}" ]; then cat "$STUB_HOST_ONLY_JSON"; else printf '{"work_item_id": "stub", "host_only": false}\n'; fi
                    exit 0
                    ;;
                resume)
                    item=""
                    repo=""
                    previous=""
                    for token in "$@"; do
                        if [ "$previous" = --item ]; then item=$token; fi
                        if [ "$previous" = --repo ]; then repo=$token; fi
                        previous=$token
                    done
                    printf '%s\n' "$item" >> "$STUB_RESUME_LOG"
                    printf '%s %s\n' "$repo" "$item" >> "$STUB_RESUME_ARGV_LOG"
                    marker_state=missing
                    if find "$STUB_INFLIGHT_DIR" -type f -print -quit | grep . >/dev/null; then marker_state=present; fi
                    lock_state=released
                    if [ -d "$STUB_LOCK_DIR" ]; then lock_state=held; fi
                    printf '%s marker=%s mutex=%s\n' "$item" "$marker_state" "$lock_state" >> "$STUB_RESUME_OBSERVATION_LOG"
                    if [ -z "${STUB_RESUME_UNLISTED:-}" ]; then
                        printf '%s %s\n' "$STUB_SERVER_GMK" "$item" > "$STUB_RESUMED_DIR/$item"
                    fi
                    exit 0
                    ;;
            esac
            if [ -n "${STUB_CRED_REFUSAL:-}" ]; then printf '%s\n' "$STUB_CRED_REFUSAL" >&2; exit 3; fi
            printf 'stub: the Claude credential is usable (HTTP 200)\n'
            exit 0
            ;;
        drive.py)
            item=""
            for token in "$@"; do
                case $token in
                    impl:*) item=${token#impl:} ;;
                    resolve-blocked:*:ready)
                        printf '%s\n' "$token" >> "$STUB_RELEASE_LOG"
                        printf '{"status": "stub-released"}\n'
                        exit 0
                        ;;
                esac
            done
            case ${LIVESPEC_FABRO_FACTORY:-} in
                petri) server=$STUB_SERVER_GMK ;;
                mi-homelab) server=$STUB_SERVER_HL ;;
                candidate) server=$STUB_SERVER_CANDIDATE ;;
                homelab-worker-arm64) server=$STUB_SERVER_ARM ;;
                *) server="" ;;
            esac
            printf '%s\n' "${LIVESPEC_FACTORY_READ_WRAPPER:-missing}" >> "$STUB_FACTORY_READ_WRAPPER_LOG"
            # The configured routing the drive received: its --acp-node arguments in order, and the
            # judge-model variables set in its environment.
            acp_nodes=""
            previous=""
            for token in "$@"; do
                if [ "$previous" = --acp-node ]; then acp_nodes="$acp_nodes$token;"; fi
                previous=$token
            done
            printf '%s acp=%s dod=%s drift=%s reflector=%s password=%s\n' "$item" "$acp_nodes" \
                "${LIVESPEC_DOD_JUDGEMENT_MODEL:-unset}" "${LIVESPEC_DRIFT_JUDGE_MODEL:-unset}" "${LIVESPEC_REFLECTOR_MODEL:-unset}" \
                "${BEADS_DOLT_PASSWORD:+present}" >> "$STUB_DRIVE_ENV_LOG"
            printf '%s\n' "$item" >> "$STUB_DRIVE_LOG"
            if [ -n "${STUB_DRIVE_FAIL_TIMES:-}" ] \
                && [ "$(grep -cxF -- "$item" "$STUB_DRIVE_LOG")" -le "$STUB_DRIVE_FAIL_TIMES" ]; then
                # A drive that exits before its run lists, optionally printing a scripted JSON answer.
                [ -z "${STUB_DRIVE_FAIL_STDOUT:-}" ] || printf '%s\n' "$STUB_DRIVE_FAIL_STDOUT"
                exit "${STUB_DRIVE_FAIL_RC:-1}"
            fi
            if [ -d "$STUB_LOCK_DIR" ]; then
                # A preceding launcher releases the mutex before it begins its
                # drive, so a following launcher may legitimately acquire it
                # first.  Record both items: only the driving launcher's own
                # held mutex violates the launcher's narrow mutex scope.
                holder_item=$(grep -oE 'item=[^ ]+' "$STUB_LOCK_DIR/holder" 2>/dev/null | sed -n '1p' | cut -d= -f2)
                if [ -n "$holder_item" ]; then
                    printf 'held driver=%s holder=%s\n' "$item" "$holder_item" >> "$STUB_DRIVE_MUTEX_LOG"
                else
                    # release_lock removes holder before rmdir, leaving a
                    # short, harmless directory-only observation window.
                    printf 'released %s\n' "$item" >> "$STUB_DRIVE_MUTEX_LOG"
                fi
            else
                printf 'released %s\n' "$item" >> "$STUB_DRIVE_MUTEX_LOG"
            fi
            if [ -n "${STUB_DRIVE_ADMIT_GATE:-}" ]; then
                # A drive waiting in its master-CI preflight: the item reads
                # `ready` until the gate file appears, then `active` (admitted),
                # and the run is submitted only after STUB_DRIVE_SUBMIT_GATE too.
                if [ -n "${STUB_DRIVE_START_GATE:-}" ]; then
                    # A slow drive start: the drive has been invoked but has not yet
                    # reached its preflight wait. The harness opens the gate once it
                    # has advanced its own clock past any fixed startup bound.
                    : > "$STUB_DRIVE_START_GATE.reached"
                    start_deadline=$(( $(date +%s) + ${HARNESS_PREFLIGHT_HANG_GUARD_S:-300} ))
                    while [ ! -e "$STUB_DRIVE_START_GATE" ] \
                        && [ "$(date +%s)" -lt "$start_deadline" ]; do
                        sleep "$HARNESS_POLL_S"
                    done
                fi
                printf '%s\n' "$item" >> "$STUB_DRIVE_WAITING"
                printf '%s\n' "$$" >> "$STUB_DRIVE_PIDS"
                if [ -n "${STUB_DRIVE_ADMIT_ON_TERM:-}" ]; then
                    # Keep the primary drive alive until stop_drive exhausts
                    # its grace period and sends KILL, as a loaded shell can
                    # when TERM arrives during a foreground poll.
                    trap '' TERM
                    # This watcher handles TERM while the primary stub is in
                    # its polling sleep.  Its TERM trap starts a new delayed
                    # admission writer, which is not in stop_drive's PID
                    # snapshot and therefore survives the grace-period KILL.
                    # The status stub rendezvouses with that writer, so case
                    # 20e orders its post-stop read without relying on timing.
                    (
                        trap '
                            : > "$STUB_ITEM_STATUS_POST_STOP_RENDEZVOUS_FILE"
                            (
                                deadline=$(( $(date +%s) + 10 ))
                                while [ ! -e "$STUB_DRIVE_ADMIT_AFTER_STOP_GATE_FILE" ] \
                                    && [ "$(date +%s)" -lt "$deadline" ]; do
                                    sleep "$HARNESS_POLL_S"
                                done
                                if [ -e "$STUB_DRIVE_ADMIT_AFTER_STOP_GATE_FILE" ]; then
                                    printf "active\\n" > "$STUB_ITEM_STATUS_FILE"
                                    : > "$STUB_ITEM_STATUS_ADMISSION_WRITTEN_FILE"
                                fi
                            ) >/dev/null 2>&1 &
                            exit 143
                        ' TERM
                        # Armed: the harness sets the hold only after this exists, so
                        # the stop's TERM cannot reach the watcher before its trap.
                        : > "$STUB_DRIVE_WATCHER_ARMED_FILE"
                        while :; do
                            sleep 60 &
                            wait "$!"
                        done
                    ) &
                fi
                wait_deadline=$(( $(date +%s) + 60 ))
                while [ ! -e "$STUB_DRIVE_ADMIT_GATE" ] && [ "$(date +%s)" -lt "$wait_deadline" ]; do
                    sleep "$HARNESS_POLL_S"
                done
                printf 'active\n' > "$STUB_ITEM_STATUS_FILE"
                while [ -n "${STUB_DRIVE_SUBMIT_GATE:-}" ] && [ ! -e "$STUB_DRIVE_SUBMIT_GATE" ] \
                    && [ "$(date +%s)" -lt "$wait_deadline" ]; do
                    sleep "$HARNESS_POLL_S"
                done
            fi
            if [ -n "$item" ] && [ -n "$server" ]; then
                printf '%s %s\n' "$server" "$item" > "$STUB_DRIVEN_DIR/$item"
            fi
            if [ -n "${STUB_DRIVE_EXPIRE_SNAPSHOT:-}" ]; then
                # The shared board snapshot ages out while the drive runs, as the real one does after its
                # TTL, so the launcher's next listing poll reads the board with this run on it.
                find "$FLEET_LAUNCH_BOARD_SNAPSHOT_DIR" -name '*.ps' -exec touch -d '2 hours ago' {} + 2>/dev/null
            fi
            # A real drive polls its run after submitting. Keep this stub alive until a
            # board listing has observed its marker, so every case orders that observation
            # instead of hoping a fixed linger outlasts a loaded host's next poll.
            if [ -n "$item" ] && [ -n "$server" ]; then
                listed_deadline=$(( $(date +%s) + 10 ))
                while [ ! -e "$STUB_DRIVE_LISTED_DIR/$item" ] \
                    && [ "$(date +%s)" -lt "$listed_deadline" ]; do
                    sleep "$HARNESS_POLL_S"
                done
            fi
            printf '{"status": "stub-dispatched", "work_item_id": "%s"}\n' "$item"
            exit 0
            ;;
    esac
done
exec "$@"
WRAPPER_STUB

# The stub `ssh`, reached on a prepended PATH. The launcher asks the factory
# host for its idle CPU and for the server env that carries the dev token; both
# answers are canned and neither leaves this machine.
cat > "$STUB/bin/ssh" <<'SSH_STUB'
#!/usr/bin/env bash
set -u
command_line=$*
case $command_line in
    *mpstat*)
        printf 'Linux stub\n\n'
        printf 'Average:     all    1.00    0.00    0.00    %s\n' "${STUB_SSH_IDLE:-95.00}"
        ;;
    *cat*) printf 'FABRO_DEV_TOKEN=stub-dev-token\n' ;;
    *) echo "stub ssh: unexpected command: $command_line" >&2; exit 1 ;;
esac
SSH_STUB

chmod +x "$STUB/fabro" "$STUB/wrapper" "$STUB/bin/ssh"

# --- the throwaway tenant repository ----------------------------------------
# The launcher fast-forwards the tenant repository to origin/master before it
# dispatches, so the stub tenant is a real clone of a real bare origin rather
# than a stubbed `git`.
ORIGIN="$WORK/origin.git"
TENANT="$WORK/tenant"
GIT_IDENTITY=(-c user.name=fleet-launch-harness -c user.email=harness@invalid -c commit.gpgsign=false)
git init --quiet --bare --initial-branch=master "$ORIGIN"
git "${GIT_IDENTITY[@]}" init --quiet --initial-branch=master "$WORK/seed"
: > "$WORK/seed/README"
git -C "$WORK/seed" "${GIT_IDENTITY[@]}" add README
git -C "$WORK/seed" "${GIT_IDENTITY[@]}" commit --quiet --no-verify -m "seed"
git -C "$WORK/seed" "${GIT_IDENTITY[@]}" push --quiet "$ORIGIN" master
git "${GIT_IDENTITY[@]}" clone --quiet "$ORIGIN" "$TENANT"
# Three more tenants for the origin-tip cases. TENANT_MAIN's remote names `main` as its default
# branch, which a launcher that assumes `master` cannot fast-forward. TENANT_BROKEN and
# TENANT_DIVERGED are damaged by the case that uses them, so they are never shared with another case.
ORIGIN_MAIN="$WORK/origin-main.git"
TENANT_MAIN="$WORK/tenant-main"
TENANT_BROKEN="$WORK/tenant-broken"
TENANT_DIVERGED="$WORK/tenant-diverged"
git init --quiet --bare --initial-branch=main "$ORIGIN_MAIN"
git "${GIT_IDENTITY[@]}" init --quiet --initial-branch=main "$WORK/seed-main"
: > "$WORK/seed-main/README"
git -C "$WORK/seed-main" "${GIT_IDENTITY[@]}" add README
git -C "$WORK/seed-main" "${GIT_IDENTITY[@]}" commit --quiet --no-verify -m "seed"
git -C "$WORK/seed-main" "${GIT_IDENTITY[@]}" push --quiet "$ORIGIN_MAIN" main
git "${GIT_IDENTITY[@]}" clone --quiet "$ORIGIN_MAIN" "$TENANT_MAIN"
git "${GIT_IDENTITY[@]}" clone --quiet "$ORIGIN" "$TENANT_BROKEN"
git "${GIT_IDENTITY[@]}" clone --quiet "$ORIGIN" "$TENANT_DIVERGED"

# --- the stub plugin install -------------------------------------------------
# `installed_build` reads the plugin registry to resolve the build this tenant
# is bound to, and the launcher reads that build's own plugin.json for the
# version it logs. Both are files, so both are fixtures.
PLUGIN_KEY="livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
PLUGIN_CACHE="$WORK/plugins/cache"
PLUGIN_BUILD="stubbuild000"
mkdir -p "$PLUGIN_CACHE/$PLUGIN_BUILD/scripts/bin"
printf '{"version": "0.0.0-stub"}\n' > "$PLUGIN_CACHE/$PLUGIN_BUILD/plugin.json"
REGISTRY="$WORK/plugins/installed_plugins.json"
cat > "$REGISTRY" <<REGISTRY_FIXTURE
{"plugins": {"$PLUGIN_KEY": [
  {"version": "$PLUGIN_BUILD", "projectPath": "$TENANT"},
  {"version": "$PLUGIN_BUILD", "projectPath": "$TENANT_MAIN"},
  {"version": "$PLUGIN_BUILD", "projectPath": "$TENANT_BROKEN"},
  {"version": "$PLUGIN_BUILD", "projectPath": "$TENANT_DIVERGED"}]}}
REGISTRY_FIXTURE
REGISTRY_ORIGINAL="$WORK/plugins/installed_plugins.original.json"
cp "$REGISTRY" "$REGISTRY_ORIGINAL"

# --- per-case state ----------------------------------------------------------
# A board fixture holding one live run per line, plus the terminal rows a real
# board carries. A launcher that counted terminal runs would read five live
# runs where there are two, so every fixture carries both kinds.
BOARD_HEADER='RUN ID       REPO      STATUS    DATE       DURATION  ITEM'

# write_board <file> <live-count> <item-prefix>: a board with <live-count> live
# runs and three terminal runs that MUST NOT be counted.
write_board() {
    local file="$1" live="$2" prefix="$3" index=1
    printf '%s\n' "$BOARD_HEADER" > "$file"
    while [ "$index" -le "$live" ]; do
        printf 'LIVE00000%03d stub-repo running   2026-10-25 1m%02ds     %s-live-%d\n' \
            "$index" "$index" "$prefix" "$index" >> "$file"
        index=$((index + 1))
    done
    printf 'DONE00000001 stub-repo succeeded 2026-10-25 9m00s     %s-done-1\n' "$prefix" >> "$file"
    printf 'DONE00000002 stub-repo failed    2026-10-25 9m00s     %s-done-2\n' "$prefix" >> "$file"
    printf 'DONE00000003 stub-repo cancelled 2026-10-25 9m00s     %s-done-3\n' "$prefix" >> "$file"
}

CASE_DIR=""
CASE_LOG=""
DRIVE_LOG=""
DRIVE_MUTEX_LOG=""
FACTORY_READ_WRAPPER_LOG=""
PREFLIGHT_LOG=""
RESUME_LOG=""
RESUME_OBSERVATION_LOG=""
RELEASE_LOG=""
PS_LOG=""
SNAPSHOT_DIR=""
BOARD_GMK=""
BOARD_HL=""
BOARD_CANDIDATE=""
CAP_FILE=""
HOLD_FILE=""

# new_case <name>: a fresh set of throwaway directories and fixtures, and the
# environment every launcher invocation of this case inherits.
new_case() {
    CASE_NAME="$1"
    CASE_DIR="$WORK/case/$CASE_NAME"
    mkdir -p "$CASE_DIR"/{boards,state,inflight,queue,lock,driven,listed,resumed}
    rmdir "$CASE_DIR/lock"
    CASE_LOG="$CASE_DIR/launcher.log"
    DRIVE_LOG="$CASE_DIR/drive-log"
    : > "$DRIVE_LOG"
    DRIVE_MUTEX_LOG="$CASE_DIR/drive-mutex-log"
    : > "$DRIVE_MUTEX_LOG"
    FACTORY_READ_WRAPPER_LOG="$CASE_DIR/factory-read-wrapper-log"
    : > "$FACTORY_READ_WRAPPER_LOG"
    PREFLIGHT_LOG="$CASE_DIR/preflight-log"
    : > "$PREFLIGHT_LOG"
    RESUME_LOG="$CASE_DIR/resume-log"
    : > "$RESUME_LOG"
    RESUME_OBSERVATION_LOG="$CASE_DIR/resume-observation-log"
    : > "$RESUME_OBSERVATION_LOG"
    RELEASE_LOG="$CASE_DIR/release-log"
    : > "$RELEASE_LOG"
    PS_LOG="$CASE_DIR/ps-log"
    : > "$PS_LOG"
    SNAPSHOT_DIR="$CASE_DIR/board-snapshot"
    BOARD_GMK="$CASE_DIR/boards/gmktec"
    BOARD_HL="$CASE_DIR/boards/mi-homelab"
    BOARD_CANDIDATE="$CASE_DIR/boards/candidate"
    BOARD_ARM="$CASE_DIR/boards/arm64"
    # The candidate board is always counted in the fleet, so every case starts with it idle; a case
    # that needs it unreadable removes the fixture.
    : > "$BOARD_CANDIDATE"
    CAP_FILE="$CASE_DIR/state/fleet-cap"
    HOLD_FILE="$CASE_DIR/state/hold-gmktec"

    export PATH="$STUB/bin:$PATH"
    export STUB_SERVER_GMK="$GMK_URL"
    export STUB_SERVER_HL="$HL_URL"
    export STUB_SERVER_CANDIDATE="$CANDIDATE_URL"
    export STUB_BOARD_GMK="$BOARD_GMK"
    export STUB_BOARD_HL="$BOARD_HL"
    export STUB_BOARD_CANDIDATE="$BOARD_CANDIDATE"
    export STUB_SERVER_ARM="$ARM_URL"
    export STUB_BOARD_ARM="$BOARD_ARM"
    export STUB_DRIVE_ENV_LOG="$CASE_DIR/drive-env-log"
    : > "$STUB_DRIVE_ENV_LOG"
    export STUB_RESUME_ARGV_LOG="$CASE_DIR/resume-argv-log"
    : > "$STUB_RESUME_ARGV_LOG"
    export STUB_WIP_CALLS="$CASE_DIR/wip-calls"
    : > "$STUB_WIP_CALLS"
    export STUB_ITEM_PRIORITY_FILE="$CASE_DIR/item-priority"
    unset STUB_HOST_ONLY_JSON STUB_HOST_ONLY_UNANSWERABLE_FILE
    # The repository WIP gate reads its counted claims and wip_cap through the stub capacity projection.
    export STUB_WIP_COUNT_FILE="$CASE_DIR/wip-count"
    export STUB_WIP_CAP_FILE="$CASE_DIR/wip-cap"
    printf '0\n' > "$STUB_WIP_COUNT_FILE"
    printf '5\n' > "$STUB_WIP_CAP_FILE"
    export STUB_WIP_UNREADABLE_FILE="$CASE_DIR/wip-unreadable"
    unset STUB_DRIVE_FAIL_TIMES STUB_DRIVE_FAIL_RC STUB_DRIVE_FAIL_STDOUT STUB_DRIVE_EXPIRE_SNAPSHOT
    export STUB_DRIVEN_DIR="$CASE_DIR/driven"
    export STUB_DRIVE_LISTED_DIR="$CASE_DIR/listed"
    export STUB_RESUMED_DIR="$CASE_DIR/resumed"
    export STUB_DRIVE_LOG="$DRIVE_LOG"
    export STUB_DRIVE_MUTEX_LOG="$DRIVE_MUTEX_LOG"
    export STUB_FACTORY_READ_WRAPPER_LOG="$FACTORY_READ_WRAPPER_LOG"
    export STUB_PREFLIGHT_LOG="$PREFLIGHT_LOG"
    export STUB_RESUME_LOG="$RESUME_LOG"
    export STUB_RESUME_OBSERVATION_LOG="$RESUME_OBSERVATION_LOG"
    export STUB_RELEASE_LOG="$RELEASE_LOG"
    export STUB_PS_LOG="$PS_LOG"
    unset STUB_PS_DELAY_S
    export STUB_READY_EXIT=0
    unset STUB_READY_REFUSALS STUB_READY_REASON
    export STUB_READY_COUNTER="$CASE_DIR/ready-counter"
    export STUB_READY_OBSERVATIONS="$CASE_DIR/ready-observations"
    : > "$STUB_READY_OBSERVATIONS"
    export STUB_PREFLIGHT_EXIT=0
    unset STUB_PREFLIGHT_SLOW_ITEM STUB_PREFLIGHT_SLOW_S STUB_PREFLIGHT_FAIL_ITEM STUB_PREFLIGHT_HEAD_LOG
    export STUB_PREFLIGHT_RELEASE="$CASE_DIR/release-held-preflight"
    export STUB_SSH_IDLE=95.00
    export STUB_ITEM_STATUS_FILE="$CASE_DIR/item-status"
    printf 'ready\n' > "$STUB_ITEM_STATUS_FILE"
    export STUB_LEDGER_COMMENTS="$CASE_DIR/ledger-comments"
    : > "$STUB_LEDGER_COMMENTS"
    export STUB_DRIVE_WAITING="$CASE_DIR/drive-waiting"
    : > "$STUB_DRIVE_WAITING"
    export STUB_DRIVE_PIDS="$CASE_DIR/drive-pids"
    : > "$STUB_DRIVE_PIDS"
    export STUB_DRIVE_ADMIT_GATE_FILE="$CASE_DIR/admit-gate"
    export STUB_DRIVE_SUBMIT_GATE_FILE="$CASE_DIR/submit-gate"
    export STUB_ITEM_STATUS_UNREADABLE_FILE="$CASE_DIR/item-status-unreadable"
    export STUB_ITEM_STATUS_ACTIVE_READ_RENDEZVOUS_FILE="$CASE_DIR/active-status-read"
    export STUB_ITEM_STATUS_RE_READ_OBSERVATION_FILE="$CASE_DIR/item-status-re-read-observation"
    export STUB_ITEM_STATUS_POST_STOP_RENDEZVOUS_FILE="$CASE_DIR/post-stop-status-rendezvous"
    export STUB_DRIVE_WATCHER_ARMED_FILE="$CASE_DIR/watcher-armed"
    export STUB_ITEM_STATUS_ADMISSION_WRITTEN_FILE="$CASE_DIR/admission-written"
    export STUB_DRIVE_ADMIT_AFTER_STOP_GATE_FILE="$CASE_DIR/admit-after-stop-gate"
    unset STUB_DRIVE_ADMIT_GATE STUB_DRIVE_SUBMIT_GATE STUB_DRIVE_ADMIT_ON_TERM STUB_ITEM_STATUS_AWAIT_POST_STOP
    unset STUB_PS_ACTIVE_LISTING_RENDEZVOUS_FILE STUB_PS_ACTIVE_LISTING_RELEASE_FILE

    export REPO_OVERRIDE="$TENANT"
    export WRAPPER="$STUB/wrapper"
    export FLEET_LAUNCH_ORCH_REPO="$CASE_DIR/orch-repo"
    export FLEET_LAUNCH_SEAT="harness-seat"
    export FLEET_LAUNCH_STATE_DIR="$CASE_DIR/state"
    export FLEET_LAUNCH_FLEET_CAP_FILE="$CAP_FILE"
    export FLEET_LAUNCH_HOLD_FILE="$HOLD_FILE"
    export FLEET_LAUNCH_REPO_HOLD_DIR="$CASE_DIR/state"
    export FLEET_LAUNCH_GMK_SERVER="$GMK_URL"
    export FLEET_LAUNCH_HL_SERVER="$HL_URL"
    export FLEET_LAUNCH_GMK_CANDIDATE_SERVER="$CANDIDATE_URL"
    export FLEET_LAUNCH_GMK_TARGET_FILE="$CASE_DIR/state/gmk-target"
    export FLEET_LAUNCH_GMK_CANDIDATE_CAP=2
    export FLEET_LAUNCH_GMK_CANDIDATE_CAP_FILE="$CASE_DIR/state/candidate-cap"
    export FLEET_LAUNCH_GMK_CAP_FILE="$CASE_DIR/state/gmk-cap"
    export FLEET_LAUNCH_HL_CAP_FILE="$CASE_DIR/state/hl-cap"
    export FLEET_LAUNCH_GMK_IDLE_FLOOR_FILE="$CASE_DIR/state/gmk-idle-floor"
    export FLEET_LAUNCH_ARM_SERVER="$ARM_URL"
    export FLEET_LAUNCH_ARM_ENROLLED_FILE="$CASE_DIR/state/arm64-enrolled"
    export FLEET_LAUNCH_ARM_CAP=1
    export FLEET_LAUNCH_FREEZE_ALLOWLIST_FILE="$CASE_DIR/state/freeze-allowlist"
    export FLEET_LAUNCH_FREEZE_ALLOWLIST_LOCK="$CASE_DIR/state/freeze-allowlist.lock"
    export FLEET_LAUNCH_FREEZE_ALLOWLIST_CONSUMED_LOG="$CASE_DIR/state/freeze-allowlist.consumed"
    export FLEET_LAUNCH_CANARY_HOLD_DIR="$CASE_DIR/state"
    export FLEET_LAUNCH_CANARY_EXEMPT_FILE="$CASE_DIR/state/canary-hold-exempt"
    export FLEET_LAUNCH_ITEM_HOLD_DIR="$CASE_DIR/state"
    export FLEET_LAUNCH_ACP_OVERRIDES_FILE="$CASE_DIR/state/acp-overrides.txt"
    export FLEET_LAUNCH_WIP_SHARED_DIR="$CASE_DIR/state"
    export FLEET_LAUNCH_WIP_CACHE_DIR="$CASE_DIR/state"
    # The shared WIP caches are off by default so a case that rewrites the count sees it on the next
    # poll; the cache case below turns them on.
    export FLEET_LAUNCH_WIP_SHARED_TTL_S=0
    export FLEET_LAUNCH_WIP_CACHE_TTL_S=0
    export FLEET_LAUNCH_WIP_POLL_S=0.01
    export FLEET_LAUNCH_QUEUE_WAIT_S=0.05
    export FLEET_LAUNCH_BOARD_RETRIES=0
    export FLEET_LAUNCH_SIZE_SCREEN=0
    export FLEET_LAUNCH_SIZE_SCREEN_COMMAND="$CASE_DIR/size-screen-stub.py"
    export FLEET_LAUNCH_RETICKET_MAX_IN_WINDOW=6
    export FLEET_LAUNCH_BREAKAGE_EXCEPTION_FILE="$CASE_DIR/breakage-exception"
    export FLEET_LAUNCH_RETICKET_STATE_DIR="$CASE_DIR/state/reticket-state"
    export FLEET_LAUNCH_RETICKET_DELAY_1_S=0
    export FLEET_LAUNCH_RETICKET_DELAY_2_S=0.01
    export FLEET_LAUNCH_RETICKET_DELAY_3_S=0.02
    export FLEET_LAUNCH_GMK_SSH="stub-factory-host"
    export FLEET_LAUNCH_GMK_SERVER_ENV="$CASE_DIR/state/server.env"
    export FLEET_LAUNCH_GMK_CAP=8
    export FLEET_LAUNCH_HL_CAP=2
    export FLEET_LAUNCH_GMK_MIN_IDLE=25
    export FLEET_LAUNCH_FABRO="$STUB/fabro"
    export FLEET_LAUNCH_FABRO_BOARD="$STUB/fabro"
    export FLEET_LAUNCH_INFLIGHT_DIR="$CASE_DIR/inflight"
    export FLEET_LAUNCH_GMK_QUEUE_DIR="$CASE_DIR/queue"
    export FLEET_LAUNCH_GMK_LOCK_DIR="$CASE_DIR/lock"
    export STUB_INFLIGHT_DIR="$FLEET_LAUNCH_INFLIGHT_DIR"
    export STUB_LOCK_DIR="$FLEET_LAUNCH_GMK_LOCK_DIR"
    export FLEET_LAUNCH_PLUGIN_REGISTRY="$REGISTRY"
    export FLEET_LAUNCH_PLUGIN_CACHE="$PLUGIN_CACHE"
    export FLEET_LAUNCH_PLUGIN_KEY="$PLUGIN_KEY"
    export FLEET_LAUNCH_DEFAULT_WRAPPER="$STUB/wrapper"
    export FLEET_LAUNCH_RESUME_WRAPPER="$STUB/wrapper"
    # The launchers use their smallest useful non-zero poll, so a queued
    # launcher rechecks FIFO almost immediately after the harness changes it.
    export FLEET_LAUNCH_MAX_WAIT_S=4
    export FLEET_LAUNCH_ABANDON_S=60
    export FLEET_LAUNCH_POLL_S=0.01
    # Keep all launcher state polls at that step: mutex release and post-drive
    # listing are observed conditions, not reasons to wait a whole second.
    export FLEET_LAUNCH_MUTEX_POLL_S=0.01
    export FLEET_LAUNCH_LISTING_POLL_S=0.01
    export FLEET_LAUNCH_PREFLIGHT_REUSE_S=600
    # A TTL of zero keeps every board read live, so a case that changes a board fixture sees it on
    # the next poll; the snapshot cases below raise it.
    export FLEET_LAUNCH_BOARD_SNAPSHOT_DIR="$SNAPSHOT_DIR"
    export FLEET_LAUNCH_BOARD_TTL_S=0
    export FLEET_LAUNCH_BOARD_REFRESH_WAIT_S=60
    export FLEET_LAUNCH_MUTEX_HOLD_S=60
    export FLEET_LAUNCH_LISTING_WAIT_S=60
    export FLEET_LAUNCH_STOP_GRACE_S=5
    unset STUB_RESUME_UNLISTED STUB_READY_BLOCKED_UNTIL_RELEASE
    unset ONLY_GMK ONLY_HL ONLY_ARM CAPTURE_NULL CAPTURE_EXPECT TICKET_NS REWORK RELEASE_BLOCKED
    unset FLEET_LAUNCH_PARENT_CHAIN_COMMAND FLEET_LAUNCH_PRIORITIES_RECORD
}

# run_launcher <item> [log]: one launcher invocation, captured. Sets RC.
run_launcher() {
    local item="$1" log="${2:-$CASE_LOG}"
    "$LAUNCHER" "$item" > "$log" 2>&1
    RC=$?
}

log_has() { grep -qF -- "$2" "$1"; }
ps_count() { grep -cxF -- "$1" "$PS_LOG" 2>/dev/null || true; }
drive_log_items() { tr '\n' ' ' < "$DRIVE_LOG" | sed 's/ *$//'; }
preflight_count() { grep -c " $1$" "$PREFLIGHT_LOG" 2>/dev/null || true; }

# This protects the harness from a hung launcher. It is not a startup budget:
# each Scenario 297 launcher normally reaches the stub preflight in milliseconds.
HARNESS_PREFLIGHT_HANG_GUARD_S=${HARNESS_PREFLIGHT_HANG_GUARD_S:-300}
PREFLIGHT_FAILURE_DETAIL=""

# wait_for_preflight <case> <launcher> <pid> <log> <item> <count>: wait until
# the stub recorded the requested number of Definition-of-Done preflights. A
# launcher that exits first is a verdict immediately; the shared guard exists
# only to stop a genuinely hung launcher from holding the harness forever.
wait_for_preflight() {
    local case_name="$1" launcher="$2" pid="$3" log="$4" item="$5" count="$6"
    local deadline launcher_rc log_tail reason launcher_alive
    deadline=$(( $(date +%s) + HARNESS_PREFLIGHT_HANG_GUARD_S ))
    while :; do
        # Liveness is sampled BEFORE the record is read: a launcher records its
        # preflight before it can exit, so a launcher seen dead here has already
        # written everything the read below can find.  Reading the record first
        # let a fast preflight finish between the two checks and be reported as
        # a launcher that never preflighted.
        launcher_alive=1
        kill -0 "$pid" 2>/dev/null || launcher_alive=0
        if [ "$(preflight_count "$item")" -ge "$count" ]; then return 0; fi
        if [ "$launcher_alive" = 0 ]; then
            wait "$pid"; launcher_rc=$?
            reason="exited rc=$launcher_rc"
            break
        fi
        if [ "$(date +%s)" -ge "$deadline" ]; then
            reason="hung past ${HARNESS_PREFLIGHT_HANG_GUARD_S}s guard"
            break
        fi
        sleep "$HARNESS_POLL_S"
    done
    log_tail=$(tail -8 "$log" 2>&1 || true)
    PREFLIGHT_FAILURE_DETAIL="case=$case_name launcher=$launcher did not reach preflight ($reason); tail of $log:
${log_tail:-<no launcher log output>}"
    return 1
}

# await_both <pid> <pid> <seconds>: wait for two launchers to exit, terminating
# whichever is still running at the bound. Sets FIRST_RC and SECOND_RC; a
# terminated launcher reports 143, which fails the exit assertion as it should.
#
# THE HARNESS BOUNDS THIS ITSELF rather than leaning on the launchers' own
# give-up deadline, which the FIFO case raises deliberately. Against a BROKEN
# launcher the two queued launchers can never dispatch, so waiting out their
# deadlines made this one case cost minutes and left the gate slowest exactly
# when it is reporting a defect. The two are awaited TOGETHER for the same
# reason: awaited in turn, the second bound starts only once the first has
# expired, so the cost is the sum rather than the maximum.
# stop_launcher <pid>...: TERM each launcher, then KILL any still alive after STOP_GRACE_S.
# Bash 5.2 can lose a TERM: when the signal lands while the launcher is parsing a $(...)
# substitution, its `trap 'exit 143' TERM` fails with "trap: line 2: unexpected EOF while
# looking for matching `)'" and the launcher keeps looping. Reproduced in 1 of 200 TERMs on
# bash 5.2.37. A bare `kill -TERM; wait` then hangs the harness on a launcher that never exits,
# which is how run 18 of 30 hung. Callers keep their own `wait` to reap the launcher.
STOP_GRACE_S=${STOP_GRACE_S:-5}
stop_launcher() {
    local pid deadline
    kill -TERM "$@" 2>/dev/null
    deadline=$(( $(date +%s) + STOP_GRACE_S ))
    for pid in "$@"; do
        while kill -0 "$pid" 2>/dev/null && [ "$(date +%s)" -lt "$deadline" ]; do
            sleep "$HARNESS_POLL_S"
        done
        kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
    done
    return 0
}

FIRST_RC=""
SECOND_RC=""
await_both() {
    local first="$1" second="$2" limit="$3" deadline
    deadline=$(( $(date +%s) + limit ))
    while :; do
        if ! kill -0 "$first" 2>/dev/null && ! kill -0 "$second" 2>/dev/null; then break; fi
        [ "$(date +%s)" -lt "$deadline" ] || break
        sleep "$HARNESS_POLL_S"
    done
    stop_launcher "$first" "$second"
    wait "$first"; FIRST_RC=$?
    wait "$second"; SECOND_RC=$?
}

# wait_for_line <log> <needle> <seconds>: poll one launcher's log for a line.
wait_for_line() {
    local log="$1" needle="$2" limit="$3" deadline
    deadline=$(( $(date +%s) + limit ))
    while :; do
        if [ -f "$log" ] && grep -qF -- "$needle" "$log"; then return 0; fi
        [ "$(date +%s)" -lt "$deadline" ] || return 1
        sleep "$HARNESS_POLL_S"
    done
}

# OBSERVE_WAIT_S bounds every wait whose job is to OBSERVE that a launcher or a
# stub reached a state (a log line, a rendezvous file, a ticket).  Each such wait
# returns the instant the state appears, so a generous bound costs a healthy run
# nothing, while a tight one turns a slow start on a loaded runner into a false
# "never ..." failure (orchestrator CI: case 23 HUP rc=75, the 100-iteration TERM
# loop, and "the allowlisted resume did not start as required").  It must NOT be
# used where the bound IS the behaviour under test: the launcher's own give-up
# (FLEET_LAUNCH_MAX_WAIT_S), STOP_GRACE_S, a stall/age bound, or a window in
# which something must NOT happen.  EXIT_WAIT_S is the same for waiting out a
# launcher that exits by itself.
OBSERVE_WAIT_S=${OBSERVE_WAIT_S:-30}
EXIT_WAIT_S=${EXIT_WAIT_S:-60}

# HOLD_LINE_WAIT_S bounds how long a scenario waits for a launcher to print
# 'repository hold present'.  wait_for_line returns the instant the line
# appears, so a generous bound costs nothing on a healthy run; a tight one turns
# a slow start on a loaded host into a false 'never yielded' failure (orchestrator
# #5448 run 44070262679: iterations 27/29/61/62/63 of the 100-iteration TERM loop).
HOLD_LINE_WAIT_S=${HOLD_LINE_WAIT_S:-$OBSERVE_WAIT_S}

# wait_for_queue_ticket: returns a ticket only after the queue itself proves it
# exists.  A cap log is not a file-system synchronization point for a launcher
# that can re-exec while preserving its ticket.
wait_for_queue_ticket() {
    local queue="$1" limit="$2" deadline ticket
    deadline=$(( $(date +%s) + limit ))
    while :; do
        ticket=$(find "$queue" -type f -print -quit)
        if [ -n "$ticket" ]; then
            printf '%s\n' "$ticket"
            return 0
        fi
        [ "$(date +%s)" -lt "$deadline" ] || return 1
        sleep "$HARNESS_POLL_S"
    done
}

# line_has_all <log> <needle>...: some single line of the log holds every needle.
line_has_all() {
    local log="$1" line needle all
    shift
    while IFS= read -r line; do
        all=1
        for needle in "$@"; do
            case $line in *"$needle"*) ;; *) all=0; break ;; esac
        done
        [ "$all" = 1 ] && return 0
    done < "$log"
    return 1
}
# set_hold <path> <text>: create a hold file whole in one step, so a launcher polling the path never reads it half written.
set_hold() {
    printf '%b\n' "$2" > "$1.new"
    mv "$1.new" "$1"
}
# wait_gone <pid> <seconds>: succeeds when the process has exited within the bound.
wait_gone() {
    local pid="$1" limit="$2" deadline
    deadline=$(( $(date +%s) + limit ))
    while kill -0 "$pid" 2>/dev/null; do
        [ "$(date +%s)" -lt "$deadline" ] || return 1
        sleep "$HARNESS_POLL_S"
    done
    return 0
}
# ticket_held_lines <ticket-file>: how many lines beginning held= the ticket carries.
ticket_held_lines() { grep -c '^held=' "$1" 2>/dev/null || true; }
# open_boards: both factory boards idle and a shared fleet cap with room.
open_boards() {
    : > "$BOARD_GMK"
    : > "$BOARD_HL"
    printf '8\n' > "$CAP_FILE"
}
echo "=== fleet-launch hermetic harness"

if [ "$HARNESS_SLICE" = all ]; then
# --- 1. reading a factory board ---------------------------------------------
# The count must be the LIVE rows only: not the header, and not the terminal
# runs a real `ps -a` board carries beside them. The absent fleet-cap file is
# what stops the launcher here, so the refusal line carries both board counts.
scenario "1. reads a stub factory board"
if bash "$HARNESS_DIR/test-scenario-watchdog.sh" >/dev/null; then
    pass "a scenario that runs past HARNESS_SCENARIO_TIMEOUT_S is killed, named and fails the run, while healthy scenarios are untouched"
else
    fail "the per-scenario watchdog regressed"
fi
new_case board-read
write_board "$BOARD_GMK" 2 gmk
write_board "$BOARD_HL" 1 hl
run_launcher bd-ib-boardread
if log_has "$CASE_LOG" "gmktec=2 hl=1 markers=0 fleet=3"; then
    pass "the board read counts the live runs of both factories"
else
    fail "the board read did not report gmktec=2 hl=1 fleet=3"
    tail -5 "$CASE_LOG" >&2
fi
if log_has "$CASE_LOG" "cap=0"; then
    pass "an absent fleet-cap file reads as a cap of zero, which is never green"
else
    fail "an absent fleet-cap file did not read as cap=0"
fi
if [ ! -s "$DRIVE_LOG" ]; then
    pass "no dispatch was made with the cap unreadable"
else
    fail "a dispatch was made with the cap unreadable: $(drive_log_items)"
fi

# --- 2. refusing a launch at the shared fleet cap ---------------------------
scenario "2. refuses a launch when the shared fleet cap is reached"
new_case fleet-cap
write_board "$BOARD_GMK" 3 gmk
write_board "$BOARD_HL" 1 hl
printf '4\n' > "$CAP_FILE"
run_launcher bd-ib-atcap
if log_has "$CASE_LOG" "fleet not green" && log_has "$CASE_LOG" "fleet=4 cap=4"; then
    pass "a fleet of four against a cap of four is refused"
else
    fail "a fleet at the cap was not refused"
    tail -5 "$CASE_LOG" >&2
fi
if [ ! -s "$DRIVE_LOG" ] && [ "$RC" = 75 ]; then
    pass "the launcher took no slot and gave up (rc=75)"
else
    fail "expected no dispatch and rc=75, got rc=$RC dispatches: $(drive_log_items)"
fi
# The positive control: the same fleet, one slot of headroom.
printf '5\n' > "$CAP_FILE"
run_launcher bd-ib-undercap "$CASE_DIR/control.log"
if [ "$(drive_log_items)" = "bd-ib-undercap" ] && [ "$RC" = 0 ]; then
    pass "control: one slot of headroom under the same cap launches"
else
    fail "control: a fleet under the cap did not launch (rc=$RC, dispatches: $(drive_log_items))"
    tail -8 "$CASE_DIR/control.log" >&2
fi
if [ "$(cat "$FACTORY_READ_WRAPPER_LOG")" = "$FLEET_LAUNCH_DEFAULT_WRAPPER" ]; then
    pass "a tenant-wrapped drive receives only the host default wrapper path for factory reads"
else
    fail "a tenant-wrapped drive did not receive the host default factory-read wrapper"
fi

# Per-dispatch build override (bd-ib-inzpxt): one launch runs on a candidate build while the
# band stays on the installed build; a build that is not materialized refuses.
CANDIDATE_BUILD="candbuild111"
mkdir -p "$PLUGIN_CACHE/$CANDIDATE_BUILD"
cp -R "$PLUGIN_CACHE/$PLUGIN_BUILD/." "$PLUGIN_CACHE/$CANDIDATE_BUILD/"
printf '{"version": "0.0.1-candidate"}\n' > "$PLUGIN_CACHE/$CANDIDATE_BUILD/plugin.json"
new_case build-override
write_board "$BOARD_GMK" 0 gmk
write_board "$BOARD_HL" 0 hl
printf '5\n' > "$CAP_FILE"
FLEET_LAUNCH_BUILD_OVERRIDE="$CANDIDATE_BUILD" run_launcher bd-ib-candidate "$CASE_DIR/candidate.log"
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = "bd-ib-candidate" ] \
    && log_has "$CASE_DIR/candidate.log" "build=$CANDIDATE_BUILD build-source=override version=0.0.1-candidate"; then
    pass "a launch given a candidate build runs on it, and its LAUNCH line names the build and the override source"
else
    fail "a launch given a candidate build did not run on it (rc=$RC, dispatches: $(drive_log_items))"
    tail -8 "$CASE_DIR/candidate.log" >&2
fi
: > "$DRIVE_LOG"
run_launcher bd-ib-band "$CASE_DIR/band.log"
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = "bd-ib-band" ] \
    && log_has "$CASE_DIR/band.log" "build=$PLUGIN_BUILD build-source=installed registry version=0.0.0-stub"; then
    pass "a launch from the same clone given no override still runs on the installed build"
else
    fail "a launch given no override did not stay on the installed build (rc=$RC, dispatches: $(drive_log_items))"
    tail -8 "$CASE_DIR/band.log" >&2
fi
: > "$DRIVE_LOG"
FLEET_LAUNCH_BUILD_OVERRIDE="missingbuild999" run_launcher bd-ib-missing "$CASE_DIR/missing.log"
if [ "$RC" != 0 ] && [ ! -s "$DRIVE_LOG" ] && log_has "$CASE_DIR/missing.log" "missingbuild999" \
    && ! log_has "$CASE_DIR/missing.log" "build=$PLUGIN_BUILD"; then
    pass "a launch given a build that is not in the plugin cache refuses naming it, with no silent fallback to the installed build"
else
    fail "an unmaterialized build override did not refuse cleanly (rc=$RC, dispatches: $(drive_log_items))"
    tail -8 "$CASE_DIR/missing.log" >&2
fi

# The installed-build guard compares real paths first, then permits exactly one
# basename fallback for a registry moved independently of the checkout. It must
# refuse before the credential probe when neither rule identifies one build.
default_orch=$(env -u FLEET_LAUNCH_ORCH_REPO \
    FLEET_LAUNCH_PLUGIN_REGISTRY="$REGISTRY" \
    FLEET_LAUNCH_PLUGIN_CACHE="$PLUGIN_CACHE" \
    FLEET_LAUNCH_PLUGIN_KEY="$PLUGIN_KEY" \
    bash -c '. "$1"; printf "%s" "$FLEET_LAUNCH_ORCH_REPO"' bash "$LAUNCH_DIR/config.sh")
if [ "$default_orch" = "$TENANT" ]; then
    pass "an unset orchestrator repository defaults from its install record, not a workspace path"
else
    fail "an unset orchestrator repository did not use its install record (got '$default_orch')"
fi

TENANT_SYMLINK="$WORK/tenant-through-symlink"
ln -s "$TENANT" "$TENANT_SYMLINK"
new_case installed-build-realpath
open_boards
REPO_OVERRIDE="$TENANT_SYMLINK" run_launcher bd-ib-realpath "$CASE_DIR/realpath.log"
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = "bd-ib-realpath" ]; then
    pass "a registry projectPath resolves through a symlinked REPO realpath"
else
    fail "a symlinked repository did not resolve its installed build (rc=$RC, dispatches: $(drive_log_items))"
    tail -8 "$CASE_DIR/realpath.log" >&2
fi

cat > "$REGISTRY" <<REGISTRY_FIXTURE
{"plugins": {"$PLUGIN_KEY": [{"version": "$PLUGIN_BUILD", "projectPath": "$WORK/relocated/${TENANT##*/}"}]}}
REGISTRY_FIXTURE
new_case installed-build-basename
open_boards
run_launcher bd-ib-basename "$CASE_DIR/basename.log"
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = "bd-ib-basename" ]; then
    pass "one registry entry with the repository basename is used as the fallback"
else
    fail "the one-entry basename fallback did not resolve the installed build (rc=$RC, dispatches: $(drive_log_items))"
    tail -8 "$CASE_DIR/basename.log" >&2
fi

cat > "$REGISTRY" <<REGISTRY_FIXTURE
{"plugins": {"$PLUGIN_KEY": [{"version": "$PLUGIN_BUILD", "projectPath": "$WORK/no-registry-match"}]}}
REGISTRY_FIXTURE
new_case installed-build-mismatch
open_boards
run_launcher bd-ib-registry-mismatch "$CASE_DIR/mismatch.log"
if [ "$RC" != 0 ] && [ ! -s "$DRIVE_LOG" ] \
    && log_has "$CASE_DIR/mismatch.log" "installed build refusal" \
    && log_has "$CASE_DIR/mismatch.log" "$REGISTRY" \
    && log_has "$CASE_DIR/mismatch.log" "$PLUGIN_KEY" \
    && log_has "$CASE_DIR/mismatch.log" "$TENANT" \
    && ! log_has "$CASE_DIR/mismatch.log" "credential probe NOT usable"; then
    pass "a registry mismatch refuses loudly before the credential probe or a dispatch"
else
    fail "a registry mismatch did not make the shared installed-build refusal (rc=$RC, dispatches: $(drive_log_items))"
    tail -8 "$CASE_DIR/mismatch.log" >&2
fi
cp "$REGISTRY_ORIGINAL" "$REGISTRY"

# --- 3. two queued tickets launch in FIFO order -----------------------------
# The FIFO order is the TICKET order, not the start order, so the launcher
# started FIRST here holds the LATER ticket and must lose. The hold file is the
# barrier: both launchers are parked on it, the second is then observed to have
# queued behind the older ticket, and only then is the hold released — so the
# later launcher cannot have slipped past the ticket check in the same poll.
scenario "3. launches two queued tickets in FIFO order"
new_case fifo
# This case PARKS both launchers on the barrier on purpose, so the give-up
# deadline every other case leans on would fire while they are waiting for each
# other. It is raised here to a bound that cannot be reached by a healthy run on
# a loaded machine, which keeps the case a test of the ticket ORDER rather than
# of how fast this host happens to be: the short deadline failed under a
# concurrent test suite while the ordering it asserts was perfectly correct.
export FLEET_LAUNCH_MAX_WAIT_S=300
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
: > "$HOLD_FILE"
LATER_LOG="$CASE_DIR/later.log"
EARLIER_LOG="$CASE_DIR/earlier.log"
ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-later > "$LATER_LOG" 2>&1 &
later_pid=$!
if ! wait_for_line "$LATER_LOG" "hold file present" 30; then
    fail "the later-ticket launcher never parked on the hold file"
    tail -8 "$LATER_LOG" >&2
fi
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-earlier > "$EARLIER_LOG" 2>&1 &
earlier_pid=$!
if wait_for_line "$LATER_LOG" "queued behind an older gmktec ticket" 30; then
    pass "the later ticket queues behind the older one"
else
    fail "the later ticket never queued behind the older one"
    tail -8 "$LATER_LOG" >&2
fi
rm -f "$HOLD_FILE"
await_both "$earlier_pid" "$later_pid" 45
earlier_rc=$FIRST_RC; later_rc=$SECOND_RC
# Binding order is what FIFO guarantees, not the order of the two drive calls:
# the narrow mutex is released before drive, so after both bind the drives may
# reach the stub in either order. A later ticket leaves the queue only once the
# older ticket is dropped at its bind, so "queued behind the older ticket" plus
# both launches is the order evidence.
if [ "$(drive_log_items | tr ' ' '\n' | sort | tr '\n' ' ' | sed 's/ $//')" = "bd-ib-earlier bd-ib-later" ] \
    && grep -qE "queued behind an older gmktec ticket: owner=harness-seat pid=[0-9]+ item=bd-ib-earlier$" "$LATER_LOG"; then
    pass "both queued tickets launched, oldest ticket first"
else
    fail "expected both launched with the later ticket queued behind bd-ib-earlier; drives '$(drive_log_items)'"
    tail -8 "$EARLIER_LOG" >&2
    tail -8 "$LATER_LOG" >&2
fi
if [ "$earlier_rc" = 0 ] && [ "$later_rc" = 0 ]; then
    pass "both launchers exited zero"
else
    fail "launcher exits: earlier=$earlier_rc later=$later_rc"
fi

# --- 4. holding a launch while the hold file exists -------------------------
scenario "4. holds a launch while the hold file exists"
new_case hold
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
: > "$HOLD_FILE"
run_launcher bd-ib-held
if log_has "$CASE_LOG" "hold file present" && [ ! -s "$DRIVE_LOG" ] && [ "$RC" = 75 ]; then
    pass "the hold file holds the launch with every other gate green"
else
    fail "the hold file did not hold the launch (rc=$RC, dispatches: $(drive_log_items))"
    tail -5 "$CASE_LOG" >&2
fi
# The positive control: the identical case with the hold file removed.
rm -f "$HOLD_FILE"
run_launcher bd-ib-released "$CASE_DIR/control.log"
if [ "$(drive_log_items)" = "bd-ib-released" ] && [ "$RC" = 0 ]; then
    pass "control: removing the hold file releases the identical launch"
else
    fail "control: the launch did not release (rc=$RC, dispatches: $(drive_log_items))"
    tail -8 "$CASE_DIR/control.log" >&2
fi

# --- 5. a retired factory's board counts as zero, not as unknown ------------
# The defect this case exists for: a launcher that reads an idle board as
# UNKNOWN sees the fleet as unknown and never launches at all. That is the
# 2026-10-24 outage the README records, and it looks exactly like a busy fleet.
scenario "5. counts a retired factory's board as zero, not as unknown"
new_case retired-board
write_board "$BOARD_GMK" 1 gmk
: > "$BOARD_HL"
printf '1\n' > "$CAP_FILE"
run_launcher bd-ib-retired
if log_has "$CASE_LOG" "hl=0" && log_has "$CASE_LOG" "fleet=1 cap=1"; then
    pass "an idle board counts as zero, so the fleet is a number"
else
    fail "an idle board was not counted as zero"
    tail -5 "$CASE_LOG" >&2
fi
# The positive control: the same idle board with headroom MUST launch, which is
# what an unknown reading could never do.
printf '8\n' > "$CAP_FILE"
run_launcher bd-ib-retired-ok "$CASE_DIR/control.log"
if [ "$(drive_log_items)" = "bd-ib-retired-ok" ] && [ "$RC" = 0 ]; then
    pass "control: a fleet counted past an idle board launches"
else
    fail "control: an idle board blocked the launch (rc=$RC, dispatches: $(drive_log_items))"
    tail -8 "$CASE_DIR/control.log" >&2
fi
# The mirror arm: an UNREADABLE board is not a zero. Without it, a launcher
# that answered zero for every board would pass the two cases above.
rm -f "$BOARD_HL"
: > "$DRIVE_LOG"
run_launcher bd-ib-unreadable "$CASE_DIR/unreadable.log"
if log_has "$CASE_DIR/unreadable.log" "hl=U" && log_has "$CASE_DIR/unreadable.log" "fleet=U"; then
    pass "an unreadable board is unknown, never a zero"
else
    fail "an unreadable board was not reported as unknown"
    tail -5 "$CASE_DIR/unreadable.log" >&2
fi
if [ ! -s "$DRIVE_LOG" ] && [ "$RC" = 75 ]; then
    pass "an unknown fleet is never green, so no slot was taken"
else
    fail "an unknown fleet launched (rc=$RC, dispatches: $(drive_log_items))"
fi

fi

# --- Queue-ticket placement: parent-chain priority, not an operator slot ---
# The queue-position fixture is deliberately tiny and textual: the command accepts an
# item id and returns its immediate parent, while the current priorities record maps
# each owning plan to its rank.  The test starts plan 11 first with the smaller
# hand-supplied namespace and plan 2 second with the larger one.  A new ticket must
# walk its own parent chain and use the record at ticket time, so plan 2 becomes the
# FIFO head despite those hostile values.  TICKET_NS remains available only to retain
# an already-created ticket across a launcher restart.
if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = queue-position ]; then
scenario "6a. derives each new queue position from its parent chain and the priorities record"
new_case parent-chain-ticket-position
open_boards
export FLEET_LAUNCH_MAX_WAIT_S=120
: > "$HOLD_FILE"
parent_chain="$CASE_DIR/parent-chain"
priorities_record="$CASE_DIR/priorities-record"
parent_chain_log="$CASE_DIR/parent-chain.log"
: > "$parent_chain_log"
printf '%s\n' \
    '#!/usr/bin/env bash' \
    'printf "%s\\n" "$1" >> "$FLEET_LAUNCH_PARENT_CHAIN_LOG"' \
    'case "$1" in' \
    '  bd-ib-priority-two-ticket) printf "%s\\n" bd-ib-priority-two-child ;;' \
    '  bd-ib-priority-two-child) printf "%s\\n" bd-ib-priority-two-plan ;;' \
    '  bd-ib-priority-two-plan|bd-ib-priority-eleven-plan) exit 0 ;;' \
    '  *) exit 2 ;;' \
    'esac' > "$parent_chain"
chmod +x "$parent_chain"
printf '%s\n' '02 bd-ib-priority-two-plan' '11 bd-ib-priority-eleven-plan' > "$priorities_record"
export FLEET_LAUNCH_PARENT_CHAIN_COMMAND="$parent_chain"
export FLEET_LAUNCH_PARENT_CHAIN_LOG="$parent_chain_log"
export FLEET_LAUNCH_PRIORITIES_RECORD="$priorities_record"

# The lower caller value belongs to the lower-priority plan.  It must not choose
# a fresh ticket's place; only a re-exec of an already-created ticket may reuse it.
ONLY_GMK=1 TICKET_NS=001 "$LAUNCHER" bd-ib-priority-eleven-plan > "$CASE_DIR/p11.log" 2>&1 &
p11_pid=$!
if ! wait_for_line "$CASE_DIR/p11.log" 'hold file present' "$OBSERVE_WAIT_S"; then
    fail "the priority-eleven launcher did not reach the queue hold"
fi
ONLY_GMK=1 TICKET_NS=999 "$LAUNCHER" bd-ib-priority-two-ticket > "$CASE_DIR/p2.log" 2>&1 &
p2_pid=$!
if ! wait_for_line "$CASE_DIR/p2.log" 'gmktec FIFO ticket taken at start' "$OBSERVE_WAIT_S"; then
    fail "the priority-two launcher did not create a queue ticket"
fi
if wait_for_line "$CASE_DIR/p11.log" 'queued behind an older gmktec ticket:' 2 \
    && grep -qE 'queued behind an older gmktec ticket: .*item=bd-ib-priority-two-ticket$' "$CASE_DIR/p11.log" \
    && grep -qxF bd-ib-priority-two-ticket "$parent_chain_log" \
    && grep -qxF bd-ib-priority-two-child "$parent_chain_log"; then
    pass "the priority-two ticket mechanically walked its parent chain at ticket time"
else
    fail "a priority-two ticket did not outrank priority eleven by walking its parent chain at ticket time (parent reads: $(tr '\n' ' ' < "$parent_chain_log"))"
fi
stop_launcher "$p11_pid" "$p2_pid"
wait "$p11_pid" 2>/dev/null || true
wait "$p2_pid" 2>/dev/null || true

# queue_position_fixture: a one-plan parent chain and a priorities record naming the plan rank 11, wired
# through the two environment overrides; the launcher parks at the queue hold once it holds a ticket.
queue_position_fixture() {
    open_boards
    export FLEET_LAUNCH_MAX_WAIT_S=120
    : > "$HOLD_FILE"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'case "$1" in bd-ib-queue-child) printf "%s\\n" bd-ib-queue-plan ;; *) exit 0 ;; esac' \
        > "$CASE_DIR/parent-chain"
    chmod +x "$CASE_DIR/parent-chain"
    printf '%s\n' '11 bd-ib-queue-plan' > "$CASE_DIR/priorities-record"
    export FLEET_LAUNCH_PARENT_CHAIN_COMMAND="$CASE_DIR/parent-chain"
    export FLEET_LAUNCH_PRIORITIES_RECORD="$CASE_DIR/priorities-record"
}

scenario "6b. a hand-supplied TICKET_NS cannot place a fresh priority ticket"
new_case hand-placed-ticket-ns
queue_position_fixture
ONLY_GMK=1 TICKET_NS=00001-1 "$LAUNCHER" bd-ib-queue-child > "$CASE_DIR/hand.log" 2>&1 &
hand_pid=$!
if wait_for_line "$CASE_DIR/hand.log" 'gmktec FIFO ticket taken at start' "$OBSERVE_WAIT_S" \
    && grep -qE 'taken at start: 00011-[0-9]+-harness-seat$' "$CASE_DIR/hand.log"; then
    pass "a fresh ticket takes its plan's rank from the priorities record, not the supplied TICKET_NS"
else
    fail "a hand-supplied TICKET_NS placed a fresh priority ticket: $(grep 'ticket taken' "$CASE_DIR/hand.log")"
fi
stop_launcher "$hand_pid"
wait "$hand_pid" 2>/dev/null || true

scenario "6c. TICKET_NS restarts only a ticket that exists for the same item"
new_case restart-ticket-ns
queue_position_fixture
mkdir -p "$FLEET_LAUNCH_GMK_QUEUE_DIR"
printf 'owner=harness-seat pid=999999 item=bd-ib-queue-child\n' > "$FLEET_LAUNCH_GMK_QUEUE_DIR/00002-5-harness-seat"
printf 'owner=harness-seat pid=999999 item=bd-ib-other-item\n' > "$FLEET_LAUNCH_GMK_QUEUE_DIR/00003-7-harness-seat"
ONLY_GMK=1 TICKET_NS=00002-5 "$LAUNCHER" bd-ib-queue-child > "$CASE_DIR/restart.log" 2>&1 &
restart_pid=$!
if wait_for_line "$CASE_DIR/restart.log" 'gmktec FIFO ticket taken at start: 00002-5-harness-seat' "$OBSERVE_WAIT_S"; then
    pass "a restart naming the item's own existing ticket keeps that ticket's place"
else
    fail "a restart naming the item's own ticket did not keep it: $(grep 'ticket' "$CASE_DIR/restart.log")"
fi
stop_launcher "$restart_pid"
wait "$restart_pid" 2>/dev/null || true
rm -f "$FLEET_LAUNCH_GMK_QUEUE_DIR"/* "$FLEET_LAUNCH_GMK_QUEUE_DIR.claims"/* 2>/dev/null
printf 'owner=harness-seat pid=999999 item=bd-ib-other-item\n' > "$FLEET_LAUNCH_GMK_QUEUE_DIR/00003-7-harness-seat"
ONLY_GMK=1 TICKET_NS=00003-7 "$LAUNCHER" bd-ib-queue-child > "$CASE_DIR/foreign.log" 2>&1 &
foreign_pid=$!
if wait_for_line "$CASE_DIR/foreign.log" 'gmktec FIFO ticket taken at start' "$OBSERVE_WAIT_S" \
    && grep -qE 'taken at start: 00011-' "$CASE_DIR/foreign.log"; then
    pass "a TICKET_NS naming another item's ticket is not honored as a restart"
else
    fail "a TICKET_NS naming another item's ticket was honored: $(grep 'ticket taken' "$CASE_DIR/foreign.log")"
fi
stop_launcher "$foreign_pid"
wait "$foreign_pid" 2>/dev/null || true

scenario "6d. a whole-queue re-sort starts exactly one launcher per queued item"
new_case resort-one-launcher
queue_position_fixture
dup_pids=()
for n in 1 2 3 4 5; do
    ONLY_GMK=1 "$LAUNCHER" bd-ib-queue-child > "$CASE_DIR/dup$n.log" 2>&1 &
    dup_pids+=("$!")
done
dup_exits=0
deadline=$(( $(date +%s) + OBSERVE_WAIT_S ))
while [ "$dup_exits" -lt 4 ] && [ "$(date +%s)" -lt "$deadline" ]; do
    dup_exits=$(cat "$CASE_DIR"/dup?.log 2>/dev/null | grep -c 'already has a live launcher for bd-ib-queue-child')
    sleep "$HARNESS_POLL_S"
done
dup_tickets=$(grep -l 'item=bd-ib-queue-child' "$FLEET_LAUNCH_GMK_QUEUE_DIR"/* 2>/dev/null | wc -l)
if [ "$dup_exits" -eq 4 ] && [ "$dup_tickets" -eq 1 ]; then
    pass "five simultaneous launchers for one item leave one ticket and four duplicate refusals"
else
    fail "simultaneous launchers for one item left $dup_tickets tickets and $dup_exits refusals"
fi
stop_launcher "${dup_pids[@]}"
for pid in "${dup_pids[@]}"; do wait "$pid" 2>/dev/null || true; done

scenario "6e. the committed defaults supply the parent-chain and priorities-record sources"
new_case default-queue-sources
open_boards
export FLEET_LAUNCH_MAX_WAIT_S=120
: > "$HOLD_FILE"
default_config=$(env -i HOME="$HOME" FLEET_LAUNCH_STATE_DIR=/state FLEET_LAUNCH_GMK_QUEUE_DIR=/queue \
    bash -c '. "$1"; printf "%s\n%s\n%s\n" "$FLEET_LAUNCH_PRIORITIES_RECORD" "$FLEET_LAUNCH_PARENT_CHAIN_COMMAND" "$FLEET_LAUNCH_GMK_CLAIM_DIR"' _ "$LAUNCH_DIR/config.sh")
if [ "$default_config" = "/state/priorities-record
$LAUNCH_DIR/parent-of.sh
/queue.claims" ] && [ -x "$LAUNCH_DIR/parent-of.sh" ]; then
    pass "config.sh defaults the priorities record, the committed parent-of.sh command and the claim directory"
else
    fail "config.sh defaults are not the committed sources: $default_config"
fi
mkdir -p "$CASE_DIR/fake-bin"
printf '%s\n' '#!/usr/bin/env bash' \
    'case "$2" in' \
    '  bd-ib-default-child) printf "%s\\n" "[{\"id\":\"bd-ib-default-child\",\"dependencies\":[{\"id\":\"bd-ib-default-plan\",\"dependency_type\":\"parent-child\"},{\"id\":\"bd-ib-blocker\",\"dependency_type\":\"blocks\"}]}]" ;;' \
    '  *) printf "%s\\n" "[{\"id\":\"$2\"}]" ;;' \
    'esac' > "$CASE_DIR/fake-bin/bd"
chmod +x "$CASE_DIR/fake-bin/bd"
if [ "$(PATH="$CASE_DIR/fake-bin:$PATH" "$LAUNCH_DIR/parent-of.sh" bd-ib-default-child)" = bd-ib-default-plan ] \
    && [ -z "$(PATH="$CASE_DIR/fake-bin:$PATH" "$LAUNCH_DIR/parent-of.sh" bd-ib-default-plan)" ]; then
    pass "parent-of.sh reads the parent-child edge and prints nothing for a root"
else
    fail "parent-of.sh did not read the parent-child edge of a bd show record"
fi
printf '%s\n' '03 bd-ib-default-plan' > "$FLEET_LAUNCH_STATE_DIR/priorities-record"
PATH="$CASE_DIR/fake-bin:$PATH" ONLY_GMK=1 "$LAUNCHER" bd-ib-default-child > "$CASE_DIR/default.log" 2>&1 &
default_pid=$!
if wait_for_line "$CASE_DIR/default.log" 'gmktec FIFO ticket taken at start' "$OBSERVE_WAIT_S" \
    && grep -qE 'taken at start: 00003-[0-9]+-harness-seat$' "$CASE_DIR/default.log"; then
    pass "with no override set, the launcher ranks a ticket from the default record and parent command"
else
    fail "the default sources did not rank the ticket: $(grep 'ticket taken' "$CASE_DIR/default.log")"
fi
stop_launcher "$default_pid"
wait "$default_pid" 2>/dev/null || true
fi

# --- 6. queued preflights, reusable passes, and FIFO binds ------------------
# The slow older ticket creates a real queue interval.  The younger ticket must
# use that interval for its own Definition-of-Done preflight, rather than wait
# for the older launcher to bind first.  The same observation also proves that
# its fresh pass is not needlessly repeated at the head.
if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = scenario297 ]; then
scenario "6. preflights while queued and reuses a fresh pass at the FIFO head"
if bash "$HARNESS_DIR/test-scenario297-polling.sh"; then
    pass "the Scenario 297 cases poll observed state at the harness interval instead of sleeping fixed seconds"
else
    fail "the Scenario 297 polling configuration regressed"
fi
new_case queued-preflight
export FLEET_LAUNCH_MAX_WAIT_S=300
export STUB_PREFLIGHT_SLOW_ITEM=bd-ib-older
export STUB_PREFLIGHT_SLOW_S=120
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-older > "$CASE_DIR/older.log" 2>&1 &
older_pid=$!
if ! wait_for_preflight "$CASE_NAME" older "$older_pid" "$CASE_DIR/older.log" bd-ib-older 1; then
    fail "$PREFLIGHT_FAILURE_DETAIL"
fi
ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-younger > "$CASE_DIR/younger.log" 2>&1 &
younger_pid=$!
# The older preflight is held, so the older launcher cannot bind until the
# release below: a younger preflight seen first ran while it was queued.
if ! wait_for_preflight "$CASE_NAME" younger "$younger_pid" "$CASE_DIR/younger.log" bd-ib-younger 1; then
    fail "$PREFLIGHT_FAILURE_DETAIL"
elif [ ! -s "$DRIVE_LOG" ]; then
    pass "the younger queued launcher starts its preflight before the older binds"
else
    fail "the younger launcher waited for the FIFO head before starting its preflight"
fi
touch "$STUB_PREFLIGHT_RELEASE"
await_both "$older_pid" "$younger_pid" 90
# As in case 3: the younger ticket leaves the queue only after the older one
# was dropped at its bind; the two drive calls themselves may race.
if [ "$(drive_log_items | tr ' ' '\n' | sort | tr '\n' ' ' | sed 's/ $//')" = "bd-ib-older bd-ib-younger" ] \
    && grep -qE "queued behind an older gmktec ticket: owner=harness-seat pid=[0-9]+ item=bd-ib-older$" "$CASE_DIR/younger.log"; then
    pass "queued launchers bind in FIFO ticket order after their preflights"
else
    fail "queued launchers did not bind in FIFO order (younger never queued behind bd-ib-older, or a launch is missing); drives: $(drive_log_items)"
fi
if [ "$(preflight_count bd-ib-younger)" = 1 ]; then
    pass "a fresh queued preflight pass is reused when the younger launcher reaches the head"
else
    fail "a fresh queued preflight was run $(preflight_count bd-ib-younger) times at the head"
fi
# Each drive leaves one observation.  `released` means no launcher held the
# mutex; `held driver=A holder=B` with A != B means the older launcher had
# already released and the younger one took the mutex first, which the narrow
# mutex scope allows and which a loaded host makes likely.  Only a driver that
# still holds its OWN mutex is a violation, so count both legal shapes.
if ! grep -qE '^held driver=([^ ]+) holder=\1$' "$DRIVE_MUTEX_LOG" \
    && [ "$(grep -cE '^(released |held driver=)' "$DRIVE_MUTEX_LOG")" -ge 2 ]; then
    pass "the mutex is released before either drive --action impl starts"
else
    fail "a drive started while its launch mutex was held: $(tr '\n' ' ' < "$DRIVE_MUTEX_LOG")"
fi

# A young pass expires while the older launcher is held in its own
# preflight.  Its ticket must re-run the preflight at the FIFO head before it
# can take the mutex.
scenario "7. re-runs a stale queued preflight at the FIFO head"
new_case stale-preflight
export FLEET_LAUNCH_MAX_WAIT_S=300
export FLEET_LAUNCH_PREFLIGHT_REUSE_S=0
export STUB_PREFLIGHT_SLOW_ITEM=bd-ib-stale-older
export STUB_PREFLIGHT_SLOW_S=120
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-stale-older > "$CASE_DIR/older.log" 2>&1 &
older_pid=$!
wait_for_preflight "$CASE_NAME" older "$older_pid" "$CASE_DIR/older.log" bd-ib-stale-older 1 \
    || fail "$PREFLIGHT_FAILURE_DETAIL"
ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-stale-younger > "$CASE_DIR/younger.log" 2>&1 &
younger_pid=$!
if ! wait_for_preflight "$CASE_NAME" younger "$younger_pid" "$CASE_DIR/younger.log" bd-ib-stale-younger 1; then
    fail "$PREFLIGHT_FAILURE_DETAIL"
elif [ -s "$DRIVE_LOG" ]; then
    fail "the stale-case younger launcher did not preflight while queued"
fi
# A zero-second reuse window makes the observed queued pass stale as soon as
# the older launcher is released; no wall-clock delay is part of this case.
touch "$STUB_PREFLIGHT_RELEASE"
await_both "$older_pid" "$younger_pid" 90
if [ "$(preflight_count bd-ib-stale-younger)" = 2 ]; then
    pass "a stale queued pass is re-run at the FIFO head before binding"
else
    fail "a stale queued pass was not re-run at the FIFO head (count=$(preflight_count bd-ib-stale-younger))"
fi

# A queued preflight failure is terminal for that launcher.  The older ticket
# is deliberately still in its preflight, so a failed younger launcher cannot
# have touched the mutex on its way out.
scenario "8. drops a ticket when its queued preflight fails"
new_case queued-preflight-failure
export FLEET_LAUNCH_MAX_WAIT_S=300
export STUB_PREFLIGHT_SLOW_ITEM=bd-ib-failing-older
export STUB_PREFLIGHT_SLOW_S=120
export STUB_PREFLIGHT_FAIL_ITEM=bd-ib-failing-younger
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-failing-older > "$CASE_DIR/older.log" 2>&1 &
older_pid=$!
wait_for_preflight "$CASE_NAME" older "$older_pid" "$CASE_DIR/older.log" bd-ib-failing-older 1 \
    || fail "$PREFLIGHT_FAILURE_DETAIL"
ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-failing-younger > "$CASE_DIR/younger.log" 2>&1 &
younger_pid=$!
if ! wait_for_preflight "$CASE_NAME" younger "$younger_pid" "$CASE_DIR/younger.log" bd-ib-failing-younger 1; then
    stop_launcher "$younger_pid"
    wait "$younger_pid"; younger_rc=$?
    fail "$PREFLIGHT_FAILURE_DETAIL"
elif [ ! -s "$DRIVE_LOG" ]; then
    wait "$younger_pid"; younger_rc=$?
else
    stop_launcher "$younger_pid"
    wait "$younger_pid"; younger_rc=$?
    fail "the younger failing preflight did not start while its ticket was queued"
fi
if [ "$younger_rc" = 4 ] && [ ! -e "$CASE_DIR/queue/200-harness-seat" ] && [ ! -d "$CASE_DIR/lock" ]; then
    pass "a failed queued preflight exits 4, drops its ticket, and never takes the mutex"
else
    fail "queued preflight failure did not cleanly exit (rc=$younger_rc ticket=$(test -e "$CASE_DIR/queue/200-harness-seat" && echo present || echo absent) lock=$(test -d "$CASE_DIR/lock" && echo present || echo absent))"
fi
touch "$STUB_PREFLIGHT_RELEASE"
stop_launcher "$older_pid"
wait "$older_pid" || true
fi

# Cases 9-14 cover the resume launcher, seat-gated releases and in-flight marker count, not
# Scenario 297's queued preflight, so the scenario297 slice skips them: that
# slice runs under a 60 s bound in tests/integration/test_fleet_launch_scenario297.py
# and the full set took it to about 73 s, turning master red on every CI run.
if [ "$HARNESS_SLICE" = all ]; then
# --- 9. a resume shares FIFO and waits for fleet headroom -------------------
# The older impl ticket reaches the head first, but the fleet begins at the
# shared cap.  Once the board drops by one the impl binds, restoring the cap
# with its in-flight marker/run.  The resume keeps its own ticket while it sees
# that cap, then starts only after the older run disappears.
scenario "9. a resume waits at the fleet cap and shares the gmktec FIFO"
new_case resume-cap-fifo
export FLEET_LAUNCH_MAX_WAIT_S=120
write_board "$BOARD_GMK" 8 gmk
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
IMPL_LOG="$CASE_DIR/impl.log"
RESUME_CASE_LOG="$CASE_DIR/resume-launcher.log"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-resume-older > "$IMPL_LOG" 2>&1 &
impl_pid=$!
if ! wait_for_line "$IMPL_LOG" "fleet not green" 30; then
    fail "the older impl ticket did not wait at the fleet cap"
fi
TICKET_NS=200 "$RESUME_LAUNCHER" bd-ib-resume > "$RESUME_CASE_LOG" 2>&1 &
resume_pid=$!
if wait_for_line "$RESUME_CASE_LOG" "queued behind an older gmktec ticket" 30; then
    pass "the resume ticket queues behind the older impl ticket"
else
    fail "the resume launcher did not queue behind the older impl ticket"
    tail -8 "$RESUME_CASE_LOG" >&2
fi
write_board "$BOARD_GMK" 7 gmk
if wait_for_line "$IMPL_LOG" "LAUNCH target=petri" 30 \
    && wait_for_line "$RESUME_CASE_LOG" "fleet at cap under mutex" 30 \
    && [ ! -s "$RESUME_LOG" ]; then
    pass "the resume keeps its FIFO ticket while the older impl refills the fleet cap"
else
    fail "the resume did not wait at the cap after the older impl bound"
    tail -8 "$IMPL_LOG" >&2
    tail -8 "$RESUME_CASE_LOG" >&2
fi
# The older run "ends" by leaving the board.  Remove its driven row only once
# the impl's stub dispatch has finished writing it: the LAUNCH line is printed
# BEFORE drive.py runs, so removing the row at LAUNCH raced the stub writing it,
# the row came back, the board stayed at the cap and the resume gave up
# (resume=75), measured 2 of 4 parallel harness runs on 2026-11-03.
wait_for_line "$IMPL_LOG" "drive rc=" 120 || fail "the older impl's dispatch did not finish"
rm -f "$CASE_DIR/driven/bd-ib-resume-older"
wait "$impl_pid"; impl_rc=$?
wait "$resume_pid"; resume_rc=$?
if [ "$impl_rc" = 0 ] && [ "$resume_rc" = 0 ] && [ "$(cat "$RESUME_LOG")" = bd-ib-resume ]; then
    pass "the resume starts after the fleet count drops below the cap"
else
    fail "the capped resume did not start cleanly (impl=$impl_rc resume=$resume_rc resumes=$(tr '\n' ' ' < "$RESUME_LOG"))"
fi
if grep -q '^bd-ib-resume marker=present mutex=released$' "$RESUME_OBSERVATION_LOG"; then
    pass "the resume in-flight marker exists before its mutex is released"
else
    fail "the resume did not retain its marker through mutex release: $(tr '\n' ' ' < "$RESUME_OBSERVATION_LOG")"
fi

# --- 10. a seat-gated direct release waits for the cap ----------------------
# A blocked item is deliberately absent from the ready set until its release
# action runs.  The release must therefore bypass that first ready-set read,
# but only after the normal FIFO/cap binding has made space and retained its
# in-flight marker.
scenario "10. a seat-gated direct release waits for the fleet cap"
new_case direct-release-cap
export FLEET_LAUNCH_MAX_WAIT_S=120
export STUB_READY_BLOCKED_UNTIL_RELEASE=1
write_board "$BOARD_GMK" 8 gmk
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
DIRECT_RELEASE_LOG="$CASE_DIR/direct-release-launcher.log"
RELEASE_BLOCKED=1 ONLY_GMK=1 "$LAUNCHER" bd-ib-direct-release > "$DIRECT_RELEASE_LOG" 2>&1 &
direct_release_pid=$!
if wait_for_line "$DIRECT_RELEASE_LOG" "fleet not green" 30 \
    && [ ! -s "$RELEASE_LOG" ] \
    && [ ! -s "$DRIVE_LOG" ]; then
    pass "a seat-gated direct release waits for fleet headroom before it releases or drives"
else
    fail "the direct release bypassed the fleet cap or stalled before the cap gate"
    tail -8 "$DIRECT_RELEASE_LOG" >&2
fi
write_board "$BOARD_GMK" 7 gmk
wait "$direct_release_pid"; direct_release_rc=$?
if [ "$direct_release_rc" = 0 ] \
    && grep -qx 'resolve-blocked:bd-ib-direct-release:ready' "$RELEASE_LOG" \
    && grep -qx 'bd-ib-direct-release' "$DRIVE_LOG"; then
    pass "the release and its drive run only after the capped FIFO binding"
else
    fail "the seat-gated direct release did not complete through the launcher (rc=$direct_release_rc releases=$(tr '\n' ' ' < "$RELEASE_LOG") drives=$(drive_log_items))"
    tail -8 "$DIRECT_RELEASE_LOG" >&2
fi

# --- 10b. a held direct release counts as one in-flight launch --------------
# While the direct release's drive runs and before its run lists, the marker it
# kept must count against the cap for a queued second launcher: with one slot
# free on the board, the held release fills it, so the second launcher sees the
# fleet at the cap and starts no drive of its own.
scenario "10b. a queued launcher counts a held direct release as in flight"
load_capacity=$(nproc 2>/dev/null || echo 1)
case $load_capacity in ''|*[!0-9]*|0) load_capacity=1 ;; esac
if [ -r /sys/fs/cgroup/cpu.max ]; then
    read -r load_quota load_period < /sys/fs/cgroup/cpu.max
    case "$load_quota:$load_period" in
        *[!0-9:]*|:*) ;;
        *) load_capacity=$(( (load_quota + load_period - 1) / load_period )) ;;
    esac
fi
case $load_capacity in ''|*[!0-9]*|0) load_capacity=1 ;; esac
load_workers="${LIVESPEC_TEST_PARALLELISM:-$load_capacity}"
case $load_workers in ''|*[!0-9]*|0) load_workers=1 ;; esac
if [ "$load_workers" -gt "$load_capacity" ]; then
    load_workers=$load_capacity
fi
if [ "$load_workers" -gt 4 ]; then
    load_workers=4
fi
load_worker=0
while [ "$load_worker" -lt "$load_workers" ]; do
    while :; do :; done &
    LOAD_PIDS="$LOAD_PIDS $!"
    load_worker=$((load_worker + 1))
done
for held_attempt in $(seq 1 "${HARNESS_CASE_10B_ATTEMPTS:-30}"); do
    new_case "direct-release-inflight-counted-$held_attempt"
    # Preserve the board reading taken before launch. The drive then submits and
    # exits while this snapshot remains young, reproducing the loaded-host race.
    export FLEET_LAUNCH_MAX_WAIT_S=0
    export FLEET_LAUNCH_BOARD_TTL_S=300
    export STUB_READY_BLOCKED_UNTIL_RELEASE=1
    export STUB_DRIVE_ADMIT_GATE="$STUB_DRIVE_ADMIT_GATE_FILE"
    write_board "$BOARD_GMK" 7 gmk
    : > "$BOARD_HL"
    printf '8\n' > "$CAP_FILE"
    mkdir -p "$SNAPSHOT_DIR"
    . "$LAUNCH_DIR/board-snapshot.sh"
    "$STUB/fabro" ps -a --server "$GMK_URL" > "$(board_snapshot_file "$GMK_URL")"
    "$STUB/fabro" ps -a --server "$HL_URL" > "$(board_snapshot_file "$HL_URL")"
    DIRECT_RELEASE_LOG="$CASE_DIR/direct-release-launcher.log"
    RELEASE_BLOCKED=1 ONLY_GMK=1 "$LAUNCHER" bd-ib-held-release > "$DIRECT_RELEASE_LOG" 2>&1 &
    held_release_pid=$!
    # The verdict is ordered on the observed waiting marker, never on elapsed
    # time: the shared hang guard only stops a genuinely hung release from
    # holding the harness forever, and a wait that reaches it fails by name.
    held_hang_deadline=$(( $(date +%s) + HARNESS_PREFLIGHT_HANG_GUARD_S ))
    held_hung=0
    while ! grep -qx 'bd-ib-held-release' "$STUB_DRIVE_WAITING"; do
        if [ "$(date +%s)" -ge "$held_hang_deadline" ]; then
            held_hung=1
            break
        fi
        sleep "$HARNESS_POLL_S"
    done
    if [ "$held_hung" = 1 ]; then
        fail "attempt $held_attempt: the wait for the held direct release to reach its drive's waiting state hung past the ${HARNESS_PREFLIGHT_HANG_GUARD_S}s guard (releases=$(tr '\n' ' ' < "$RELEASE_LOG"))"
        tail -8 "$DIRECT_RELEASE_LOG" >&2
    elif grep -qx 'bd-ib-held-release' "$STUB_DRIVE_WAITING" \
        && grep -qx 'resolve-blocked:bd-ib-held-release:ready' "$RELEASE_LOG" \
        && [ -n "$(find "$CASE_DIR/inflight" -type f -print -quit)" ]; then
        pass "attempt $held_attempt: the direct release holds its in-flight marker while its drive runs and before its run lists"
    else
        fail "attempt $held_attempt: the direct release did not hold a marker during its drive (releases=$(tr '\n' ' ' < "$RELEASE_LOG"))"
        tail -8 "$DIRECT_RELEASE_LOG" >&2
    fi
    SECOND_LOG="$CASE_DIR/second-launcher.log"
    FLEET_LAUNCH_MAX_WAIT_S=4 ONLY_GMK=1 "$LAUNCHER" bd-ib-second > "$SECOND_LOG" 2>&1; second_rc=$?
    if [ "$second_rc" = 75 ] && log_has "$SECOND_LOG" "fleet=8 cap=8" \
        && ! grep -qx 'bd-ib-second' "$DRIVE_LOG"; then
        pass "attempt $held_attempt: a queued launcher counts the held direct release against the cap and starts no drive"
    else
        fail "attempt $held_attempt: a queued launcher did not count the held direct release (rc=$second_rc drives=$(drive_log_items))"
        tail -6 "$SECOND_LOG" >&2
    fi
    : > "$STUB_DRIVE_ADMIT_GATE_FILE"
    wait "$held_release_pid"; held_release_rc=$?
    if [ "$held_release_rc" = 0 ] && [ -z "$(find "$CASE_DIR/inflight" -type f -print -quit)" ]; then
        pass "attempt $held_attempt: the direct release drops its marker once its run lists"
    else
        fail "attempt $held_attempt: the direct release did not finish cleanly (rc=$held_release_rc)"
        tail -8 "$DIRECT_RELEASE_LOG" >&2
    fi
done
stop_load

# --- 11. a resume marker stays counted until the board lists the run --------
# The resume client returns at once, before the run lists on the board.  The
# launcher must keep its in-flight marker so concurrent launchers still count
# the resume, and drop it only after the board lists the run.
scenario "10. a resume marker stays counted after the client returns, until the board lists the run"
new_case resume-marker-retained
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
export STUB_RESUME_UNLISTED=1
RESUME_CASE_LOG="$CASE_DIR/resume-launcher.log"
"$RESUME_LAUNCHER" bd-ib-unlisted > "$RESUME_CASE_LOG" 2>&1 &
resume_pid=$!
waited=0
while [ ! -s "$RESUME_LOG" ] && [ "$waited" -lt 30 ]; do sleep 1; waited=$((waited + 1)); done
sleep 3
if kill -0 "$resume_pid" 2>/dev/null && [ -n "$(find "$CASE_DIR/inflight" -type f -print -quit)" ]; then
    pass "the resume marker is still present after the client returned before the board listed it"
else
    fail "the resume marker was dropped before the board listed the run"
fi
printf '%s %s\n' "$GMK_URL" bd-ib-unlisted > "$CASE_DIR/resumed/bd-ib-unlisted"
wait "$resume_pid"; resume_rc=$?
if [ "$resume_rc" = 0 ] && [ -z "$(find "$CASE_DIR/inflight" -type f -print -quit)" ]; then
    pass "the resume marker is removed once the board lists the run"
else
    fail "the resume marker was not cleared after listing (rc=$resume_rc)"
fi

# --- 12. an unreadable in-flight directory counts as at the cap -------------
# A regular file stands where the in-flight directory belongs, so the count of
# in-flight launches cannot be read.  With empty boards and headroom under the
# cap, the resume must still refuse to start.
scenario "11. a resume refuses to start when the in-flight directory cannot be read"
new_case resume-inflight-unreadable
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
rmdir "$FLEET_LAUNCH_INFLIGHT_DIR"
: > "$FLEET_LAUNCH_INFLIGHT_DIR"
RESUME_CASE_LOG="$CASE_DIR/resume-launcher.log"
"$RESUME_LAUNCHER" bd-ib-blind > "$RESUME_CASE_LOG" 2>&1; resume_rc=$?
if [ "$resume_rc" = 75 ] && [ ! -s "$RESUME_LOG" ] && grep -q 'fleet=U' "$RESUME_CASE_LOG"; then
    pass "the resume treats an unreadable in-flight directory as at the cap and does not start"
else
    fail "the resume started or misread an unreadable in-flight directory (rc=$resume_rc resumes=$(tr '\n' ' ' < "$RESUME_LOG"))"
fi

# --- 13. a launch that lists between the board read and the marker read ----
# Another launcher's in-flight marker covers a run the board does not list yet.
# During the resume's board read, that launcher sees its run listed and removes
# its marker (the hook below does both, after the read has captured its rows).
# The resume must still count that launch: its board read predates the listing,
# so the marker it read must be counted, and the fleet stays at the cap.
scenario "12. a launch listed between the board read and the marker read stays counted"
new_case resume-listing-race
export FLEET_LAUNCH_MAX_WAIT_S=6
write_board "$BOARD_GMK" 7 gmk
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
sleep 600 &
racer_pid=$!
racer_marker="$FLEET_LAUNCH_INFLIGHT_DIR/100-other-seat-bd-ib-racer"
echo "owner=other-seat pid=$racer_pid item=bd-ib-racer factory=petri" > "$racer_marker"
cat > "$CASE_DIR/list-racer.sh" <<HOOK
printf '%s %s\\n' "$GMK_URL" bd-ib-racer > "$CASE_DIR/driven/bd-ib-racer"
rm -f "$racer_marker"
HOOK
export STUB_PS_AFTER_READ_HOOK="$CASE_DIR/list-racer.sh"
RESUME_CASE_LOG="$CASE_DIR/resume-launcher.log"
"$RESUME_LAUNCHER" bd-ib-race-resume > "$RESUME_CASE_LOG" 2>&1; resume_rc=$?
unset STUB_PS_AFTER_READ_HOOK
kill "$racer_pid" 2>/dev/null; wait "$racer_pid" 2>/dev/null
if [ "$resume_rc" = 75 ] && [ ! -s "$RESUME_LOG" ] && grep -q 'fleet at cap under mutex: fleet=8 cap=8' "$RESUME_CASE_LOG"; then
    pass "a launch listed between the board read and the marker read keeps the fleet at the cap"
else
    fail "the resume undercounted a launch that listed mid-read (rc=$resume_rc resumes=$(tr '\n' ' ' < "$RESUME_LOG"))"
    tail -6 "$RESUME_CASE_LOG" >&2
fi

# --- 14. the impl launcher counts a launch listed mid-read too -------------
# The same race as case 12, against the impl launcher's fleet-green count.
scenario "13. the impl launcher keeps a launch listed mid-read counted"
new_case impl-listing-race
export FLEET_LAUNCH_MAX_WAIT_S=6
write_board "$BOARD_GMK" 7 gmk
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
sleep 600 &
racer_pid=$!
racer_marker="$FLEET_LAUNCH_INFLIGHT_DIR/100-other-seat-bd-ib-racer"
echo "owner=other-seat pid=$racer_pid item=bd-ib-racer factory=petri" > "$racer_marker"
cat > "$CASE_DIR/list-racer.sh" <<HOOK
printf '%s %s\\n' "$GMK_URL" bd-ib-racer > "$CASE_DIR/driven/bd-ib-racer"
rm -f "$racer_marker"
HOOK
export STUB_PS_AFTER_READ_HOOK="$CASE_DIR/list-racer.sh"
IMPL_CASE_LOG="$CASE_DIR/impl-launcher.log"
ONLY_GMK=1 "$LAUNCHER" bd-ib-race-impl > "$IMPL_CASE_LOG" 2>&1; impl_rc=$?
unset STUB_PS_AFTER_READ_HOOK
kill "$racer_pid" 2>/dev/null; wait "$racer_pid" 2>/dev/null
if [ ! -s "$DRIVE_LOG" ] && grep -q 'fleet not green: gmktec=7 hl=0 markers=1 fleet=8 cap=8' "$IMPL_CASE_LOG"; then
    pass "the impl launcher counts a launch listed between the board read and the marker read"
else
    fail "the impl launcher undercounted a launch that listed mid-read (rc=$impl_rc drives=$(tr '\n' ' ' < "$DRIVE_LOG"))"
    tail -6 "$IMPL_CASE_LOG" >&2
fi

# --- 14. queued launchers share one board snapshot --------------------------
# Six launchers poll one at-cap fleet at once, against a petri-sized slow listing. Each polls
# for the whole wait window, yet the factory server is asked for ONE listing per factory:
# the first launcher refreshes the snapshot and the others read it, instead of each sending the
# server a listing of its own on every poll (bd-ib-busjvz).
scenario "14. queued launchers read one shared board snapshot"
new_case snapshot-shared
export FLEET_LAUNCH_MAX_WAIT_S=4
export FLEET_LAUNCH_BOARD_TTL_S=300
export STUB_PS_DELAY_S=1
write_board "$BOARD_GMK" 3 gmk
write_board "$BOARD_HL" 1 hl
printf '4\n' > "$CAP_FILE"
snapshot_pids=""
for index in 1 2 3 4 5 6; do
    "$LAUNCHER" "bd-ib-shared-$index" > "$CASE_DIR/launcher-$index.log" 2>&1 &
    snapshot_pids="$snapshot_pids $!"
done
snapshot_bad=0
for snapshot_pid in $snapshot_pids; do
    wait "$snapshot_pid"; [ "$?" = 75 ] || snapshot_bad=$((snapshot_bad + 1))
done
if [ "$(ps_count "$GMK_URL")" = 1 ] && [ "$(ps_count "$HL_URL")" = 1 ]; then
    pass "six polling launchers sent each factory server one listing"
else
    fail "the factory servers were asked for gmktec=$(ps_count "$GMK_URL") mi-homelab=$(ps_count "$HL_URL") listings, not one each"
fi
if [ "$snapshot_bad" = 0 ] && [ -z "$(cat "$DRIVE_LOG")" ] \
    && [ "$(grep -lF 'gmktec=3 hl=1 markers=0 fleet=4' "$CASE_DIR"/launcher-*.log | wc -l)" = 6 ]; then
    pass "every launcher read the same fleet of four from the snapshot and held at the cap"
else
    fail "a launcher read a different fleet or launched (unexpected exits: $snapshot_bad)"
    tail -3 "$CASE_DIR/launcher-1.log" >&2
fi

# --- 14a. a refresh handoff is re-checked after taking the lock -------------
# A peer can finish its refresh after this launcher sees the snapshot as stale
# but before it takes the now-free lock. Make that window deterministic: the
# first age check says stale while writing the peer's fresh snapshot. The
# post-lock age check must then read that snapshot without another listing.
scenario "14a. a refresh handoff re-checks the shared board snapshot"
new_case snapshot-refresh-handoff
export FLEET_LAUNCH_BOARD_TTL_S=300
mkdir -p "$SNAPSHOT_DIR"
. "$LAUNCH_DIR/board-snapshot.sh"
handoff_snapshot=$(board_snapshot_file "$GMK_URL")
handoff_age_checks=0
board_snapshot_age_ok() {
    handoff_age_checks=$((handoff_age_checks + 1))
    if [ "$handoff_age_checks" = 1 ]; then
        printf '%s\n' "$BOARD_HEADER" > "$handoff_snapshot"
        return 1
    fi
    [ -f "$1" ]
}
handoff_text=$(board_snapshot_text "$STUB/fabro" "$GMK_URL")
handoff_rc=$?
if [ "$handoff_rc" = 0 ] && [ "$handoff_text" = "$BOARD_HEADER" ] \
    && [ "$(ps_count "$GMK_URL")" = 0 ] && [ ! -d "$handoff_snapshot.refresh.d" ]; then
    pass "a launcher that takes a refreshed lock reads the peer snapshot without listing"
else
    fail "a launcher listed after a peer refreshed the snapshot (rc=$handoff_rc listings=$(ps_count "$GMK_URL"))"
fi

# --- 15. an old snapshot is refreshed, a young one is not -------------------
scenario "15. a snapshot older than the TTL is refreshed before the count"
new_case snapshot-ttl
export FLEET_LAUNCH_BOARD_TTL_S=300
write_board "$BOARD_GMK" 3 gmk
write_board "$BOARD_HL" 1 hl
printf '4\n' > "$CAP_FILE"
run_launcher bd-ib-ttl-seed
write_board "$BOARD_GMK" 1 gmk
run_launcher bd-ib-ttl-young "$CASE_DIR/young.log"
if log_has "$CASE_DIR/young.log" "gmktec=3 hl=1 markers=0 fleet=4" && [ "$(ps_count "$GMK_URL")" = 1 ] && [ ! -s "$DRIVE_LOG" ]; then
    pass "a snapshot younger than the TTL is read without asking the server again"
else
    fail "a young snapshot was not shared (gmktec listings: $(ps_count "$GMK_URL"))"
    tail -3 "$CASE_DIR/young.log" >&2
fi
find "$SNAPSHOT_DIR" -name '*.ps' -exec touch -d '2 hours ago' {} +
export STUB_DRIVE_EXPIRE_SNAPSHOT=1
run_launcher bd-ib-ttl-old "$CASE_DIR/old.log"
unset STUB_DRIVE_EXPIRE_SNAPSHOT
if [ "$(ps_count "$GMK_URL")" -ge 2 ] && [ "$(drive_log_items)" = "bd-ib-ttl-old" ] && [ "$RC" = 0 ]; then
    pass "control: a snapshot older than the TTL is refreshed and the launcher counts the new board"
else
    fail "an old snapshot was not refreshed (gmktec listings: $(ps_count "$GMK_URL") rc=$RC dispatches: $(drive_log_items))"
    tail -4 "$CASE_DIR/old.log" >&2
fi

# --- 16. a refresh that cannot read the board is unknown, not zero ----------
scenario "16. an unreadable refresh leaves the fleet count unknown"
new_case snapshot-unreadable
export FLEET_LAUNCH_BOARD_TTL_S=300
write_board "$BOARD_GMK" 0 gmk
: > "$BOARD_HL"
run_launcher bd-ib-unreadable-seed
find "$SNAPSHOT_DIR" -name '*.ps' -exec touch -d '2 hours ago' {} +
rm -f "$BOARD_GMK"
printf '8\n' > "$CAP_FILE"
run_launcher bd-ib-unreadable "$CASE_DIR/unreadable.log"
if log_has "$CASE_DIR/unreadable.log" "fleet not green: gmktec=U" && [ ! -s "$DRIVE_LOG" ]; then
    pass "the stale snapshot's empty board was not used: the count was unknown and nothing launched"
else
    fail "an unreadable refresh fell back to the stale snapshot (rc=$RC dispatches: $(drive_log_items))"
    tail -4 "$CASE_DIR/unreadable.log" >&2
fi

# --- 17. the binding count reads the factory directly -----------------------
# The snapshot says one run is live, the factory has seven. The green check reads the snapshot and
# passes; the binding count under the mutex must read the factory and refuse. Then the same
# launcher, once the factory agrees with the snapshot, launches (the positive control).
scenario "17. the binding count reads the board directly, not the snapshot"
new_case snapshot-binding
export FLEET_LAUNCH_BOARD_TTL_S=300
export FLEET_LAUNCH_MAX_WAIT_S=6
write_board "$BOARD_GMK" 1 gmk
: > "$BOARD_HL"
printf '9\n' > "$CAP_FILE"
FLEET_LAUNCH_GMK_CAP=1 run_launcher bd-ib-seed-binding "$CASE_DIR/seed.log"
write_board "$BOARD_GMK" 9 gmk
FLEET_LAUNCH_GMK_CAP=20 run_launcher bd-ib-binding "$CASE_DIR/binding.log"
if log_has "$CASE_DIR/binding.log" "binding count with our marker: fleet=10 cap=9" && [ ! -s "$DRIVE_LOG" ]; then
    pass "the binding count saw the factory's nine runs that the snapshot did not list"
else
    fail "the binding count did not read the board directly (rc=$RC dispatches: $(drive_log_items))"
    tail -4 "$CASE_DIR/binding.log" >&2
fi
write_board "$BOARD_GMK" 1 gmk
export STUB_DRIVE_EXPIRE_SNAPSHOT=1
run_launcher bd-ib-binding-control "$CASE_DIR/control.log"
unset STUB_DRIVE_EXPIRE_SNAPSHOT
if [ "$(drive_log_items)" = "bd-ib-binding-control" ] && [ "$RC" = 0 ]; then
    pass "control: with the factory agreeing with the snapshot the same launcher launches"
else
    fail "control: the launcher did not launch (rc=$RC dispatches: $(drive_log_items))"
    tail -4 "$CASE_DIR/control.log" >&2
fi

# --- 18. launcher lines carry a UTC date-time -------------------------------
scenario "18. launcher log lines are stamped with an ISO-8601 UTC date-time"
new_case iso-stamp
write_board "$BOARD_GMK" 2 gmk
write_board "$BOARD_HL" 1 hl
run_launcher bd-ib-stamp "$CASE_DIR/impl-stamp.log"
printf '3\n' > "$CAP_FILE"
"$RESUME_LAUNCHER" bd-ib-stamp-resume > "$CASE_DIR/resume-stamp.log" 2>&1
stamp_pattern='^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z '
if grep -qE "$stamp_pattern" "$CASE_DIR/impl-stamp.log" && ! grep -E '^[0-9]{2}:[0-9]{2}:[0-9]{2} ' "$CASE_DIR/impl-stamp.log" | grep . >/dev/null \
    && grep -qE "$stamp_pattern" "$CASE_DIR/resume-stamp.log" && ! grep -E '^[0-9]{2}:[0-9]{2}:[0-9]{2} ' "$CASE_DIR/resume-stamp.log" | grep . >/dev/null; then
    pass "both launchers stamp every line with a date, not a time of day alone"
else
    fail "a launcher line carried a time of day without its date"
    head -4 "$CASE_DIR/impl-stamp.log" "$CASE_DIR/resume-stamp.log" >&2
fi

fi

# --- 18a. a marker released after its listed run leaves the board -----------
# Scenario 242 — The provisional fleet launch check fails the build on a broken
# launcher. A dead launcher may leave its marker behind while its drive
# merge-polls. Once another launcher has observed that marker's run on a board,
# the marker must no longer hold a slot after the run leaves that board. A
# never-listed marker remains counted while that drive is alive.
if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = scenario242 ]; then
# A stand-in for a dead launcher's live drive, whose command line the
# launcher's `pgrep -f "drive.py .*--action impl:<item>( |$)"` matches.  The
# drive arguments ride as ordinary trailing argv of a sleeping python3, never
# as a renamed argv[0]: the uutils coreutils multicall sleep refuses an
# unrecognised argv[0] ("Security violation: Requested utility ... does not
# match executable name"), and so does a mise shim ("... is not a valid
# shim") (bd-ib-jp82i).
start_named_drive() {
    python3 -c 'import time; time.sleep(600)' drive.py --action "impl:$1" &
}
scenario "18a. releases a listed-and-finished drive's stale marker"
new_case listed-marker-left-board
export FLEET_LAUNCH_MAX_WAIT_S=4
write_board "$BOARD_GMK" 7 gmk
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
start_named_drive bd-ib-ended
ended_drive_pid=$!
ended_marker="$FLEET_LAUNCH_INFLIGHT_DIR/100-stopped-seat-bd-ib-ended"
echo "owner=stopped-seat pid=999999 item=bd-ib-ended factory=petri" > "$ended_marker"
printf '%s %s\n' "$GMK_URL" bd-ib-ended > "$CASE_DIR/driven/bd-ib-ended"
ONLY_GMK=1 "$LAUNCHER" bd-ib-observer > "$CASE_DIR/observer.log" 2>&1 &
observer_pid=$!
if wait_for_line "$ended_marker" "listed=1" "$OBSERVE_WAIT_S"; then
    pass "a board observer records that the dead launcher's run listed"
else
    fail "the observed listed run was not recorded on its in-flight marker"
fi
stop_launcher "$observer_pid"
wait "$observer_pid" 2>/dev/null || true
rm -f "$CASE_DIR/driven/bd-ib-ended"
run_launcher bd-ib-after-ended "$CASE_DIR/after-ended.log"
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = bd-ib-after-ended ]; then
    pass "a listed-and-finished run's merge-polling drive no longer holds a fleet slot"
else
    fail "a listed-and-finished run still held a fleet slot (rc=$RC dispatches: $(drive_log_items))"
    tail -6 "$CASE_DIR/after-ended.log" >&2
fi
kill "$ended_drive_pid" 2>/dev/null; wait "$ended_drive_pid" 2>/dev/null

new_case unlisted-marker-stays-counted
export FLEET_LAUNCH_MAX_WAIT_S=4
write_board "$BOARD_GMK" 7 gmk
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
start_named_drive bd-ib-unlisted
unlisted_drive_pid=$!
echo "owner=stopped-seat pid=999999 item=bd-ib-unlisted factory=petri" \
    > "$FLEET_LAUNCH_INFLIGHT_DIR/100-stopped-seat-bd-ib-unlisted"
run_launcher bd-ib-must-wait "$CASE_DIR/unlisted.log"
if [ "$RC" = 75 ] && [ ! -s "$DRIVE_LOG" ] \
    && log_has "$CASE_DIR/unlisted.log" "fleet=8 cap=8"; then
    pass "an unlisted marker remains counted while its dead launcher has a live drive"
else
    fail "an unlisted marker did not hold the fleet slot (rc=$RC dispatches: $(drive_log_items))"
    tail -6 "$CASE_DIR/unlisted.log" >&2
fi
kill "$unlisted_drive_pid" 2>/dev/null; wait "$unlisted_drive_pid" 2>/dev/null
fi

# --- 19. repository holds scope themselves to their named launch kinds ------
# A repository hold yields its own FIFO ticket so another launch kind can run.
# The scope parser fails closed: absent, empty, and malformed kinds all retain
# the former all-kinds hold.  The launch-point case puts the hold in place only
# after the impl launcher has reached the mutex, proving that the binding path
# re-reads the hold before it can call drive.
if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = scenario316 ]; then
scenario "19. repository holds scope launch kinds and are re-read under the mutex"
new_case repository-hold-dispatch
export FLEET_LAUNCH_MAX_WAIT_S=120
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
cat > "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")" <<'HOLD'
kinds: dispatch
reason: commit_green ceiling
until: PR 4440 merged
HOLD
DISPATCH_LOG="$CASE_DIR/dispatch.log"
RESUME_CASE_LOG="$CASE_DIR/resume.log"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-held-dispatch > "$DISPATCH_LOG" 2>&1 &
dispatch_pid=$!
if ! wait_for_line "$DISPATCH_LOG" "repository hold present" "$OBSERVE_WAIT_S"; then
    fail "a dispatch-scoped repository hold did not yield the impl launcher"
fi
TICKET_NS=200 "$RESUME_LAUNCHER" bd-ib-open-resume > "$RESUME_CASE_LOG" 2>&1
resume_rc=$?
if kill -0 "$dispatch_pid" 2>/dev/null \
    && [ -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat" ] \
    && [ ! -s "$DRIVE_LOG" ] \
    && [ "$resume_rc" = 0 ] \
    && [ "$(cat "$RESUME_LOG")" = bd-ib-open-resume ] \
    && grep -qF 'kinds=dispatch reason=commit_green ceiling until=PR 4440 merged' "$DISPATCH_LOG"; then
    pass "a dispatch-scoped hold keeps the impl ticket, lets resume launch, and logs its scope"
else
    fail "a dispatch-scoped hold did not keep only the impl launch parked"
    tail -n 8 "$DISPATCH_LOG" "$RESUME_CASE_LOG" >&2
fi
stop_launcher "$dispatch_pid"
wait "$dispatch_pid" 2>/dev/null

new_case repository-hold-resume
export FLEET_LAUNCH_MAX_WAIT_S=120
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
printf 'kinds: resume\n' > "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
RESUME_CASE_LOG="$CASE_DIR/resume.log"
IMPL_LOG="$CASE_DIR/impl.log"
TICKET_NS=100 "$RESUME_LAUNCHER" bd-ib-held-resume > "$RESUME_CASE_LOG" 2>&1 &
resume_pid=$!
if ! wait_for_line "$RESUME_CASE_LOG" "repository hold present" "$OBSERVE_WAIT_S"; then
    fail "a resume-scoped repository hold did not yield the resume launcher"
fi
ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-open-dispatch > "$IMPL_LOG" 2>&1
impl_rc=$?
if kill -0 "$resume_pid" 2>/dev/null \
    && grep -lF 'item=bd-ib-held-resume' "$FLEET_LAUNCH_GMK_QUEUE_DIR"/* >/dev/null 2>&1 \
    && [ ! -s "$RESUME_LOG" ] \
    && [ "$impl_rc" = 0 ] \
    && [ "$(drive_log_items)" = bd-ib-open-dispatch ]; then
    pass "a resume-scoped hold keeps the resume ticket and lets dispatch launch"
else
    fail "a resume-scoped hold did not keep only the resume launch parked"
    tail -n 8 "$RESUME_CASE_LOG" "$IMPL_LOG" >&2
fi
stop_launcher "$resume_pid"
wait "$resume_pid" 2>/dev/null

for hold_shape in no-kinds empty-kinds malformed-kinds; do
    new_case "repository-hold-$hold_shape"
    export FLEET_LAUNCH_MAX_WAIT_S=120
    : > "$BOARD_GMK"
    : > "$BOARD_HL"
    printf '8\n' > "$CAP_FILE"
    hold_path="$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
    case "$hold_shape" in
        no-kinds) printf 'reason: all launch kinds\n' > "$hold_path" ;;
        empty-kinds) printf 'kinds: \n' > "$hold_path" ;;
        malformed-kinds) printf 'kinds: dispatch,unknown\n' > "$hold_path" ;;
    esac
    ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-held-impl > "$CASE_DIR/impl.log" 2>&1 &
    impl_pid=$!
    TICKET_NS=200 "$RESUME_LAUNCHER" bd-ib-held-resume > "$CASE_DIR/resume.log" 2>&1 &
    resume_pid=$!
    if wait_for_line "$CASE_DIR/impl.log" "repository hold present" "$OBSERVE_WAIT_S" \
        && wait_for_line "$CASE_DIR/resume.log" "repository hold present" "$OBSERVE_WAIT_S" \
        && kill -0 "$impl_pid" 2>/dev/null && kill -0 "$resume_pid" 2>/dev/null \
        && [ ! -s "$DRIVE_LOG" ] && [ ! -s "$RESUME_LOG" ]; then
        pass "a $hold_shape repository hold fails closed for both launch kinds"
    else
        fail "a $hold_shape repository hold did not hold both launch kinds"
    fi
    stop_launcher "$impl_pid" "$resume_pid"
    wait "$impl_pid" 2>/dev/null
    wait "$resume_pid" 2>/dev/null
done

new_case repository-hold-launch-point
export FLEET_LAUNCH_MAX_WAIT_S=120
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
mkdir "$FLEET_LAUNCH_GMK_LOCK_DIR"
sleep 600 &
holder_pid=$!
printf 'owner=other-seat pid=%s item=bd-ib-holder\n' "$holder_pid" > "$FLEET_LAUNCH_GMK_LOCK_DIR/holder"
LAUNCH_POINT_LOG="$CASE_DIR/impl.log"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-launch-point > "$LAUNCH_POINT_LOG" 2>&1 &
launch_point_pid=$!
if ! wait_for_line "$LAUNCH_POINT_LOG" "queue for the gmktec mutex" "$OBSERVE_WAIT_S"; then
    fail "the launch-point impl launcher did not wait for the mutex"
fi
printf 'kinds: dispatch\n' > "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
kill "$holder_pid" 2>/dev/null
wait "$holder_pid" 2>/dev/null
rm -f "$FLEET_LAUNCH_GMK_LOCK_DIR/holder"
rmdir "$FLEET_LAUNCH_GMK_LOCK_DIR"
# The "repository hold present" line is printed before release_lock frees the mutex, and while
# the hold stands the launcher keeps re-taking and re-yielding the mutex every FLEET_LAUNCH_POLL_S.
# So the yield is judged from the launcher's state, not from one snapshot taken at that log line
# (bd-ib-eb5zl5): poll until one instant shows it alive, its ticket kept, no in-flight marker and
# the mutex free, with nothing driven. The deadline is a liveness guard only; a launcher that never
# frees the mutex, or that drives, never satisfies the condition.
hold_yield_settled() {
    kill -0 "$launch_point_pid" 2>/dev/null \
        && [ -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat" ] \
        && [ -z "$(find "$FLEET_LAUNCH_INFLIGHT_DIR" -type f -print -quit)" ] \
        && [ ! -d "$FLEET_LAUNCH_GMK_LOCK_DIR" ] \
        && [ ! -s "$DRIVE_LOG" ]
}
wait_for_hold_yield_settled() {
    local limit="$1" deadline
    deadline=$(( $(date +%s) + limit ))
    while :; do
        if hold_yield_settled; then return 0; fi
        [ "$(date +%s)" -lt "$deadline" ] || return 1
        sleep "$HARNESS_POLL_S"
    done
}
hold_yielded=0
if wait_for_line "$LAUNCH_POINT_LOG" "repository hold present" "$OBSERVE_WAIT_S" \
    && wait_for_hold_yield_settled "$OBSERVE_WAIT_S"; then
    hold_yielded=1
fi
stop_launcher "$launch_point_pid"
wait "$launch_point_pid" 2>/dev/null
# Nothing may have been driven at any point, including after the settled instant was observed.
if [ "$hold_yielded" = 1 ] && [ ! -s "$DRIVE_LOG" ]; then
    pass "a hold created during the mutex wait releases the mutex and marker without driving"
else
    fail "a launch-point repository hold did not cleanly yield its bound launch"
    tail -10 "$LAUNCH_POINT_LOG" >&2
fi
fi

# --- 20. a hold re-read until admission stops a launched drive ---------------
# Scenario 330. The stub drive waits in its master-CI preflight (the item reads
# `ready`) until the harness opens an admission gate, then reads `active`, and
# submits its run only after a second gate. A hold file created while the drive
# waits must stop it before any run is submitted and keep the launcher's ticket;
# a hold created once the item reads `active` must not.
if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = scenario330 ]; then
scenario "20. holds are re-read until admission"

# prepare_330_case <name>: a fresh case with empty boards and a waiting drive.
prepare_330_case() {
    new_case "$1"
    export FLEET_LAUNCH_MAX_WAIT_S=120
    : > "$BOARD_GMK"
    : > "$BOARD_HL"
    printf '8\n' > "$CAP_FILE"
    export STUB_DRIVE_ADMIT_GATE="$STUB_DRIVE_ADMIT_GATE_FILE"
    export STUB_DRIVE_SUBMIT_GATE="$STUB_DRIVE_SUBMIT_GATE_FILE"
}
# harness_now: the case-20 waits' clock. HARNESS_CLOCK_SKEW_FILE, when it names a
# file, adds its seconds, so a case can put the clock past any fixed startup bound
# while the drive is held, without sleeping that long.
harness_now() {
    local skew=0
    if [ -n "${HARNESS_CLOCK_SKEW_FILE:-}" ] && [ -s "$HARNESS_CLOCK_SKEW_FILE" ]; then
        skew=$(cat "$HARNESS_CLOCK_SKEW_FILE")
    fi
    echo $(( $(date +%s) + skew ))
}
# wait_on_launcher <launcher> <pid> <log> <condition...>: until the condition holds.
# The verdict is the launcher's own state: the condition holding passes, and the
# launcher exiting first fails at once. HARNESS_PREFLIGHT_HANG_GUARD_S only stops a
# genuinely hung launcher; it is not a startup budget, so a slow start still passes.
# On failure WAIT_FAILURE_DETAIL names the reason and the last launcher log line.
WAIT_FAILURE_DETAIL=""
wait_on_launcher() {
    local launcher="$1" pid="$2" log="$3" deadline reason alive last_line
    shift 3
    deadline=$(( $(harness_now) + HARNESS_PREFLIGHT_HANG_GUARD_S ))
    while :; do
        # Liveness first, then the condition, as wait_for_preflight samples them.
        alive=1
        kill -0 "$pid" 2>/dev/null || alive=0
        if "$@"; then return 0; fi
        if [ "$alive" = 0 ]; then reason="the launcher exited first"; break; fi
        if [ "$(harness_now)" -ge "$deadline" ]; then
            reason="hung past the ${HARNESS_PREFLIGHT_HANG_GUARD_S}s guard"
            break
        fi
        sleep "$HARNESS_POLL_S"
    done
    last_line=$(tail -n 1 "$log" 2>/dev/null || true)
    WAIT_FAILURE_DETAIL="launcher=$launcher: $reason; last launcher log line: ${last_line:-<no launcher log output>}"
    return 1
}
drive_invoked_at_least() { [ "$(wc -l < "$STUB_DRIVE_WAITING")" -ge "$1" ]; }
item_reads() { [ "$(cat "$STUB_ITEM_STATUS_FILE")" = "$1" ]; }
# wait_for_drive_invocations <count> <pid> <log>: until the stub drive has started <count> times.
wait_for_drive_invocations() { wait_on_launcher drive-start "$2" "$3" drive_invoked_at_least "$1"; }
# wait_for_item_status <status> <pid> <log>: until the stub item reads <status>.
wait_for_item_status() { wait_on_launcher item-status "$2" "$3" item_reads "$1"; }
# drive_gone: no stub drive process is left running for this case.
drive_gone() {
    local pid
    while read -r pid; do kill -0 "$pid" 2>/dev/null && return 1; done < "$STUB_DRIVE_PIDS"
    return 0
}
wait_for_drive_gone() {
    local limit="$1" deadline
    deadline=$(( $(date +%s) + limit ))
    while ! drive_gone; do
        [ "$(date +%s)" -lt "$deadline" ] || return 1
        sleep "$HARNESS_POLL_S"
    done
}
# wait_for_file: the file exists.  The limit only guards against a hang.
wait_for_file() {
    local file="$1" limit="$2" deadline
    deadline=$(( $(date +%s) + limit ))
    while [ ! -e "$file" ]; do
        [ "$(date +%s)" -lt "$deadline" ] || return 1
        sleep "$HARNESS_POLL_S"
    done
}
inflight_empty() { [ -z "$(find "$FLEET_LAUNCH_INFLIGHT_DIR" -type f -print -quit)" ]; }

# 20a. A hold set before admission stops the drive; the ticket survives; the
# positive control (hold removed, gates opened) then launches and lists.
prepare_330_case hold-before-admission
STOP_LOG="$CASE_DIR/launcher.log"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-hold-before > "$STOP_LOG" 2>&1 &
stop_pid=$!
if wait_for_drive_invocations 1 "$stop_pid" "$STOP_LOG"; then
    set_hold "$HOLD_FILE" 'engine restart'
    if wait_for_line "$STOP_LOG" "stopped the drive for bd-ib-hold-before" "$OBSERVE_WAIT_S" \
        && kill -0 "$stop_pid" 2>/dev/null \
        && [ -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat" ] \
        && inflight_empty && drive_gone \
        && [ ! -e "$STUB_DRIVEN_DIR/bd-ib-hold-before" ] \
        && line_has_all "$STOP_LOG" 'stopped the drive for bd-ib-hold-before' 'ticket 100' 'engine restart'; then
        pass "a hold set before admission stops the drive, keeps ticket 100 and logs the hold text"
    else
        fail "a hold set before admission did not stop the drive and keep its ticket"
        tail -n 8 "$STOP_LOG" >&2
    fi
    rm -f "$HOLD_FILE"
    : > "$STUB_DRIVE_ADMIT_GATE_FILE"
    : > "$STUB_DRIVE_SUBMIT_GATE_FILE"
    wait "$stop_pid"
    stop_rc=$?
    if [ "$stop_rc" = 0 ] && [ "$(drive_log_items)" = "bd-ib-hold-before bd-ib-hold-before" ] \
        && log_has "$STOP_LOG" "LISTED on petri" && [ ! -s "$STUB_LEDGER_COMMENTS" ]; then
        pass "with the hold removed the stopped launcher re-launches and its run lists"
    else
        fail "the stopped launcher did not re-launch once the hold was removed (rc=$stop_rc)"
        tail -n 8 "$STOP_LOG" >&2
    fi
else
    fail "the stub drive never started for the hold-before-admission case ($WAIT_FAILURE_DETAIL)"
    stop_launcher "$stop_pid"
    wait "$stop_pid" 2>/dev/null
fi

# 20b. A repository hold scoped to dispatch stops the drive and logs its fields;
# one scoped to resume does not.
prepare_330_case repository-hold-before-admission
STOP_LOG="$CASE_DIR/launcher.log"
printf 'kinds: resume\n' > "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-repo-hold > "$STOP_LOG" 2>&1 &
stop_pid=$!
if wait_for_drive_invocations 1 "$stop_pid" "$STOP_LOG"; then
    sleep 0.3
    if log_has "$STOP_LOG" "stopped the drive"; then
        fail "a resume-scoped repository hold stopped an impl drive"
    fi
    set_hold "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")" \
        'kinds: dispatch\nreason: commit_green ceiling\nuntil: PR 4440 merged'
    if wait_for_line "$STOP_LOG" "stopped the drive for bd-ib-repo-hold" "$OBSERVE_WAIT_S" \
        && [ -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat" ] && inflight_empty \
        && line_has_all "$STOP_LOG" 'stopped the drive' 'reason=commit_green ceiling until=PR 4440 merged'; then
        pass "a dispatch-scoped repository hold stops the drive and a resume-scoped one does not"
    else
        fail "a dispatch-scoped repository hold did not stop the drive with its fields"
        tail -n 8 "$STOP_LOG" >&2
    fi
else
    fail "the stub drive never started for the repository-hold case ($WAIT_FAILURE_DETAIL)"
fi
stop_launcher "$stop_pid"
wait "$stop_pid" 2>/dev/null

# 20c. A hold set after the item reads active does not stop the drive.
prepare_330_case hold-after-admission
STOP_LOG="$CASE_DIR/launcher.log"
: > "$STUB_DRIVE_ADMIT_GATE_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-hold-after > "$STOP_LOG" 2>&1 &
stop_pid=$!
if wait_for_item_status active "$stop_pid" "$STOP_LOG"; then
    rm -f "$STUB_ITEM_STATUS_ACTIVE_READ_RENDEZVOUS_FILE"
    set_hold "$HOLD_FILE" 'engine restart'
    if wait_for_file "$STUB_ITEM_STATUS_ACTIVE_READ_RENDEZVOUS_FILE" "$HARNESS_PREFLIGHT_HANG_GUARD_S"; then
        held_alive=0
        if kill -0 "$stop_pid" 2>/dev/null && ! drive_gone; then held_alive=1; fi
        : > "$STUB_DRIVE_SUBMIT_GATE_FILE"
        wait "$stop_pid"
        stop_rc=$?
        if [ "$held_alive" = 1 ] && [ "$stop_rc" = 0 ] && ! log_has "$STOP_LOG" "stopped the drive" \
            && log_has "$STOP_LOG" "LISTED on petri" && [ "$(drive_log_items)" = bd-ib-hold-after ]; then
            pass "a hold set after the item reads active leaves the drive alone and the run lists"
        else
            fail "a hold set after admission disturbed the drive (rc=$stop_rc alive=$held_alive)"
            tail -n 8 "$STOP_LOG" >&2
        fi
    else
        fail "the launcher did not re-read active after the hold in the hold-after-admission case"
        stop_launcher "$stop_pid"
        wait "$stop_pid" 2>/dev/null
    fi
else
    fail "the stub item never read active in the hold-after-admission case ($WAIT_FAILURE_DETAIL)"
    stop_launcher "$stop_pid"
    wait "$stop_pid" 2>/dev/null
fi

# 20c delayed-listing control. The launcher's board read is held after it has
# re-read the active item. Only then may the stub submit its run; the read is
# released after the driven marker exists. This makes the former poll-versus-
# exit race deterministic without a wall-clock allowance.
prepare_330_case hold-after-admission-delayed-listing
STOP_LOG="$CASE_DIR/launcher.log"
export STUB_PS_ACTIVE_LISTING_RENDEZVOUS_FILE="$CASE_DIR/active-listing-read"
export STUB_PS_ACTIVE_LISTING_RELEASE_FILE="$CASE_DIR/release-active-listing-read"
: > "$STUB_DRIVE_ADMIT_GATE_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-hold-after-delayed > "$STOP_LOG" 2>&1 &
stop_pid=$!
if wait_for_item_status active "$stop_pid" "$STOP_LOG"; then
    set_hold "$HOLD_FILE" 'engine restart'
    # The launcher lists before its next hold re-read. The normal case above
    # proves that re-read; this control waits for the earlier board-poll state.
    if wait_for_file "$STUB_PS_ACTIVE_LISTING_RENDEZVOUS_FILE" "$HARNESS_PREFLIGHT_HANG_GUARD_S"; then
        held_alive=0
        if kill -0 "$stop_pid" 2>/dev/null && ! drive_gone; then held_alive=1; fi
        : > "$STUB_DRIVE_SUBMIT_GATE_FILE"
        if wait_for_file "$STUB_DRIVEN_DIR/bd-ib-hold-after-delayed" "$HARNESS_PREFLIGHT_HANG_GUARD_S"; then
            : > "$STUB_PS_ACTIVE_LISTING_RELEASE_FILE"
            wait "$stop_pid"
            stop_rc=$?
            if [ "$held_alive" = 1 ] && [ "$stop_rc" = 0 ] && ! log_has "$STOP_LOG" "stopped the drive" \
                && log_has "$STOP_LOG" "LISTED on petri" && [ "$(drive_log_items)" = bd-ib-hold-after-delayed ]; then
                pass "a hold set after the item reads active survives a delayed run-listing poll"
            else
                fail "a delayed listing poll disturbed the post-admission drive (rc=$stop_rc alive=$held_alive)"
                tail -n 8 "$STOP_LOG" >&2
            fi
        else
            fail "the delayed-listing stub never submitted its run after the observed poll"
            : > "$STUB_PS_ACTIVE_LISTING_RELEASE_FILE"
            stop_launcher "$stop_pid"
            wait "$stop_pid" 2>/dev/null
        fi
    else
        fail "the launcher did not enter the delayed listing poll after item admission"
        stop_launcher "$stop_pid"
        wait "$stop_pid" 2>/dev/null
    fi
else
    fail "the stub item never read active in the delayed hold-after-admission case ($WAIT_FAILURE_DETAIL)"
    stop_launcher "$stop_pid"
    wait "$stop_pid" 2>/dev/null
fi

# 20d. With no hold file the drive proceeds from launch to listing as before.
prepare_330_case no-hold
STOP_LOG="$CASE_DIR/launcher.log"
: > "$STUB_DRIVE_ADMIT_GATE_FILE"
: > "$STUB_DRIVE_SUBMIT_GATE_FILE"
ONLY_GMK=1 TICKET_NS=100 run_launcher bd-ib-no-hold "$STOP_LOG"
if [ "$RC" = 0 ] && log_has "$STOP_LOG" "LISTED on petri" && ! log_has "$STOP_LOG" "stopped the drive" \
    && [ "$(drive_log_items)" = bd-ib-no-hold ]; then
    pass "with no hold file the drive proceeds from launch to the run listing"
else
    fail "a launch with no hold file did not proceed to listing (rc=$RC)"
    tail -n 8 "$STOP_LOG" >&2
fi

# report_case_20e_admission_order: on any case 20e failure, say whether the stub drive had written
# `active` before the launcher re-read the item's status, or that the re-read did not occur, and
# whether the watcher armed and the TERM rendezvous and the admission write happened.
report_case_20e_admission_order() {
    printf 'stub admission at launcher re-read: %s\n' \
        "$(cat "$STUB_ITEM_STATUS_RE_READ_OBSERVATION_FILE" 2>/dev/null || echo 'not-observed: the launcher never re-read the status after every stub drive was gone')" >&2
    printf 'watcher armed: %s; TERM rendezvous: %s; admission written: %s\n' \
        "$([ -e "$STUB_DRIVE_WATCHER_ARMED_FILE" ] && echo yes || echo no)" \
        "$([ -e "$STUB_ITEM_STATUS_POST_STOP_RENDEZVOUS_FILE" ] && echo yes || echo no)" \
        "$([ -e "$STUB_ITEM_STATUS_ADMISSION_WRITTEN_FILE" ] && echo yes || echo no)" >&2
}

# 20e. A drive that admits its item as the stop takes effect, or whose status
# cannot be read after the stop, ends in a stopped-after-admission non-run exit.
for after_stop in admitted unreadable; do
    prepare_330_case "stopped-after-admission-$after_stop"
    STOP_LOG="$CASE_DIR/launcher.log"
    if [ "$after_stop" = admitted ]; then
        export STUB_DRIVE_ADMIT_ON_TERM=1 STUB_ITEM_STATUS_AWAIT_POST_STOP=1
    fi
    ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-stop-admit > "$STOP_LOG" 2>&1 &
    stop_pid=$!
    if wait_for_drive_invocations 1 "$stop_pid" "$STOP_LOG"; then
        if [ "$after_stop" = unreadable ]; then : > "$STUB_ITEM_STATUS_UNREADABLE_FILE"; fi
        if [ "$after_stop" = admitted ] && ! wait_for_file "$STUB_DRIVE_WATCHER_ARMED_FILE" "$OBSERVE_WAIT_S"; then
            fail "the stub drive's TERM watcher never armed its trap before case 20e set the hold"
            report_case_20e_admission_order
            stop_launcher "$stop_pid"
            wait "$stop_pid" 2>/dev/null
            continue
        fi
        set_hold "$HOLD_FILE" 'engine restart'
        if [ "$after_stop" = admitted ] \
            && ! wait_for_file "$STUB_ITEM_STATUS_POST_STOP_RENDEZVOUS_FILE" "$HARNESS_PREFLIGHT_HANG_GUARD_S"; then
            fail "the stopped drive's TERM watcher never ran before case 20e released its admission rendezvous"
            report_case_20e_admission_order
            stop_launcher "$stop_pid"
            wait "$stop_pid" 2>/dev/null
            continue
        fi
        if [ "$after_stop" = admitted ]; then
            # The watcher was triggered by stop_drive's TERM.  Release its writer
            # immediately and prove its admission landed before the launcher can
            # perform its post-stop status read; waiting for the stopped primary
            # first is a load-sensitive ordering assumption.
            : > "$STUB_DRIVE_ADMIT_AFTER_STOP_GATE_FILE"
            if ! wait_for_file "$STUB_ITEM_STATUS_ADMISSION_WRITTEN_FILE" "$HARNESS_PREFLIGHT_HANG_GUARD_S"; then
                fail "the stopped drive's TERM watcher did not write its delayed admission"
                report_case_20e_admission_order
                stop_launcher "$stop_pid"
                wait "$stop_pid" 2>/dev/null
                continue
            fi
        fi
        wait "$stop_pid"
        stop_rc=$?
        if [ "$stop_rc" != 0 ] \
            && line_has_all "$STOP_LOG" 'terminal:' 'item=bd-ib-stop-admit' 'ticket=100' 'cause=stopped-after-admission' \
            && [ ! -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat" ] \
            && [ "$(wc -l < "$STUB_LEDGER_COMMENTS")" = 1 ] \
            && grep -qF 'ticket 100' "$STUB_LEDGER_COMMENTS" \
            && grep -qF 'move' "$STUB_LEDGER_COMMENTS" \
            && [ "$(drive_log_items)" = bd-ib-stop-admit ] && inflight_empty \
            && [ -s "$STUB_ITEM_STATUS_RE_READ_OBSERVATION_FILE" ]; then
            pass "a stopped drive that admitted its item ($after_stop) exits stopped-after-admission, re-takes no ticket and comments once"
        else
            fail "a stopped drive that admitted its item ($after_stop) did not make the stopped-after-admission exit (rc=$stop_rc)"
            report_case_20e_admission_order
            tail -n 8 "$STOP_LOG" >&2
        fi
    else
        fail "the stub drive never started for the stopped-after-admission case ($WAIT_FAILURE_DETAIL)"
        report_case_20e_admission_order
        stop_launcher "$stop_pid"
        wait "$stop_pid" 2>/dev/null
    fi
done

# 20f. A slow drive start still passes the case-20 wait: the drive is held at its start
# gate while the wait's clock is put 15 s past launcher start, beyond the fixed 10 s bound
# the waits once used, and only then released. The wait is decided by the drive starting.
prepare_330_case slow-drive-start
STOP_LOG="$CASE_DIR/launcher.log"
export STUB_DRIVE_START_GATE="$CASE_DIR/drive-start-gate"
export HARNESS_CLOCK_SKEW_FILE="$CASE_DIR/clock-skew"
: > "$STUB_DRIVE_ADMIT_GATE_FILE"
: > "$STUB_DRIVE_SUBMIT_GATE_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-slow-start > "$STOP_LOG" 2>&1 &
stop_pid=$!
slow_rc_file="$CASE_DIR/slow-start-wait.rc"
if wait_for_file "$STUB_DRIVE_START_GATE.reached" "$HARNESS_PREFLIGHT_HANG_GUARD_S"; then
    ( wait_for_drive_invocations 1 "$stop_pid" "$STOP_LOG"; printf '%s\n' "$?" > "$slow_rc_file" ) &
    slow_waiter=$!
    printf '15\n' > "$HARNESS_CLOCK_SKEW_FILE"
    : > "$STUB_DRIVE_START_GATE"
    wait "$slow_waiter"
    wait "$stop_pid"
    stop_rc=$?
    if [ "$(cat "$slow_rc_file")" = 0 ] && [ "$stop_rc" = 0 ] && log_has "$STOP_LOG" "LISTED on petri"; then
        pass "a drive that starts 15 s after the launcher still passes the case-20 wait and its run lists"
    else
        fail "a slow drive start failed the case-20 wait (wait rc=$(cat "$slow_rc_file") launcher rc=$stop_rc)"
        tail -n 8 "$STOP_LOG" >&2
    fi
else
    fail "the stub drive never reached its start gate in the slow-start case"
    stop_launcher "$stop_pid"
    wait "$stop_pid" 2>/dev/null
fi
unset STUB_DRIVE_START_GATE HARNESS_CLOCK_SKEW_FILE
fi

# --- 23. a launcher that exits without a run leaves a terminal line ---------
# Scenario 312. The cases below stop, refuse or starve a launcher before its run lists and read what
# it leaves behind: one terminal line in its sequence log, written before its ticket file is removed,
# and one ledger comment on the item when the item still reads ready. Each refusal is contrasted
# with a launch that leaves neither.
if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = scenario312 ]; then
scenario "23. a launcher that exits without a run leaves a terminal line and a ledger comment"

# make_rm_probe: a PATH directory whose `rm` records, for each queue ticket it removes, whether the
# launcher's own log already carried a terminal line and a stall line at that moment.
make_rm_probe() {
    mkdir -p "$STUB/rm-probe"
    cat > "$STUB/rm-probe/rm" <<'RM_PROBE'
#!/usr/bin/env bash
for argument in "$@"; do
    case $argument in
        "$FLEET_LAUNCH_GMK_QUEUE_DIR"/*)
            terminal=no
            stall=no
            if grep -qF 'terminal:' "$STUB_RM_PROBE_LOG_SOURCE" 2>/dev/null; then terminal=yes; fi
            if grep -qF 'stall:' "$STUB_RM_PROBE_LOG_SOURCE" 2>/dev/null; then stall=yes; fi
            printf '%s terminal=%s stall=%s\n' "${argument##*/}" "$terminal" "$stall" >> "$STUB_RM_PROBE_OUT"
            ;;
    esac
done
exec "$STUB_REAL_RM" "$@"
RM_PROBE
    chmod +x "$STUB/rm-probe/rm"
}
make_rm_probe
STUB_REAL_RM=$(command -v rm)
export STUB_REAL_RM

# prepare_312_case <name>: a fresh case with empty boards, headroom and a tenant repository hold path.
prepare_312_case() {
    new_case "$1"
    export FLEET_LAUNCH_MAX_WAIT_S=120
    : > "$BOARD_GMK"
    : > "$BOARD_HL"
    printf '8\n' > "$CAP_FILE"
    TENANT_HOLD="$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
    export STUB_RM_PROBE_OUT="$CASE_DIR/rm-probe-out"
    : > "$STUB_RM_PROBE_OUT"
    export STUB_RM_PROBE_LOG_SOURCE="$CASE_DIR/probed.log"
    : > "$STUB_RM_PROBE_LOG_SOURCE"
}
count_matching() { grep -cF -- "$2" "$1" 2>/dev/null || true; }
# queue_ticket_number: the number of the one ticket in the case's queue directory.
queue_ticket_number() {
    local file
    file=$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -print -quit)
    file=${file##*/}
    printf '%s' "${file%%-*}"
}
# check_term_exit <label> <ticket-number>: the terminal line and the ledger comment a TERMed launcher leaves.
check_term_exit() {
    local label="$1" number="$2" probe last_line
    probe=$(cat "$STUB_RM_PROBE_OUT")
    last_line=$(tail -n 1 "$STUB_RM_PROBE_LOG_SOURCE")
    if [ "$term_rc" = 143 ] \
        && [ "$(count_matching "$STUB_RM_PROBE_LOG_SOURCE" 'terminal:')" = 1 ] \
        && line_has_all "$STUB_RM_PROBE_LOG_SOURCE" 'terminal:' 'item=bd-ib-term' "ticket=$number" 'TERM' \
        && case $last_line in *'terminal:'*) true ;; *) false ;; esac \
        && [ -z "$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -print -quit)" ] \
        && case $probe in *"$number-"*" terminal=yes"*) true ;; *) false ;; esac; then
        pass "$label: a TERM leaves one last terminal line naming the item, the ticket number and TERM, written before the ticket file is removed"
    else
        fail "$label: the TERMed launcher did not leave its terminal line first (rc=$term_rc; ticket probe: ${probe:-none})"
        tail -n 4 "$STUB_RM_PROBE_LOG_SOURCE" >&2
    fi
    if [ "$(wc -l < "$STUB_LEDGER_COMMENTS")" = 1 ] \
        && grep -qF "ticket $number" "$STUB_LEDGER_COMMENTS" \
        && grep -qF 'TERM' "$STUB_LEDGER_COMMENTS" \
        && grep -qF 'not a run ending' "$STUB_LEDGER_COMMENTS" \
        && ! grep -qF 'held by its owner' "$STUB_LEDGER_COMMENTS"; then
        pass "$label: the dropped ticket is reported in one ledger comment naming the number, TERM and that the exit was not a run ending"
    else
        fail "$label: the ledger comment for the dropped ticket is missing or wrong ($(cat "$STUB_LEDGER_COMMENTS"))"
    fi
}

# bash 5.2 can fail while parsing a TERM trap action when TERM arrives while a
# command substitution is active.  The launchers must therefore rely on
# bash's default TERM exit and let their EXIT cleanup describe it; INT and HUP keep their traps.
# Keep this assertion separate from the exercise below: it makes the former
# design fail deterministically, while the exercise proves the replacement.
if grep -Eq '^[[:space:]]*trap .+ TERM$' "$LAUNCHER" "$RESUME_LAUNCHER"; then
    fail "the launchers install a TERM trap whose action bash must parse during command substitution"
else
    pass "the launchers use the default TERM exit rather than a parseable TERM trap action"

    # INT and HUP have the same bash 5.2 trap-delivery parser hazard as TERM.
    # An action registered with trap is parsed at signal delivery, including
    # while the launcher is evaluating a command substitution, so neither
    # launcher may retain an INT or HUP trap action.
    if grep -Eq '^[[:space:]]*trap .+ (INT|HUP)$' "$LAUNCHER" "$RESUME_LAUNCHER"; then
        fail "the launchers install an INT or HUP trap action bash must parse during command substitution"
    else
        pass "the launchers use default INT and HUP exits rather than parseable trap actions"
    fi

    # This PATH-local sed pauses inside repository_hold_applies' $(sed ...) read.
    # The parent waits for its gate before delivering TERM, and adds a small
    # random jitter across 200 deliveries so the proof covers distinct parser
    # instants rather than a single lucky timing.
    mkdir -p "$STUB/term-sed"
    STUB_REAL_SED=$(command -v sed)
    export STUB_REAL_SED
    cat > "$STUB/term-sed/sed" <<'TERM_SED'
#!/usr/bin/env bash
printf '%s\n' "$$" >> "$STUB_TERM_SUBSTITUTION_GATE"
sleep "$STUB_TERM_SUBSTITUTION_SED_DELAY_S"
exec "$STUB_REAL_SED" "$@"
TERM_SED
    chmod +x "$STUB/term-sed/sed"

    # signal_during_hold_substitution <launcher> <label> <signal> <rc>: each
    # iteration waits until the launcher has a FIFO ticket, then sends the signal
    # while its next hold read is evaluating $(sed ...).  The exit must carry
    # 128+N, run EXIT cleanup and leave a terminal line naming that signal.
    # HARNESS_SIGNAL_SUBSTITUTION_ATTEMPTS sets the jittered attempts per case.
    signal_during_hold_substitution() {
        local launcher="$1" label="$2" sig="$3" want_rc="$4" attempt sig_pid sig_rc gate gate_deadline failures=0 sig_cause sig_parse_error
        for attempt in $(seq 1 "${HARNESS_SIGNAL_SUBSTITUTION_ATTEMPTS:-100}"); do
            prepare_312_case "$sig-substitution-$label-$attempt"
            export FLEET_LAUNCH_POLL_S=0.01
            set_hold "$TENANT_HOLD" "reason: substitution-$sig"
            gate="$CASE_DIR/substitution-gate"
            export STUB_TERM_SUBSTITUTION_GATE="$gate"
            export STUB_TERM_SUBSTITUTION_SED_DELAY_S=0.01
            # A background job of a non-interactive shell starts with INT ignored;
            # restore the default before the launcher takes over.
            PATH="$STUB/term-sed:$PATH" ONLY_GMK=1 TICKET_NS="$attempt" python3 -c 'import os, signal, sys
signal.signal(signal.SIGINT, signal.SIG_DFL)
os.execv(sys.argv[1], sys.argv[1:])' "$launcher" bd-ib-term > "$STUB_RM_PROBE_LOG_SOURCE" 2>&1 &
            sig_pid=$!
            if ! wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'repository hold present' "$HOLD_LINE_WAIT_S"; then
                fail "$label $sig iteration $attempt never yielded on the repository hold"
                stop_launcher "$sig_pid"
                wait "$sig_pid" 2>/dev/null
                failures=$((failures + 1))
                continue
            fi
            : > "$gate"
            gate_deadline=$(( $(date +%s) + ${OBSERVE_WAIT_S:-30} ))
            while [ ! -s "$gate" ] && [ "$(date +%s)" -lt "$gate_deadline" ]; do
                sleep "$HARNESS_POLL_S"
            done
            if [ ! -s "$gate" ]; then
                fail "$label $sig iteration $attempt never entered the gated command substitution"
                stop_launcher "$sig_pid"
                wait "$sig_pid" 2>/dev/null
                failures=$((failures + 1))
                continue
            fi
            sleep "0.00$((RANDOM % 5))"
            kill -"$sig" "$sig_pid" 2>/dev/null
            gate_deadline=$(( $(date +%s) + STOP_GRACE_S ))
            while kill -0 "$sig_pid" 2>/dev/null && [ "$(date +%s)" -lt "$gate_deadline" ]; do
                sleep "$HARNESS_POLL_S"
            done
            if kill -0 "$sig_pid" 2>/dev/null; then
                stop_launcher "$sig_pid"
            fi
            wait "$sig_pid"
            sig_rc=$?
            sig_cause=no
            sig_parse_error=no
            if grep -F -- "cause=signal $sig" "$STUB_RM_PROBE_LOG_SOURCE" >/dev/null; then
                sig_cause=yes
            fi
            if grep -F -- 'unexpected EOF while looking for matching' "$STUB_RM_PROBE_LOG_SOURCE" >/dev/null; then
                sig_parse_error=yes
            fi
            if [ "$sig_rc" != "$want_rc" ] \
                || [ -n "$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -print -quit)" ] \
                || [ -d "$FLEET_LAUNCH_GMK_LOCK_DIR" ] \
                || [ "$(count_matching "$STUB_RM_PROBE_LOG_SOURCE" 'terminal:')" != 1 ] \
                || [ "$sig_cause" != yes ] \
                || [ "$sig_parse_error" = yes ]; then
                fail "$label iteration $attempt did not exit cleanly from $sig in a command substitution (rc=$sig_rc)"
                tail -n 4 "$STUB_RM_PROBE_LOG_SOURCE" >&2
                failures=$((failures + 1))
            fi
        done
        if [ "$failures" = 0 ]; then
            pass "$label exits within the stop bound with rc $want_rc and a terminal line naming $sig for ${HARNESS_SIGNAL_SUBSTITUTION_ATTEMPTS:-100} jittered ${sig}s during repository-hold command substitutions, dropping its FIFO ticket"
        fi
    }

    signal_during_hold_substitution "$LAUNCHER" impl TERM 143
    signal_during_hold_substitution "$RESUME_LAUNCHER" resume TERM 143
    signal_during_hold_substitution "$LAUNCHER" impl INT 130
    signal_during_hold_substitution "$RESUME_LAUNCHER" resume INT 130
    signal_during_hold_substitution "$LAUNCHER" impl HUP 129
    signal_during_hold_substitution "$RESUME_LAUNCHER" resume HUP 129
    unset STUB_TERM_SUBSTITUTION_GATE STUB_TERM_SUBSTITUTION_SED_DELAY_S

    # wait_for_signal_exit <pid> <signal> <log>: one directly delivered signal
    # must end the launcher. Retrying would conceal the Bash signal-loss race
    # this Scenario 312 case is meant to reject under CPU contention.
    SIGNAL_EXIT_GRACE_S=${SIGNAL_EXIT_GRACE_S:-5}
    wait_for_signal_exit() {
        local pid="$1" sig="$2" log="$3" deadline
        kill -"$sig" "$pid" 2>/dev/null || return 1
        deadline=$(( $(date +%s) + SIGNAL_EXIT_GRACE_S ))
        while kill -0 "$pid" 2>/dev/null && [ "$(date +%s)" -lt "$deadline" ]; do
            sleep "$HARNESS_POLL_S"
        done
        if kill -0 "$pid" 2>/dev/null; then
            stop_launcher "$pid"
            return 1
        fi
        return 0
    }

    # signal_during_hold <launcher> <label> <signal> <rc> <expected cause>:
    # an INT or HUP that lands in the repository-hold wait must be recorded as
    # that signal, not as the TERM description the wait loop preloads.
    signal_during_hold() {
        local launcher="$1" label="$2" sig="$3" want_rc="$4" want_cause="$5" attempt="$6" sig_pid sig_rc
        prepare_312_case "signal-$sig-$label-$attempt"
        export FLEET_LAUNCH_POLL_S=0.01
        set_hold "$TENANT_HOLD" "reason: signal-$sig"
        # A background job of a non-interactive shell starts with INT ignored,
        # and a script cannot take that back; restore the default first.  The
        # launcher gets its own process group, but the signal goes to its shell
        # directly (wait_for_signal_exit): under CPU saturation a process-group
        # INT or HUP can be consumed by its short-lived sleep before Bash runs
        # its attribution trap.  The shell owns the trap and reaps that child.
        # This probe always ends by delivering $sig after wait_for_line's
        # five-second observation bound.  Give the launcher a test-only one-day
        # give-up budget, rather than guessing at a sufficiently long start-up
        # window, so the no-slot give-up (rc 75) cannot beat the signal to the
        # repository-hold wait on a loaded host.
        PATH="$STUB/rm-probe:$PATH" ONLY_GMK=1 TICKET_NS=7 FLEET_LAUNCH_MAX_WAIT_S=86400 python3 -c 'import os, signal, sys
signal.signal(signal.SIGINT, signal.SIG_DFL)
os.setsid()
os.execv(sys.argv[1], sys.argv[1:])' "$launcher" bd-ib-term > "$STUB_RM_PROBE_LOG_SOURCE" 2>&1 &
        sig_pid=$!
        if ! wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'repository hold present' "$HOLD_LINE_WAIT_S"; then
            fail "$label never yielded on the repository hold before $sig"
            stop_launcher "$sig_pid"
            wait "$sig_pid" 2>/dev/null
            return 0
        fi
        if ! wait_for_signal_exit "$sig_pid" "$sig" "$STUB_RM_PROBE_LOG_SOURCE"; then
            wait "$sig_pid" 2>/dev/null
            fail "$label did not exit after bounded $sig delivery during the repository-hold wait"
            tail -n 4 "$STUB_RM_PROBE_LOG_SOURCE" >&2
            return 0
        fi
        wait "$sig_pid"
        sig_rc=$?
        if [ "$sig_rc" = "$want_rc" ] \
            && [ "$(count_matching "$STUB_RM_PROBE_LOG_SOURCE" 'terminal:')" = 1 ] \
            && line_has_all "$STUB_RM_PROBE_LOG_SOURCE" 'terminal:' 'item=bd-ib-term' 'ticket=' "cause=$want_cause" \
            && [ -z "$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -print -quit)" ] \
            && [ ! -d "$FLEET_LAUNCH_GMK_LOCK_DIR" ] \
            && ! grep -qF -- 'cause=resume gave up:' "$STUB_RM_PROBE_LOG_SOURCE" \
            && { [ "$sig" = TERM ] || ! grep -qF -- 'cause=signal TERM' "$STUB_RM_PROBE_LOG_SOURCE"; }; then
            pass "$label records a $sig during the repository-hold wait as $want_cause, not as TERM"
        else
            fail "$label did not record $sig as $want_cause (rc=$sig_rc)"
            tail -n 4 "$STUB_RM_PROBE_LOG_SOURCE" >&2
        fi
    }
    # The normal gate samples each signal once. The resume INT hold-wait case
    # is the focused stability proof: it must survive 200 first-delivery
    # attempts under the CPU contention Scenario 10b leaves active.
    for signal_attempt in $(seq 1 "${HARNESS_SIGNAL_HOLD_ATTEMPTS:-1}"); do
        signal_during_hold "$LAUNCHER" impl INT 130 'signal INT' "$signal_attempt"
        signal_during_hold "$LAUNCHER" impl TERM 143 'signal TERM' "$signal_attempt"
        signal_during_hold "$LAUNCHER" impl HUP 129 'signal HUP' "$signal_attempt"
        signal_during_hold "$RESUME_LAUNCHER" resume TERM 143 'signal TERM' "$signal_attempt"
        signal_during_hold "$RESUME_LAUNCHER" resume HUP 129 'signal HUP' "$signal_attempt"
    done
    for signal_attempt in $(seq 1 "${HARNESS_RESUME_INT_HOLD_ATTEMPTS:-200}"); do
        signal_during_hold "$RESUME_LAUNCHER" resume INT 130 'signal INT' "$signal_attempt"
    done

    # A separate gate pauses dispatch after it has recorded its mutex holder.
    # TERM must remove both that owned mutex and its ticket before the process
    # exits, rather than leaving the next launcher blocked behind either.
    prepare_312_case terminal-term-owned-mutex
    STUB_TERM_MUTEX_GATE="$CASE_DIR/mutex-gate"
    export STUB_TERM_MUTEX_GATE
    ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-term > "$STUB_RM_PROBE_LOG_SOURCE" 2>&1 &
    term_pid=$!
    gate_deadline=$(( $(date +%s) + ${OBSERVE_WAIT_S:-30} ))
    while [ ! -e "$STUB_TERM_MUTEX_GATE" ] && [ "$(date +%s)" -lt "$gate_deadline" ]; do
        sleep "$HARNESS_POLL_S"
    done
    if [ -e "$STUB_TERM_MUTEX_GATE" ] && [ -d "$FLEET_LAUNCH_GMK_LOCK_DIR" ]; then
        stop_launcher "$term_pid"
        wait "$term_pid"
        term_rc=$?
        if [ "$term_rc" = 143 ] \
            && [ -z "$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -print -quit)" ] \
            && [ ! -d "$FLEET_LAUNCH_GMK_LOCK_DIR" ]; then
            pass "a TERMed launcher that owns the gmktec mutex drops its ticket and releases the mutex"
        else
            fail "a TERMed mutex owner left a ticket or gmktec mutex behind (rc=$term_rc)"
        fi
    else
        fail "the dispatch launcher never reached the owned-mutex TERM gate"
        tail -n 8 "$STUB_RM_PROBE_LOG_SOURCE" >&2
        stop_launcher "$term_pid"
        wait "$term_pid" 2>/dev/null
    fi
    unset STUB_TERM_MUTEX_GATE
fi

prepare_312_case terminal-term-impl
export FLEET_LAUNCH_POLL_S=0.2
set_hold "$TENANT_HOLD" 'reason: harness'
PATH="$STUB/rm-probe:$PATH" ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-term > "$STUB_RM_PROBE_LOG_SOURCE" 2>&1 &
term_pid=$!
if wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'repository hold present' "$OBSERVE_WAIT_S"; then
    stop_launcher "$term_pid"
    wait "$term_pid"
    term_rc=$?
    check_term_exit 'impl launcher yielding on a repository hold' 100
else
    fail "the impl launcher never yielded on the repository hold"
    stop_launcher "$term_pid"
    wait "$term_pid" 2>/dev/null
fi

prepare_312_case terminal-term-resume
export FLEET_LAUNCH_POLL_S=0.2
set_hold "$TENANT_HOLD" 'reason: harness'
PATH="$STUB/rm-probe:$PATH" "$RESUME_LAUNCHER" bd-ib-term > "$STUB_RM_PROBE_LOG_SOURCE" 2>&1 &
term_pid=$!
if wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'repository hold present' "$OBSERVE_WAIT_S"; then
    resume_number=$(queue_ticket_number)
    stop_launcher "$term_pid"
    wait "$term_pid"
    term_rc=$?
    check_term_exit 'resume launcher yielding on a repository hold' "$resume_number"
else
    fail "the resume launcher never yielded on the repository hold"
    stop_launcher "$term_pid"
    wait "$term_pid" 2>/dev/null
fi

# A TERM that lands while the launcher retries a refused ready-set check, before the launcher has
# reached the later parts of its script, must still leave the terminal line and the ledger comment:
# the exit path may not depend on a helper defined below the point the signal interrupts.
prepare_312_case terminal-term-ready-retry
export FLEET_LAUNCH_POLL_S=0.2
export FLEET_LAUNCH_READY_RETRY_POLLS=99
export STUB_READY_REFUSALS=99
export STUB_READY_REASON='open blockers: bd-ib-dep=active'
PATH="$STUB/rm-probe:$PATH" ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-term > "$STUB_RM_PROBE_LOG_SOURCE" 2>&1 &
term_pid=$!
if wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'ready-set check refused' "$OBSERVE_WAIT_S"; then
    stop_launcher "$term_pid"
    wait "$term_pid"
    term_rc=$?
    check_term_exit 'impl launcher retrying a refused ready-set check' 100
    if grep -qF 'command not found' "$STUB_RM_PROBE_LOG_SOURCE"; then
        fail "the TERMed ready-set retry called a helper that was not yet defined ($(grep -m 1 -F 'command not found' "$STUB_RM_PROBE_LOG_SOURCE"))"
    else
        pass "a TERM during the ready-set retry calls no helper that is not yet defined"
    fi
else
    fail "the impl launcher never logged a refused ready-set check"
    stop_launcher "$term_pid"
    wait "$term_pid" 2>/dev/null
fi
unset FLEET_LAUNCH_READY_RETRY_POLLS STUB_READY_REFUSALS STUB_READY_REASON

prepare_312_case terminal-control-launch
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-term > "$CASE_LOG" 2>&1
control_rc=$?
if [ "$control_rc" = 0 ] && [ "$(drive_log_items)" = bd-ib-term ] \
    && [ "$(count_matching "$CASE_LOG" 'terminal:')" = 0 ] && [ ! -s "$STUB_LEDGER_COMMENTS" ]; then
    pass "control: a launcher whose run lists leaves no terminal line and no ledger comment"
else
    fail "control: a launching launcher wrote a terminal line or a comment (rc=$control_rc)"
    tail -n 4 "$CASE_LOG" >&2
fi

prepare_312_case ready-refusal-clears
export FLEET_LAUNCH_READY_RETRY_POLLS=3
export STUB_READY_REFUSALS=2
export STUB_READY_REASON='open blockers: bd-ib-dep=active'
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-ready > "$CASE_LOG" 2>&1
ready_rc=$?
first_poll=$(sed -n 1p "$STUB_READY_OBSERVATIONS")
second_poll=$(sed -n 2p "$STUB_READY_OBSERVATIONS")
if [ "$ready_rc" = 0 ] && [ "$(drive_log_items)" = bd-ib-ready ] \
    && [ "$first_poll" = 'call=1 ticket=present mutex=none marker=none' ] \
    && [ "$second_poll" = 'call=2 ticket=present mutex=none marker=none' ] \
    && [ "$(count_matching "$CASE_LOG" 'terminal:')" = 0 ] && [ ! -s "$STUB_LEDGER_COMMENTS" ]; then
    pass "a ready-set refusal that clears within the retry bound keeps the ticket, holds no mutex or marker, and launches"
else
    fail "a ready-set refusal that clears within the retry bound did not keep the ticket and launch (rc=$ready_rc; polls: $first_poll / $second_poll)"
    tail -n 6 "$CASE_LOG" >&2
fi

prepare_312_case ready-refusal-exhausts
export FLEET_LAUNCH_READY_RETRY_POLLS=3
export STUB_READY_REFUSALS=99
export STUB_READY_REASON='open blockers: bd-ib-dep=active'
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-ready > "$CASE_LOG" 2>&1
ready_rc=$?
if [ "$ready_rc" = 3 ] && [ "$(cat "$STUB_READY_COUNTER")" = 3 ] && [ ! -s "$DRIVE_LOG" ] \
    && line_has_all "$CASE_LOG" 'terminal:' 'item=bd-ib-ready' 'ticket=100' 'open blockers: bd-ib-dep=active' '3 polls tried' \
    && [ -z "$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -print -quit)" ]; then
    pass "a ready-set refusal that outlasts the retry bound ends after exactly the bound with a terminal line naming the reason and the polls tried"
else
    fail "a persistent ready-set refusal did not end with the bounded terminal line (rc=$ready_rc, polls=$(cat "$STUB_READY_COUNTER"))"
    tail -n 6 "$CASE_LOG" >&2
fi
if [ "$(wc -l < "$STUB_LEDGER_COMMENTS")" = 1 ] \
    && grep -qF 'ticket 100' "$STUB_LEDGER_COMMENTS" \
    && grep -qF 'open blockers: bd-ib-dep=active' "$STUB_LEDGER_COMMENTS" \
    && grep -qF '3 polls tried' "$STUB_LEDGER_COMMENTS"; then
    pass "the persistent ready-set refusal is recorded in one ledger comment naming the ticket, the reason and the polls tried"
else
    fail "the persistent ready-set refusal left no correct ledger comment ($(cat "$STUB_LEDGER_COMMENTS"))"
fi

prepare_312_case give-up
export FLEET_LAUNCH_MAX_WAIT_S=1
printf '0\n' > "$CAP_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-giveup > "$CASE_LOG" 2>&1
giveup_rc=$?
if [ "$giveup_rc" = 75 ] \
    && line_has_all "$CASE_LOG" 'terminal:' 'item=bd-ib-giveup' 'ticket=100' 'no slot within 1s' \
    && [ "$(wc -l < "$STUB_LEDGER_COMMENTS")" = 1 ] \
    && grep -qF 'ticket 100' "$STUB_LEDGER_COMMENTS" \
    && grep -qF 'no slot within 1s' "$STUB_LEDGER_COMMENTS"; then
    pass "a launcher that gives up for want of a slot leaves a terminal line and reports its dropped ticket while the item reads ready"
else
    fail "the give-up exit left no terminal line or ledger comment (rc=$giveup_rc)"
    tail -n 4 "$CASE_LOG" >&2
fi

# check_stall <label> <log>: the stall line a queue reader writes for a ticket whose launcher is dead.
check_stall() {
    local label="$1" log="$2" probe
    probe=$(cat "$STUB_RM_PROBE_OUT")
    if [ "$(count_matching "$log" 'stall:')" = 1 ] \
        && line_has_all "$log" 'stall:' 'item=bd-ib-dead' 'ticket=100' "dead-pid=$dead_pid" \
        && case $probe in *"100-other-seat terminal=no stall=yes"*) true ;; *) false ;; esac \
        && [ ! -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-other-seat" ]; then
        pass "$label: a dead-pid ticket is reported as one stall line naming item, ticket number and pid before it is removed"
    else
        fail "$label: the dead-pid ticket was not reported as a stall (probe: ${probe:-none})"
        tail -n 6 "$log" >&2
    fi
    if line_has_all "$log" 'stall:' 'bd-ib-live'; then
        fail "$label: a ticket with a live launcher was reported as a stall"
    else
        pass "$label: control: a ticket whose launcher is alive is not reported"
    fi
}
# seed_queue: a dead-pid ticket 100 for bd-ib-dead and a live-pid ticket 150 for bd-ib-live.
seed_queue() {
    mkdir -p "$FLEET_LAUNCH_GMK_QUEUE_DIR"
    sleep 0 &
    dead_pid=$!
    wait "$dead_pid"
    sleep 600 &
    live_pid=$!
    printf 'owner=other-seat pid=%s item=bd-ib-dead\n' "$dead_pid" > "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-other-seat"
    printf 'owner=live-seat pid=%s item=bd-ib-live\n' "$live_pid" > "$FLEET_LAUNCH_GMK_QUEUE_DIR/150-live-seat"
}

prepare_312_case stall-impl
printf '0\n' > "$CAP_FILE"
seed_queue
PATH="$STUB/rm-probe:$PATH" ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-reader > "$STUB_RM_PROBE_LOG_SOURCE" 2>&1 &
reader_pid=$!
if wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'stall:' "$OBSERVE_WAIT_S" && wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'queued behind' "$OBSERVE_WAIT_S"; then
    check_stall 'impl launcher reading the queue' "$STUB_RM_PROBE_LOG_SOURCE"
else
    fail "the impl launcher never reported the dead-pid ticket"
fi
stop_launcher "$reader_pid"
wait "$reader_pid" 2>/dev/null
kill "$live_pid" 2>/dev/null
wait "$live_pid" 2>/dev/null

prepare_312_case stall-resume
printf '0\n' > "$CAP_FILE"
seed_queue
PATH="$STUB/rm-probe:$PATH" "$RESUME_LAUNCHER" bd-ib-reader > "$STUB_RM_PROBE_LOG_SOURCE" 2>&1 &
reader_pid=$!
if wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'stall:' "$OBSERVE_WAIT_S" && wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'queued behind' "$OBSERVE_WAIT_S"; then
    check_stall 'resume launcher reading the queue' "$STUB_RM_PROBE_LOG_SOURCE"
else
    fail "the resume launcher never reported the dead-pid ticket"
fi
stop_launcher "$reader_pid"
wait "$reader_pid" 2>/dev/null
kill "$live_pid" 2>/dev/null
wait "$live_pid" 2>/dev/null
fi

# --- 21. a running launcher follows its script on disk ------------------------
# A bash launcher keeps executing the script content it started with, so a hold
# check added to the script after the launcher started never reached it
# (bd-ib-5ycmsm: bd-ib-fkd4ve launched straight through a repository hold on
# 2026-11-08). Each case starts a launcher from a private copy of the committed
# scripts whose hold check is DISABLED, replaces that copy on disk with the
# committed script exactly as a deploy does (write beside, then mv), and holds a
# repository hold file. Every refusal is contrasted with a launch once the hold
# is removed.
if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = launcher-reexec ]; then
copy_launchers() { mkdir -p "$1" && cp "$LAUNCH_DIR"/*.sh "$1/"; }
replace_script() { cp "$2" "$1.new" && chmod +x "$1.new" && mv -f "$1.new" "$1"; }
without_hold_handling() {
    sed 's/^repository_hold_applies() {$/repository_hold_applies() { return 1/' "$1"
}
as_legacy_launcher() {
    sed -e 's/^script_changed() {$/script_changed() { return 1/' \
        -e 's/^reexec_on_script_change() {$/reexec_on_script_change() { return 0/' "$1"
}
ticket_pid() { grep -oE 'pid=[0-9]+' "$1" 2>/dev/null | sed -n 1p; }

scenario "21. an impl launcher started before a hold check was added honours the hold"
new_case launcher-reexec-dispatch
export FLEET_LAUNCH_MAX_WAIT_S=120
launchers="$CASE_DIR/launchers"
copy_launchers "$launchers"
cp "$launchers/dispatch-dual.sh" "$CASE_DIR/committed-dispatch-dual.sh"
without_hold_handling "$CASE_DIR/committed-dispatch-dual.sh" > "$launchers/dispatch-dual.sh"
chmod +x "$launchers/dispatch-dual.sh"
if cmp -s "$CASE_DIR/committed-dispatch-dual.sh" "$launchers/dispatch-dual.sh"; then
    fail "the harness could not disable the copy's hold check"
fi
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '0\n' > "$CAP_FILE"
ONLY_GMK=1 TICKET_NS=100 "$launchers/dispatch-dual.sh" bd-ib-reexec > "$CASE_DIR/impl.log" 2>&1 &
reexec_pid=$!
ticket_path="$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat"
wait_for_line "$CASE_DIR/impl.log" "fleet not green" "$OBSERVE_WAIT_S" || fail "the impl launcher never reached its waiting loop"
ticket_before=$(ticket_pid "$ticket_path")
printf 'reason: canary gate\n' > "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
replace_script "$launchers/dispatch-dual.sh" "$CASE_DIR/committed-dispatch-dual.sh"
wait_for_line "$CASE_DIR/impl.log" "launcher script changed on disk" "$OBSERVE_WAIT_S" \
    || fail "the waiting launcher never noticed its script changed on disk"
printf '8\n' > "$CAP_FILE"
wait_for_line "$CASE_DIR/impl.log" "repository hold present" "$OBSERVE_WAIT_S" \
    || fail "the waiting launcher never read the repository hold"
sleep 0.3
if kill -0 "$reexec_pid" 2>/dev/null && [ ! -s "$DRIVE_LOG" ] \
    && [ -n "$ticket_before" ] && [ "$(ticket_pid "$ticket_path")" = "$ticket_before" ]; then
    pass "a hold file created while the launcher waits stops it, keeping its original queue ticket"
else
    fail "the launcher started before the hold check launched through the hold (dispatches: $(drive_log_items))"
    tail -6 "$CASE_DIR/impl.log" >&2
fi
rm -f "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
wait_for_line "$CASE_DIR/impl.log" "drive rc=" "$OBSERVE_WAIT_S"
if [ "$(drive_log_items)" = bd-ib-reexec ]; then
    pass "control: removing the hold launches the same launcher"
else
    fail "control: the launcher did not launch once the hold was removed (dispatches: $(drive_log_items))"
    tail -6 "$CASE_DIR/impl.log" >&2
fi
stop_launcher "$reexec_pid"
wait "$reexec_pid" 2>/dev/null

scenario "21a. an impl launcher bound at the mutex re-reads changed hold code before launching"
new_case launcher-reexec-launch-point
export FLEET_LAUNCH_MAX_WAIT_S=120
launchers="$CASE_DIR/launchers"
copy_launchers "$launchers"
cp "$launchers/dispatch-dual.sh" "$CASE_DIR/committed-dispatch-dual.sh"
without_hold_handling "$CASE_DIR/committed-dispatch-dual.sh" > "$launchers/dispatch-dual.sh"
chmod +x "$launchers/dispatch-dual.sh"
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
mkdir "$FLEET_LAUNCH_GMK_LOCK_DIR"
sleep 600 &
holder_pid=$!
printf 'owner=other-seat pid=%s item=bd-ib-holder\n' "$holder_pid" > "$FLEET_LAUNCH_GMK_LOCK_DIR/holder"
ONLY_GMK=1 TICKET_NS=100 "$launchers/dispatch-dual.sh" bd-ib-reexec-bound > "$CASE_DIR/impl.log" 2>&1 &
reexec_pid=$!
wait_for_line "$CASE_DIR/impl.log" "queue for the gmktec mutex" "$OBSERVE_WAIT_S" || fail "the launcher did not wait for the mutex"
printf 'reason: canary gate\n' > "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
replace_script "$launchers/dispatch-dual.sh" "$CASE_DIR/committed-dispatch-dual.sh"
kill "$holder_pid" 2>/dev/null
wait "$holder_pid" 2>/dev/null
rm -f "$FLEET_LAUNCH_GMK_LOCK_DIR/holder"
rmdir "$FLEET_LAUNCH_GMK_LOCK_DIR"
wait_for_line "$CASE_DIR/impl.log" "repository hold present" "$OBSERVE_WAIT_S" \
    || fail "the bound launcher never read the repository hold"
sleep 0.3
if kill -0 "$reexec_pid" 2>/dev/null && [ ! -s "$DRIVE_LOG" ] \
    && [ -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat" ] \
    && [ -z "$(find "$FLEET_LAUNCH_INFLIGHT_DIR" -type f -print -quit)" ]; then
    pass "a launcher bound at the mutex when its script changed holds under the changed code and keeps its ticket"
else
    fail "the bound launcher launched under its old hold code (dispatches: $(drive_log_items))"
    tail -6 "$CASE_DIR/impl.log" >&2
fi
stop_launcher "$reexec_pid"
wait "$reexec_pid" 2>/dev/null

scenario "21b. a resume launcher started before a hold check was added honours the hold"
new_case launcher-reexec-resume
export FLEET_LAUNCH_MAX_WAIT_S=120
launchers="$CASE_DIR/launchers"
copy_launchers "$launchers"
cp "$launchers/resume-capped.sh" "$CASE_DIR/committed-resume-capped.sh"
without_hold_handling "$CASE_DIR/committed-resume-capped.sh" > "$launchers/resume-capped.sh"
chmod +x "$launchers/resume-capped.sh"
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '0\n' > "$CAP_FILE"
"$launchers/resume-capped.sh" bd-ib-reexec-resume > "$CASE_DIR/resume.log" 2>&1 &
reexec_pid=$!
wait_for_line "$CASE_DIR/resume.log" "fleet at cap under mutex" "$OBSERVE_WAIT_S" || fail "the resume launcher never reached its waiting loop"
# The cap log does not prove the queue entry has reached the filesystem.  Wait
# for the ticket itself before reading its pid so a post-cap scheduling race
# cannot turn a correctly held launcher into a false launch-through verdict.
ticket_path=$(wait_for_queue_ticket "$FLEET_LAUNCH_GMK_QUEUE_DIR" "$OBSERVE_WAIT_S") \
    || fail "the resume launcher never wrote its queue ticket"
ticket_before=""
[ -n "$ticket_path" ] && ticket_before=$(ticket_pid "$ticket_path")
printf 'reason: canary gate\n' > "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
replace_script "$launchers/resume-capped.sh" "$CASE_DIR/committed-resume-capped.sh"
wait_for_line "$CASE_DIR/resume.log" "launcher script changed on disk" "$OBSERVE_WAIT_S" \
    || fail "the waiting resume launcher never noticed its script changed on disk"
printf '8\n' > "$CAP_FILE"
wait_for_line "$CASE_DIR/resume.log" "repository hold present" "$OBSERVE_WAIT_S" \
    || fail "the waiting resume launcher never read the repository hold"
sleep 0.3
case_21b_failed=0
if ! kill -0 "$reexec_pid" 2>/dev/null; then
    fail "case 21b: the resume launcher died while the repository hold was present"
    case_21b_failed=1
fi
if [ -s "$RESUME_LOG" ]; then
    fail "case 21b: the resume log is non-empty while the repository hold was present"
    case_21b_failed=1
fi
if [ -z "$ticket_before" ]; then
    fail "case 21b: no ticket was read before the repository hold"
    case_21b_failed=1
fi
ticket_after=""
if [ -n "$ticket_path" ] && [ -e "$ticket_path" ]; then
    ticket_after=$(ticket_pid "$ticket_path")
fi
if [ -n "$ticket_before" ] && [ "$ticket_after" != "$ticket_before" ]; then
    fail "case 21b: the ticket's pid changed while the repository hold was present (before=${ticket_before:-none} after=${ticket_after:-none})"
    case_21b_failed=1
fi
if [ "$case_21b_failed" = 0 ]; then
    pass "a hold file created while the resume launcher waits stops it, keeping its original queue ticket"
else
    tail -6 "$CASE_DIR/resume.log" >&2
fi
rm -f "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
wait "$reexec_pid" 2>/dev/null
if [ "$(tr '\n' ' ' < "$RESUME_LOG" | sed 's/ *$//')" = bd-ib-reexec-resume ]; then
    pass "control: removing the hold resumes the same launcher"
else
    fail "control: the resume launcher did not resume once the hold was removed"
    tail -6 "$CASE_DIR/resume.log" >&2
fi
stop_launcher "$reexec_pid"

scenario "22. launcher-versions.sh marks the launcher running a stale script"
new_case launcher-versions
export FLEET_LAUNCH_MAX_WAIT_S=120
stale_dir="$CASE_DIR/stale-launchers"
fresh_dir="$CASE_DIR/fresh-launchers"
copy_launchers "$stale_dir"
copy_launchers "$fresh_dir"
as_legacy_launcher "$LAUNCHER" > "$stale_dir/dispatch-dual.sh"
chmod +x "$stale_dir/dispatch-dual.sh"
stale_started=$(sha256sum < "$stale_dir/dispatch-dual.sh" | cut -c1-12)
fresh_started=$(sha256sum < "$fresh_dir/dispatch-dual.sh" | cut -c1-12)
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '0\n' > "$CAP_FILE"
ONLY_GMK=1 TICKET_NS=100 "$stale_dir/dispatch-dual.sh" bd-ib-stale > "$CASE_DIR/stale.log" 2>&1 &
stale_pid=$!
ONLY_GMK=1 TICKET_NS=200 "$fresh_dir/dispatch-dual.sh" bd-ib-fresh > "$CASE_DIR/fresh.log" 2>&1 &
fresh_pid=$!
wait_for_line "$CASE_DIR/stale.log" "fleet not green" "$OBSERVE_WAIT_S" || fail "the stale-case launcher never reached its waiting loop"
wait_for_line "$CASE_DIR/fresh.log" "queued behind an older gmktec ticket" "$OBSERVE_WAIT_S" || fail "the fresh-case launcher never reached its waiting loop"
{ cat "$stale_dir/dispatch-dual.sh"; printf '# changed on disk\n'; } > "$CASE_DIR/stale-replacement.sh"
replace_script "$stale_dir/dispatch-dual.sh" "$CASE_DIR/stale-replacement.sh"
stale_on_disk=$(sha256sum < "$stale_dir/dispatch-dual.sh" | cut -c1-12)
queue_before=$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -name "[0-9]*" | sort | tr '\n' ' ')
report=$(bash "$LAUNCH_DIR/launcher-versions.sh" 2>&1)
stale_row=$(printf '%s\n' "$report" | awk -v p="$stale_pid" '$1==p')
fresh_row=$(printf '%s\n' "$report" | awk -v p="$fresh_pid" '$1==p')
stale_ok=$(printf '%s\n' "$stale_row" | awk -v r="$stale_started" -v d="$stale_on_disk" '$2=="STALE" && $3==r && $4==d {ok=1} END{if (ok) print "yes"}')
fresh_ok=$(printf '%s\n' "$fresh_row" | awk -v r="$fresh_started" '$2=="current" && $3==r && $4==r {ok=1} END{if (ok) print "yes"}')
if [ "$stale_ok" = yes ] && [ "$fresh_ok" = yes ]; then
    pass "the readback lists each launcher's running script version and marks only the one that differs from disk"
else
    fail "the readback did not mark the stale launcher (stale row: ${stale_row:-none}; fresh row: ${fresh_row:-none})"
    printf '%s\n' "$report" >&2
fi
if [ "$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -name "[0-9]*" | sort | tr '\n' ' ')" = "$queue_before" ] \
    && kill -0 "$stale_pid" 2>/dev/null && kill -0 "$fresh_pid" 2>/dev/null; then
    pass "the readback changes no queue ticket and stops no launcher"
else
    fail "the readback disturbed a launcher or its ticket"
fi
stop_launcher "$stale_pid" "$fresh_pid"
wait "$stale_pid" 2>/dev/null
wait "$fresh_pid" 2>/dev/null
fi

# --- Scenario 307: the committed launchers enforce the interim launcher's gates ------------------
# Each case below carries its own positive control: the same inputs with the one gate opened, which
# MUST launch.  A refusal that is never contrasted with a launch is satisfied by a launcher that
# refuses everything.
if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = scenario307 ]; then


scenario "23. a repository at its wip_cap yields the FIFO head without a preflight"
new_case wip-at-cap
export FLEET_LAUNCH_MAX_WAIT_S=120
open_boards
printf '5\n' > "$STUB_WIP_COUNT_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-wip-held > "$CASE_LOG" 2>&1 &
wip_pid=$!
if wait_for_line "$CASE_LOG" "repository WIP at cap: counted=5 cap=5" "$OBSERVE_WAIT_S" \
    && kill -0 "$wip_pid" 2>/dev/null \
    && [ "$(ticket_held_lines "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat")" = 1 ] \
    && [ ! -s "$PREFLIGHT_LOG" ] && [ ! -s "$DRIVE_LOG" ]; then
    pass "a launcher at the cap keeps its ticket, marks it held= once and runs no preflight"
else
    fail "a launcher at the cap did not yield without a preflight (preflights: $(wc -l < "$PREFLIGHT_LOG"), dispatches: $(drive_log_items))"
    tail -5 "$CASE_LOG" >&2
fi
printf '4\n' > "$STUB_WIP_COUNT_FILE"
if wait_gone "$wip_pid" "$EXIT_WAIT_S" && wait "$wip_pid" \
    && [ "$(drive_log_items)" = bd-ib-wip-held ] && [ "$(preflight_count bd-ib-wip-held)" -ge 1 ]; then
    pass "control: once the count drops below the cap the launcher takes its place back, preflights and launches"
else
    fail "control: the launcher did not launch after the count dropped below the cap"
    tail -8 "$CASE_LOG" >&2
    stop_launcher "$wip_pid"
    wait "$wip_pid" 2>/dev/null
fi

scenario "24. only a breakage-exception item passes the WIP gate one above the cap"
new_case wip-breakage-exception
export FLEET_LAUNCH_MAX_WAIT_S=120
open_boards
printf '5\n' > "$STUB_WIP_COUNT_FILE"
printf 'bd-ib-listed\n' > "$FLEET_LAUNCH_BREAKAGE_EXCEPTION_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-unlisted > "$CASE_DIR/unlisted.log" 2>&1 &
unlisted_pid=$!
run_launcher bd-ib-listed "$CASE_DIR/listed.log"
listed_rc=$RC
if [ "$listed_rc" = 0 ] && [ "$(drive_log_items)" = bd-ib-listed ] \
    && wait_for_line "$CASE_DIR/unlisted.log" "repository WIP at cap: counted=5 cap=5 effective=5" "$OBSERVE_WAIT_S" \
    && kill -0 "$unlisted_pid" 2>/dev/null; then
    pass "at counted == wip_cap the listed item launches and the unlisted item is held"
else
    fail "the breakage exception did not separate the listed item from the unlisted one (listed rc=$listed_rc, dispatches: $(drive_log_items))"
    tail -4 "$CASE_DIR/listed.log" "$CASE_DIR/unlisted.log" >&2
fi
stop_launcher "$unlisted_pid"
wait "$unlisted_pid" 2>/dev/null
printf '6\n' > "$STUB_WIP_COUNT_FILE"
: > "$DRIVE_LOG"
ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-listed > "$CASE_DIR/listed-above.log" 2>&1 &
above_pid=$!
if wait_for_line "$CASE_DIR/listed-above.log" "repository WIP at cap: counted=6 cap=5 effective=6" "$OBSERVE_WAIT_S" \
    && kill -0 "$above_pid" 2>/dev/null && [ ! -s "$DRIVE_LOG" ]; then
    pass "the exception is one above the cap and no more: a listed item is held at wip_cap + 1"
else
    fail "a listed item was not held at wip_cap + 1"
    tail -4 "$CASE_DIR/listed-above.log" >&2
fi
stop_launcher "$above_pid"
wait "$above_pid" 2>/dev/null

scenario "25. an unreadable counted-claims count does not hold the launch"
new_case wip-unreadable
open_boards
printf '9\n' > "$STUB_WIP_COUNT_FILE"
: > "$STUB_WIP_UNREADABLE_FILE"
run_launcher bd-ib-wip-unreadable
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = bd-ib-wip-unreadable ] \
    && log_has "$CASE_LOG" "repository WIP count unreadable"; then
    pass "a count that cannot be read is not held on; the Dispatcher's own cap still applies"
else
    fail "an unreadable WIP count held the launch (rc=$RC, dispatches: $(drive_log_items))"
    tail -5 "$CASE_LOG" >&2
fi

scenario "26. a drive that exits before its run lists re-takes a ticket for the same item"
new_case reticket
open_boards
export FLEET_LAUNCH_MAX_WAIT_S=120
export STUB_DRIVE_FAIL_TIMES=2
export STUB_DRIVE_FAIL_RC=1
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-reticket > "$CASE_LOG" 2>&1
reticket_rc=$?
if [ "$reticket_rc" = 0 ] \
    && [ "$(drive_log_items)" = "bd-ib-reticket bd-ib-reticket bd-ib-reticket" ] \
    && [ "$(grep -cF 'gmktec FIFO ticket taken at start: 100-harness-seat' "$CASE_LOG")" = 3 ] \
    && [ "$(grep -cF 'terminal: item=bd-ib-reticket ticket=100 cause=drive-exit-early' "$CASE_LOG")" = 2 ] \
    && [ ! -e "$FLEET_LAUNCH_RETICKET_STATE_DIR/bd-ib-reticket.early-exits" ]; then
    pass "two early drive exits each re-take ticket 100 for the same item; a listed run resets the count"
else
    fail "an early drive exit did not re-take the ticket (rc=$reticket_rc, dispatches: $(drive_log_items))"
    tail -12 "$CASE_LOG" >&2
fi
new_case reticket-persisted
open_boards
export FLEET_LAUNCH_MAX_WAIT_S=120
export STUB_DRIVE_FAIL_TIMES=1
mkdir -p "$FLEET_LAUNCH_RETICKET_STATE_DIR"
printf '2\n' > "$FLEET_LAUNCH_RETICKET_STATE_DIR/bd-ib-persisted.early-exits"
run_launcher bd-ib-persisted
if [ "$RC" = 0 ] && grep -qF 'consecutive early exits 3): re-ticket item=bd-ib-persisted' "$CASE_LOG" \
    && grep -qF 're-ticket-after=0.02s' "$CASE_LOG"; then
    pass "the early-exit count survives a launcher restart and picks the third configured delay"
else
    fail "the persisted early-exit count was not honoured (rc=$RC)"
    tail -6 "$CASE_LOG" >&2
fi

scenario "27. a failed goal template preflight is never re-ticketed"
new_case reticket-goal-template
open_boards
export FLEET_LAUNCH_MAX_WAIT_S=120
export STUB_DRIVE_FAIL_TIMES=5
export STUB_DRIVE_FAIL_RC=1
export STUB_DRIVE_FAIL_STDOUT='{"dispatcher": {"exit_code": 1, "stdout_json": [{"stage": "goal-minijinja-preflight", "status": "failed", "detail": "field description offset 12"}]}}'
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-template > "$CASE_LOG" 2>&1
template_rc=$?
if [ "$template_rc" = 1 ] && [ "$(drive_log_items)" = bd-ib-template ] \
    && grep -qF 'terminal: item=bd-ib-template ticket=100 cause=goal-minijinja-preflight' "$CASE_LOG" \
    && [ "$(grep -c . "$STUB_LEDGER_COMMENTS")" = 1 ] \
    && grep -qF 'goal-minijinja-preflight' "$STUB_LEDGER_COMMENTS" \
    && ! grep -qE '\{\{|\{%|\{#' "$CASE_LOG" "$STUB_LEDGER_COMMENTS"; then
    pass "a goal-minijinja-preflight failure stops after one drive with a terminal line and one comment free of template openers"
else
    fail "a goal template failure was re-ticketed or left no record (rc=$template_rc, dispatches: $(drive_log_items))"
    tail -6 "$CASE_LOG" >&2
fi
new_case reticket-zero-exit
open_boards
export FLEET_LAUNCH_MAX_WAIT_S=120
export STUB_DRIVE_FAIL_TIMES=1
export STUB_DRIVE_FAIL_RC=0
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-zero > "$CASE_LOG" 2>&1
zero_rc=$?
if [ "$zero_rc" = 0 ] && [ "$(drive_log_items)" = "bd-ib-zero bd-ib-zero" ] \
    && [ "$(grep -cF 'terminal: item=bd-ib-zero ticket=100 cause=drive-exit-early drive-exit=0' "$CASE_LOG")" = 1 ]; then
    pass "a drive that exits 0 before its run lists re-takes ticket 100 rather than dropping the item"
else
    fail "a zero-status early drive exit dropped the item (rc=$zero_rc, dispatches: $(drive_log_items))"
    tail -8 "$CASE_LOG" >&2
fi
new_case reticket-zero-exit-not-ready
open_boards
export FLEET_LAUNCH_MAX_WAIT_S=120
export STUB_DRIVE_FAIL_TIMES=1
export STUB_DRIVE_FAIL_RC=0
printf 'active\n' > "$STUB_ITEM_STATUS_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-zero-not-ready > "$CASE_LOG" 2>&1
zero_not_ready_rc=$?
if [ "$zero_not_ready_rc" = 0 ] && [ "$(drive_log_items)" = bd-ib-zero-not-ready ] \
    && grep -qF 'terminal: item=bd-ib-zero-not-ready ticket=100 cause=drive-exit-early drive-exit=0' "$CASE_LOG"; then
    pass "a zero-status drive with no final listing does not re-take a ticket when its item is not ready"
else
    fail "a zero-status drive re-took a ticket despite its item not reading ready (rc=$zero_not_ready_rc, dispatches: $(drive_log_items))"
    tail -8 "$CASE_LOG" >&2
fi
new_case reticket-refused
open_boards
export FLEET_LAUNCH_MAX_WAIT_S=120
export STUB_DRIVE_FAIL_TIMES=5
export STUB_DRIVE_FAIL_RC=5
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-refused > "$CASE_LOG" 2>&1
refused_rc=$?
if [ "$refused_rc" = 5 ] && [ "$(drive_log_items)" = bd-ib-refused ] \
    && grep -qF 'cause=refused' "$CASE_LOG" && [ "$(grep -c . "$STUB_LEDGER_COMMENTS")" = 1 ]; then
    pass "a drive that exits 5 is a permanent refusal: no ticket is re-taken"
else
    fail "a drive exiting 5 was re-ticketed (rc=$refused_rc, dispatches: $(drive_log_items))"
    tail -6 "$CASE_LOG" >&2
fi

scenario "28. the gmktec hold path is assigned in each launcher and checked at the launch point"
for launcher_file in "$LAUNCHER" "$RESUME_LAUNCHER"; do
    if grep -qE '^GMK_HOLD_FILE=\$FLEET_LAUNCH_HOLD_FILE$' "$launcher_file" \
        && grep -qF '[ -e "$GMK_HOLD_FILE" ]' "$launcher_file"; then
        pass "$(basename "$launcher_file") assigns the gmktec hold path itself and tests it"
    else
        fail "$(basename "$launcher_file") does not assign and test the gmktec hold path"
    fi
done
new_case gmk-hold-launch-point
export FLEET_LAUNCH_MAX_WAIT_S=120
open_boards
mkdir "$FLEET_LAUNCH_GMK_LOCK_DIR"
sleep 600 &
gmk_holder_pid=$!
printf 'owner=other-seat pid=%s item=bd-ib-holder\n' "$gmk_holder_pid" > "$FLEET_LAUNCH_GMK_LOCK_DIR/holder"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-gmk-launch-point > "$CASE_LOG" 2>&1 &
gmk_lp_pid=$!
wait_for_line "$CASE_LOG" "queue for the gmktec mutex" "$OBSERVE_WAIT_S" || fail "the launcher did not wait for the gmktec mutex"
: > "$HOLD_FILE"
kill "$gmk_holder_pid" 2>/dev/null
wait "$gmk_holder_pid" 2>/dev/null
rm -f "$FLEET_LAUNCH_GMK_LOCK_DIR/holder"
rmdir "$FLEET_LAUNCH_GMK_LOCK_DIR"
if wait_for_line "$CASE_LOG" "hold file present" "$OBSERVE_WAIT_S" \
    && kill -0 "$gmk_lp_pid" 2>/dev/null \
    && [ -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat" ] && [ ! -s "$DRIVE_LOG" ]; then
    pass "a gmktec hold created while the launcher waits for the mutex launches nothing and keeps the ticket"
else
    fail "a gmktec hold created during the mutex wait did not hold the launch"
    tail -6 "$CASE_LOG" >&2
fi
rm -f "$HOLD_FILE"
if wait_gone "$gmk_lp_pid" "$EXIT_WAIT_S" && wait "$gmk_lp_pid" && [ "$(drive_log_items)" = bd-ib-gmk-launch-point ]; then
    pass "control: removing the gmktec hold file releases the same launcher"
else
    fail "control: the launcher did not launch once the gmktec hold was removed"
    tail -6 "$CASE_LOG" >&2
    stop_launcher "$gmk_lp_pid"
    wait "$gmk_lp_pid" 2>/dev/null
fi

scenario "29. the gmktec target setting names the instance a launch goes to"
new_case gmk-target-candidate
export FLEET_LAUNCH_MAX_WAIT_S=120
open_boards
write_board "$BOARD_CANDIDATE" 2 cand
printf 'candidate\n' > "$FLEET_LAUNCH_GMK_TARGET_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-candidate > "$CASE_LOG" 2>&1 &
cand_pid=$!
if wait_for_line "$CASE_LOG" "gmktec candidate not green: live=2 cap=2" "$OBSERVE_WAIT_S" \
    && kill -0 "$cand_pid" 2>/dev/null && [ ! -s "$DRIVE_LOG" ]; then
    pass "a candidate target holds while the candidate's live run count is at its cap, with the default instance idle"
else
    fail "the candidate cap did not hold the launch"
    tail -5 "$CASE_LOG" >&2
fi
write_board "$BOARD_CANDIDATE" 1 cand
if wait_gone "$cand_pid" "$EXIT_WAIT_S" && wait "$cand_pid" \
    && [ "$(drive_log_items)" = bd-ib-candidate ] \
    && [ "$(cut -d' ' -f1 "$STUB_DRIVEN_DIR/bd-ib-candidate")" = "$CANDIDATE_URL" ]; then
    pass "below the candidate cap the launch goes to the candidate instance, not the default one"
else
    fail "the launch did not go to the candidate instance"
    tail -6 "$CASE_LOG" >&2
    stop_launcher "$cand_pid"
    wait "$cand_pid" 2>/dev/null
fi
new_case gmk-target-unreadable-candidate
export FLEET_LAUNCH_MAX_WAIT_S=120
open_boards
rm -f "$BOARD_CANDIDATE"
printf 'candidate\n' > "$FLEET_LAUNCH_GMK_TARGET_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-candidate-unreadable > "$CASE_LOG" 2>&1 &
unreadable_pid=$!
if wait_for_line "$CASE_LOG" "fleet not green" "$OBSERVE_WAIT_S" && kill -0 "$unreadable_pid" 2>/dev/null && [ ! -s "$DRIVE_LOG" ]; then
    pass "a candidate board that cannot be read holds the launch"
else
    fail "an unreadable candidate board did not hold the launch"
    tail -5 "$CASE_LOG" >&2
fi
stop_launcher "$unreadable_pid"
wait "$unreadable_pid" 2>/dev/null
for target_word in absent default; do
    new_case "gmk-target-$target_word"
    open_boards
    : > "$BOARD_CANDIDATE"
    [ "$target_word" = absent ] || printf 'something-else\n' > "$FLEET_LAUNCH_GMK_TARGET_FILE"
    run_launcher bd-ib-default-instance
    if [ "$RC" = 0 ] && [ "$(cut -d' ' -f1 "$STUB_DRIVEN_DIR/bd-ib-default-instance")" = "$GMK_URL" ]; then
        pass "a target setting that is $target_word selects the default instance"
    else
        fail "a target setting that is $target_word did not select the default instance (rc=$RC)"
        tail -5 "$CASE_LOG" >&2
    fi
done

scenario "30. the checkout is fast-forwarded to origin's default branch before the preflight and the launch"
git -C "$WORK/seed" "${GIT_IDENTITY[@]}" commit --quiet --allow-empty --no-verify -m "origin advances"
git -C "$WORK/seed" "${GIT_IDENTITY[@]}" push --quiet "$ORIGIN" master
master_tip=$(git -C "$WORK/seed" rev-parse HEAD)
new_case origin-tip
export FLEET_LAUNCH_MAX_WAIT_S=120
open_boards
export STUB_PREFLIGHT_HEAD_LOG="$CASE_DIR/preflight-heads"
behind_head=$(git -C "$TENANT" rev-parse HEAD)
run_launcher bd-ib-origin-tip
if [ "$RC" = 0 ] && [ "$behind_head" != "$master_tip" ] \
    && [ "$(git -C "$TENANT" rev-parse HEAD)" = "$master_tip" ] \
    && [ "$(cat "$STUB_PREFLIGHT_HEAD_LOG")" = "$master_tip" ] \
    && [ "$(drive_log_items)" = bd-ib-origin-tip ]; then
    pass "a checkout behind origin is fast-forwarded before the preflight reads it, then launches"
else
    fail "the checkout was not at the origin tip when the preflight read it (rc=$RC)"
    tail -5 "$CASE_LOG" >&2
fi
git -C "$WORK/seed-main" "${GIT_IDENTITY[@]}" commit --quiet --allow-empty --no-verify -m "origin main advances"
git -C "$WORK/seed-main" "${GIT_IDENTITY[@]}" push --quiet "$ORIGIN_MAIN" main
main_tip=$(git -C "$WORK/seed-main" rev-parse HEAD)
new_case origin-tip-main
open_boards
export REPO_OVERRIDE="$TENANT_MAIN"
export STUB_PREFLIGHT_HEAD_LOG="$CASE_DIR/preflight-heads"
run_launcher bd-ib-origin-main
if [ "$RC" = 0 ] && [ "$(git -C "$TENANT_MAIN" rev-parse HEAD)" = "$main_tip" ] \
    && [ "$(cat "$STUB_PREFLIGHT_HEAD_LOG")" = "$main_tip" ]; then
    pass "a repository whose default branch is main is fast-forwarded to main, never assumed to be master"
else
    fail "a main-default checkout was not fast-forwarded (rc=$RC)"
    tail -5 "$CASE_LOG" >&2
fi
git -C "$TENANT_BROKEN" remote set-url origin "$WORK/no-such-origin.git"
new_case origin-tip-broken
open_boards
export REPO_OVERRIDE="$TENANT_BROKEN"
run_launcher bd-ib-origin-broken
if [ "$RC" != 0 ] && [ ! -s "$DRIVE_LOG" ] && [ ! -s "$PREFLIGHT_LOG" ] \
    && grep -qF 'terminal: item=bd-ib-origin-broken ticket=none cause=checkout-not-at-origin-tip step=default-branch' "$CASE_LOG" \
    && [ -z "$(find "$FLEET_LAUNCH_INFLIGHT_DIR" -type f -print -quit)" ] \
    && [ ! -d "$FLEET_LAUNCH_GMK_LOCK_DIR" ] && [ -z "$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -print -quit)" ]; then
    pass "a remote that cannot be read launches nothing, runs no preflight and takes no factory slot"
else
    fail "a failed origin read did not stop the launcher cleanly (rc=$RC)"
    tail -5 "$CASE_LOG" >&2
fi
git -C "$TENANT_DIVERGED" "${GIT_IDENTITY[@]}" commit --quiet --allow-empty --no-verify -m "local only"
new_case origin-tip-diverged
open_boards
export REPO_OVERRIDE="$TENANT_DIVERGED"
git -C "$WORK/seed" "${GIT_IDENTITY[@]}" commit --quiet --allow-empty --no-verify -m "origin advances again"
git -C "$WORK/seed" "${GIT_IDENTITY[@]}" push --quiet "$ORIGIN" master
run_launcher bd-ib-origin-diverged
if [ "$RC" != 0 ] && [ ! -s "$DRIVE_LOG" ] && [ ! -s "$PREFLIGHT_LOG" ] \
    && grep -qF 'cause=checkout-not-at-origin-tip step=fast-forward' "$CASE_LOG"; then
    pass "a diverged checkout launches nothing and names the fast-forward step"
else
    fail "a diverged checkout was not refused at the fast-forward (rc=$RC)"
    tail -5 "$CASE_LOG" >&2
fi

scenario "31. a ready-set refusal lists as open blockers only dependencies that are neither closed nor done"
STUB_PLUGIN="$WORK/ready-check-plugin"
mkdir -p "$STUB_PLUGIN/scripts/bin" "$STUB_PLUGIN/scripts/livespec_orchestrator_beads_fabro/commands"
cat > "$STUB_PLUGIN/scripts/bin/_bootstrap.py" <<'BOOTSTRAP_STUB'
import sys
from pathlib import Path


def bootstrap():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
BOOTSTRAP_STUB
: > "$STUB_PLUGIN/scripts/livespec_orchestrator_beads_fabro/__init__.py"
: > "$STUB_PLUGIN/scripts/livespec_orchestrator_beads_fabro/commands/__init__.py"
cat > "$STUB_PLUGIN/scripts/livespec_orchestrator_beads_fabro/commands/_config.py" <<'CONFIG_STUB'
def resolve_store_config(*, cwd, work_items_arg):
    return None
CONFIG_STUB
cat > "$STUB_PLUGIN/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_loop_selection.py" <<'SELECTION_STUB'
def ready_items(*, items, repo):
    return []
SELECTION_STUB
cat > "$STUB_PLUGIN/scripts/livespec_orchestrator_beads_fabro/store.py" <<'STORE_STUB'
from types import SimpleNamespace


def read_work_items(*, path):
    deps = [{"work_item_id": name} for name in ("bd-dep-done", "bd-dep-closed", "bd-dep-open")]
    return [
        SimpleNamespace(id="bd-me", status="ready", assignee=None, depends_on=deps),
        SimpleNamespace(id="bd-dep-done", status="done", assignee=None, depends_on=()),
        SimpleNamespace(id="bd-dep-closed", status="closed", assignee=None, depends_on=()),
        SimpleNamespace(id="bd-dep-open", status="ready", assignee=None, depends_on=()),
    ]
STORE_STUB
blocker_line=$(python3 "$LAUNCH_DIR/ready-set-check.py" "$STUB_PLUGIN" "$WORK" bd-me 2>&1)
blocker_rc=$?
if [ "$blocker_rc" = 3 ] && grep -qF 'bd-dep-open=ready' <<<"$blocker_line" \
    && ! grep -qE 'bd-dep-(done|closed)' <<<"$blocker_line"; then
    pass "a done dependency is not listed as an open blocker, a closed one is not, and an open one is; the refusal stands"
else
    fail "the refusal line mislists blockers (rc=$blocker_rc): $blocker_line"
fi

fi

# --- parity with the running launcher copies (bd-ib-yax6gv, 2026-11-15) ---------------------------
# The gates the dispatching host's interim launcher copies carried that the committed launchers lacked.
# Each refusal carries its own positive control.
if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = parity ]; then

scenario "32. the fleet count sums the gmktec, candidate and mi-homelab lanes and leaves arm64 out"
new_case fleet-sum-candidate
export FLEET_LAUNCH_MAX_WAIT_S=120
write_board "$BOARD_GMK" 1 gmk
: > "$BOARD_HL"
write_board "$BOARD_CANDIDATE" 2 cand
: > "$FLEET_LAUNCH_ARM_ENROLLED_FILE"
write_board "$BOARD_ARM" 1 arm
printf '3\n' > "$CAP_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-fleet-sum > "$CASE_LOG" 2>&1 &
sum_pid=$!
if wait_for_line "$CASE_LOG" "fleet not green: gmktec=1 hl=0 markers=0 fleet=3 cap=3 candidate=2 arm64=1" "$OBSERVE_WAIT_S" \
    && kill -0 "$sum_pid" 2>/dev/null && [ ! -s "$DRIVE_LOG" ] \
    && [ -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat" ]; then
    pass "a fleet at the cap only because of candidate-lane runs launches nothing and keeps its ticket; arm64 is outside the sum"
else
    fail "the fleet count did not include the candidate lane or did include the arm64 lane"
    tail -5 "$CASE_LOG" >&2
fi
printf '4\n' > "$CAP_FILE"
if wait_gone "$sum_pid" "$EXIT_WAIT_S" && wait "$sum_pid" && [ "$(drive_log_items)" = bd-ib-fleet-sum ] \
    && [ "$(cut -d' ' -f1 "$STUB_DRIVEN_DIR/bd-ib-fleet-sum")" = "$GMK_URL" ]; then
    pass "control: one slot of headroom in the same sum launches onto the default instance"
else
    fail "control: the launcher did not launch with headroom in the fleet sum"
    tail -6 "$CASE_LOG" >&2
    stop_launcher "$sum_pid"; wait "$sum_pid" 2>/dev/null
fi

scenario "33. the arm64 lane launches against its own cap only once enrolled"
new_case arm64-lane
export FLEET_LAUNCH_MAX_WAIT_S=120
write_board "$BOARD_GMK" 8 gmk
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
: > "$BOARD_ARM"
ONLY_ARM=1 TICKET_NS=100 "$LAUNCHER" bd-ib-arm-unenrolled > "$CASE_DIR/unenrolled.log" 2>&1 &
arm_pid=$!
if wait_for_line "$CASE_DIR/unenrolled.log" "homelab-worker-arm64 not green: enrolled=no" "$OBSERVE_WAIT_S" \
    && kill -0 "$arm_pid" 2>/dev/null && [ ! -s "$DRIVE_LOG" ]; then
    pass "an arm64 launcher launches nothing while the instance is not enrolled"
else
    fail "an unenrolled arm64 lane did not hold the launch"
    tail -5 "$CASE_DIR/unenrolled.log" >&2
fi
: > "$FLEET_LAUNCH_ARM_ENROLLED_FILE"
if wait_gone "$arm_pid" "$EXIT_WAIT_S" && wait "$arm_pid" && [ "$(drive_log_items)" = bd-ib-arm-unenrolled ] \
    && [ "$(cut -d' ' -f1 "$STUB_DRIVEN_DIR/bd-ib-arm-unenrolled")" = "$ARM_URL" ] \
    && grep -q 'LAUNCH target=homelab-worker-arm64' "$CASE_DIR/unenrolled.log"; then
    pass "control: once enrolled the arm64 launcher launches onto the arm64 instance with the fleet at its cap"
else
    fail "the enrolled arm64 lane did not launch (dispatches: $(drive_log_items))"
    tail -6 "$CASE_DIR/unenrolled.log" >&2
    stop_launcher "$arm_pid"; wait "$arm_pid" 2>/dev/null
fi
: > "$DRIVE_LOG"
# The first launch's driven row has left the board; the fixture alone holds one live run.
rm -f "$STUB_DRIVEN_DIR/bd-ib-arm-unenrolled"
write_board "$BOARD_ARM" 1 arm
ONLY_ARM=1 TICKET_NS=200 "$LAUNCHER" bd-ib-arm-capped > "$CASE_DIR/capped.log" 2>&1 &
arm_capped_pid=$!
if wait_for_line "$CASE_DIR/capped.log" "homelab-worker-arm64 not green: enrolled=yes arm_inflight=1 cap=1" "$OBSERVE_WAIT_S" \
    && kill -0 "$arm_capped_pid" 2>/dev/null && [ ! -s "$DRIVE_LOG" ]; then
    pass "an arm64 launcher holds at the arm64 cap, whatever the fleet sum"
else
    fail "the arm64 cap did not hold the launch"
    tail -5 "$CASE_DIR/capped.log" >&2
fi
stop_launcher "$arm_capped_pid"; wait "$arm_capped_pid" 2>/dev/null

scenario "34. the freeze allowlist releases a listed item from the gmktec hold exactly once"
new_case allowlist-one-shot
export FLEET_LAUNCH_MAX_WAIT_S=120
open_boards
: > "$HOLD_FILE"
printf 'bd-ib-other\nbd-ib-listed\n' > "$FLEET_LAUNCH_FREEZE_ALLOWLIST_FILE"
run_launcher bd-ib-listed
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = bd-ib-listed ] \
    && [ "$(cat "$FLEET_LAUNCH_FREEZE_ALLOWLIST_FILE")" = bd-ib-other ] \
    && grep -q 'bd-ib-listed consumed at LAUNCH' "$FLEET_LAUNCH_FREEZE_ALLOWLIST_CONSUMED_LOG" \
    && log_has "$CASE_LOG" "ONE-SHOT: freeze-allowlist line for bd-ib-listed consumed at LAUNCH"; then
    pass "an allowlisted item launches through the hold and its line is consumed at LAUNCH, other lines kept"
else
    fail "the allowlisted item did not launch once through the hold (rc=$RC, dispatches: $(drive_log_items), allowlist: $(tr '\n' ' ' < "$FLEET_LAUNCH_FREEZE_ALLOWLIST_FILE"))"
    tail -6 "$CASE_LOG" >&2
fi
: > "$DRIVE_LOG"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-listed > "$CASE_DIR/second.log" 2>&1 &
second_pid=$!
if wait_for_line "$CASE_DIR/second.log" "hold file present" "$OBSERVE_WAIT_S" && kill -0 "$second_pid" 2>/dev/null && [ ! -s "$DRIVE_LOG" ]; then
    pass "a second launcher for the same item is held: one line releases one launch"
else
    fail "the consumed allowlist line released a second launch"
    tail -5 "$CASE_DIR/second.log" >&2
fi
rm -f "$HOLD_FILE"
if wait_gone "$second_pid" "$EXIT_WAIT_S" && wait "$second_pid" && [ "$(drive_log_items)" = bd-ib-listed ]; then
    pass "control: removing the hold releases the held second launcher"
else
    fail "control: the second launcher did not launch once the hold was removed"
    stop_launcher "$second_pid"; wait "$second_pid" 2>/dev/null
fi

scenario "35. a priority-1 item launches through the gmktec hold without an allowlist line"
new_case priority-one-release
open_boards
: > "$HOLD_FILE"
printf 'bd-ib-other\n' > "$FLEET_LAUNCH_FREEZE_ALLOWLIST_FILE"
printf '1\n' > "$STUB_ITEM_PRIORITY_FILE"
run_launcher bd-ib-p1
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = bd-ib-p1 ] && [ "$(cat "$FLEET_LAUNCH_FREEZE_ALLOWLIST_FILE")" = bd-ib-other ]; then
    pass "a priority-1 item launches through the hold and the allowlist is unchanged"
else
    fail "a priority-1 item was held, or consumed an allowlist line (rc=$RC, dispatches: $(drive_log_items))"
    tail -5 "$CASE_LOG" >&2
fi
new_case priority-two-held
export FLEET_LAUNCH_MAX_WAIT_S=120
open_boards
: > "$HOLD_FILE"
printf '2\n' > "$STUB_ITEM_PRIORITY_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-p2 > "$CASE_LOG" 2>&1 &
p2_pid=$!
if wait_for_line "$CASE_LOG" "hold file present" "$OBSERVE_WAIT_S" && kill -0 "$p2_pid" 2>/dev/null && [ ! -s "$DRIVE_LOG" ]; then
    pass "control: a priority-2 item without an allowlist line is held"
else
    fail "control: a priority-2 item launched through the hold"
fi
stop_launcher "$p2_pid"; wait "$p2_pid" 2>/dev/null

scenario "36. a held queue head does not block a released ticket behind it"
new_case held-head-skipped
export FLEET_LAUNCH_MAX_WAIT_S=120
open_boards
: > "$HOLD_FILE"
printf 'bd-ib-released\n' > "$FLEET_LAUNCH_FREEZE_ALLOWLIST_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-held-head > "$CASE_DIR/held.log" 2>&1 &
held_pid=$!
wait_for_line "$CASE_DIR/held.log" "hold file present" "$OBSERVE_WAIT_S" || fail "the held head never parked on the hold"
ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-released > "$CASE_DIR/released.log" 2>&1 &
released_pid=$!
if wait_gone "$released_pid" "$EXIT_WAIT_S" && wait "$released_pid" && [ "$(drive_log_items)" = bd-ib-released ] \
    && kill -0 "$held_pid" 2>/dev/null && [ -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat" ]; then
    pass "the allowlisted ticket behind a held head binds and launches; the held head keeps its ticket number"
else
    fail "the held head blocked the released ticket (dispatches: $(drive_log_items))"
    tail -5 "$CASE_DIR/released.log" >&2
    stop_launcher "$released_pid"; wait "$released_pid" 2>/dev/null
fi
rm -f "$HOLD_FILE"
if wait_gone "$held_pid" "$EXIT_WAIT_S" && wait "$held_pid" && [ "$(drive_log_items)" = "bd-ib-released bd-ib-held-head" ]; then
    pass "control: the held head takes its place back and launches when the hold is removed"
else
    fail "control: the held head did not launch after the lift (dispatches: $(drive_log_items))"
    stop_launcher "$held_pid"; wait "$held_pid" 2>/dev/null
fi

scenario "37. a canary repository hold yields every launch except an exempt item"
new_case canary-hold
export FLEET_LAUNCH_MAX_WAIT_S=120
open_boards
set_hold "$FLEET_LAUNCH_CANARY_HOLD_DIR/canary-hold-repo-$(basename "$TENANT")" "canary v0.0.0-stub adopting"
printf 'bd-ib-exempt\n' > "$FLEET_LAUNCH_CANARY_EXEMPT_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-canary-held > "$CASE_DIR/held.log" 2>&1 &
canary_pid=$!
if wait_for_line "$CASE_DIR/held.log" "canary repository hold present" "$OBSERVE_WAIT_S" && kill -0 "$canary_pid" 2>/dev/null \
    && grep -qx 'held=canary-hold' "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat" && [ ! -s "$DRIVE_LOG" ]; then
    pass "an unlisted item yields on the canary hold, marks its ticket held=canary-hold and launches nothing"
else
    fail "the canary hold did not yield the unlisted item"
    tail -5 "$CASE_DIR/held.log" >&2
fi
run_launcher bd-ib-exempt "$CASE_DIR/exempt.log"
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = bd-ib-exempt ]; then
    pass "an exempt item launches normally under the canary hold"
else
    fail "the exempt item did not launch under the canary hold (rc=$RC)"
    tail -5 "$CASE_DIR/exempt.log" >&2
fi
rm -f "$FLEET_LAUNCH_CANARY_HOLD_DIR/canary-hold-repo-$(basename "$TENANT")"
if wait_gone "$canary_pid" "$EXIT_WAIT_S" && wait "$canary_pid" && [ "$(drive_log_items)" = "bd-ib-exempt bd-ib-canary-held" ]; then
    pass "control: removing the canary hold releases the held launcher in the order of its ticket"
else
    fail "control: the held launcher did not launch after the canary hold was removed"
    stop_launcher "$canary_pid"; wait "$canary_pid" 2>/dev/null
fi

scenario "38. launch-time commands run under the target repository's committed credential wrapper"
TENANT_STUB_WRAPPER="$STUB/tenant-wrapper"
cat > "$TENANT_STUB_WRAPPER" <<'TENANT_WRAPPER_STUB'
#!/usr/bin/env bash
# The stub tenant wrapper: records that it ran and whether the family password reached it, then
# answers through the stub default wrapper.
set -u
[ "${1:-}" = -- ] && shift
printf 'tenant-wrapper password=%s %s\n' "${BEADS_DOLT_PASSWORD:+present}" "$*" >> "$STUB_TENANT_WRAPPER_LOG"
exec "$STUB_DEFAULT_WRAPPER" -- "$@"
TENANT_WRAPPER_STUB
chmod +x "$TENANT_STUB_WRAPPER"
new_case tenant-wrapper
open_boards
unset WRAPPER
export STUB_TENANT_WRAPPER_LOG="$CASE_DIR/tenant-wrapper-log"
: > "$STUB_TENANT_WRAPPER_LOG"
export STUB_DEFAULT_WRAPPER="$STUB/wrapper"
printf '{"credential_wrapper": ["%s", "--"]}\n' "$TENANT_STUB_WRAPPER" > "$TENANT/.livespec.jsonc"
BEADS_DOLT_PASSWORD=family-stub run_launcher bd-ib-tenant
rm -f "$TENANT/.livespec.jsonc"
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = bd-ib-tenant ] \
    && grep -q 'ready-set-check.py' "$STUB_TENANT_WRAPPER_LOG" && grep -q 'dod-preflight.sh' "$STUB_TENANT_WRAPPER_LOG" \
    && grep -q 'ledger-item.py\|wip-claimed-count.py' "$STUB_TENANT_WRAPPER_LOG" && grep -q 'drive.py' "$STUB_TENANT_WRAPPER_LOG" \
    && ! grep -q 'password=present' "$STUB_TENANT_WRAPPER_LOG" \
    && log_has "$CASE_LOG" "wrapper: tenant tenant-wrapper nested in wrapper"; then
    pass "the ready-set check, the preflight, the ledger reads and the drive run under the tenant wrapper nested in the default one, with the family password absent"
else
    fail "launch-time commands did not run under the tenant wrapper as required (rc=$RC)"
    head -5 "$STUB_TENANT_WRAPPER_LOG" >&2
    head -2 "$CASE_LOG" >&2
    tail -3 "$CASE_LOG" >&2
fi
new_case tenant-wrapper-family
open_boards
unset WRAPPER
# Route C's shape (#5361): the family wrapper, then a /bin/sh hop that maps the org App pair onto
# GITHUB_APP_ID / GITHUB_PRIVATE_KEY. The whole argv must reach every launch-time command.
printf '{"credential_wrapper": ["%s", "--", "/bin/sh", "-c", "GITHUB_APP_ID=\\"$GITHUB_APP_ID_ORG\\" GITHUB_PRIVATE_KEY=\\"$GITHUB_PRIVATE_KEY_ORG\\" exec \\"$@\\"", "sh"]}\n' "$STUB/wrapper" > "$TENANT/.livespec.jsonc"
run_launcher bd-ib-family
rm -f "$TENANT/.livespec.jsonc"
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = bd-ib-family ] && log_has "$CASE_LOG" "wrapper: committed wrapper argv, 6 words, run as written"; then
    pass "a target whose credential_wrapper starts with the family wrapper runs its whole six-word argv as written: the /bin/sh org-App hop is kept"
else
    fail "a family-wrapper argv was not run as written (rc=$RC)"
    tail -4 "$CASE_LOG" >&2
fi
new_case tenant-wrapper-family-bare
open_boards
unset WRAPPER
printf '{"credential_wrapper": ["%s", "--"]}\n' "$STUB/wrapper" > "$TENANT/.livespec.jsonc"
run_launcher bd-ib-family-bare
rm -f "$TENANT/.livespec.jsonc"
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = bd-ib-family-bare ] && log_has "$CASE_LOG" "wrapper: committed wrapper argv, 2 words, run as written"; then
    pass "control: the bare family argv is run as written too, so the one rule covers both shapes"
else
    fail "the bare family argv was not run as written (rc=$RC)"
    tail -4 "$CASE_LOG" >&2
fi
new_case tenant-wrapper-absent
open_boards
unset WRAPPER
run_launcher bd-ib-no-key
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = bd-ib-no-key ] && log_has "$CASE_LOG" "wrapper: default wrapper"; then
    pass "a target declaring no credential_wrapper runs under the default wrapper"
else
    fail "a target without a credential_wrapper did not run under the default wrapper (rc=$RC)"
fi
new_case tenant-wrapper-unreadable
open_boards
unset WRAPPER
printf '{"credential_wrapper": ["not", "closed"\n' > "$TENANT/.livespec.jsonc"
run_launcher bd-ib-unreadable-wrapper
rm -f "$TENANT/.livespec.jsonc"
if [ "$RC" != 0 ] && [ ! -s "$DRIVE_LOG" ] && [ ! -s "$PREFLIGHT_LOG" ] \
    && grep -qF 'terminal: item=bd-ib-unreadable-wrapper ticket=none cause=credential-wrapper-unreadable' "$CASE_LOG"; then
    pass "a target whose credential_wrapper cannot be read launches nothing and leaves a credential-wrapper-unreadable terminal line"
else
    fail "an unreadable credential_wrapper did not stop the launcher (rc=$RC)"
    tail -4 "$CASE_LOG" >&2
fi

scenario "39. the configured ACP overrides and judge-model environment reach every drive"
new_case routing
open_boards
printf '# a comment\nNODE_A={"a": 1}\n\nNODE_B={"b": 2}\n' > "$FLEET_LAUNCH_ACP_OVERRIDES_FILE"
FLEET_LAUNCH_DOD_JUDGEMENT_MODEL=stub-dod FLEET_LAUNCH_DRIFT_JUDGE_MODEL=stub-drift FLEET_LAUNCH_REFLECTOR_MODEL='' run_launcher bd-ib-routed
if [ "$RC" = 0 ] && grep -q 'bd-ib-routed acp=NODE_A={"a": 1};NODE_B={"b": 2}; dod=stub-dod drift=stub-drift reflector=unset' "$STUB_DRIVE_ENV_LOG" \
    && log_has "$CASE_LOG" "acp overrides: 2 --acp-node arguments"; then
    pass "two override lines reach the drive as two --acp-node arguments in order; non-empty judge models are exported and an empty one is not"
else
    fail "the configured routing did not reach the drive: $(cat "$STUB_DRIVE_ENV_LOG")"
    tail -4 "$CASE_LOG" >&2
fi
rm -f "$FLEET_LAUNCH_ACP_OVERRIDES_FILE"
: > "$STUB_DRIVE_ENV_LOG"
run_launcher bd-ib-unrouted
if [ "$RC" = 0 ] && grep -q 'bd-ib-unrouted acp= ' "$STUB_DRIVE_ENV_LOG" && log_has "$CASE_LOG" "acp overrides: 0 --acp-node arguments"; then
    pass "control: an absent overrides file adds no --acp-node argument"
else
    fail "an absent overrides file still routed the drive: $(cat "$STUB_DRIVE_ENV_LOG")"
fi

scenario "40. a host-only item exits before the mutex and the preflight with one comment"
new_case host-only
open_boards
export STUB_HOST_ONLY_JSON="$CASE_DIR/host-only.json"
printf '{"work_item_id": "bd-ib-hostonly", "host_only": true, "reason": "declares an edit under .github/workflows/"}\n' > "$STUB_HOST_ONLY_JSON"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-hostonly > "$CASE_LOG" 2>&1
host_only_rc=$?
if [ "$host_only_rc" = 5 ] && [ ! -s "$DRIVE_LOG" ] && [ ! -s "$PREFLIGHT_LOG" ] && [ ! -d "$FLEET_LAUNCH_GMK_LOCK_DIR" ] \
    && grep -qF 'terminal: item=bd-ib-hostonly ticket=100 cause=host-only' "$CASE_LOG" \
    && [ "$(grep -c . "$STUB_LEDGER_COMMENTS")" = 1 ] && grep -q 'ticket 100' "$STUB_LEDGER_COMMENTS" \
    && grep -q 'declares an edit under .github/workflows/' "$STUB_LEDGER_COMMENTS" \
    && [ -z "$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -print -quit)" ]; then
    pass "a host-only verdict is a non-run exit naming the item, ticket 100 and the cause host-only, with one comment naming the reason"
else
    fail "the host-only screen did not stop the launcher as required (rc=$host_only_rc, comments: $(tr '\n' ' ' < "$STUB_LEDGER_COMMENTS"))"
    tail -5 "$CASE_LOG" >&2
fi
new_case host-only-unanswerable
open_boards
export STUB_HOST_ONLY_UNANSWERABLE_FILE="$CASE_DIR/unanswerable"
: > "$STUB_HOST_ONLY_UNANSWERABLE_FILE"
run_launcher bd-ib-unanswered
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = bd-ib-unanswered ] && log_has "$CASE_LOG" "host-only screen could not answer"; then
    pass "control: a host-only command that cannot answer is not read as host_only false, and the launch proceeds to the Dispatcher's own refusal"
else
    fail "an unanswerable host-only screen stopped the launch (rc=$RC)"
fi

scenario "41. a ticket marked wip-wait=1 by the interim launcher is skipped like a held= ticket"
new_case wip-wait-skipped
open_boards
mkdir -p "$FLEET_LAUNCH_GMK_QUEUE_DIR"
sleep 600 &
legacy_pid=$!
printf 'owner=legacy pid=%s item=bd-ib-legacy\nwip-wait=1\n' "$legacy_pid" > "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-legacy"
ONLY_GMK=1 TICKET_NS=200 run_launcher bd-ib-behind-legacy
kill "$legacy_pid" 2>/dev/null; wait "$legacy_pid" 2>/dev/null
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = bd-ib-behind-legacy ] && [ -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-legacy" ]; then
    pass "a launcher behind a live wip-wait=1 ticket binds and launches; the marked ticket keeps its number"
else
    fail "a wip-wait=1 ticket blocked the launcher behind it (rc=$RC)"
    tail -5 "$CASE_LOG" >&2
fi

scenario "42. the repository WIP count is read once per time-to-live and shared"
new_case wip-shared-cache
export FLEET_LAUNCH_MAX_WAIT_S=120
export FLEET_LAUNCH_WIP_SHARED_TTL_S=600
open_boards
printf '5\n' > "$STUB_WIP_COUNT_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-cache-a > "$CASE_DIR/a.log" 2>&1 &
cache_a=$!
wait_for_line "$CASE_DIR/a.log" "repository WIP at cap: counted=5 cap=5" "$OBSERVE_WAIT_S" || fail "the first launcher did not read the count"
ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-cache-b > "$CASE_DIR/b.log" 2>&1 &
cache_b=$!
wait_for_line "$CASE_DIR/b.log" "repository WIP at cap: counted=5 cap=5" "$OBSERVE_WAIT_S" || fail "the second launcher did not read the count"
sleep 0.3
calls=$(grep -c . "$STUB_WIP_CALLS")
if [ "$calls" = 1 ] && [ "$(cut -d' ' -f2- "$FLEET_LAUNCH_WIP_SHARED_DIR/wip-act.$(basename "$TENANT")" 2>/dev/null)" = "5 5" ]; then
    pass "two launchers polling within one time-to-live computed the count once and shared it through the per-repository file"
else
    fail "the shared WIP count was computed $calls times within one time-to-live"
fi
stop_launcher "$cache_a" "$cache_b"; wait "$cache_a" 2>/dev/null; wait "$cache_b" 2>/dev/null
new_case wip-cache-disabled
open_boards
export FLEET_LAUNCH_WIP_SHARED_TTL_S=0
printf '4\n' > "$STUB_WIP_COUNT_FILE"
run_launcher bd-ib-uncached
if [ "$RC" = 0 ] && [ "$(grep -c . "$STUB_WIP_CALLS")" -ge 1 ] && [ ! -e "$FLEET_LAUNCH_WIP_SHARED_DIR/wip-act.$(basename "$TENANT")" ]; then
    pass "control: a time-to-live of 0 disables the shared file and asks the helper every pass"
else
    fail "a time-to-live of 0 still wrote the shared file or skipped the helper (rc=$RC)"
fi

scenario "43. a resume honours the gmktec hold with its allowlist release, consumed at RESUME, through the resume helper"
new_case resume-allowlist
export FLEET_LAUNCH_MAX_WAIT_S=120
open_boards
: > "$HOLD_FILE"
TICKET_NS=100 "$RESUME_LAUNCHER" bd-ib-resume-held > "$CASE_DIR/held.log" 2>&1 &
resume_held_pid=$!
if wait_for_line "$CASE_DIR/held.log" "hold file present" "$OBSERVE_WAIT_S" && kill -0 "$resume_held_pid" 2>/dev/null && [ ! -s "$RESUME_LOG" ]; then
    pass "a resume whose item is not allowlisted waits on the gmktec hold"
else
    fail "a resume launched through the gmktec hold"
    tail -4 "$CASE_DIR/held.log" >&2
fi
printf 'bd-ib-resume-held\n' > "$FLEET_LAUNCH_FREEZE_ALLOWLIST_FILE"
if wait_gone "$resume_held_pid" "$EXIT_WAIT_S" && wait "$resume_held_pid" && [ "$(cat "$RESUME_LOG")" = bd-ib-resume-held ] \
    && [ ! -s "$FLEET_LAUNCH_FREEZE_ALLOWLIST_FILE" ] && grep -q 'consumed at RESUME' "$FLEET_LAUNCH_FREEZE_ALLOWLIST_CONSUMED_LOG" \
    && grep -q "^$TENANT bd-ib-resume-held$" "$STUB_RESUME_ARGV_LOG"; then
    pass "an allowlisted resume starts through resume-repo.sh in the target repository and its line is consumed at RESUME"
else
    fail "the allowlisted resume did not start as required (resumes: $(tr '\n' ' ' < "$RESUME_LOG"), argv: $(tr '\n' ' ' < "$STUB_RESUME_ARGV_LOG"))"
    tail -6 "$CASE_DIR/held.log" >&2
    stop_launcher "$resume_held_pid"; wait "$resume_held_pid" 2>/dev/null
fi
new_case resume-three-args
open_boards
"$RESUME_LAUNCHER" 300 "$TENANT" bd-ib-three-args > "$CASE_LOG" 2>&1
three_rc=$?
if [ "$three_rc" = 0 ] && [ "$(cat "$RESUME_LOG")" = bd-ib-three-args ] && log_has "$CASE_LOG" "300-harness-seat"; then
    pass "the seat's three-argument form names the ticket number, the repository and the item"
else
    fail "the three-argument resume form did not resume (rc=$three_rc)"
    tail -4 "$CASE_LOG" >&2
fi

scenario "44. the size screen holds an item whose materialized workflow would exceed the cap"
new_case size-screen-hold
open_boards
export FLEET_LAUNCH_SIZE_SCREEN=1
printf '#!/usr/bin/env python3\nimport sys\nprint("HOLD   bd-ib-big  worst=524,900 threshold=520,000")\nsys.exit(3)\n' > "$FLEET_LAUNCH_SIZE_SCREEN_COMMAND"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-big > "$CASE_LOG" 2>&1
size_rc=$?
hold_item="$FLEET_LAUNCH_ITEM_HOLD_DIR/hold-item-bd-ib-big"
if [ "$size_rc" = 4 ] && [ ! -s "$DRIVE_LOG" ] && [ ! -s "$PREFLIGHT_LOG" ] && [ -e "$hold_item" ] \
    && grep -q '^OWNER: ' "$hold_item" && grep -q '^END CONDITION: ' "$hold_item" && grep -q '^NEXT STEP: ' "$hold_item" \
    && grep -qF 'terminal: item=bd-ib-big ticket=100 cause=size-screen verdict=OVER-THRESHOLD rc=3' "$CASE_LOG" \
    && [ "$(grep -c . "$STUB_LEDGER_COMMENTS")" = 1 ]; then
    pass "a HOLD verdict writes hold-item with owner, end condition and next step, runs no preflight and leaves a size-screen terminal line and one comment"
else
    fail "the size screen did not hold the item as required (rc=$size_rc)"
    tail -5 "$CASE_LOG" >&2
fi
new_case size-screen-launch
open_boards
export FLEET_LAUNCH_SIZE_SCREEN=1
printf '#!/usr/bin/env python3\nprint("LAUNCH bd-ib-small worst=100,000 threshold=520,000")\n' > "$FLEET_LAUNCH_SIZE_SCREEN_COMMAND"
run_launcher bd-ib-small
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = bd-ib-small ] && log_has "$CASE_LOG" "size screen LAUNCH"; then
    pass "control: a LAUNCH verdict lets the same launch proceed"
else
    fail "a LAUNCH size verdict did not launch (rc=$RC)"
fi

scenario "45. the slot-narrowing wrapper strips slots INSIDE the target's committed credential_wrapper chain"
# The stub family wrapper projects what the host wrapper projects: a personal App pair, the org pair
# and the slot tokens. Values are stubs; the probe prints which pair the child holds, whether the
# unnumbered token is the judge slot's, and the NAMES of the numbered slots left, never a value.
new_case slotnarrow
cat > "$CASE_DIR/family-wrapper" <<'FAMILY_STUB'
#!/usr/bin/env bash
[ "${1:-}" = -- ] && shift
GITHUB_APP_ID=personal-stub GITHUB_PRIVATE_KEY=personal-key-stub GITHUB_APP_ID_ORG=org-stub GITHUB_PRIVATE_KEY_ORG=org-key-stub \
CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_1=stub-one CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4=stub-four CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_7=stub-seven CLAUDE_CODE_OAUTH_TOKEN=stub-plain \
exec "$@"
FAMILY_STUB
chmod +x "$CASE_DIR/family-wrapper"
mkdir -p "$CASE_DIR/route-c-tenant" "$CASE_DIR/bare-tenant"
printf '{"credential_wrapper": ["%s", "--", "/bin/sh", "-c", "GITHUB_APP_ID=\\"$GITHUB_APP_ID_ORG\\" GITHUB_PRIVATE_KEY=\\"$GITHUB_PRIVATE_KEY_ORG\\" exec \\"$@\\"", "sh"]}\n' "$CASE_DIR/family-wrapper" > "$CASE_DIR/route-c-tenant/.livespec.jsonc"
slot_probe='if [ "$GITHUB_APP_ID" = "$GITHUB_APP_ID_ORG" ] && [ "$GITHUB_PRIVATE_KEY" = "$GITHUB_PRIVATE_KEY_ORG" ]; then printf org-app; else printf personal-app; fi
if [ "${CLAUDE_CODE_OAUTH_TOKEN:-}" = "${CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4:-unset}" ]; then printf " judge=slot4"; else printf " judge=other"; fi
printf " slots=%s" "$(env | sed -n "s/^\(CLAUDE_CODE_OAUTH_TOKEN__[A-Z0-9_]*\)=.*/\1/p" | sort | tr "\n" ",")"'
narrow_in() {
    (cd "$1" && FLEET_LAUNCH_DEFAULT_WRAPPER="$CASE_DIR/family-wrapper" FLEET_LAUNCH_SLOTNARROW_EXCLUDED_SLOTS="ANTHROPIC_1 ANTHROPIC_3" FLEET_LAUNCH_SLOTNARROW_JUDGE_SLOT=ANTHROPIC_4 \
        WRAPPER="$LAUNCH_DIR/wrappers/with-livespec-env-slotnarrow.sh" "$LAUNCH_DIR/wrappers/with-livespec-env-slotnarrow.sh" -- sh -c "$slot_probe")
}
narrowed=$(narrow_in "$CASE_DIR/route-c-tenant")
if [ "$narrowed" = "org-app judge=slot4 slots=CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4,CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_7," ]; then
    pass "a slot-narrowed launch of a route C repository holds the org App pair, the judge slot's unnumbered token, and only the slots not excluded"
else
    fail "the slot-narrowing wrapper did not compose with route C's committed argv: $narrowed"
fi
bare=$(narrow_in "$CASE_DIR/bare-tenant")
if [ "$bare" = "personal-app judge=slot4 slots=CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4,CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_7," ]; then
    pass "control: with no committed argv the same narrowing runs under the bare family wrapper, which holds the personal App pair"
else
    fail "control: the undeclared case did not narrow under the bare family wrapper: $bare"
fi
printf '{"credential_wrapper": ["not", "closed"\n' > "$CASE_DIR/bare-tenant/.livespec.jsonc"
unreadable_rc=0; unreadable_out=$(narrow_in "$CASE_DIR/bare-tenant" 2>&1) || unreadable_rc=$?
rm -f "$CASE_DIR/bare-tenant/.livespec.jsonc"
if [ "$unreadable_rc" = 78 ] && [ -z "${unreadable_out##*cannot be read*}" ]; then
    pass "an unreadable credential_wrapper makes the slot-narrowing wrapper refuse (rc=78) instead of guessing a chain"
else
    fail "an unreadable credential_wrapper did not make the slot-narrowing wrapper refuse (rc=$unreadable_rc): $unreadable_out"
fi

scenario "46. early exits are bounded per window, and a -refused stage is a permanent refusal"
new_case reticket-bound
open_boards
export FLEET_LAUNCH_MAX_WAIT_S=120
export FLEET_LAUNCH_RETICKET_MAX_IN_WINDOW=1
export STUB_DRIVE_FAIL_TIMES=5
export STUB_DRIVE_FAIL_RC=1
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-bounded > "$CASE_LOG" 2>&1
bound_rc=$?
if [ "$bound_rc" = 1 ] && [ "$(drive_log_items)" = "bd-ib-bounded bd-ib-bounded" ] \
    && grep -qF 'cause=reticket-bound early-exits-in-window=2' "$CASE_LOG" && [ "$(grep -c . "$STUB_LEDGER_COMMENTS")" = 1 ]; then
    pass "the second early exit inside the window exceeds a bound of one: no third ticket, a reticket-bound terminal line and one comment"
else
    fail "the re-ticket bound was not applied (rc=$bound_rc, dispatches: $(drive_log_items))"
    tail -6 "$CASE_LOG" >&2
fi
new_case reticket-refused-stage
open_boards
export FLEET_LAUNCH_MAX_WAIT_S=120
export STUB_DRIVE_FAIL_TIMES=5
export STUB_DRIVE_FAIL_RC=1
export STUB_DRIVE_FAIL_STDOUT='{"dispatcher": {"exit_code": 1, "stdout_json": [{"stage": "host-only-refused", "status": "failed", "detail": "needs-host-secrets"}]}}'
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-stage-refused > "$CASE_LOG" 2>&1
stage_rc=$?
if [ "$stage_rc" = 1 ] && [ "$(drive_log_items)" = bd-ib-stage-refused ] \
    && grep -qF 'terminal: item=bd-ib-stage-refused ticket=100 cause=refused' "$CASE_LOG" && [ "$(grep -c . "$STUB_LEDGER_COMMENTS")" = 1 ]; then
    pass "a stage ending in -refused is a permanent refusal: one drive, a refused terminal line, one comment, no re-ticket"
else
    fail "a -refused stage was re-ticketed (rc=$stage_rc, dispatches: $(drive_log_items))"
    tail -6 "$CASE_LOG" >&2
fi

scenario "47. the homelab wrapper argv names the committed homelab credential wrapper, never a parameter value"
if [ "$(sed -n 1p "$LAUNCH_DIR/wrappers/homelab-wrapper.argv")" = "/home/ubuntu/workspace/homelab/with-homelab-credentials.sh" ] \
    && [ "$(sed -n 2p "$LAUNCH_DIR/wrappers/homelab-wrapper.argv")" = "--" ] && [ "$(grep -c . "$LAUNCH_DIR/wrappers/homelab-wrapper.argv")" = 2 ]; then
    pass "homelab-wrapper.argv is the homelab repository's committed credential wrapper followed by --"
else
    fail "homelab-wrapper.argv does not carry the homelab credential wrapper route"
fi

scenario "48. a committed family-wrapper argv reaches the command intact: the child holds the org App pair"
# Value-free: the stub family wrapper projects a personal App id and an org pair, exactly as the
# host wrapper does, and the probe prints only WHICH pair the child holds, never a value. The
# 2026-11-15 defect printed personal-app here, because the argv was dropped on argv[0]'s basename.
new_case committed-argv-intact
cat > "$CASE_DIR/family-wrapper" <<'FAMILY_STUB'
#!/usr/bin/env bash
[ "${1:-}" = -- ] && shift
GITHUB_APP_ID=personal-stub GITHUB_PRIVATE_KEY=personal-key-stub GITHUB_APP_ID_ORG=org-stub GITHUB_PRIVATE_KEY_ORG=org-key-stub exec "$@"
FAMILY_STUB
chmod +x "$CASE_DIR/family-wrapper"
mkdir -p "$CASE_DIR/route-c-tenant" "$CASE_DIR/bare-tenant"
printf '{"credential_wrapper": ["%s", "--", "/bin/sh", "-c", "GITHUB_APP_ID=\\"$GITHUB_APP_ID_ORG\\" GITHUB_PRIVATE_KEY=\\"$GITHUB_PRIVATE_KEY_ORG\\" exec \\"$@\\"", "sh"]}\n' "$CASE_DIR/family-wrapper" > "$CASE_DIR/route-c-tenant/.livespec.jsonc"
which_app='if [ "$GITHUB_APP_ID" = "$GITHUB_APP_ID_ORG" ] && [ "$GITHUB_PRIVATE_KEY" = "$GITHUB_PRIVATE_KEY_ORG" ]; then echo org-app; else echo personal-app; fi'
resolve_and_probe() {
    REPO="$1" FLEET_LAUNCH_DEFAULT_WRAPPER="$CASE_DIR/family-wrapper" WRAPPER='' bash -c '
        set -u
        . "$1/config.sh"
        . "$1/launch-lib.sh"
        resolve_tenant_wrapper || { echo "mode=$TENANT_WRAPPER_MODE"; exit 1; }
        printf "mode=%s words=%s " "$TENANT_WRAPPER_MODE" "${#TENANT_WRAPPER[@]}"
        wrap -- sh -c "$2"' probe "$LAUNCH_DIR" "$which_app"
}
routed=$(resolve_and_probe "$CASE_DIR/route-c-tenant")
if [ "$routed" = "mode=committed words=6 org-app" ]; then
    pass "under route C's committed argv the launch-time command holds the org App pair: the argv was honoured whole"
else
    fail "the committed family-wrapper argv did not reach the command intact: $routed"
fi
bare=$(resolve_and_probe "$CASE_DIR/bare-tenant")
if [ "$bare" = "mode=default words=0 personal-app" ]; then
    pass "control: a target declaring no credential_wrapper runs under the bare family wrapper and holds the personal App pair"
else
    fail "control: the undeclared case did not run under the bare family wrapper: $bare"
fi

fi

if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = gate-detach ]; then
echo "--- 49. a launcher started under the gate runner detaches itself out of the runner's stall cap, and only then"
# just gate-start ends the gate's whole process group after 900 s without output (dev-tooling/gate-run.sh),
# which kills a launcher and its drive while the factory run goes on. The runner exports
# LIVESPEC_GATE_RUN_PROGRESS_STAMP into everything it runs; that is the marker the launcher reads.
pid_live() { local state; state=$(sed 's/^.*) //' "/proc/$1/stat" 2>/dev/null | cut -c1); [ -n "$state" ] && [ "$state" != Z ]; }
wait_pid_gone() { local waited=0; while pid_live "$1" && [ "$waited" -lt 600 ]; do sleep 0.1; waited=$((waited + 1)); done; }
detached_pid_of() { printf '%s\n' "$1" | sed -n 's/.*detached pid \([0-9][0-9]*\).*/\1/p'; }
detached_log_of() { printf '%s\n' "$1" | sed -n 's/.*log file \(.*\)$/\1/p'; }

new_case gate-detach-dispatch
open_boards
export FLEET_LAUNCH_MAX_WAIT_S=120
parent_out=$(LIVESPEC_GATE_RUN_PROGRESS_STAMP="$CASE_DIR/progress-stamp" ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-gatedetach 2>&1)
parent_rc=$?
detached_pid=$(detached_pid_of "$parent_out")
detached_log=$(detached_log_of "$parent_out")
[ -n "$detached_pid" ] && wait_pid_gone "$detached_pid"
if [ "$parent_rc" = 0 ] && [ -n "$detached_pid" ] && [ -f "$detached_log" ] \
    && grep -qF "detached launcher: pid=$detached_pid session=$detached_pid" "$detached_log" \
    && grep -qF "gate-stamp=absent" "$detached_log" \
    && [ "$(drive_log_items)" = "bd-ib-gatedetach" ]; then
    pass "dispatch-dual.sh under the gate runner returns 0 naming a detached pid and log; the child leads its own session, has no gate stamp, and dispatched the item once"
else
    fail "dispatch-dual.sh under the gate runner did not detach cleanly (rc=$parent_rc, pid='$detached_pid', log='$detached_log', dispatches: $(drive_log_items))"
    printf '%s\n' "$parent_out" | tail -5 >&2
    [ -f "$detached_log" ] && tail -8 "$detached_log" >&2
fi

new_case gate-detach-resume
open_boards
export FLEET_LAUNCH_MAX_WAIT_S=120
parent_out=$(LIVESPEC_GATE_RUN_PROGRESS_STAMP="$CASE_DIR/progress-stamp" ONLY_GMK=1 TICKET_NS=100 "$RESUME_LAUNCHER" bd-ib-gatedetach-resume 2>&1)
parent_rc=$?
detached_pid=$(detached_pid_of "$parent_out")
detached_log=$(detached_log_of "$parent_out")
[ -n "$detached_pid" ] && wait_pid_gone "$detached_pid"
if [ "$parent_rc" = 0 ] && [ -n "$detached_pid" ] && [ -f "$detached_log" ] \
    && grep -qF "detached launcher: pid=$detached_pid session=$detached_pid" "$detached_log" \
    && grep -qF "gate-stamp=absent" "$detached_log"; then
    pass "resume-capped.sh under the gate runner detaches the same way: returns 0, the child leads its own session and has no gate stamp"
else
    fail "resume-capped.sh under the gate runner did not detach cleanly (rc=$parent_rc, pid='$detached_pid', log='$detached_log')"
    printf '%s\n' "$parent_out" | tail -5 >&2
    [ -f "$detached_log" ] && tail -8 "$detached_log" >&2
fi

new_case gate-detach-optout
open_boards
export FLEET_LAUNCH_MAX_WAIT_S=120
parent_out=$(LIVESPEC_GATE_RUN_PROGRESS_STAMP="$CASE_DIR/progress-stamp" FLEET_LAUNCH_ALLOW_UNDER_GATE=1 ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-gateoptout 2>&1)
parent_rc=$?
if [ "$parent_rc" = 0 ] && [ -z "$(detached_pid_of "$parent_out")" ] && [ "$(drive_log_items)" = "bd-ib-gateoptout" ]; then
    pass "control: FLEET_LAUNCH_ALLOW_UNDER_GATE=1 under the gate runner runs in place and dispatches without detaching"
else
    fail "control: the opt-out detached or did not dispatch (rc=$parent_rc, dispatches: $(drive_log_items))"
fi

new_case gate-detach-plain
open_boards
export FLEET_LAUNCH_MAX_WAIT_S=120
parent_out=$(ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-gateplain 2>&1)
parent_rc=$?
if [ "$parent_rc" = 0 ] && [ -z "$(detached_pid_of "$parent_out")" ] && [ "$(drive_log_items)" = "bd-ib-gateplain" ]; then
    pass "control: with no gate stamp the launcher runs in place exactly as before and dispatches"
else
    fail "control: a launcher with no gate stamp detached or did not dispatch (rc=$parent_rc, dispatches: $(drive_log_items))"
fi
fi

if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = probe-stderr ]; then

new_case probe-stderr
open_boards
export FLEET_LAUNCH_MAX_WAIT_S=120
refusal="credential_wrapper could not run in this environment (required secret env var(s) ['BEADS_DOLT_PASSWORD', 'GITHUB_APP_ID'])"
parent_out=$(STUB_CRED_REFUSAL="$refusal" ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-probestderr 2>&1)
parent_rc=$?
probe_held=no
case $parent_out in
    *"credential probe NOT usable (rc=3)"*"required secret env var(s) ['BEADS_DOLT_PASSWORD', 'GITHUB_APP_ID']"*) probe_held=yes ;;
esac
if [ "$parent_rc" = 75 ] && [ "$probe_held" = yes ] && [ -z "$(drive_log_items)" ]; then
    pass "a credential probe refused by the wrapper holds the launch (exit 75) and the launcher log carries the refusal text naming the missing variables"
else
    fail "the probe refusal was swallowed or the launch was not held (rc=$parent_rc): $(printf '%s' "$parent_out" | tail -5)"
fi

new_case probe-stderr-control
open_boards
export FLEET_LAUNCH_MAX_WAIT_S=120
parent_out=$(ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-probeok 2>&1)
parent_rc=$?
if [ "$parent_rc" = 0 ] && [ "$(drive_log_items)" = "bd-ib-probeok" ]; then
    pass "control: a usable credential probe still launches and dispatches"
else
    fail "control: a usable probe did not dispatch (rc=$parent_rc, dispatches: $(drive_log_items))"
fi
fi

echo
echo "=== fleet-launch hermetic harness: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
