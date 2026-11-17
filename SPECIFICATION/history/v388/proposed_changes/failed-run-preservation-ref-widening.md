---
topic: failed-run-preservation-ref-widening
author: claude-sonnet-5-5
created_at: 2026-11-17T06:46:42Z
---

## Proposal: A failed run with committed work and no needs-human ref is published to a preservation ref

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Widen the preservation-ref publication of §"Failed engine checkpoint commit attribution" (Scenario 183) from a run that ended on a failed engine checkpoint to ANY run that ends failed with no terminal patch observed and no refs/heads/needs-human/<dispatch-id> ref on origin. The same no-hook Git Data API publication, ledger comments and rest state are reused; one new scenario exercises the measured case.

### Motivation

Work item bd-ib-nckst7.1, plan factory-run-work-preservation (epic bd-ib-nckst7). Measured 2026-11-17 on livespec-driver-claude-rjop3g run 01M7KR00K1FP: the run ended failed at commit_green and left no needs-human ref and no preservation ref, so its tree was recoverable only from two hand-saved diff patches; a reconstructed tree was then refused at the pre-push replay gate, so no sanctioned hand-push route existed. The ratified publication fires only for a failed engine checkpoint, so any other failed ending whose work nothing else carries loses that work. The maintainer's direction for the plan is that every factory run ending keeps its committed tree on a ref on origin. Coordinator ruling (throughput-plans-coordinator, 2026-11-17): this is a spec change and the design is accepted as written.

### Proposed Changes

**1. contracts.md, §"Failed engine checkpoint commit attribution", paragraph "A tree that nothing else carries is published to a preservation ref."** Add, immediately after that paragraph, a new paragraph:

**A failed run whose tree nothing else carries is published to a preservation ref whether or not it failed a checkpoint.** When a run's terminal outcome is a failure, the Dispatcher has not observed a terminal patch on the run's terminal `run.failed` event, and origin carries no ref `refs/heads/needs-human/<dispatch-id>` for the run's dispatch id (the value of the run's `livespec.dispatch.id` label, also the `livespec.factoryRunId` git configuration value in the run's sandbox), the Dispatcher MUST publish the run's changed files exactly as the preceding paragraph requires for a failed engine checkpoint, with the same ref, parent, tree, no-`git push`-and-no-hook rule, ledger comments (`livespec-preserved-tree`, success and not-preserved forms), rest state and unchanged dispatch outcome and exit code. The existence of the needs-human ref MUST be read from origin; a read that fails does not count as the ref existing, so the publication MUST be attempted. A terminal patch the Dispatcher could not observe because the run's events cannot be read does not count as observed. A run that carries a needs-human ref or an observed terminal patch MUST NOT also receive a preservation ref. Scenario 379 in `scenarios.md` exercises this paragraph.

**2. scenarios.md.** Append a new section after Scenario 378, with this heading verbatim and this body:

## Scenario 379 — A failed run whose tree nothing else carries is published to a preservation ref even when it did not fail a checkpoint

Governing clause: `contracts.md` §"Failed engine checkpoint commit attribution" → "A failed run whose tree nothing else carries is published to a preservation ref whether or not it failed a checkpoint".

```gherkin
Feature: The work of any failed run survives the run
  As the maintainer of a repository dispatched through the factory
  I want the committed work of a failed run published to a ref when nothing else carries it
  So that finished work is recoverable after the run's sandbox is gone

  Scenario: a run that failed at commit_green with committed work and no needs-human ref is published
    Given a dispatched run whose terminal outcome is a failure at node commit_green rather than a failed engine checkpoint
    And the run's sandbox holds committed work
    And its terminal run.failed event carries no terminal patch
    And origin carries no ref refs/heads/needs-human/<dispatch-id> for the run
    When the Dispatcher reports the dispatch result
    Then the forge carries a ref refs/livespec/preserved-publish/<work-item-id>/<commit-sha> whose commit's parent is the run's base commit and whose tree reflects every change the run made
    And no git push and no repository hook ran for that publication
    And a livespec-preserved-tree ledger comment names the run id, the factory, the preservation ref and its commit id

  Scenario: a failed run that carries a needs-human ref gets no preservation ref
    Given a dispatched run whose terminal outcome is a failure
    And origin carries a ref refs/heads/needs-human/<dispatch-id> for the run
    When the Dispatcher reports the dispatch result
    Then no ref under refs/livespec/preserved-publish/<work-item-id>/ is created for that run

  Scenario: a failed run whose needs-human ref cannot be read is still published
    Given a dispatched run whose terminal outcome is a failure with no terminal patch observed
    And the read of origin's needs-human refs fails
    When the Dispatcher reports the dispatch result
    Then it attempts the publication of the run's changed files to a ref under refs/livespec/preserved-publish/<work-item-id>/
```

**3. tests/heading-coverage.json.** Add an entry for the heading `## Scenario 379 — A failed run whose tree nothing else carries is published to a preservation ref even when it did not fail a checkpoint` (`test` MAY be the literal `"TODO"` with a non-empty `reason`, naming bd-ib-nckst7.1).
