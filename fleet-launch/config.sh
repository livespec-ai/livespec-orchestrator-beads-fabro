# shellcheck shell=bash
# PROVISIONAL / EXPERIMENTAL — fleet-launch host configuration.
#
# The ONE place a fleet-launch script reads a host-specific value. Every script in
# fleet-launch/ sources this file and never writes a host value inline. This
# directory is a stopgap; its first-class replacements are the livespec console
# application and the committed launch-loop tool bd-ib-jr6w7v (see README.md).
#
# Each value can be overridden from the environment, which is how the hermetic
# harness points the scripts at stub boards and throwaway directories.

# The orchestrator plugin registry and cache, used to resolve the installed build.
: "${FLEET_LAUNCH_PLUGIN_REGISTRY:=/home/ubuntu/.claude/plugins/installed_plugins.json}"
: "${FLEET_LAUNCH_PLUGIN_CACHE:=/home/ubuntu/.claude/plugins/cache/livespec-orchestrator-beads-fabro/livespec-orchestrator-beads-fabro}"
: "${FLEET_LAUNCH_PLUGIN_KEY:=livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro}"

# Repository and seat identity. A launcher invoked without an explicit repository is the checkout
# that holds this file, so its holds, caps and canary-hold-exempt marker are read from that checkout
# (bd-ib-ctunsl: taking the registry's FIRST projectPath named another repository's state directory
# and silently failed every hold open). Only a copy of config.sh that is not inside a git checkout,
# such as an installed build, follows its install record; if that cannot be read, it uses its own tree.
if [ -z "${FLEET_LAUNCH_ORCH_REPO:-}" ]; then
  FLEET_LAUNCH_ORCH_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
  if [ ! -e "$FLEET_LAUNCH_ORCH_REPO/.git" ]; then
    FLEET_LAUNCH_ORCH_RECORD=$(python3 - "$FLEET_LAUNCH_PLUGIN_REGISTRY" "$FLEET_LAUNCH_PLUGIN_KEY" <<'PY' 2>/dev/null
import json
import sys

try:
    entries = json.load(open(sys.argv[1], encoding="utf-8"))["plugins"][sys.argv[2]]
    paths = [entry.get("projectPath") for entry in entries if isinstance(entry.get("projectPath"), str)]
except (OSError, ValueError, KeyError, TypeError):
    paths = []
print(paths[0] if paths else "")
PY
)
    [ -z "$FLEET_LAUNCH_ORCH_RECORD" ] || FLEET_LAUNCH_ORCH_REPO=$FLEET_LAUNCH_ORCH_RECORD
    unset FLEET_LAUNCH_ORCH_RECORD
  fi
fi
: "${FLEET_LAUNCH_SEAT:=petri-factory-on-gmktec}"

# Seat load guard (fleet-launch/seat/load-guard.sh): the percentage of the mounted /tmp tmpfs used at or
# above which the guard answers HOLD. It is a fraction of the size `df` reports at run time, so it holds
# for every host (a 48G tmpfs and a 24G one bind at the same share); a fixed GB limit sized for one host
# held every launch on a smaller one. A value in the environment wins.
: "${LDSEAT_TMP_HOLD_PCT:=80}"
export LDSEAT_TMP_HOLD_PCT

# Data directory: logs, verdicts, the shared fleet-cap file and the hold file.
# It holds data only, never a script.
: "${FLEET_LAUNCH_STATE_DIR:=$FLEET_LAUNCH_ORCH_REPO/tmp/petri-canary}"
: "${FLEET_LAUNCH_FLEET_CAP_FILE:=$FLEET_LAUNCH_STATE_DIR/fleet-cap}"
: "${FLEET_LAUNCH_HOLD_FILE:=$FLEET_LAUNCH_STATE_DIR/hold-gmktec}"
# A repository hold is hold-repo-<target-checkout-basename> in this directory.
# It scopes a red repository to its own launches without stopping other tenants.
: "${FLEET_LAUNCH_REPO_HOLD_DIR:=$FLEET_LAUNCH_STATE_DIR}"
# The committed breakage-exception list: one work-item id per line. The repository WIP gate treats the
# cap as one above the repository's wip_cap for a listed item, and for no other.
: "${FLEET_LAUNCH_BREAKAGE_EXCEPTION_FILE:=$FLEET_LAUNCH_ORCH_REPO/fleet-launch/breakage-exception}"
# The gmktec target setting: a one-word file. `candidate` sends a gmktec launch to the candidate
# instance; an absent file, or any other word, selects the default instance.
: "${FLEET_LAUNCH_GMK_TARGET_FILE:=$FLEET_LAUNCH_STATE_DIR/gmk-target}"
# Where an item's consecutive early-exit count survives a launcher restart.
: "${FLEET_LAUNCH_RETICKET_STATE_DIR:=$FLEET_LAUNCH_STATE_DIR/reticket-state}"
# A launcher stops re-taking a ticket for one item after this many early exits inside the window.
: "${FLEET_LAUNCH_RETICKET_MAX_IN_WINDOW:=6}"
: "${FLEET_LAUNCH_RETICKET_WINDOW_S:=10800}"
# The freeze allowlist releases a listed item from the gmktec hold exactly once: the launcher
# consumes the item's line at LAUNCH (or at RESUME) under the shared lock and logs the grant.
: "${FLEET_LAUNCH_FREEZE_ALLOWLIST_FILE:=$FLEET_LAUNCH_STATE_DIR/freeze-allowlist}"
: "${FLEET_LAUNCH_FREEZE_ALLOWLIST_LOCK:=$FLEET_LAUNCH_STATE_DIR/freeze-allowlist.lock}"
: "${FLEET_LAUNCH_FREEZE_ALLOWLIST_CONSUMED_LOG:=$FLEET_LAUNCH_STATE_DIR/freeze-allowlist.consumed}"
# A canary repository hold is canary-hold-repo-<target-checkout-basename> in this directory; the
# exemption list holds one work-item id per line and releases a launch from that hold only.
: "${FLEET_LAUNCH_CANARY_HOLD_DIR:=$FLEET_LAUNCH_STATE_DIR}"
: "${FLEET_LAUNCH_CANARY_EXEMPT_FILE:=$FLEET_LAUNCH_STATE_DIR/canary-hold-exempt}"
# Per-item holds the launcher's own size screen writes (hold-item-<item>); the seat reads them
# before it tickets an item. The launcher itself never gates on one.
: "${FLEET_LAUNCH_ITEM_HOLD_DIR:=$FLEET_LAUNCH_STATE_DIR}"
# The ACP overrides file: one --acp-node argument per non-empty, non-comment line, passed to
# every drive. An absent or empty file adds none, so the committed routing governs.
: "${FLEET_LAUNCH_ACP_OVERRIDES_FILE:=$FLEET_LAUNCH_STATE_DIR/acp-overrides.txt}"
# The judge-model environment: each non-empty value is exported into every preflight and drive
# the launcher starts; an empty one is not. A pass-through only; it carries no model-selection
# authority. These three take the default only when UNSET, so an operator can empty one from the
# environment.
: "${FLEET_LAUNCH_DOD_JUDGEMENT_MODEL=claude-haiku-5-5}"
: "${FLEET_LAUNCH_DRIFT_JUDGE_MODEL=claude-sonnet-5-5}"
: "${FLEET_LAUNCH_REFLECTOR_MODEL=claude-haiku-5-5}"

# Factory servers. hp-xubuntu and vps are retired as factories and are never read.
: "${FLEET_LAUNCH_GMK_SERVER:=https://gmktec-xubuntu.perch-rudd.ts.net:32276}"
: "${FLEET_LAUNCH_GMK_CANDIDATE_SERVER:=https://gmktec-xubuntu.perch-rudd.ts.net:32278}"
: "${FLEET_LAUNCH_HL_SERVER:=https://gmktec-xubuntu.perch-rudd.ts.net:32277}"
: "${FLEET_LAUNCH_GMK_SSH:=cwoolley@gmktec-xubuntu}"
: "${FLEET_LAUNCH_GMK_SERVER_ENV:=/home/cwoolley/.fabro/storage/server.env}"
: "${FLEET_LAUNCH_GMK_CANDIDATE_SERVER_ENV:=/home/cwoolley/.fabro-candidate/storage/server.env}"
# The homelab-worker-arm64 instance (gmktec :32279) runs on the M4 worker's own pod budget: its
# runs are OUTSIDE the shared fleet sum and are capped by FLEET_LAUNCH_ARM_CAP alone. Its board is
# read only while the enrolment marker exists; from then on an unreadable board fails closed.
: "${FLEET_LAUNCH_ARM_SERVER:=https://gmktec-xubuntu.perch-rudd.ts.net:32279}"
: "${FLEET_LAUNCH_ARM_ENROLLED_FILE:=$FLEET_LAUNCH_STATE_DIR/arm64-enrolled}"
: "${FLEET_LAUNCH_ARM_CAP:=1}"
# Per-factory ceilings. Each is read live, on every gate pass, from a one-number state file so the
# seat can raise a cap without restarting launchers; the constant is the fallback when that file is
# absent or unreadable (the candidate cap falls back to 0, which never launches onto the candidate).
: "${FLEET_LAUNCH_GMK_CAP_FILE:=$FLEET_LAUNCH_STATE_DIR/gmk-cap}"
: "${FLEET_LAUNCH_GMK_CAP:=8}"
: "${FLEET_LAUNCH_GMK_CANDIDATE_CAP_FILE:=$FLEET_LAUNCH_STATE_DIR/candidate-cap}"
: "${FLEET_LAUNCH_GMK_CANDIDATE_CAP:=0}"
: "${FLEET_LAUNCH_HL_CAP_FILE:=$FLEET_LAUNCH_STATE_DIR/hl-cap}"
: "${FLEET_LAUNCH_HL_CAP:=2}"
# Minimum gmktec idle CPU percentage before a gmktec launch, read live from a state file with the
# constant as fallback. A reading that cannot be taken holds the launch.
: "${FLEET_LAUNCH_GMK_IDLE_FLOOR_FILE:=$FLEET_LAUNCH_STATE_DIR/gmk-idle-floor}"
: "${FLEET_LAUNCH_GMK_MIN_IDLE:=3}"

# The Fabro client the launcher polls its own run's listing with: the build gmktec serves,
# bbe693847 (bd-ib-xoh477). Keep it equal to dispatcher.factories.petri.bin.
: "${FLEET_LAUNCH_FABRO:=/home/ubuntu/.local/state/fabro-web-prod/v0393-bbe693847/fabro}"
# The Fabro client every fleet board read uses (the snapshot refresh and the binding count):
# plain `ps` on c39bdbded costs the petri server 1.3-5.5 s against 16-46 s on the launch client
# (fabro-currency, 2026-11-04).
: "${FLEET_LAUNCH_FABRO_BOARD:=/home/ubuntu/.local/state/fabro-web-prod/v0393-c39bdbded/fabro}"
# A failed board listing is retried this many times, FLEET_LAUNCH_BOARD_RETRY_S times the attempt
# number apart, before the board reads as unknown; the client's own timeout is never raised.
: "${FLEET_LAUNCH_BOARD_RETRIES:=2}"
: "${FLEET_LAUNCH_BOARD_RETRY_S:=10}"

# The shared factory-board snapshot (board-snapshot.sh). Every launcher on the host reads a factory's
# board through one snapshot file per factory, so the factory server receives at most one run listing
# per FLEET_LAUNCH_BOARD_TTL_S from them however many launchers are queued. 0 turns the sharing off.
# A launcher waits at most FLEET_LAUNCH_BOARD_REFRESH_WAIT_S for another launcher's refresh to finish
# (one listing costs the petri server 25-40 s) before it reads the board as unknown.
: "${FLEET_LAUNCH_BOARD_SNAPSHOT_DIR:=/run/user/1000/fleet-board-snapshot.d}"
: "${FLEET_LAUNCH_BOARD_TTL_S:=60}"
: "${FLEET_LAUNCH_BOARD_REFRESH_WAIT_S:=180}"

# Cross-seat coordination directories (shared by every seat on this host).
: "${FLEET_LAUNCH_INFLIGHT_DIR:=/run/user/1000/fleet-inflight.d}"
: "${FLEET_LAUNCH_GMK_QUEUE_DIR:=/run/user/1000/gmktec-launch-queue.d}"
: "${FLEET_LAUNCH_GMK_LOCK_DIR:=/run/user/1000/gmktec-launch-lock.d}"
# A ticket is published by rename, but a reader also tolerates a just-created
# unreadable ticket for this long before treating it as a stalled launcher.
: "${FLEET_LAUNCH_EMPTY_TICKET_GRACE_S:=5}"
# One launcher per queued item: a launcher claims its item here (a symlink named for the item whose
# target is the owning pid), so a whole-queue re-sort never starts a second launcher for a queued item.
: "${FLEET_LAUNCH_GMK_CLAIM_DIR:=${FLEET_LAUNCH_GMK_QUEUE_DIR}.claims}"
# Queue position. A ticket's rank comes from a mechanical walk of the item's parent chain to the
# owning plan and that plan's rank in the latest priorities record, read at ticket time. The record
# is a data file the seat refreshes from the coordinator's latest priorities-record: one
# "<rank> <plan-id>" line per ranked plan, rank 1 first. With no readable record, tickets are ordered
# by arrival. The parent command prints the parent id of the item it is given (nothing for a root);
# it runs in the tenant repository under its credential wrapper.
: "${FLEET_LAUNCH_PRIORITIES_RECORD:=$FLEET_LAUNCH_STATE_DIR/priorities-record}"
: "${FLEET_LAUNCH_PARENT_CHAIN_COMMAND:=${FLEET_LAUNCH_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}/parent-of.sh}"

# Credential wrappers. The default is the family wrapper; independent tenants
# pass WRAPPER=<fleet-launch/wrappers/...> per launch.
: "${FLEET_LAUNCH_DEFAULT_WRAPPER:=/usr/local/bin/with-livespec-env.sh}"
: "${FLEET_LAUNCH_DOLT_SERVER_WRAPPER:=/usr/local/bin/with-dolt-server-env.sh}"
: "${FLEET_LAUNCH_OPENBRAIN_WRAPPER:=$HOME/workspace/1password-env-wrapper/with-openbrain-env.sh}"
: "${FLEET_LAUNCH_RESUME_WRAPPER:=$HOME/workspace/resume/with-resume-env.sh}"
# The resume helper (resume-repo.sh) names this factory and this invoker on every
# `dispatcher.py resume` it starts; the impl launcher's drive invoker is the seat.
: "${FLEET_LAUNCH_RESUME_FACTORY:=petri}"
: "${FLEET_LAUNCH_RESUME_INVOKER:=claude:legacy-dispatcher-agent}"
# wrappers/with-livespec-env-slotnarrow.sh removes these numbered Claude credential slots from
# the environment a family-tenant launch runs under, and points the unnumbered token at the judge
# slot so host-side judges keep a credential. Slot NAMES only; no value is ever read here.
: "${FLEET_LAUNCH_SLOTNARROW_EXCLUDED_SLOTS:=ANTHROPIC_0 ANTHROPIC_1 ANTHROPIC_3 ANTHROPIC_2 ANTHROPIC_5 ANTHROPIC_6}"
: "${FLEET_LAUNCH_SLOTNARROW_JUDGE_SLOT:=ANTHROPIC_4}"
: "${FLEET_LAUNCH_HOMELAB_AWS_WRAPPER:=/usr/local/bin/with-homelab-aws.sh}"
: "${FLEET_LAUNCH_HL_CLI:=/home/ubuntu/.nix-profile/bin/hl}"

# Timing.
: "${FLEET_LAUNCH_MAX_WAIT_S:=86400}"
: "${FLEET_LAUNCH_ABANDON_S:=1200}"
: "${FLEET_LAUNCH_POLL_S:=30}"
: "${FLEET_LAUNCH_PREFLIGHT_REUSE_S:=600}"
# A queued launcher preflights while it waits only when its FIFO rank is within this many of the head.
: "${FLEET_LAUNCH_PREFLIGHT_AHEAD_MAX:=10}"
# A launcher that is not at the FIFO head re-checks only its position, woken by a change to the
# queue directory or after this bound; a launcher yielding on the repository WIP gate re-reads the
# count this often.
: "${FLEET_LAUNCH_QUEUE_WAIT_S:=120}"
: "${FLEET_LAUNCH_WIP_POLL_S:=120}"
# The repository WIP claim count. The launcher reads the shared per-repository result file
# (wip-act.<repo>: "<epoch> <counted-claims> <wip_cap>") before it spawns anything, and refreshes
# it through wip-claimed-count.py once per FLEET_LAUNCH_WIP_SHARED_TTL_S per repository under a
# lock; that helper keeps its own per-repository JSON cache for FLEET_LAUNCH_WIP_CACHE_TTL_S.
# A time-to-live of 0 disables the cache it governs.
: "${FLEET_LAUNCH_WIP_SHARED_DIR:=$FLEET_LAUNCH_STATE_DIR}"
: "${FLEET_LAUNCH_WIP_SHARED_TTL_S:=60}"
: "${FLEET_LAUNCH_WIP_CACHE_DIR:=$FLEET_LAUNCH_STATE_DIR}"
: "${FLEET_LAUNCH_WIP_CACHE_TTL_S:=25}"
# The INTERIM pre-launch size screen of the materialized workflow.toml (Fabro's per-file cap is
# 524,288 B). 1 runs the named screen script (exit 0 LAUNCH, 3 HOLD, anything else ERROR) before every
# launch-time preflight and holds the item (hold-item-<item>) on HOLD or ERROR; 0 skips the screen.
# The screen script itself is not committed (see README.md): the seat names its copy here.
: "${FLEET_LAUNCH_SIZE_SCREEN:=0}"
: "${FLEET_LAUNCH_SIZE_SCREEN_COMMAND:=$FLEET_LAUNCH_STATE_DIR/wfsize-screen.py}"
: "${FLEET_LAUNCH_SIZE_SCREEN_THRESHOLD:=520000}"
# How many times a launcher runs the ready-set check, one poll apart, before it gives up on a
# refusal. A refusal that clears on its own (a blocker that has just closed, a ledger read that
# lagged) keeps the launcher's ticket; one that persists ends with a terminal line and a ledger comment.
: "${FLEET_LAUNCH_READY_RETRY_POLLS:=5}"
: "${FLEET_LAUNCH_MUTEX_HOLD_S:=900}"
# Seconds a launcher waits before it re-takes its ticket after its drive exited before the run listed:
# after the first, the second, and the third and each later consecutive early exit of one item.
: "${FLEET_LAUNCH_RETICKET_DELAY_1_S:=0}"
: "${FLEET_LAUNCH_RETICKET_DELAY_2_S:=300}"
: "${FLEET_LAUNCH_RETICKET_DELAY_3_S:=600}"
# The two fixed poll intervals below are waits on an observed state (a free
# mutex, a listed run); the hermetic harness shortens them so each of its cases
# advances on that state instead of sitting out a production-sized interval.
: "${FLEET_LAUNCH_MUTEX_POLL_S:=10}"
: "${FLEET_LAUNCH_LISTING_POLL_S:=15}"
# How long an impl launcher waits for a drive it stopped for a hold to exit after TERM before it
# sends KILL.
: "${FLEET_LAUNCH_STOP_GRACE_S:=30}"
# How long a resume launcher keeps its in-flight marker counted after the resume
# client has exited, while it waits for the run to list on the factory board.
: "${FLEET_LAUNCH_LISTING_WAIT_S:=600}"
