---
proposal: the-review-fix-open-red.md
decision: modify
revised_at: 2026-11-16T04:13:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5 (sandbox-commit-gate-follow-ups f29dd5)
---

## Decision and Rationale

Accept as proposed. States that the review_fix open-Red visit limit counts only consecutive passes on an open Red and resets on a pass with none, so earlier review rounds no longer spend a later round's allowance, and raises the engine visit limits to cover every admitted round. Unblocks bd-ib-nkyeve. Decided under the coordinator's R301 delegation.

## Modifications

Folded in after the LLM doctor phase on the coordinator's GO (R301 delegation, v381 fold-in precedent). Doctor finding 2: the proposal's closing MUST, that the engine visit limits of `review_fix`, `review_fix_commit_settle` and `review_fix_open_red_route` accommodate every admitted review round, had no scenario. Scenario 199 gains one case, "The engine visit limits of the review_fix loop admit every review round". No H2 heading changes. The ratification review recorded below covered the pre-fold bytes; a second independent read-only review covered the folded bytes.

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
