---
topic: a-tier-judgement-reads-the-fetched
author: claude-sonnet-5-5
created_at: 2026-11-16T18:30:00Z
---

## Proposal: A spec-change tier judgement reads the fetched origin default-branch specification, refuses a stale clone, and never lets an older-spec record supersede a newer one

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The spec-change tier judge, the pre-dispatch tier gate and the pre-dispatch tier wall read the governed `SPECIFICATION/` from the dispatching host's working tree with no freshness check, and nothing refuses a tier record written at a spec version below one the item already carries. This proposal states three rules: the judgement reads the specification of the FETCHED origin default branch of the target repository and records that branch's spec version; a judgement that can read the spec only from a working tree behind that fetched ref is refused, naming the ref and the commits-behind count, with no record written; and a new tier record at a spec version below the item's existing record is refused as a stale read. Scenario 344 gains scenarios exercising each. Fleet scope is every judge or valve that reads spec text from a local clone, on every dispatching host.

### Motivation

Measured 2026-11-16 (date -u): overseer-zlaim4 was released by release-spec-tier at overseer spec v117 (17:04:54Z, tier none). At 17:09:30Z the dispatcher's preflight re-classified it at spec version 116 (tier spec-change) because its overseer clone was behind origin/master; the newer release record was silently superseded and the item could not be placed. The same class occurred the same day on hetzner-xubuntu (release-spec-tier refused with "not an H2 heading of the ratified specification" until the clone was fast-forwarded) and on 2026-11-15 (a stale clone read a tier against the pre-v114 spec). The written rule "fetch first" has failed repeatedly. The Definition-of-Done wall already resolves References against the target repository's origin default branch (bd-ib-ahtcng, orchestrator#4803); the tier gate and tier wall (`_spec_change_tier_gate.py`, `_spec_change_tier_wall.py`) were never changed the same way. Linked work-item: bd-ib-2sbrov (plan overseer-iyfjbo).

### Proposed Changes

In SPECIFICATION/contracts.md §"Dispatcher classify-tier invocation surface", immediately after the bullet ending "It MUST exit non-zero, writing nothing, when the judgement cannot be obtained.", insert:

> - **The judgement reads the fetched origin default branch.** `classify-tier`, the pre-dispatch tier gate and the pre-dispatch tier wall MUST judge against the `SPECIFICATION/` text of the target repository's FETCHED origin default branch, never against the dispatching host's working tree, and the tier record MUST name that branch's spec version. Any fetch this performs MUST take the shared fetch lock of the concurrent-git-fetches rule.
> - **A stale clone is refused, not read.** When the governed specification can be read only from a working tree that is behind the fetched origin default branch, the judgement MUST be refused with a message naming the ref and the number of commits the clone is behind, and MUST write no tier record.
> - **An older-spec record never supersedes a newer one.** When a work-item already carries a `livespec-spec-change-tier` record at spec version N, a new record at a spec version lower than N MUST be refused as a stale read, writing nothing, and the item's newer record stands.
> - **Fleet scope.** The same rule governs every judge or valve that reads specification text from a local clone, including the admission screen and the approve-time tier read, on every dispatching host.

In SPECIFICATION/scenarios.md, inside the gherkin block of "## Scenario 344 — An item classified bug whose asked-for behaviour the spec does not state waits for ratification, and classify-tier re-judges a changed item", immediately after the scenario "classify-tier re-judges a changed item", insert the following scenarios. They add no H2 heading, so tests/heading-coverage.json is unchanged:

```gherkin
  Scenario: A tier judgement reads the fetched origin default branch
    Given the dispatching host's clone of the target repository is behind its fetched origin default branch
    When classify-tier or the pre-dispatch wall judges an item
    Then it judges against the specification text of the fetched origin default branch
    And the tier record it writes names that branch's spec version
  Scenario: A judgement that can read only a stale working tree is refused
    Given the governed specification is readable only from a working tree behind its fetched origin default branch
    When a tier judgement is attempted
    Then it is refused with a message naming the ref and the number of commits the clone is behind
    And no tier record is written
  Scenario: A tier record at an older spec version is refused as a stale read
    Given a work-item whose latest tier record is at spec version N
    When a tier judgement would write a record at a spec version lower than N
    Then the write is refused as a stale read and nothing is appended
    And the item's newer record stands
```
