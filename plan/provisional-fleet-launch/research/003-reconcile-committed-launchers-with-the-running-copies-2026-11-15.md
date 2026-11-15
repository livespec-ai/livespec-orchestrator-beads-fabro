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

## Fix 3: the committed argv is honoured whole (2026-11-15, second head)

central-credential-service found, and legacy-coordinator-agent re-graded the first head to FIX
REQUIRED on, a defect in `launch-lib.sh`'s `resolve_tenant_wrapper`: an argv whose first word's
BASENAME was the default wrapper's was collapsed to the bare family wrapper. Under route C (#5361,
`["/usr/local/bin/with-livespec-env.sh", "--", "/bin/sh", "-c", "GITHUB_APP_ID=\"$GITHUB_APP_ID_ORG\"
GITHUB_PRIVATE_KEY=\"$GITHUB_PRIVATE_KEY_ORG\" exec \"$@\"", "sh"]`) that dropped the org-App hop, so a
launch minted as the personal App 3668528, which livespec-ai repositories refuse.

The fix keys on the argv's presence and on its first word's exact path: a declared argv is ALWAYS run
whole, and the only decision left is nesting (`committed`, run as declared, when the first word is
the default wrapper path; `tenant`, nested with the family password removed, otherwise). Evidence:

- Harness case 48 (unit probe through `resolve_tenant_wrapper` and `wrap`, a stub family wrapper that
  projects a personal id and an org pair, printing only WHICH pair the child holds): the committed
  head 881fd675a printed `mode=default words=0 personal-app`; the fix prints
  `mode=committed words=6 org-app`. Control: no declared argv prints `mode=default words=0 personal-app`.
- Harness case 38 now runs the full launcher under route C's six-word argv and under the bare
  two-word family argv, each logged `run as written`; the non-family nested case is unchanged.
- Value-free host check on hetzner-xubuntu through the fixed chain with route C's argv and the real
  `/usr/local/bin/with-livespec-env.sh`: child `GITHUB_APP_ID == GITHUB_APP_ID_ORG` true; JWT as App
  `livespec-ai-factory-bot` (5761962, owner livespec-ai); installations `[(182016479, livespec-ai)]`;
  installation token minted (length 383, `repository_selection all`). Control, bare wrapper: App
  `thewoolleyman-factory-bot` (3668528), installation 131208965 only, 182016479 absent.

Rule K sweep for the same special case, each placement reported:

- `fleet-launch/launch-lib.sh` `resolve_tenant_wrapper`: FIXED (the only basename test on the
  family wrapper in the committed tree).
- `fleet-launch/dispatch-dual.sh`: CLEAN; its one basename test (`is_fabro_run`) matches `fabro`
  in a `/proc` cmdline and is unrelated to wrappers.
- `fleet-launch/resume-capped.sh`, `resume-repo.sh`: CLEAN; they call `wrap` only.
- `fleet-launch/wrappers/with-livespec-env-slotnarrow.sh`: CLEAN of the basename case. NOTE for the
  coordinator: `WRAPPER=` is mode `override` and replaces the whole chain by design, so a slot-narrowed
  launch of a route C repository bypasses the committed argv and mints as the personal App. Not
  changed here: composing the two (narrow the slots AND keep the org hop) needs a ruling, because
  nesting the family wrapper inside itself in either order undoes one of them.
- The live `tmp/petri-canary/dispatch-dual-r681b.sh` `tenant_wrap` and
  `/usr/local/libexec/livespec-tenant-wrap.sh` on vps (read over ssh, 2026-11-15 ~11:3xZ): CLEAN of the
  drop. Both test the basename but exec `"${cw[@]}" "$@"` whole and fall back to the bare family
  wrapper only when no argv is declared.

### Slot narrowing composes with the committed argv (coordinator ruling, same head)

legacy-coordinator-agent ruled the `WRAPPER=` finding above is not a design call: legacy-dispatcher-agent
had already composed the two live. Per its answer (session 3aa1c4): the old seat
`with-livespec-env-slotnarrow.sh` (92f3c43da2d1) is RETIRED for placements; the live file is
`/var/tmp/ldseat/with-tenant-slotstrip.sh` (961ccb6f782b, read over ssh), passed as `WRAPPER=` by the
three placers `t-widen-fresh.sh`, `t-widen-seeded.sh` and `t-ticket-only.sh` through `ticket.sh`; the
launcher `dispatch-dual-r681b.sh` (f0eeecfea2a2) is unchanged. Its order: resolve the target's committed
argv (as `tenant_wrap`), then run `bash -c '<set CLAUDE_CODE_OAUTH_TOKEN to _4; env -u the excluded
slots>' <cmd>` INSIDE that chain, so the route C hop runs before the strip and the strip touches only
Claude slot variables. Proof on xowhol 10:27:08Z: `GITHUB_APP_ID == _ORG`, only slot `_4` present, token
equals `_4`; the 10:48:58Z mint probe reached installation 182016479 through the same chain.

The committed `fleet-launch/wrappers/with-livespec-env-slotnarrow.sh` now does the same through
`launch-lib.sh` (`resolve_tenant_wrapper`, then the new `wrapper_chain`, then `exec` of the chain with
the strip innermost). Harness case 45 asserts the child under route C's argv holds the org pair, the
judge slot's unnumbered token and only the non-excluded slot names; the control (no committed argv)
narrows under the bare family wrapper and holds the personal pair; an unreadable argv refuses with
rc 78. `/usr/local/libexec/livespec-tenant-wrap.sh` (003e543956c8) is the reconcile-runs variant
without the strip; its backfill bd-ib-ft426g is central-credential-service's.
