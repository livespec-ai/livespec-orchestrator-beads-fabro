---
topic: an-abandoned-incident-chain-retires
author: claude:zhonwq-hand-lane
created_at: 2026-11-22T22:30:00Z
---

## Proposal: an-abandoned-incident-chain-retires

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

An incident chain none of whose expedited changes reached master (its carrier pull request closed unmerged, a drill stopped before its recorded close, or an entry was never attempted) MUST be able to end through one sanctioned `retire` action of the incident authority writer, which records who retired it and why, moves it to a terminal phase `retired` with canonical lifecycle state `done`, and closes the item with no repayment owed. Retiring a chain any of whose changes reached master is refused by name.

### Motivation

Work item livespec-dev-tooling-zhonwq (orchestrator half of livespec-dev-tooling-lf043; observer half livespec-dev-tooling-s7yiut; plan livespec-dev-tooling-bqnzcm). Closure requires a merged normal repayment, and `drill-close` admits only a recorded scratch drill whose every carrier merged into `incident-scratch/**`, so an expedited attempt whose PR closed unmerged can never close: livespec-dev-tooling-gig42c (2026-11-12), livespec-dev-tooling-zq2i4c (attempt zq2i4c-attempt-1, livespec-dev-tooling#4818 closed unmerged, 2026-11-16) and livespec-dev-tooling-ypvfll (2026-11-17). The adopter drills of dae4kc, latoat and s6jt4u must be closable. The implementation shipped spec-first under the maintainer's local-only expedited exception (the PR naming livespec-dev-tooling-zhonwq); this proposal ratifies it.

### Proposed Changes

In SPECIFICATION/contracts.md §"Expedited incident lifecycle", add to the phase table the row `| retired | done | The retire action retired a chain none of whose changes reached master. |`, and append after the paragraph that begins "A recorded drill MUST be able to end" the following paragraph:

"An incident chain none of whose expedited changes reached master MUST be able to end through the `retire` action of the incident authority writer, the only writer of incident phase `retired`: the `commit-transition` action MUST refuse a `retired` successor with the named reason `incident-retire-requires-action`. The action takes the full fenced identity and a canonical record naming who retires the chain (`retired_by`) and why (`reason`); a blank value is refused `incident-retire-unattributed`. It applies only at incident phase `repair`, `master-observation`, `reverting`, `rollback-conflict` or `collecting-failures`, and any other phase is refused `incident-retire-ineligible-phase`. Before it writes, an authenticated forge read MUST show that no bound carrier pull request is open (else `incident-retire-carrier-open`), that no bound carrier pull request merged into a base outside `incident-scratch/**`, and that no attempt landed commit and no recorded revert commit in the history is reachable from `master` (else `incident-retire-landed-on-master`, naming the pull request or commit); a forge read that fails or is incomplete is refused `incident-retire-evidence-unavailable`. In every refusal it MUST write nothing. Otherwise it MUST take the same generation fence and immutable operation identity as every incident transition, record `retired` with no repayment required, record who retired the chain and why on the item, publish canonical lifecycle state `done` and release the incident owner's claim; a same-operation retry MUST recover that result and record the retirement once. A `retired` item owes no repayment, MUST NOT be reported as phase `closed` or as a completed incident (its completion rules name `incident-retired`), and its receipts MUST report no repayment outstanding."

Add to SPECIFICATION/scenarios.md, numbered at revise:

## Scenario NNN — An abandoned incident chain retires and a chain that reached master is refused

Given an incident item at phase repair whose bound carrier pull request against master closed unmerged, with no landed commit
And a second incident item whose recorded landed commit is reachable from master
And a third whose bound carrier pull request is still open
When an operator applies the retire action to each, naming who retires it and why
Then the first item reads incident phase retired with canonical lifecycle state done, is closed, owes no repayment and carries the retirement record
And the second is refused with incident-retire-landed-on-master and the third with incident-retire-carrier-open, each unchanged
And a commit-transition naming a retired successor is refused with incident-retire-requires-action
