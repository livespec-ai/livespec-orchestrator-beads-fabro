# Reconciling the committed fleet-launch tree with the launchers the dispatching host runs (2026-11-15)

Written by the provisional-fleet-launch plan seat (session 7fb0e5) for work item bd-ib-yax6gv, which
legacy-coordinator-agent re-parented into this plan on 2026-11-15 and reopened with one scope: land ONE
reconciliation pull request so the committed `fleet-launch/` tree equals the copies the live launchers
execute, retire the dead copies from every launch path, and hand legacy-dispatcher-agent the cutover steps.

## What was measured (read-only, over ssh to vmi3006760, 2026-11-15 ~08:0xZ)

The live launchers run from `/data/projects/livespec-orchestrator-beads-fabro/tmp/petri-canary/`, the
realpath of that host's `~/workspace` checkout, under `factory-dispatch.slice` scopes started by the
seat's `/var/tmp/ldseat/ticket.sh` and `resume.sh`:

| Running script | Version (sha256 first 12) | Lines | Committed counterpart |
| --- | --- | --- | --- |
| `dispatch-dual-r681b.sh` (3 launchers) | `f0eeecfea2a2` | 857 | `fleet-launch/dispatch-dual.sh`, 819 lines |
| `resume-capped.sh` (1 launcher) | `d88909698f00` | 48, sources functions out of r681b | `fleet-launch/resume-capped.sh`, 356 lines |
| `resume-repo.sh` | | 16 | none |
| `wip-claimed-count.py` | | 112 | none (`ready-set-check.py capacity` stood in) |
| `wfsize-screen.py` | | 364 | none |
| `homelab-wrapper.argv` | | 2 (route C: `with-homelab-credentials.sh --`) | parameter-store argv |
| `/var/tmp/ldseat/with-livespec-env-slotnarrow.sh` | | 51 | none |

Live state-file values at the time: `fleet-cap` 18, `gmk-cap` 20, `hl-cap` 2, `candidate-cap` 18,
`gmk-idle-floor` 0, `gmk-target` petri, `arm64-enrolled` present, `hold-gmktec` present (scoped
STOP-AT-SECOND fleet hold), `freeze-allowlist` empty, `acp-overrides.txt` absent.

Gates the running `dispatch-dual-r681b.sh` carried that the committed launcher lacked: the tenant
credential wrapper read from the target's `.livespec.jsonc`; the freeze allowlist with its one-shot
consume at LAUNCH and the priority-1 release; the held-head skip; the canary repository hold and its
exemption list; the candidate lane always counted in the fleet; the arm64 lane (`:32279`) outside the
fleet sum with its own cap and `ONLY_ARM=1`; `server=hl` FIFO classes; caps and the idle floor read
live from state files; a separate board-read client; plain `ps` with bounded retries; the shared
per-repository WIP count (`wip-act.<repo>`, `wip-claimed-count.py` with its cache) and head-only
polling; the concurrent preflight bounded to the first ten ranks; the size screen; the ACP overrides
file; the judge-model environment; the `-refused` stage detection and the per-window re-ticket bound;
the precise `drive_alive_for` match. The running `resume-capped.sh` carried the hold-gmktec allowlist
gate with the consume at RESUME (the 07:4xZ break-fix) and started the resume through `resume-repo.sh`
under the target's wrapper; the committed one invoked a `resume` command under the `resume` tenant
repository's wrapper, which is not the resume at all.

## What the pull request does

Every gate above is now in `fleet-launch/`, on the committed skeleton (which keeps the spec-conformant
pieces the live copies lacked: terminal lines and dropped-ticket comments, bounded ready-set retries,
the `ls-remote --symref` origin-tip refresh, re-exec on script change, holds re-read until admission,
the host-only screen). New files: `launch-lib.sh` (shared functions), `resume-repo.sh`,
`wip-claimed-count.py`, `wrappers/with-livespec-env-slotnarrow.sh`. The interim `wfsize-screen.py`
is NOT committed (405 logical lines and broad catches the repository's gates refuse); the launcher
keeps its gate behind `FLEET_LAUNCH_SIZE_SCREEN=1` pointing at the seat's copy. Every host
value is a `FLEET_LAUNCH_` value in `config.sh`. The harness gained a `parity` slice (cases 32 to 47)
with a positive control per refusal; the Scenario 307 slice still passes unchanged.

`fleet-launch/README.md` §"Parity with the running copies" lists every deliberate difference with its
reason, every deliberate omission with its reason, and the cutover procedure, which follows the
ratified clause's own order (drain every interim launcher first, because its queue reader honours only
`wip-wait=1`).

## Overlaps the coordinator should dispose

- bd-ib-4xqmqh (the committed launcher lacks the gates the seat's launcher runs): every Definition of
  Done bullet is satisfied by this change. Dispose as absorbed when the pull request merges.
- bd-ib-zwtfbq (the once-per-repository WIP claim-count cache): satisfied by this change
  (`wip-act.<repo>` read before any spawn, one helper call per time-to-live, the in-flight addition
  recomputed every pass, a failed computation writes no file). Dispose as absorbed.
- bd-ib-pdmadj (cut every launcher over, then delete the tmp scripts) is the cutover itself; its order
  stays binding. The README's cutover steps are its first half.

## Not done here

- The spec's factory-class pressure gate: neither copy implements it; both gate on whole-host
  `mpstat` idle against `gmk-idle-floor`. Recorded in the README as a known gap.
- The seat's pre-launch screen cannot see the dispatch-stage spec-change-tier judgement (finding of
  2026-11-13). Neither can the launcher; the Dispatcher's exit-5 refusal still ends it without a
  re-ticket.
