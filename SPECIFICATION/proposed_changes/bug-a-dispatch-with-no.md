---
topic: bug-a-dispatch-with-no
author: claude-opus-5-5
created_at: 2026-11-22T12:23:24Z
---

## Proposal: Preserved-work comments and seed-ref riders reach a goal only when a current seed ruling releases them

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Today "A goal carries a bounded rider set" carries every rider appended after the item's last dispatch claim, and the records a failed run leaves behind (`livespec-preserved-tree`, `livespec-preserve-by-reference`, `livespec-needs-human-cause`) are riders under that definition. So the next dispatch's goal hands the agent an earlier run's preserved tree even when no seed ruling released it. This proposal makes those records, and any operator rider that names a seed ref, carried ONLY while a current seed ruling releases them. Every goal of a dispatch routed `fresh` also states that the run starts fresh from the default branch and must not restore any ref a comment names. The records stay on the ledger. Two scenarios are added under Scenario 239; no heading is added, removed or renamed. This proposal is held PENDING until PR #5675's canary shows whether carrying a complete seed is the desired behaviour; the coordinator will rule on it then. The agreement of the route label with the goal is internal and is handled separately, not by this proposal.

### Motivation

The goal and the recovery route disagreed about whether a run was seeded, and the agent followed the goal. Measured 2026-11-22 on run 01M81FHNK5J3 (item livespec-dev-tooling-mwh6o5, candidate factory :32278, build 2b0542c8e). The run's goal (run.json spec.settings.run.goal.value, 8,489 characters) carried riders [2] to [5] appended after the prior claim: [2] a `livespec-preserve-by-reference` comment for run 01M80Z25N44T, [3] a `livespec-needs-human-cause` comment, [4] a `livespec-preserved-tree` comment, and [5] an operator comment pointing at `refs/heads/preserve/candidate-01M80Z25N44T-mwh6o5` at cf42be26 with the words "seed from this ref". No seed ruling was current. The dispatch journal's `recovery-route` record for the same dispatch (2026-11-22T11:16:11Z) reads `route: fresh` with `preserved_work: absent`. The Red agent then restored the preserved tree (stages/047-red@1/response.md: "The preserved ref is intact ... I'll carry the preserved Red test forward"), so a run labelled fresh was in fact seeded and the seeded-run guards did not apply to it; it ended at needs_human with LIVESPEC_GREEN_PREVIEW_REFUSED. An in-process render_goal on registered build 9aae3b07b73d reproduces the run's goal byte-for-byte (sha256 2800f3a1...a1a3d9); with the four preserved-work riders removed the goal is 3,939 characters and names no preserve ref, no cf42be26 and no "seed from this ref". Code locations (package livespec_orchestrator_beads_fabro/commands/): `_dispatcher_goal.py` render_goal renders every carried rider; `_dispatcher_rider_bound.py` bound_riders / _is_carried carry any rider appended after the prior claim; `_dispatcher_dod_judgement_markers.py` is_receipt_comment is the only exclusion; the marker writers are `_dispatcher_preserved_tree_record.py`, `_dispatcher_preserve_reference_body.py` and `_dispatcher_needs_human_cause.py`; the route is decided in `_dispatcher_recovery_routing.py` with the seed ruling read by `_dispatcher_ruling_currency.py` current_seed_ruling; the route label is written by `_dispatcher_recovery_records.py` recovery_route_record via `_dispatcher_recovery_launch.py`; and the launch record `_drive_impl_scope.py` launch_record carries no route today. Work item: bd-ib-ycvwxn.

### Proposed Changes

In `contracts.md` §"Dispatch-brief lessons injection", append the following to the paragraph **A goal carries a bounded rider set.**, directly after the sentence ending "MUST NOT move the bound for that same dispatch's goal.":

> A PRESERVED-WORK RIDER is a rider whose first line is `livespec-preserved-tree`, `livespec-preserve-by-reference` or `livespec-needs-human-cause`, or a rider whose text names a ref under `refs/heads/needs-human/`, `refs/heads/preserve/` or `refs/livespec/preserved-publish/`, in its full form or in its short form without the `refs/heads/` prefix. Notwithstanding the conditions above, a preserved-work rider MUST be CARRIED only when the dispatch being rendered follows a current seed ruling (§"Factory-configurable ACP fallback priority" → "A ruled seed names the tree a released item's next dispatch starts from") that releases the tree the rider records or names; otherwise it MUST NOT be carried, whether it is standing, stage-scoped or appended after the most recent claim. A preserved-work rider that is not carried MUST stay on the item's ledger unchanged and is counted by the left-out line above like any other rider that is not carried. When the dispatch's recovery route is `fresh`, or the item has no recovery route because it was never dispatched, the goal's operator-rider section MUST state, in one line that is the same for every stage of the dispatch, that the run starts fresh from the default branch and MUST NOT restore, check out, cherry-pick or diff-apply any preserved, needs-human or preservation ref that a ledger comment names. That line is not part of the GOAL component of any judgement subject. A goal of a dispatch routed `seeded` from the preference order rather than from a ruling names its seed through the interrupted-prior-attempt brief this specification already requires, not through preserved-work riders.

In `scenarios.md`, under `## Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric`, add these two scenarios directly after "A comment that is not carried does not change the subject digest":

```gherkin
  Scenario: A dispatch with no seed ruling omits preserved-work riders and states a fresh start
    Given a released item whose earlier run left livespec-preserved-tree, livespec-preserve-by-reference and livespec-needs-human-cause comments after its most recent dispatch claim
    And an operator comment appended after that claim naming refs/heads/preserve/candidate-<run>-<item> with the words "seed from this ref"
    And no current seed ruling on the item
    When the Dispatcher renders the implement stage's goal for the item's next dispatch, routed fresh
    Then the goal carries none of those four comments
    And the goal states that the run starts fresh from the default branch and must not restore any ref a ledger comment names
    And the item's ledger still carries all four comments

  Scenario: A current seed ruling releases the preserved-work record of the tree it names
    Given a released item carrying a livespec-preserved-tree comment for the tree at ref R
    And a current seed ruling naming R
    When the Dispatcher renders the implement stage's goal for the item's next dispatch
    Then the goal carries that livespec-preserved-tree comment
    And the goal carries no fresh-start statement
```

No `## ` heading changes, so `tests/heading-coverage.json` needs no co-edit.
