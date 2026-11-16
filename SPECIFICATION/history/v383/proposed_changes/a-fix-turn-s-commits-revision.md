---
proposal: a-fix-turn-s-commits.md
decision: accept
revised_at: 2026-11-16T04:13:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5 (sandbox-commit-gate-follow-ups f29dd5)
---

## Decision and Rationale

Accept as proposed. Defines which tests the affected-tests gate selects for a changed product module, bounds the widening, and limits an in-turn coverage refusal to changed lines, with a countable refusal line. Removes the narrow-mirror reading that stopped the fleet factory in #5085 and keeps the janitor's full aggregate as the whole-module authority. Unblocks the re-land of bd-ib-fde4ie. Decided under the coordinator's R301 delegation; the proposal text matches the realized edits byte for byte per the independent review.

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
proposal_stem: a-fix-turn-s-commits
content_digest: be2341588ba48a515a139b1f1dec995ae5c9d7b944d682c7c3fde28772071775
