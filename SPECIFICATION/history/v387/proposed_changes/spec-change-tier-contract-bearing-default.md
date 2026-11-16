---
topic: spec-change-tier-contract-bearing-default
author: claude-sonnet-5-5
created_at: 2026-11-16T21:21:33Z
---

## Proposal: Spec-change tier needs a contract-bearing item

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The existing spec-stated judgement is taken under a rubric that treats an item changing no contract between components or repositories, no safety or security guarantee and no promise to users or operators as internal, so its tier is none. A spec-change tier record without a pending hold is a record only.

### Motivation

Plan spec-scope-criteria (epic livespec-u2gsfz), lane (b). Today every implement-kind item whose behaviour is partial or unstated waits for a spec proposal, so internal fixes wait for clauses that need no new contract. The spec is for contracts. This is deliberately minimal: one rubric idea, no new field, judgement or hold rule; the code half is a rubric change plus separating the recorded tier from the hold in the classify-tier report.

### Proposed Changes

All replace-targets are verbatim, and unique, on origin/master of livespec-orchestrator-beads-fabro. Blockquote markers below are markup, not part of any target. No `## ` heading changes, so `tests/heading-coverage.json` needs no edit. No record field, reuse rule, hold rule, `dod_gate` text or `constraints.md` text changes.

**1. `SPECIFICATION/contracts.md` §"Grooming and slice-size calibration", bullet "An autonomy tier is assigned".** Replace:

> an item classified `feature` whose asked-for behaviour the judgement reports `partial` or `unstated` is spec-change tier.

with:

> an item whose asked-for behaviour the judgement reports `partial` or `unstated` is spec-change tier only when it changes or adds a contract between components or repositories, a safety or security guarantee, or a promise to users or operators. The judgement is taken under a rubric stating that an item changing none of these is internal (code and tests, a flake fix, a bug fix, a process rule), that its asked-for behaviour needs no new clause, and that its tier is therefore none whatever the verdict.

**2. Same bullet.** Replace:

> An item classified `bug`, `chore` or `non_functional` is spec-change tier when the spec-stated judgement reports its asked-for behaviour `partial` or `unstated`, exactly as an item classified `feature` is, and routes as every other factory-dispatchable item only when that judgement reports the behaviour `stated`.

with:

> An item classified `bug`, `chore` or `non_functional` is spec-change tier on exactly the terms by which an item classified `feature` is, namely that its asked-for behaviour is reported `partial` or `unstated` and it changes or adds a contract between components or repositories, a safety or security guarantee, or a promise to users or operators, whatever its classification, and otherwise routes as every other factory-dispatchable item. A `tier: spec-change` record without a pending hold, which is a record whose linked topic is ratified and whose re-run judgement returns `stated`, is a record only; reports of the tier MUST show the recorded tier and the hold separately.

**3. `SPECIFICATION/contracts.md` §"Effective acceptance criteria", "The spec-stated judgement is one shared component".** Replace:

> the item's classification taken together with the verdict on its asked-for behaviour

with:

> the verdict on its asked-for behaviour, taken under the contract-bearing rubric of "An autonomy tier is assigned"

**4. `SPECIFICATION/scenarios.md`, Scenario 344.** Replace the line `    And the spec-stated judgement reports its asked-for behaviour unstated` (first occurrence, inside Scenario 344) with that line followed by `    And the item changes or adds a contract between components or repositories`. After the line `    And the item is held out of ready`, add:

>   Scenario: An internal fix for unstated behaviour is not held
>     Given an implement-kind item classified bug whose asked-for behaviour the judgement reports unstated
>     And the item changes no contract, safety or security guarantee, or promise to users or operators
>     When the item is filed
>     Then its tier record reads tier none and the item routes as every other factory-dispatchable item

**5. `SPECIFICATION/scenarios.md`, Scenario 206.** After the verbatim line `    Given an implement-kind item typed feature whose asked-for behaviour the spec-stated judgement reports unstated`, and after the verbatim line `    And the judgement reports part of its asked-for behaviour unstated`, add, in each of those two scenarios, the line `    And the item changes or adds a contract between components or repositories`. The `## ` titles of Scenarios 206 and 344 are left unchanged.
