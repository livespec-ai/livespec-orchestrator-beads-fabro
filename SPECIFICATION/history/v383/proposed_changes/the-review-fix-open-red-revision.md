---
proposal: the-review-fix-open-red.md
decision: accept
revised_at: 2026-11-16T04:13:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5 (sandbox-commit-gate-follow-ups f29dd5)
---

## Decision and Rationale

Accept as proposed. States that the review_fix open-Red visit limit counts only consecutive passes on an open Red and resets on a pass with none, so earlier review rounds no longer spend a later round's allowance, and raises the engine visit limits to cover every admitted round. Unblocks bd-ib-nkyeve. Decided under the coordinator's R301 delegation.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-16T04:12:14Z
verdict: NO BLOCKERS
proposal_stem: the-review-fix-open-red
content_digest: d2948c142319f1cc630719850a80c2d2bfbf784c3b54a9996ec928702089a953
