---
topic: affected-tests-selection-by-recorded-coverage
author: claude-sonnet-5-5
created_at: 2026-11-19T01:05:34Z
---

## Proposal: affected-tests-selection-by-recorded-coverage

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The affected-tests gate selects a changed product module's tests from a recorded coverage-execution map, falling back to the transitive-import selection only when the map does not cover the module, so a change to a module the dispatcher's hub modules import no longer selects nearly the whole suite.

### Motivation

Measured 2026-11-19 (bd-ib-uvx5l7, plan bd-ib-3goerg): on run 01M7R8D9H9PT (bd-ib-mot7bm, orchestrator 0.340.0) the affected-tests gate ran 15,359 and 15,362 tests, the whole suite, in 1611.85 s and 1715.76 s for two fix commits. Reproduced on master with the gate's own tests_reaching scan: a change to _dispatcher_loop_selection.py selects 1687 of 1820 test modules (93%), and a change to _dispatcher_needs_human_cause.py selects 1687 too, because a dozen hub modules that the scan treats as importers (dispatcher.py, _dispatcher_loop.py, _dispatcher_run_checks.py and others) each already reach all 1687 test modules. The clause 'An implement, fix or review_fix turn's commits run the affected-tests gate' defines the affected tests as every test module importing the module directly or transitively, so the over-selection is the ratified behaviour, and a narrower selection changes that clause. The narrower mirror-test-only set was reverted in #5142 because it refused in-turn commits for coverage that other tests supply (it did not pass a regression), so the replacement must select every test that actually executes the module. A recorded coverage-execution map names exactly those tests.

### Proposed Changes

Two edits. No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.

**Edit 1 — `SPECIFICATION/contracts.md`, the paragraph beginning **An implement, fix or review_fix turn's commits run the affected-tests gate.**.** Replace the sentence 'The affected tests of a changed product module are every test module that imports it directly, or imports a module that (transitively) imports it.' with: 'The affected tests of a changed product module are every test module that executed that module in the repository's recorded coverage-execution map, together with that module's mirror-paired test module and its `test_<name>_*.py` siblings. The coverage-execution map is a record, produced by a run of the full check aggregate on the default branch, of which test modules executed which product modules; the gate reads it and never produces it. When no recorded map covers the changed module, or the map's recorded default-branch commit is not an ancestor of the commit being made, the affected tests of that module are instead every test module that imports it directly, or imports a module that (transitively) imports it.' Keep the following sentences unchanged: selecting more test modules than strictly needed stays permitted, the gate MUST NOT measure that module's coverage over a set narrower than the one defined here, the widening by every test module whose text names the module and every test module with a non-literal dynamic import stays, and the retry of the whole suite before a coverage-only refusal stays.

**Edit 2 — `SPECIFICATION/scenarios.md`, §"Scenario 255 — A commit inside an implement, fix or review_fix turn runs the affected-tests gate, and the janitor runs the full aggregate once".** Append these scenarios to the end of that scenario's Gherkin block, inside the same fenced block:

```gherkin
  Scenario: A change to a module the dispatcher's hub modules import selects only the tests that executed it
    Given a recorded coverage-execution map whose recorded default-branch commit is an ancestor of the commit being made
    And the map names the test modules that executed the changed product module
    When the affected-tests gate selects the tests for a commit that changes only that module
    Then the selected test modules are those the map names, the module's mirror-paired test module and its siblings, widened as the clause requires
    And the selection does not include a test module that reaches the module only through another module's imports

  Scenario: A module the recorded map does not cover keeps the import-graph selection
    Given a changed product module that no recorded coverage-execution map covers
    When the affected-tests gate selects the tests for a commit that changes only that module
    Then the selected test modules are every test module that imports the module directly or transitively

  Scenario: A map recorded on a commit that is not an ancestor is not used
    Given a recorded coverage-execution map whose recorded default-branch commit is not an ancestor of the commit being made
    When the affected-tests gate selects the tests for a commit that changes a product module the map names
    Then the selected test modules are every test module that imports the module directly or transitively
```

