---
topic: a-module-the-branch-adds-counts-as-wholly-changed
author: claude-sonnet-5-5 (sandbox-commit-gate-follow-ups f29dd5)
created_at: 2026-11-16T04:29:56Z
---

## Proposal: A module the branch adds, renames or moves counts as wholly changed has a scenario

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Revise v383 ratified, in contracts.md, that for the affected-tests gate a module the run's branch adds, renames or moves counts as wholly changed, so every executable line of it must be executed by the widened set. No Scenario 255 case exercises that clause. Add one case inside the existing Scenario 255 gherkin block, with no heading change.

### Motivation

Doctor objective finding 4 on v383 (post-step LLM delta review, posted on livespec-orchestrator-beads-fabro#5378): behavior stated as a MUST with no scenario breaks the authoring rule that load-bearing behavior needs a clause and a scenario. Explicitly deferred from the v383 fold-in on throughput-plans-coordinator's ruling of 2026-11-16. Low severity.

### Proposed Changes

Applies after revise v383 (livespec-ai/livespec-orchestrator-beads-fabro#5378) is on master, because it adds a case beside text that revise ratifies.

1. In SPECIFICATION/scenarios.md, under '## Scenario 255 — A commit inside an implement, fix or review_fix turn runs the affected-tests gate, and the janitor runs the full aggregate once', inside the existing gherkin block, immediately after the scenario 'An in-turn coverage refusal is countable', add:

```gherkin
  Scenario: A module the branch adds, renames or moves counts as wholly changed
    Given a fix turn committing a product module that the run's branch adds, or renames or moves from another path
    And the widened set of test modules leaves some of that module's executable lines unexecuted
    When its commit hook runs
    Then the affected-tests gate refuses the commit naming that module and each executable line the widened set leaves unexecuted
    And the refusal reports check-check-coverage-incremental as its failed target
    And the full check aggregate is not run
```

No H2 heading is added, changed or removed, so tests/heading-coverage.json is unchanged. No contracts.md change: the clause 'A module the branch adds, renames or moves counts as wholly changed.' is already ratified in v383.
