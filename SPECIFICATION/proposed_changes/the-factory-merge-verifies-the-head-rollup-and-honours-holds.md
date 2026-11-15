---
topic: the-factory-merge-verifies-the-head-rollup-and-honours-holds
author: claude-opus-5-5
created_at: 2026-11-15T04:45:20Z
---

## Proposal: The factory merge verifies the head rollup and honours every hold

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Adds a MUST paragraph under the existing H2 `## Self-contained plugin dispatch` stating that the orchestrator's shared merge path merges only on an all-passing head rollup read from the forge (SUCCESS, SKIPPED and NEUTRAL count as passing; required-only checks are not enough), refuses with a named cause when the target branch requires no status checks, re-reads the item's merge-hold label and every active merge-time hold at merge time on every merge path (direct merge and auto-merge arming alike) and refuses while any is set, and never reports a refused or non-all-passing merge as green or as a successful merge. The rule is fleet-scoped: every repository the factory merges into inherits it from the shared merge path with no per-repo copies.

### Motivation

Carrier work-item bd-ib-x73d36 (stop-the-line, ratify route ruled by legacy-coordinator-agent 2026-11-15; classify-tier returned spec-change because none of these behaviours is stated in contracts.md). Evidence quoted in bd-ib-x73d36: mi-homelab/homelab#1190 (item hl-u5jlef, fabro run 01M7ENY4Z2R0) was merged by the factory at 2026-11-15T04:15:05Z while its checks `shared credential provisioning` and `ci-green` had concluded FAILURE (head 02b51e06585fa95f35b4f5fde3803fdc87ca6346); the drive reported rc=0 GREEN and homelab main went red. homelab main's protection carried no required_status_checks and no rulesets. mi-homelab/homelab#1192 (item hl-bfl2ln) was merged red at 2026-11-15T04:30:25Z while its item carried merge-hold:on, as a direct merge with no auto-merge request; the drive returned rc=0 and closed the item. Today the `pr` paragraph only leaves auto-merge unarmed under a hold, and the merge-wait paragraphs ("Armed pull request overtaken by the default branch", the terminal-failure re-run paragraph) judge only checks "the forge reports as required", so a target with no required checks has nothing to judge and a direct merge has no hold check.

### Proposed Changes

Insert the following paragraph into `contracts.md` under the existing H2 `## Self-contained plugin dispatch`, immediately after the `pr` stage paragraph that ends "...A merge hold MUST preserve the ready pull request and leave auto-merge unarmed. ..." (and its rejected-arming continuation), and before the paragraph "**Armed pull request overtaken by the default branch.**". No new `## ` heading is added to `contracts.md`.

> **The factory merge verifies the head rollup and honours every hold.** These rules govern the orchestrator's one shared merge path. A *merge path* is any automated act by which the factory causes a pull request to merge: a direct merge (`gh pr merge` without `--auto`, or any equivalent forge call that merges immediately) and the arming of auto-merge (`gh pr merge --auto`, or the scripted publication command that arms it) alike, from the `pr` stage, the Dispatcher's merge wait, `merge_on_review_cap`, a hold release, or any other caller. The *head rollup* of a pull request is the set of every check run and every commit status that the forge reports on the pull request's current head commit, read from the forge at the moment of the decision and never from a cached, local or previously journaled copy; it is not limited to the checks the forge reports as required.
>
> 1. **All-passing head rollup.** A merge path MUST count an entry of the head rollup as passing when it concluded SUCCESS, SKIPPED or NEUTRAL. A merge path MUST count as not passing an entry that concluded FAILURE, CANCELLED, TIMED_OUT, ACTION_REQUIRED, STARTUP_FAILURE or STALE, and any non-completed entry (pending, queued, in_progress, expected). This matches GitHub's own treatment of a skipped required check. A merge path MUST merge a pull request, and MUST treat a merge as complete, only when the head rollup is non-empty and every entry in it is passing. The checks the forge reports as required are NOT sufficient: any entry that is not passing MUST prevent a direct merge. The same holds for arming auto-merge: the merge path MUST read the head rollup before arming and MUST NOT arm until every entry is passing, so that an armed request can never be completed by the forge on the strength of required checks alone; a merge the forge reports completed MUST NOT be recorded as successful unless the head rollup of the merged head was all-passing at the decision. When the forge cannot report the head rollup, the merge path MUST refuse with the named cause `head-rollup-unreadable`; when any entry is not passing it MUST refuse with the named cause `head-rollup-not-green`, naming every non-passing entry and its conclusion or state.
> 2. **Protection-less target refusal.** Before any merge path merges or arms, it MUST read the target branch's protection and rulesets from the forge. When the target branch requires no status checks — no branch-protection `required_status_checks` with at least one context or check, and no ruleset requiring a status check — the merge path MUST refuse with the named cause `target-requires-no-checks` and MUST NOT merge or arm, even when the head rollup is all-passing, because nothing on the forge would stop a later red head from merging an armed request. When the protection or rulesets cannot be read, it MUST refuse with the named cause `target-protection-unreadable`.
> 3. **Merge-time hold re-read.** Immediately before every direct merge and every auto-merge arming, on every merge path, the merge path MUST re-read from the ledger the item's `merge-hold:` label and every other active merge-time hold — every repository hold, factory hold or other hold that the Dispatcher honours as forbidding a merge at the time of the merge — and MUST NOT rely on the rendered `merge_hold` workflow input, on a value read at dispatch, or on any earlier read alone. While any such hold is set, the merge path MUST refuse with the named cause `merge-hold-active` (naming each hold found) and MUST NOT merge or arm. A hold that cannot be read MUST be treated as set, with the named cause `merge-hold-unreadable`. The existing rule that a merge hold leaves auto-merge unarmed is unchanged; this rule extends the same refusal to a direct merge.
> 4. **A refusal is never green.** A refused merge, and a pull request whose head rollup is not all-passing, MUST NOT report green, MUST NOT end the drive or the dispatch as a successful merge, MUST NOT report exit code 0 as a merged outcome, and MUST NOT transition the item to `acceptance` or `done` or close it. The pull request MUST be left open and unmerged. The dispatch outcome MUST be `blocked` at the stage that refused, with `blocked_reason: needs-human` through the same transition and `needs-human-blocked` journal row that a `needs_human` terminal produces, the named cause as the item's question, and a non-zero exit code already defined by §"Dispatcher exit codes" (no exit code is added or redefined). A held item whose `pr` stage readied the pull request without arming under the existing hold rule is not a refused merge and keeps its existing outcome.
>
> **Fleet scope.** These rules live in the orchestrator's single shared merge path, so every repository the factory merges into inherits them with no per-repository copy, no per-repository opt-in and no per-repository override. A repository MUST NOT be able to weaken them through its `.livespec.jsonc`, a registered workflow variant, or the target branch's own protection; a variant's merge seam MUST route through the same shared check, and the seam-equivalence check MUST hold a variant to it.
>
> Scenario 375 in `scenarios.md` exercises this paragraph.

## Proposal: Scenario 375 exercises the head-rollup, protection-less and merge-hold refusals

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Adds Scenario 375 to scenarios.md with four Given/When/Then cases: a protection-less target with a red rollup is refused, left unmerged and reported non-green with a named cause; a merge-hold:on item reaching a direct merge is refused and reported non-green; a green rollup on a protected target merges; a path-skipped job beside a green rollup merges.

### Motivation

The clause added by the first proposal is load-bearing behaviour and MUST carry a scenario (authoring discipline split (i)). The cases mirror the two observed incidents from bd-ib-x73d36 (homelab#1190 red merge on a protection-less target; homelab#1192 direct merge while merge-hold:on) plus the positive case.

### Proposed Changes

Append the following new scenario to `scenarios.md` after the highest-numbered scenario. Scenario 374 is claimed by the pending proposal `the-pre-dispatch-screen-admits`, so this proposal MUST use number 375; if revise finds 375 taken, it MUST renumber to the next free number and update the contracts.md cross-reference in the same change.

Because this adds a new `## ` heading to `scenarios.md`, the revise pass MUST update `tests/heading-coverage.json` in the same change (via `resulting_files[]`), adding an entry for this heading with `spec_root` `SPECIFICATION`, `spec_file` `scenarios.md`, `work_item` `bd-ib-x73d36`, and `test` `TODO` with a non-empty reason naming the owed test (a drive against a protection-less target with a red rollup, a direct merge of a merge-hold:on item, and a green rollup on a protected target). `contracts.md` gains no new `## ` heading.

## Scenario 375 — The factory merge refuses a red head rollup, a protection-less target and a held item on every merge path, and merges a green rollup on a protected target

```gherkin
Feature: the factory merge verifies the head rollup and honours every hold
  As the operator of every repository the factory merges into
  I want the factory to merge only an all-passing head on a protected target with no hold set
  So that a red check or a merge hold never lands on a default branch and a refused merge never reports green

  Scenario: A red head rollup on a protection-less target is refused and stays unmerged
    Given a target branch whose protection and rulesets require no status checks
    And a factory run whose pull request head carries one check run concluded success and two concluded failure
    When the factory's merge step reaches the merge
    Then it refuses with the named cause target-requires-no-checks and names the failed checks under head-rollup-not-green
    And the pull request is open and unmerged, with no auto-merge request
    And the dispatch outcome is blocked with blocked_reason needs-human, its exit code is non-zero, and it never reports green or a successful merge

  Scenario: An item carrying merge-hold:on is refused at a direct merge
    Given a protected target branch that requires a status check
    And an item whose merge-hold label was set on after its dispatch rendered merge_hold false
    And its pull request head rollup is all success
    When the factory's merge step attempts a direct merge without an auto-merge request
    Then it re-reads the item's hold labels from the ledger and refuses with the named cause merge-hold-active
    And the pull request is open and unmerged
    And the dispatch outcome is blocked with blocked_reason needs-human, it never reports green, and the item is not closed

  Scenario: A green head rollup on a protected target merges
    Given a protected target branch that requires a status check
    And an item carrying no merge hold and no other merge-time hold is active
    And its pull request head rollup is non-empty and every check run and commit status concluded success
    When the factory's merge step reaches the merge
    Then the pull request merges with the resolved merge method
    And the item proceeds to acceptance as a successful merge

  Scenario: A path-skipped job beside a green rollup merges
    Given a protected target branch that requires a status check
    And an item carrying no merge hold and no other merge-time hold is active
    And its pull request head rollup holds check runs concluded success and one path-filtered job concluded skipped
    When the factory's merge step reaches the merge
    Then the skipped job counts as passing and the merge step does not refuse with head-rollup-not-green
    And the pull request merges with the resolved merge method
    And the item proceeds to acceptance as a successful merge
```
