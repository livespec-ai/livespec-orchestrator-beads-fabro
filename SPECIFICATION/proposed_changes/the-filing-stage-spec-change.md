---
topic: the-filing-stage-spec-change
author: claude-sonnet-5-5
created_at: 2026-11-21T17:50:08Z
---

## Proposal: The filing-stage classification records the References heading as the generalization-target when it records tier none

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The ratified check-4 exception reads a livespec-spec-change-tier record of tier none that names the item's References heading as its generalization-target, but no clause obliges the filing-stage classification to write that record. The classifier writes tier none with generalization-target (none), so the exception never applies and check 4 decides by judge variance. This proposal obliges the filing-stage classification to record the References heading as the generalization-target when it records tier none for an item whose Definition of Done cites a resolvable heading, and to record (none) only when no resolvable heading is cited.

### Motivation

Work item bd-ib-lcxiwd, filed 2026-11-21 under legacy-coordinator-agent's order R301 and ruled top priority under its section 2. Measured on the same Definition of Done: livespec-dev-tooling-opmvc6 rested at needs-human at check 4 while its replacement livespec-dev-tooling-kd7ss5 was admitted, and livespec-dev-tooling-ktk2gs was refused at dod_gate check 4 twice, on two different References headings. The tier record on kd7ss5 reads: stage filing, tier none, classification bug, verdict-kind stated, generalization-target (none), spec-version 258. On bd-ib-lcxiwd itself the classifier recorded tier spec-change with rationale that the ratified text states the exception but does not state that the filing-stage classifier must record the References heading as the generalization-target. A hand-appended tier record is not read as current, and release-spec-tier refuses a not-held item, so no valve repairs it. Option not chosen: a valve that records an internal ruling carrying a generalization-target; the classifier is the one place every filed item passes, so fixing it there covers every tenant the dod gate serves. No new H2 heading is added or removed, so tests/heading-coverage.json is unchanged. Scenarios 206 and 239 govern.

### Proposed Changes

**1. contracts.md, section 'Effective acceptance criteria', the check-4 recorded-internal-ruling paragraph.** Immediately after the sentence ending 'a newer record of another tier replaces an older `none` record.', add: 'The filing-stage classification MUST make this exception reachable: when it records tier `none` for an item whose Definition of Done carries a `References:` line naming a heading that resolves to an H2 of the governed specification tree, it MUST record that heading as the record's `generalization-target`, and it MUST record `(none)` only when the item cites no heading that resolves. The recorded heading is the one the item's `References:` line names, so the classification never substitutes a heading of its own choosing.'

**2. scenarios.md, under the existing heading 'Scenario 206 - The spec-change tier is decided by the spec-stated judgement, and a feature waits for ratification' (no new H2).** Append these two nested scenarios:

```gherkin
  Scenario: A none classification names the cited References heading as its generalization-target
    Given an item whose Definition of Done References line names a heading that resolves to an H2 of the specification tree
    And that heading governs none of the item's assertions
    When the filing-stage classification records tier none for the item
    Then the livespec-spec-change-tier record's generalization-target is that References heading
    And check 4 accepts the References line as coherent on the recorded internal ruling

  Scenario: A none classification for an item citing no resolvable heading records none as its target
    Given an item whose Definition of Done cites no References heading that resolves to an H2
    When the filing-stage classification records tier none for the item
    Then the livespec-spec-change-tier record's generalization-target reads (none)
```
