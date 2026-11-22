---
topic: reconcile-runs-run-lane-acts
author: claude-sonnet-5-5
created_at: 2026-11-22T19:42:44Z
---

## Proposal: A reconciliation surface acts on a run only when it was dispatched by its own host

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

The stranded-claim lane already holds a claim whose stamp names another host (contracts.md, `Only the owning host recovers a claim`, and the `owner-elsewhere` hold). The RUN lane has no such rule: orphan export and terminate (the orphan sentence under `A factory run never awaits a human`), the sandbox-container sweep and the ended-run collection (`Collection reaches every dispatching repository's runs`) act on every run the shared factories list, whichever host dispatched it. This proposal states the same fence for the run lane.

### Motivation

Measured 2026-11-19T21:16Z: the VPS `reconcile-runs` timer pass cancelled run 01M7TRYVYD91, a healthy run dispatched by hetzner-xubuntu that the pass's own report listed held `owner-elsewhere` (orphan reason superseded-run, cancel 202; evidence on bd-ib-defs3b). The fence is a safety guarantee (a host must not terminate or delete a run another host owns), so it is stated in the specification, not left to implementation. The live hetzner timer carries the same missing fence. Work item bd-ib-mnkasb is the implementation.

### Proposed Changes

In `SPECIFICATION/contracts.md`, in the stranded-claim subsection, directly after the bullet `Only the owning host recovers a claim.`, add a bullet: **Only the dispatching host acts on a run.** Ledger writers and factories are shared across hosts, so no reconciler can observe another host's dispatch. A reconciliation surface (the loop tick, the dispatch preamble and the standalone `reconcile-runs` sweep) MUST act on a run, by exporting it, terminating it as an orphan, deleting it as an ended run, or sweeping its sandbox containers, only when the run's journaled dispatching host is the reconciler's own host. A run whose journaled dispatching host is another host MUST be left exactly as it is and listed in the pass's `held` output with the reason `owner-elsewhere`, naming the run id and the dispatching host; the ended-run collection MUST journal the refusal with the same two facts. A run with no journaled dispatching host (journaled before host stamping, or unattributable) MUST be held `owner-elsewhere` on every host except where a single declared host owns the factory, in which case that host acts; the held entry names the absence. Add `Scenario 350` to `SPECIFICATION/scenarios.md` after Scenario 349 with Given a factory carrying a healthy non-terminal run whose journaled dispatching host is host A and a reconcile-runs pass on host B whose ledger classifies that run an orphan; When the pass runs; Then it neither exports nor terminates the run, its `held` output lists the run with reason `owner-elsewhere` naming the run id and host A, and a pass on host A exports and terminates the same run as it did before; plus the ended-run collection and container-sweep variants. Add a `## Scenario 350 ...` entry to `tests/heading-coverage.json` with `test` the literal `TODO` and a non-empty `reason`. No other heading changes.
