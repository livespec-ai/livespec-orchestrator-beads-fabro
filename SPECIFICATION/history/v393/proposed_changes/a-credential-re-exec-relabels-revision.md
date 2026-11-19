---
proposal: a-credential-re-exec-relabels.md
decision: accept
revised_at: 2026-11-19T16:32:21Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Accepted exactly as proposed under the repository's delegated decision mode. Measured defect (scripts/bin/_bootstrap.py, plugin build 55126d726cb3): the re-exec branch relabels any non-zero exit with empty stdout as a credential failure and drops the child's stderr. The independent reviewer found no contradiction with a ratified clause; Scenario 303 covers only launch-time preflight. The proposal's placeholder Scenario 379 is renumbered to 382, the next free number at cut time. The new H2 heading has its tests/heading-coverage.json TODO row (work_item bd-ib-32jkpv) and the regenerated debt register in the same commit.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-19T16:31:06Z
verdict: NO BLOCKERS
proposal_stem: a-credential-re-exec-relabels
content_digest: 30a09014fcc4690431da355937944f28cc208ff93df70df3c7d9b61d76e0b4ae
