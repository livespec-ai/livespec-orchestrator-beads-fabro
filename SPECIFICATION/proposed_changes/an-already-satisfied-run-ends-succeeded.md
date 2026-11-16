---
topic: an-already-satisfied-run-ends-succeeded
author: claude:legacy-dispatcher-agent
created_at: 2026-11-16T19:30:00Z
---

## Proposal: an-already-satisfied-run-ends-succeeded

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A fresh already-satisfied run must end with status succeeded (a terminal success edge from the already_satisfied node), not failed with execution failed, and hand the item to acceptance.

### Motivation

Work item bd-ib-utdijk. Measured 2026-11-16: livespec-dev-tooling-bxnqo7 run 01M7JNQCRXA5 on v0.333.2 (b51b407db7f7) and run 01M7JTGT21GV on v0.334.0 (d1de60a76254): red declared the work already satisfied, already_satisfied@1 succeeded (tree equals dispatch base), and the run then ended status failed, error execution failed (48 and 49 firings); the item did rest in acceptance. Scenario 266 and the contracts paragraph require an already-satisfied OUTCOME and acceptance, but do not state the run status, so the graph has no terminal success edge for a fresh item. The earlier item bd-ib-kn7jaf (same defect on v0.287.0) was closed as moot after the split-graph revert, so no open item owned it.

### Proposed Changes

Modify the paragraph in SPECIFICATION/contracts.md that begins "**An implement turn that reports completion with no diff ends as already satisfied.**" by appending after its sentence "After that outcome the Dispatcher MUST release the run's factory claim and MUST rest the item in `acceptance`, ..." the following sentences:

"The run itself MUST end with the status `succeeded`, carrying the already-satisfied outcome, and MUST NOT end with the status `failed` or the error `execution failed`: the already-satisfied ending is a terminal SUCCESS ending of the workflow graph, reached from the `already_satisfied` node by an edge to the success exit. The launcher that dispatched the run MUST report the run as ended without an error exit. This holds for a fresh run whose `red` turn declared the work already satisfied on an unchanged tree, exactly as for a seeded run whose carried changes already meet the Definition of Done."

Add to SPECIFICATION/scenarios.md the following scenario, numbered with the next free scenario number at revise (shown here as NNN):

## Scenario NNN — A fresh already-satisfied run ends succeeded and hands the item to acceptance

```gherkin
Feature: A run whose red turn finds the work already satisfied ends as a success
  As the operator of a factory
  I want an already-satisfied run to end succeeded, not failed
  So that no one reads a satisfied item as a broken run

  Scenario: A fresh run whose tree equals the dispatch base ends succeeded
    Given a fresh run on an item whose Definition of Done already holds on the dispatch base
    And the red turn declares the work already satisfied
    And the run's tree is unchanged against the dispatch base
    When the already_satisfied node succeeds
    Then the run ends with the status succeeded and an already-satisfied outcome naming the item and the dispatch base
    And the run does not end with the error execution failed
    And the Dispatcher journals the outcome distinctly from a dead-implementer truncation and releases the run's factory claim
    And the launcher reports the run as ended without an error exit
    And the item rests in acceptance
```

