---
proposal: failed-run-preservation-ref-widening.md
decision: modify
revised_at: 2026-11-17T06:50:04Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Accepted as designed (coordinator ruling R301). Modified after independent review: the no-publication rule is limited to non-checkpoint runs, and a needs-human ref counts only when it holds the run's work.

## Modifications

Closing rule of the new contracts paragraph narrowed to runs that did not end on a failed engine checkpoint; needs-human ref condition uses the CARRIES NO WORK rule and hyphen-suffixed lap refs; Scenario 379 wording aligned.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-17T06:49:33Z
verdict: NO BLOCKERS
proposal_stem: failed-run-preservation-ref-widening
content_digest: 478ec4020ace9ccb76865f337d7363521b3092d13da2b06b985b24db1c5ed715
