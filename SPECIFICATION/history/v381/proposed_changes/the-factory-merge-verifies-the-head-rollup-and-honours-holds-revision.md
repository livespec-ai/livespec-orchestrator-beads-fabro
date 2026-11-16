---
proposal: the-factory-merge-verifies-the-head-rollup-and-honours-holds.md
decision: modify
revised_at: 2026-11-15T05:52:33Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

ACCEPT as proposed, then MODIFIED by the doctor fixes under Modifications. Carrier bd-ib-x73d36 (stop-the-line, ratify route ruled by legacy-coordinator-agent 2026-11-15): the shared factory merge path merges only on a non-empty all-passing head rollup read from the forge (SUCCESS, SKIPPED, NEUTRAL pass), refuses a target requiring no status checks, re-reads the merge-hold label and every active merge-time hold before every direct merge and auto-merge arming, and never reports a refused merge green; fleet-scoped through the one shared merge path. Evidence: mi-homelab/homelab#1190 merged red on a protection-less target and mi-homelab/homelab#1192 merged directly while merge-hold:on, both reported rc=0. Scenario 375 exercises the paragraph (375 is free; 374 is claimed by a pending proposal). legacy-coordinator-agent graded the proposal PASS (livespec-orchestrator-beads-fabro#5342). Decided under delegated revise_decision_mode; spec-led, not drift-origin; no design record is contradicted. The new H2 gets a TODO row in tests/heading-coverage.json owned by bd-ib-x73d36, co-edited in the revise commit.

## Modifications

Doctor fixes, on legacy-coordinator-agent's grade of livespec-orchestrator-beads-fabro#5347 (2026-11-15), PASS on the condition that the revise's LLM doctor phases run before the PR is readied and that findings in v381's own new text are fixed in the PR. Each fixes a defect that the objective or subjective phase, or their re-pass, found in this paragraph:

1. Pending checks. As proposed, rule 1 forbade arming until every entry passed, counted a running entry as not passing, and made every such refusal blocked. Every fresh run would then have been refused at `pr`, which arms right after publication, and the handed-off merge wait could never occur. The intent is kept: no merge or arming is made unless the head rollup is all-passing at the decision. A rollup with running entries and no failed entry is now *pending*, which is a wait and not a refusal (new rule 3). `pr` readies the pull request without arming and reports `ROLLUP=pending`. The merge wait polls the rollup and arms on its first all-passing read. When the budget runs out while the rollup is still pending, the wait is a pending handoff, recorded as `rollup: pending` on its `merge-wait-handed-off` row. Hold 8 of Stranded claim release completes only such a handoff, notwithstanding its rest of an unarmed pull request. It arms on a later all-passing read and then journals a new handoff row without `rollup: pending`, so that later passes apply its ordinary rules, rests on a failed entry or a protection refusal, and keeps the claim held on a merge-hold refusal or a read that is still pending. An unreadable rollup at budget exhaustion refuses with `head-rollup-unreadable`. Refusals in the merge wait report exit code 4. A failed entry on an armed pull request is disarmed before the refusal. The release valve does not wait. An intermediate draft let `pr` arm while entries were running. The re-pass showed that the forge then completes the request as soon as the required checks pass, which reintroduces the defect, so that draft was discarded.
2. The *decision* is defined as the direct merge call or the arming call. Every factory merge is decided on an all-passing rollup, so a merge the forge reports completed is recorded as successful exactly as before. This keeps the ratified rules that an already-merged pull request is a recorded success.
3. The merge paths are listed as the code that merges or arms: the `pr` stage's scripted publication, the merge wait's and hold 8's arming of a pending rollup, the `set-merge-hold:<work-item-id>:off` release valve, and any path that a policy setting such as `merge_on_review_cap` routes to.
4. The hold set is exact. The `merge-hold:` label is the only merge-time hold, and the launch-time repository and factory holds are out of scope.
5. A refusal order is stated: protection, then hold, then rollup. The first rule that fails gives the named cause, and the outcome detail names every other cause and every failed entry. Scenario 375 case 1's Then line now expects `target-requires-no-checks` as the cause, with `head-rollup-not-green` and the two failed checks in the detail.
6. The release valve, which has no dispatch or stage, gets its own refusal: it does not arm, it leaves the label and the item's status unchanged, it fails with `drive`'s existing refused-action exit code, and it is exempt from the hold re-read.
7. The never-green rule is scoped to refusals. A merge made by hand is outside it.
8. The rationale aside about GitHub's skipped-check treatment is dropped. The rules are restructured and renumbered 1 to 7: classification, the rollup gate, waiting on a pending rollup, protection, the hold re-read, refusal order, and never green.

Scenario 375 changes as follows. Case 2 drives the `pr` stage's arming, because no ratified merge path makes a direct merge. Every case names the `pr` stage's decision in place of 'the factory's merge step'. The hold Givens name only the `merge-hold:` label. Three cases are added: a pending rollup armed only once every entry passes; a pending rollup still running when the merge wait's budget ends, which is handed off and armed by hold 8; and a pending rollup whose running check fails, which is refused and never armed. The heading is unchanged.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-15T05:52:16Z
verdict: NO BLOCKERS
proposal_stem: the-factory-merge-verifies-the-head-rollup-and-honours-holds
content_digest: 651670d73f7e7ab4aa950b67ebd5ab916b52dc5f4fccc3688aa74778048c2ec8
