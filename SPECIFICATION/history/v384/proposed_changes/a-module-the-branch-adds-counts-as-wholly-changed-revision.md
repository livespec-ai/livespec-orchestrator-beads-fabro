---
proposal: a-module-the-branch-adds-counts-as-wholly-changed.md
decision: accept
revised_at: 2026-11-16T05:42:48Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5 (sandbox-commit-gate-follow-ups f29dd5)
---

## Decision and Rationale

Accept as proposed. Adds the one Scenario 255 case that exercises the ratified clause that, for the affected-tests gate, a module the run's branch adds, renames or moves counts as wholly changed. It was doctor finding 4 on revise v383, deferred from that revise's fold-in. No heading or coverage-map change. Decided under the coordinator's R301 delegation; the coordinator graded PR 5379 PASS.

## Resulting Changes

- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-16T05:42:33Z
verdict: NO BLOCKERS
proposal_stem: a-module-the-branch-adds-counts-as-wholly-changed
content_digest: b2228e4a121f5921d6ca53dfb7b2db5e310bacf507c67eef397e1ba044c7e187
