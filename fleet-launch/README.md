# `fleet-launch/` — PROVISIONAL and EXPERIMENTAL fleet launch scripts (stopgap)

**This directory is a provisional, experimental stopgap.** It captures a dispatch
pattern that emerged during one plan, petri-factory-on-gmktec (epic `bd-ib-fyozyd`),
so that the scripts the factory seats run are committed, reviewed and tested instead
of living uncommitted under `tmp/`. It is not the design the fleet should keep.

**The preferred means is first-class, not this directory.** Fleet launch should be
driven through the livespec console application, whose track is on hold, or through a
committed, tested launch-loop tool: work-item `bd-ib-jr6w7v`. This directory points at
both. New capability belongs there, not here.

**Retirement condition.** Delete this directory once every factory launch on the
operator host is made by the console application or by the `bd-ib-jr6w7v` launch-loop
tool, and no seat runs a script from here. The plan that committed it is
provisional-fleet-launch (epic `bd-ib-klkbxp`).

## Why it is caller-side, and the Dispatcher is untouched

`SPECIFICATION/contracts.md` §"Host concurrency belongs to the Fabro scheduler" (spec
v053) gives the Dispatcher no host-level concurrency limit, admission gauge or lock;
`wip_cap` is its only concurrency control. The admission section (§"Dispatcher
admission, WIP cap, and post-merge acceptance") lets a caller add gates of its own for
conditions the Dispatcher does not own: host capacity, a launch slot the caller
schedules, and launch spacing. Everything here is such a caller-side gate. These
scripts decide only WHEN to invoke `drive --action impl:<item>`; they never stand in
for the Dispatcher's own admission conditions.

## What is here

| File | What it does |
| --- | --- |
| `config.sh` | The one place a host-specific value is set: factory server URLs, the fabro client path, the fleet-cap and hold files, the queue, lock and in-flight directories, the plugin registry and cache, the wrappers and the timings. Every value can be overridden from the environment. |
| `board-snapshot.sh` | The shared factory-board reader both launchers source. Every launcher on the host reads a factory's board through one snapshot file refreshed at most once per `FLEET_LAUNCH_BOARD_TTL_S`, because one run listing costs the petri server 25-40 s; an unreadable refresh is an unknown count, never zero, and the binding count under the launch mutex reads the factory directly. |
| `launch-lib.sh` | The functions both launchers and the resume helper share: the tenant credential wrapper (the target repository's committed `credential_wrapper`, always run as written whole; a non-family one is nested inside the default wrapper with the family `BEADS_DOLT_PASSWORD` removed, and one that starts with the default wrapper path runs as declared, so route C's org-App hop is kept), the installed-build lookup, caps read live from state files, the gmktec hold with its freeze-allowlist and priority-1 releases and the one-shot consume, the canary repository hold, and the FIFO queue scan (class `server=hl` tickets, `held=` and `wip-wait=1` yields, and the held-head skip). |
| `dispatch-dual.sh` | Launches one work-item. Gates, in order: the Dispatcher's ready set (a bounded number of retries), the host-only screen (the Dispatcher's own `host-only` command), the repository hold file and the canary repository hold (with its exemption list), the repository WIP gate (counted claims plus this repository's not-yet-active in-flight launches against `wip_cap`, one above for an item in `breakage-exception`; an unreadable count never holds; the count is shared per repository and read before any process is spawned), the per-factory FIFO (a launcher behind the head re-checks only its place and preflights while queued, within `FLEET_LAUNCH_PREFLIGHT_AHEAD_MAX` of the head), the shared fleet cap (the gmktec, candidate and mi-homelab boards plus launches not yet listed; the arm64 lane is outside the sum), the gmktec hold (released for an allowlisted item, whose line is consumed at LAUNCH, and for a priority-1 item), a fast-forward of the checkout to origin's default branch, the size screen of the materialized workflow and then the launch-time Definition-of-Done preflight under the judge-model environment, the target's own ceiling and gmktec idle CPU (the gmktec target setting selects the default or candidate instance; `ONLY_HL=1` and `ONLY_ARM=1` select the mi-homelab and arm64 instances), the mutex, the launch-point re-read of every hold, a binding re-count including this launch's in-flight marker, a second checkout fast-forward and a usable-credential probe, and the configured ACP overrides on the drive. A drive that exits before its run lists re-takes a ticket at the same ticket number after the delay its consecutive early-exit count selects, except a failed `goal-minijinja-preflight` stage or an exit `5`, which end the launcher with a terminal line and one ledger comment. After it invokes the drive it re-reads every applicable hold on each poll until the item reads `active`, the run lists or the drive exits; a hold set while the item still reads `ready` stops the drive with TERM, keeps the FIFO ticket at its number and logs the hold, and a stop that finds the item `active` makes a `stopped-after-admission` non-run exit with one ledger comment (Scenario 330). |
| `ledger-item.py` | Reads a work-item's ledger status or priority, or appends one ledger comment to it, through the installed plugin build's own store seam; the launcher uses it to tell `ready` from `active` after a stop and to read the priority-1 release once. |
| `wip-claimed-count.py` | The repository WIP claim count the WIP gate compares against `wip_cap`: the installed build's own `claimed_active_projection` plus this repository's in-flight launches not yet active, computed once per `FLEET_LAUNCH_WIP_CACHE_TTL_S` per repository under a lock into a JSON cache beside a `.statuses` sidecar the launcher reads without Python. |
| `resume-capped.sh` | Launches one `resume --item`. It takes a FIFO ticket (the seat's `<ticket> <repo> <item>` form is accepted), yields on the repository and canary holds, honours the gmktec hold with the same allowlist and priority-1 releases (consuming the allowlist line at RESUME), binds under the mutex at the fleet cap and starts the resume through `resume-repo.sh`. |
| `resume-repo.sh` | Starts `dispatcher.py resume --repo <repo> --item <item>` on the repository's installed build, under its committed credential wrapper, with the target factory's dev token exported. |
| `launcher-versions.sh` | Read-only readback: lists every running `dispatch-dual*.sh` and `resume-capped*.sh` launcher with the version (first 12 hex digits of the sha256) of the script content it is executing, read from bash's open file descriptor, and the version of the script file on disk, and marks each launcher whose two differ `STALE`. |
| `ready-set-check.py` | Asks the installed plugin build's own `ready_items()` whether an item is dispatchable, so the answer cannot diverge from the Dispatcher's selection. |
| `release-hold-on-caam-rotation.sh` | Keeps the hold file in place until caam's active Claude profile changes, then removes it. |
| `resolve-default-factory.sh` | Prints a repository's committed `dispatcher.default_factory` from its origin default branch. |
| `host-capture-payload.py` | Builds a `host_recorded` Proof-of-Done payload from a registry-resolved capture dispatch; refuses, writing nothing, when any evidence is missing. |
| `wrappers/` | PATH-keeping shims around each independent tenant's committed credential wrapper, passed as `WRAPPER=` to `dispatch-dual.sh` when the default (the target's own `credential_wrapper`) is not wanted. `homelab-wrapper.argv` is the homelab repository's committed credential wrapper route. `with-livespec-env-slotnarrow.sh` narrows a family launch's Claude credential pool to the slots the seat allows (slot names only; `FLEET_LAUNCH_SLOTNARROW_EXCLUDED_SLOTS` and `FLEET_LAUNCH_SLOTNARROW_JUDGE_SLOT`), resolving the target repository's committed `credential_wrapper` chain exactly as an un-overridden launch does and stripping the slots as the innermost hop of that chain, so route C's org-App hop is kept (the live seat's `with-tenant-slotstrip.sh` order). |
| `test/run-tests.sh` | The hermetic harness run by `just check-fleet-launch`; it uses stub boards, credentials, preflights, queue, lock, in-flight and state directories, never a live factory. |

## Running a launch

Run it from a checkout of this repository's `master`, never from a copy under
`tmp/`, and through the detached gate runner so it outlives the calling session:

```bash
mise exec -- just gate-start -- bash -c 'env ONLY_GMK=1 fleet-launch/dispatch-dual.sh <item-id> >> <state-dir>/seq-<item-id>.log 2>&1'
```

The gate runner ends a gate's whole process group after 900 s without output (its stall cap), which
killed a launcher and its drive at 15m07s on four gate runs on 2026-11-17 while the factory run went on.
Both launchers (`dispatch-dual.sh` and `resume-capped.sh`) therefore detect the runner, which exports
`LIVESPEC_GATE_RUN_PROGRESS_STAMP` into everything it runs, and re-execute themselves in a new session
with that variable removed. The call returns `0` at once and prints `detached pid <pid>, log file <path>`;
the log is `detached-<launcher>-<UTC>-<pid>.log` under `FLEET_LAUNCH_STATE_DIR`, and its first line
names the detached pid, its session and its parent. Set `FLEET_LAUNCH_ALLOW_UNDER_GATE=1` to run in
place instead. The harness slice `gate-detach` covers both launchers and both controls.

For another tenant, add `REPO_OVERRIDE="$HOME/workspace/<repo>"`; the launcher runs every
launch-time command under that repository's committed `credential_wrapper`, run as written (a
non-family one nested inside the family wrapper), so `WRAPPER=` is needed only to override that
chain, as the slot-narrowing wrapper does. For a registry-resolved capture dispatch, add
`CAPTURE_NULL=1 CAPTURE_EXPECT=petri`. A queue ticket's position is computed when it is taken, by
walking the item's parent chain (`parent-of.sh`, run in the tenant repository under its wrapper) to
the owning plan and reading that plan's rank in the priorities record
(`FLEET_LAUNCH_PRIORITIES_RECORD`, one `<rank> <plan-id>` line per plan); an unranked chain takes the
last rank, and a host with no readable record orders tickets by arrival. A queued launcher also
claims its item, so a second launcher for an item that already has a live one exits without a
ticket. To keep a queue position across a restart, pass the old ticket's number as `TICKET_NS`;
under priority ticketing it is honored only while that ticket still exists for the item. A resume is launched the same way through
`fleet-launch/resume-capped.sh <item-id>` (or `<ticket> <repo> <item>`).

A running bash launcher executes the script content it started with, so a hold check added
to the script later never reached it (bd-ib-5ycmsm). Both launchers therefore compare their
script on disk with the content they started on at the top of every wait loop and again
after they bind at the launch point, and re-execute themselves when it differs, keeping
their pid, FIFO ticket and give-up deadline. Replace a launcher script atomically (write
beside it, then `mv`); an in-place edit corrupts a running bash. A launcher started before
this change cannot re-execute itself, so after any change to a hold or guard, run
`fleet-launch/launcher-versions.sh` and restart each launcher it marks `STALE` (pass its old
ticket number as `TICKET_NS` to keep its place) before relying on the change. `config.sh`,
`board-snapshot.sh` and `launch-lib.sh` are read when a launcher starts and are not part of the
version.

The state directory (`FLEET_LAUNCH_STATE_DIR`) holds data only: logs, verdicts, the shared
`fleet-cap`, `gmk-cap`, `hl-cap`, `candidate-cap`, `gmk-idle-floor` and `gmk-target` files, the
`hold-gmktec`, `hold-repo-<repo>`, `canary-hold-repo-<repo>` and `hold-item-<item>` holds, the
`freeze-allowlist` with its lock and consumed log, `canary-hold-exempt`, `arm64-enrolled`,
`acp-overrides.txt`, the per-repository `wip-act.<repo>` and `wip-claimed-cache.<repo>.*` files
and the re-ticket state. It never holds a script.

## Parity with the running copies (2026-11-15, bd-ib-yax6gv)

The launchers the dispatching host ran (`tmp/petri-canary/dispatch-dual-r681b.sh` at version
`f0eeecfea2a2`, `resume-capped.sh` at `d88909698f00`, `resume-repo.sh`, `wip-claimed-count.py`,
`wfsize-screen.py`, `homelab-wrapper.argv` and the seat's `with-livespec-env-slotnarrow.sh`) had
diverged wholesale from this directory. This directory now carries every gate those copies ran,
with these deliberate differences, each with its reason:

- **Yield marker.** A yielding ticket is marked `held=<cause>`, never `wip-wait=1`, because
  `contracts.md` §"Provisional fleet launch scripts" forbids a conforming launcher the
  `wip-wait=1` form. The queue scan skips BOTH forms. The interim launcher honours only
  `wip-wait=1`, so a mixed fleet would let it stall behind a `held=` ticket: the cutover below
  drains every interim launcher first.
- **Ready-set refusals are retried** `FLEET_LAUNCH_READY_RETRY_POLLS` times with the ticket kept,
  then end with a terminal line and one ledger comment; the interim launcher exited at once (spec
  "Bounded ready-set retry").
- **Non-run exits leave a terminal line and a dropped-ticket comment** (Scenario 312); the interim
  launcher's TERM trap only dropped the ticket.
- **The origin-tip refresh** reads the default branch with `git ls-remote --symref`, never
  `origin/HEAD` with a `master` fallback, and refuses the launch when the checkout cannot be
  fast-forwarded (spec "Checkout at the origin tip").
- **The host-only screen** (`dispatcher.py host-only`) runs before the mutex and the preflight
  (Scenario 314); the interim launcher left it to the seat's pre-launch screen.
- **Only a released launcher skips held heads.** A launcher the gmktec hold holds keeps the full
  ticket order in its own queue scan, so held launchers bind in ticket order at the lift; the interim
  copy skipped held tickets unconditionally, which let two held launchers bind in either order.
- **The resume launcher honours the priority-1 release too**; the interim `resume-capped.sh`
  released only allowlisted items.
- **Every host value is a `FLEET_LAUNCH_` value in `config.sh`**: the four caps and the idle floor
  are read live from state files with the constants as fallbacks (the interim copy hard-coded the
  file paths), `FLEET_LAUNCH_FABRO` stays the Dispatcher's own petri client for the post-launch
  listing poll (the interim copy used fabro-currency's carrier build), the slot-narrowing wrapper
  takes its slot names from config instead of a hand-edited `env -u` list, and the per-repository
  WIP count lives in `wip-act.<repo>` plus the helper's JSON cache and `.statuses` sidecar so the
  launcher recomputes the in-flight addition on every pass instead of caching it (spec "Shared WIP
  claim-count cache").
- **Poll intervals** are config values (`FLEET_LAUNCH_POLL_S`, `FLEET_LAUNCH_WIP_POLL_S`,
  `FLEET_LAUNCH_QUEUE_WAIT_S`); the interim copy used 20 s to 120 s literals.
- **A declared `credential_wrapper` argv is run as written, whole.** The resolver keys on the
  argv's presence and on whether its first word is the default wrapper path itself (run as
  declared) or another tenant's wrapper (nested inside the default wrapper with the family
  `BEADS_DOLT_PASSWORD` removed); it never shortens the argv. The first committed copy keyed on
  argv[0]'s basename and collapsed route C's argv (the family wrapper followed by the `/bin/sh` hop
  that maps `GITHUB_APP_ID_ORG` onto `GITHUB_APP_ID`) to the bare family wrapper, so a launch
  minted as the personal App, which livespec-ai repositories refuse (found by
  central-credential-service, 2026-11-15). The interim `tenant_wrap` tests the basename too but
  execs the argv whole, so it never had the defect. Harness cases 38 and 48 cover both shapes with
  a positive control; a value-free host check through the fixed chain minted livespec-ai
  installation 182016479 as App 5761962, and the bare wrapper minted App 3668528.
- **The slot-narrowing wrapper composes with the committed argv.** `WRAPPER=` overrides the
  launcher's chain, so the first committed slot-narrowing wrapper ran the bare default wrapper and a
  slot-narrowed launch of a route C repository would have minted as the personal App. It now resolves
  the target's committed `credential_wrapper` through `launch-lib.sh` and strips the slots as the
  innermost hop, the order the live seat's `with-tenant-slotstrip.sh` (`961ccb6f782b`) uses; harness
  case 45 asserts, value-free, that the child holds the org pair, the judge slot's unnumbered token and
  only the non-excluded slots, with a bare-wrapper control and an unreadable-argv refusal. Two
  deliberate differences from that live copy: the excluded and judge slots are the `config.sh` values
  `FLEET_LAUNCH_SLOTNARROW_EXCLUDED_SLOTS` and `FLEET_LAUNCH_SLOTNARROW_JUDGE_SLOT`, not a hand-edited
  `env -u` list; and an unreadable `credential_wrapper` makes the committed wrapper REFUSE with exit
  78, where the live copy falls back to the bare family wrapper, because a guessed chain under route C
  is exactly the personal-App mint this fix exists to prevent.
- **The drive is exec'd in its subshell, and the harness runs under a non-reaping subreaper.** The
  drive's subshell ends in `exec` of the resolved wrapper chain, so the chain is the launcher's direct
  child and `wait` reaps it; a subshell ending in the `wrap` function left the chain a grandchild
  that stop_drive's kill turned into a zombie wherever PID 1 does not reap orphans, which CI
  containers do not. Scenario 330 cases 20a and 20e failed in CI alone on 2026-11-15 for that reason
  (`kill -0` read the stopped drive as alive) while passing on every developer host, so
  `dev-tooling/just-check-fleet-launch.sh` now runs the harness under `PR_SET_CHILD_SUBREAPER` with
  a parent that reaps only its one child, and the same leak fails locally.
- **The gmktec idle gate measures whole-host `mpstat` idle** against `gmk-idle-floor` (live value
  0, fallback 3), exactly as the interim copy did. The spec's factory-class pressure measure is
  implemented by neither copy; that gap is recorded here rather than hidden.

Deliberate omissions, each with its reason:

- `dispatch-dual-r681b-scgc.sh`, `dispatch-dual-f6cc.sh`, `dispatch-resume*-r2xx.sh` and
  `dispatch-resume-r382.sh`: dead copies no launcher runs; deleted at the cutover.
- `reticket-decision.sh`: absorbed into the launcher's own early-exit path (the `-refused` stage
  detection, the 0/300/600 s delays and the per-window bound are all in `dispatch-dual.sh`).
- `wfsize-screen.py` (the INTERIM size screen of the materialized `workflow.toml`): NOT committed. It
  is 405 logical lines of in-process rendering through the installed build's private modules, with
  broad catches this repository's `check-file-lloc` and `check-no-except-outside-io` gates refuse, and
  it is interim until the compression fix is in the launch build. The launcher keeps the GATE: with
  `FLEET_LAUNCH_SIZE_SCREEN=1` it runs `FLEET_LAUNCH_SIZE_SCREEN_COMMAND` (default
  `tmp/petri-canary/wfsize-screen.py`, the seat's copy) before every preflight and writes
  `hold-item-<item>` on HOLD or ERROR exactly as the interim launcher did. The repository-level
  measurement is `check-materialized-workflow-toml-size`.
- `dod-preflight-codexfirst.sh`: a shim that only exported the judge models and ran the committed
  `dev-tooling/dod-preflight.sh`; the launcher does both itself.
- `chain-opd3hq-after-close.sh`, `fill-precheck.py`, `drive_cpu_*.py`, `throughput-watch.sh` and
  the other one-off chain, watch and measurement scripts: seat-side tooling, not launch gates; their
  evidence lives in the ledger comments that cite them.
- The seat's `ticket.sh`, `resume.sh`, `seeded-ticket.sh`, `allowlist-add.sh` and `hold-write.sh`
  under `/var/tmp/ldseat`: the seat's own entry points and hold editors; they invoke these launchers
  and are not launch gates. The cutover changes only the launcher path they name.
- The seat's pre-launch screen cannot see the Dispatcher's dispatch-stage spec-change-tier
  judgement (finding on bd-ib-yax6gv, 2026-11-13); neither can this launcher. The Dispatcher's own
  refusal (exit 5, cause `refused`) still ends the launcher without a re-ticket.

### Cutover from the interim copies

Required by `contracts.md` §"Provisional fleet launch scripts" ("The cutover MUST drain every live
interim launcher before the first committed launch"). The seat that runs the launchers performs it,
on the dispatching host, after this change is on master:

1. Fast-forward the primary checkout to `origin/master` and run `fleet-launch/launcher-versions.sh`
   to list the live launchers (each shows its `tmp/petri-canary/...` script).
2. Stop ticketing. For each live interim launcher, record its item and ticket number (the first
   number of its ticket file in `/run/user/1000/gmktec-launch-queue.d`), then stop it with TERM; a
   launcher whose drive is already running may finish its listing poll first. Every interim
   launcher must be gone before step 4, because its queue reader skips only `wip-wait=1`.
3. Point the seat's entry points at the committed tree: `ticket.sh` runs
   `bash "$REPO/fleet-launch/dispatch-dual.sh" "$ITEM"` and `resume.sh` runs
   `bash "$REPO/fleet-launch/resume-capped.sh" "$KEY" "$REPO" "$ITEM"`, with `REPO` the primary
   checkout. The state directory is unchanged (`FLEET_LAUNCH_STATE_DIR` defaults to
   `tmp/petri-canary`, where every hold, cap, allowlist and log file already lives). Launches that
   used the seat's slot-narrowing wrapper pass
   `WRAPPER=$REPO/fleet-launch/wrappers/with-livespec-env-slotnarrow.sh`; to keep the interim size
   screen, export `FLEET_LAUNCH_SIZE_SCREEN=1` (the command defaults to the seat's
   `tmp/petri-canary/wfsize-screen.py`).
4. Relaunch each stopped launcher from the committed tree with its old ticket number as
   `TICKET_NS`, smallest item first, and confirm with `launcher-versions.sh` that every running
   launcher executes a `fleet-launch/` script at the version on disk.
5. Move the interim copies out of any launch path: rename `tmp/petri-canary/dispatch-dual-r681b.sh`,
   `resume-capped.sh` and `resume-repo.sh` to `*.retired-<UTC>` so a stale entry point fails loudly,
   and delete the dead copies named above. bd-ib-pdmadj then deletes every remaining script under
   the fleet repositories' `tmp/` directories.

The known defects that shaped the first commit still hold and are still guarded by the harness: a
launcher reading a stopped factory's board saw the fleet as unknown and never launched (2026-10-24);
an early FIFO ticket was dropped when a binding count failed; and an edit that appended a trailing
comment to a multi-statement line silently dropped the mi-homelab board read, which `bash -n` could
not catch. That last one is why this directory's check target runs a hermetic harness, not only a
syntax check.
