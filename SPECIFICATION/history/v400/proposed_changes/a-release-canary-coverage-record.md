---
topic: a-release-canary-coverage-record
author: claude-sonnet-5-5
created_at: 2026-11-23T12:29:07Z
---

## Proposal: A release canary coverage record flags a tag whose reverted commit has its reland outside the tag, and the roll refuses a flagged tag until a canary traversal covers it

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

In `contracts.md` §"Self-contained plugin dispatch", the **Canary coverage.** clause gains a revert-and-reland check. Before the workflow moves `release`, it finds every *revert commit* between the base and the named tag's commit, and for each finds the *reland* of the reverted change on `master`. A revert whose reland is on `master` but outside the tag is a *split pair*. The tag's `canary-coverage.json` MUST list every split pair, and the run MUST fail, naming the tag and each uncovered split pair, unless each is covered by a journal citation of a canary sample on the tag's commit that completed the workflow paths the reverted change touched. A tag that holds both halves of a pair, or neither, is not flagged. One scenario set is added to Scenario 331.

### Motivation

Work item bd-ib-ozxhs4 (plan throughput-plans-coordinator, epic livespec-dev-tooling-r7iuj6), raised by legacy-coordinator-agent 2026-11-23 after the 0.346.1 stop-the-line. Release 0.346.1 included the credential withdrawal but not the broker re-landing, which merged to `master` after the tag. On 0.346.1 every proof and review comment failed with a 403. The 7axaqn canary sample passed `publish_draft` (livespec-dev-tooling#5332) and then failed `proof_capture`, so the failure was found only after the build had become the launch build of the fleet's canary clones, and the ruling was a roll forward to 0.346.3. The existing coverage record covers the workflow paths a tag CHANGED. A revert whose reland sits outside the tag changes no path the record lists as new, so a tag can pass the record while holding half of a revert-and-reland pair. This extends the same roll-gating contract as the ratified topic the-roll-refuses-a-tag-without-canary-coverage-of-changed-workfl, beside it in the same clause, ruled by legacy-coordinator-agent under R301 on 2026-11-23. Reading of the ruled resolution: a flagged pair is cleared by a canary journal citation that traversed the affected paths on the tag's commit; a tag that contains the reland is not flagged at all, so naming the reland commit alone does not clear a pair whose reland lies outside the tag. In-flight alignment: default-align. The pending proposal factory-canary-record-one-line concerns the canary fixture's deliverable and does not touch this clause, and red-green-route-labels-under-the-static-gate concerns the pre-merge static gate; neither is folded in.

### Proposed Changes

**1. contracts.md, "Self-contained plugin dispatch", immediately after the paragraph that ends "...each path it changes is covered by a journal citation from a canary sample on its build or by a routing test." and before the sentence "Scenario 331 in `scenarios.md` exercises **The release channel.** and **Canary coverage.**", insert this paragraph:**

> **Revert and reland coverage.** A *revert commit* is a commit between the base and the named tag's commit, the tag's commit included, that reverts an earlier commit of this repository, identified by the `This reverts commit <sha>` line `git revert` writes or by a subject that names the commit it reverts. A *reland* of the reverted change is a commit reachable from `master` whose `Relands:` trailer names the reverted commit's sha or whose patch restores the reverted commit's diff. A *split pair* is a revert commit whose reland is reachable from `master` but is not an ancestor of the tag's commit. A tag that contains both halves of a pair, and a tag that contains neither, holds no split pair. Before the workflow moves `release`, at the roll step or in a corrective roll-forward, it MUST find every split pair for the named tag. The tag's `canary-coverage.json` MUST list every split pair it finds, naming the revert commit, the reverted commit and the reland commit, and MUST cover each split pair by a journal citation, in the form **Canary coverage.** defines, of a canary sample on the tag's commit that completed, with a successful outcome through its success edge, every workflow node the reverted commit changed. A split pair whose reverted commit changed no path in the workflow scope is covered by a journal citation of any canary sample on the tag's commit that completed `proof_capture` successfully. The run MUST fail, naming the tag and each uncovered split pair, and `release` MUST keep its commit, when a split pair is absent from the record, is listed without a covering citation, or is covered by a citation that names a build commit other than the tag's commit. When the tag holds no split pair, the record MUST still carry an empty list of split pairs. A corrective roll-forward is excepted from the canary's pass judgement, not from this record.

**2. scenarios.md, Scenario 331, inside its existing gherkin block, append these scenarios:**

```gherkin
  Scenario: the roll step refuses a tag that holds a revert whose reland is outside the tag
    Given the `release` branch names the commit of release tag v1.0.0
    And release v1.1.0's commit descends from v1.0.0's commit
    And a commit in v1.0.0..v1.1.0 reverts the broker commit B
    And a commit on `master` that is not an ancestor of v1.1.0's commit relands B
    And release v1.1.0's `canary-coverage.json` asset lists no split pair
    When an operator runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.1.0`
    Then the run fails naming v1.1.0 and the split pair for B
    And the `release` branch still names the commit of v1.0.0

  Scenario: a split pair covered by a canary traversal of the reverted paths lets the roll proceed
    Given the `release` branch names the commit of release tag v1.0.0
    And a commit in v1.0.0..v1.1.0 reverts the broker commit B and its reland on `master` is not an ancestor of v1.1.0's commit
    And release v1.1.0's `canary-coverage.json` asset lists the split pair and embeds a journal row of a v1.1.0 sample completing every node B changed through its success edge
    And release v1.1.0's canary samples were judged to pass
    When an operator runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.1.0`
    Then the `release` branch names the commit of v1.1.0 when the run ends

  Scenario: a tag that holds both halves of a revert-and-reland pair holds no split pair
    Given a commit in v1.0.0..v1.1.0 reverts the broker commit B
    And a later commit that is an ancestor of v1.1.0's commit relands B
    And release v1.1.0's `canary-coverage.json` asset lists an empty list of split pairs
    When an operator runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.1.0`
    Then the run does not fail on a split pair
```

**3. Heading coverage.** No H2 heading is added, removed or changed, so `tests/heading-coverage.json` is unchanged.

