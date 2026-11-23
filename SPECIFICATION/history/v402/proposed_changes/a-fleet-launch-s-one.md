---
topic: a-fleet-launch-s-one
author: claude:fleet-launch-helper
created_at: 2026-11-23T20:38:52Z
---

## Proposal: a-fleet-launch-s-one

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A one-shot freeze-allowlist grant is consumed when the drive is ADMITTED (the work item reads active), not at the LAUNCH that invokes the drive. A drive stopped for a hold before admission keeps its unconsumed grant, and the hold re-read before admission honours an unconsumed grant, so an allowlisted item is not stopped by the hold it was exempted from.

### Motivation

Work item bd-ib-c5swt3. MEASURED 2026-11-23: bd-ib-wvem3o's launcher logged `ONE-SHOT: freeze-allowlist line for bd-ib-wvem3o consumed at LAUNCH`, then 11-15 s later `hold set before admission: stopped the drive for bd-ib-wvem3o ... gmktec hold`, six cycles; overseer-faf7w4 never started (19:26-20:25Z); only pausing hold-gmktec let them launch (record on livespec-dev-tooling-6tgd2z). Consuming at LAUNCH removes the exemption before the pre-admission hold re-read, which then stops the drive. Delegated decision basis: legacy-coordinator-agent R301 2026-11-23.

### Proposed Changes

In SPECIFICATION/contracts.md, section Provisional fleet launch scripts, bullet gmktec factory hold, sub-bullet One-shot allowlist release: replace 'remove that item's line from the allowlist at that LAUNCH' with removal when the drive is admitted (first moment the work item reads active or the run lists), not at the LAUNCH; for resume (already active) removal at the resume invocation; add that a drive stopped for a hold before admission leaves the grant unconsumed and that the hold re-read before admission honours it. The closing paragraph of the bullet also applies the releases at the Holds re-read until admission bullet. In SPECIFICATION/scenarios.md, Scenario 307: edit 'An allowlisted item launches once through the gmktec hold' so the line is removed once bd-x reads active, and add 'A drive stopped before admission keeps its allowlist grant' (a Scenario inside the existing Scenario 307 feature, no new H2 heading, so tests/heading-coverage.json needs no new row).
