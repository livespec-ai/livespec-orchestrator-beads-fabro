---
topic: v380-doctor-scenario-and-term-gaps
author: claude-opus-5-5:v380-r301-poststeps
created_at: 2026-11-15T04:22:43Z
---

## Proposal: Scenario 331 exercises a cited release-commit CI run whose cited attempt did not conclude success

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

contracts.md (v380, line 3204) makes the roll step refuse when a cited release-commit CI run's conclusion on the cited attempt is not `success`, but none of Scenario 331's five CI-citation scenarios exercises that refusal. This proposal adds one Scenario 331 scenario: the removed edge is covered only by a routing test citing the required CI workflow's master push run on v1.1.0's commit whose cited attempt concluded `failure`, even though the cited job's results record the test as passing; the run fails naming v1.1.0 and the edge, and `release` keeps v1.0.0.

### Motivation

Doctor objective finding O1 on orchestrator spec v380 (doctor-llm-objective-delta-uncovered-behavior, severity medium, SPECIFICATION/contracts.md line 3204): "contracts.md now requires the roll step to refuse when a cited release-commit CI run's conclusion on the cited attempt is not `success`, but none of the five new Scenario 331 scenarios exercises a cited run whose conclusion is not success (they cover wrong head_sha, test not executed, unreadable artifact, retry-only pass, and the success path)." Ruled by legacy-coordinator-agent under R301 on the v380 post-steps.

### Proposed Changes

scenarios.md, §"Scenario 331 — The release branch advances only on an operator dispatch that starts a canary": inside that section's gherkin block, IMMEDIATELY AFTER the scenario "the roll step refuses a routing test that passed only after an in-place retry" and before the scenario "a corrective roll-forward is held to the canary coverage record", separated by one blank line on each side, insert this scenario. The roll step MUST behave as it states:

```gherkin
  Scenario: the roll step refuses a routing test whose cited CI run attempt did not conclude success
    Given the `release` branch names the commit of release tag v1.0.0
    And release v1.1.0's commit descends from v1.0.0's commit
    And release v1.1.0 removes the edge `fix_commit_settle -> needs_human`
    And release v1.1.0's `canary-coverage.json` asset covers the removed edge only by a routing test citing the required CI workflow's `master` push run on v1.1.0's commit, whose cited attempt concluded `failure`
    And the cited job's per-test results artifact on that attempt records the cited test id as passing on its first execution
    When an operator runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.1.0`
    Then the run fails naming v1.1.0 and the edge `fix_commit_settle -> needs_human`
    And the `release` branch still names the commit of v1.0.0
```

No heading changes, so tests/heading-coverage.json MUST NOT change.

## Proposal: Scenario 285 exercises commit_red's refusal of conflicting Red test file and Test file lines

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

contracts.md (v380, line 3822) requires commit_red to refuse without committing, naming both paths, when the latest red section carries both a 'Red test file:' and a 'Test file:' line naming different paths; Scenario 285 exercises only the accepted Test-file line and the red prompt's literal. This proposal adds the refusal scenario to Scenario 285.

### Motivation

Doctor objective finding O2 on orchestrator spec v380 (doctor-llm-objective-delta-uncovered-behavior, severity medium, SPECIFICATION/contracts.md line 3822): "The new 'commit_red reads the Red test file from either field line' paragraph requires commit_red to refuse without committing, naming both paths, when the latest red section carries both a 'Red test file:' and a 'Test file:' line naming different paths; no scenario exercises this refusal (Scenario 285 only adds the Test-file-accepted and red-prompt-literal cases)." Ruled by legacy-coordinator-agent under R301 on the v380 post-steps.

### Proposed Changes

scenarios.md, §"Scenario 285 — Red and Green run as separate nodes and every implement commit is made by a command node": inside that section's gherkin block, IMMEDIATELY AFTER the scenario "commit_red accepts a Test file line as the Red test file" and before the scenario "The red prompt spells out the field line commit_red reads", separated by one blank line on each side, insert this scenario. commit_red MUST behave as it states:

```gherkin
  Scenario: commit_red refuses a red section whose Red test file and Test file lines name different paths
    Given the latest red section of the handoff file carries the line "Red test file: tests/a.py" and the line "Test file: tests/b.py"
    When commit_red runs
    Then commit_red makes no commit
    And the handoff file's newest section names both tests/a.py and tests/b.py
```

No heading changes, so tests/heading-coverage.json MUST NOT change.

## Proposal: Scenario 285 exercises the test-wrong return from a seed's open Red commit

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

The seeded-run bullet 'An open Red commit in the seed is completed, not repeated' (contracts.md v380, line 3818) requires that, when a green turn declares the test wrong, the run returns to that open Red commit's parent, keeping its changes in the working tree as carried changes, so that the next commit_red makes the run's one Red commit. No Scenario 285 scenario exercises that return path. This proposal adds it.

### Motivation

Doctor objective finding O3 on orchestrator spec v380 (doctor-llm-objective-delta-uncovered-behavior, severity medium, SPECIFICATION/contracts.md line 3818): "The seeded-run 'open Red commit in the seed is completed, not repeated' bullet requires that, when a green turn declares the test wrong, the run returns to that open Red commit's parent while keeping its changes in the working tree as carried changes, so the next commit_red makes the run's one Red commit; no Scenario 285 scenario exercises this test-wrong return path." Ruled by legacy-coordinator-agent under R301 on the v380 post-steps.

### Proposed Changes

scenarios.md, §"Scenario 285 — Red and Green run as separate nodes and every implement commit is made by a command node": inside that section's gherkin block, IMMEDIATELY AFTER the scenario "A seed that ends in an open Red commit is completed, not repeated", separated by one blank line on each side, insert this scenario. The run MUST behave as it states:

```gherkin
  Scenario: A green turn that finds a seed's open Red test wrong returns the run to that commit's parent
    Given a run seeded from a preserved tree whose Fabro checkpoint commits are followed by a commit carrying Red trailers and no Green trailers
    And the run has taken that commit as its Red commit
    When a green turn declares the test wrong
    Then the run returns to that commit's parent
    And that commit's changes are in the working tree as carried changes
    And the next commit_red makes exactly one Red commit, directly on the dispatch base
```

No heading changes, so tests/heading-coverage.json MUST NOT change.

## Proposal: The release-commit CI run names its workflow: ci.yml, whose ci-green job is master's required check

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The v380 release-commit CI run definition (contracts.md line 3177) relies on "this repository's required CI workflow", a term the spec uses nowhere else and never defines, while the repository carries several CI workflows. This proposal names it: the workflow defined by `.github/workflows/ci.yml` (workflow name `CI`), whose aggregate `ci-green` job is the only status check master's branch protection requires; a run of any other workflow, including the scheduled root-uid workflow `.github/workflows/ci-root-uid.yml`, is not a release-commit CI run.

### Motivation

Doctor objective finding O5 on orchestrator spec v380 (doctor-llm-objective-undefined-term, severity low, SPECIFICATION/contracts.md line 3177): "The new release-commit CI run definition relies on 'this repository's required CI workflow', a term used nowhere else in the spec and not defined. The repository has several push-triggered workflows (e.g. ci.yml, ci-root-uid.yml), so the roll step cannot tell from the spec which workflow's run qualifies." Ruled by legacy-coordinator-agent under R301 on the v380 post-steps. Measured 2026-11-15: `gh api repos/{owner}/{repo}/rules/branches/master` reports one required status check, context `ci-green`, from ruleset master-incident-recovery-bypass; `ci-green` is the aggregate job of .github/workflows/ci.yml (triggers pull_request and push). .github/workflows/ci-root-uid.yml triggers only on schedule and workflow_dispatch, and its own header states it is NOT the master gate ("ci.yml stays the one gating workflow").

### Proposed Changes

contracts.md, in the bullet that begins "- A *routing test* is a test of exactly that node and edge": replace the sentence "That run is the run of this repository's required CI workflow triggered by the push to `master` whose `head_sha` is the tag's commit." with:

"That run is the run of this repository's *required CI workflow* triggered by the push to `master` whose `head_sha` is the tag's commit. The required CI workflow is the workflow defined by `.github/workflows/ci.yml` (workflow name `CI`), whose aggregate `ci-green` job is the status check that `master`'s branch protection requires. A run of any other workflow, including the scheduled root-uid workflow `.github/workflows/ci-root-uid.yml`, MUST NOT be taken as the release-commit CI run."

No other sentence changes, and no heading changes, so tests/heading-coverage.json MUST NOT change.
