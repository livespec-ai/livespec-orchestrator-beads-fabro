---
topic: a-release-commit-ci-run-proves-a-canary-routing-test
author: claude-opus-5-5
created_at: 2026-11-15T02:06:09Z
---

## Proposal: A release commit's required CI run proves a canary routing test

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A routing test in a canary coverage record can now be shown passing on the tag's commit by the repository's own required CI run on that exact commit, as well as by a recorded `factory_captured` proof. The run counts only when it is the `master` push run of the required CI workflow whose `head_sha` is the tag's commit, it concluded `success`, and the cited job ran the cited test id and that test passed. The record then cites the run id, the job id, the `head_sha` and the test id in place of a proof. Everything else stays as it is: a removed node or edge still needs a routing test, and the refusal list grows so the roll fails when a cited CI run is on another commit, did not conclude `success`, or did not run the cited test, or when that test did not pass.

### Motivation

Maintainer-directed on 2026-11-15, about 02:3xZ: "Yes I want you to take both of those recommendations and do them." Throughput track: throughput-plans-coordinator (livespec-dev-tooling-r7iuj6).

Measured: master CI already runs the full test suite on the release commit. Example: release v0.332.1 is commit a5f972288da4740daa29ad7efca24d522769c6b7. CI run 43661487945 (workflow `CI`, event `push`, branch `master`) has that commit as its `head_sha` and concluded `success`. Its jobs include `acceptance`, `e2e-cli` and the four `check-per-file-coverage-shard` jobs, which run the suite. Today the clause accepts only a recorded `factory_captured` proof on the tag's commit, so the same evidence has to be bought a second time from the factory. That costs one proof-only factory run per roll; work item bd-ib-rxdbs4 exists only to make that run. When a routing test has to be added, it also costs a release cycle: the test lands, a new tag is cut, and a new proof is taken on the new tag's commit.

A required CI run on the exact commit is as strong as a proof for this purpose. It runs the test from the tag's tree on the tag's commit, and the code-hosting service records its result, which the roll workflow can read. The `head_sha`, conclusion and test-id conditions keep the evidence tied to the tag's commit, the same way the proof rule does.

Fleet scope: this clause is orchestrator-only. Rule CANARY-COVERS-CHANGED-PATHS lives in this repository's contract. livespec-dev-tooling's roll refusal carrier, livespec-dev-tooling-faetyh, must implement whichever form ratifies.

In-flight alignment: default-align. Open spec pull requests surveyed 2026-11-15 (#5316, #5293, #5281, #5180, #5120, #5083, #5061, #5048, #5005) each add one proposed-change file, and none of them touches §"Self-contained plugin dispatch" → "Canary coverage". The pending in-tree proposal factory-canary-record-one-line says it does not change Canary coverage.

Scenario 331 gains three Gherkin scenarios inside its existing H2. No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Self-contained plugin dispatch", paragraph **Canary coverage.**, the routing-test definition and the refusal list MUST change as follows. All other text in the paragraph stays as it is, including the rule that a removed node and a removed edge MUST each be covered by a routing test, and the corrective roll-forward sentence.

```diff
-- A *routing test* is a test of exactly that node and edge, named by its
-  path and test id, present in the tag's tree and passing in a recorded
-  `factory_captured` proof on the tag's commit.
+- A *routing test* is a test of exactly that node and edge, named by its
+  path and test id, present in the tag's tree, and passing on the tag's
+  commit. It passes on the tag's commit when a recorded
+  `factory_captured` proof on the tag's commit shows it passing, or when
+  the tag's *release-commit CI run* shows it passing. That run is the run
+  of this repository's required CI workflow triggered by the push to
+  `master` whose `head_sha` is the tag's commit. It shows the test
+  passing only when its conclusion is `success` and the job the record
+  cites executed the cited test id and that test passed. A routing test
+  covered by the release-commit CI run MUST cite, in place of a proof,
+  the run's id, the job's id, the run's `head_sha`, and the test id. The
+  workflow MUST read the cited run and job from the code-hosting service
+  to confirm these conditions, and MUST NOT take them from the record
+  alone.
```

```diff
 test is absent from the tag's tree; or a cited routing test has no
-passing recorded `factory_captured` proof on the tag's commit. When no
+passing recorded `factory_captured` proof on the tag's commit and no
+cited release-commit CI run; a cited CI run's `head_sha` is not the
+tag's commit; a cited CI run's conclusion is not `success`; or the
+cited job of a cited CI run did not execute the cited test id, or that
+test did not pass in it. When no
```

(The refusal sentence's list MUST also have its connective fixed: the existing "; or a cited routing test is absent from the tag's tree" loses its "or", which moves to the new last case.)

In `SPECIFICATION/scenarios.md`, Scenario 331's Gherkin block MUST gain these three scenarios after "the roll step advances when every changed workflow path is covered". The existing scenarios stay unchanged, including the one that covers a removed edge with a `factory_captured` proof, because that form is still valid.

```gherkin
  Scenario: the roll step advances when a removed edge's routing test passed in the release commit's CI run
    Given the `release` branch names the commit of release tag v1.0.0
    And release v1.1.0's commit descends from v1.0.0's commit
    And release v1.1.0 changes the script of workflow node `fix_commit_settle` and removes the edge `fix_commit_settle -> needs_human`
    And release v1.1.0's `canary-coverage.json` asset embeds a journal row of a v1.1.0 sample completing node `fix_commit_settle` with a successful outcome through its success edge
    And it names, for the removed edge, a routing test present in v1.1.0's tree, citing the run id, job id and `head_sha` of the required CI workflow's `master` push run on v1.1.0's commit
    And that run concluded `success`, and the cited job executed that test id and the test passed
    When an operator runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.1.0`
    Then the `release` branch names the commit of v1.1.0 when the run ends

  Scenario: the roll step refuses a routing test cited to a CI run on another commit
    Given the `release` branch names the commit of release tag v1.0.0
    And release v1.1.0's commit descends from v1.0.0's commit
    And release v1.1.0 removes the edge `fix_commit_settle -> needs_human`
    And release v1.1.0's `canary-coverage.json` asset covers the removed edge only by a routing test citing a CI run whose `head_sha` is v1.0.0's commit
    When an operator runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.1.0`
    Then the run fails naming v1.1.0 and the edge `fix_commit_settle -> needs_human`
    And the `release` branch still names the commit of v1.0.0

  Scenario: the roll step refuses a routing test whose cited CI job did not run it
    Given the `release` branch names the commit of release tag v1.0.0
    And release v1.1.0's commit descends from v1.0.0's commit
    And release v1.1.0 removes the edge `fix_commit_settle -> needs_human`
    And release v1.1.0's `canary-coverage.json` asset covers the removed edge only by a routing test citing the required CI workflow's `master` push run on v1.1.0's commit, which concluded `success`
    And the cited job's recorded test results do not include the cited test id
    When an operator runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.1.0`
    Then the run fails naming v1.1.0 and the edge `fix_commit_settle -> needs_human`
    And the `release` branch still names the commit of v1.0.0
```

No `## ` heading changes, so `tests/heading-coverage.json` MUST NOT need an entry change. Scenario 331's existing coverage entry stays owned by bd-ib-5psq3e.
